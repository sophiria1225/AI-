"""Audit completed P6/P8 costs from saved public-operation metadata.

No API replay, model inference, answer access, or trajectory text export. The
optional tokenizer analysis measures adjacent input prefixes, not a speedup.
"""
import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import urllib.request

from local_llama import post
from model_provenance import check_live_model


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prefix_length(left, right):
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return index
    return min(len(left), len(right))


def archive_last(payload):
    """Only reorder one JSON object's keys, retaining every value and message."""
    result = copy.deepcopy(payload)
    body = json.loads(result['messages'][-1]['content'])
    memory = body['memory']
    if list(memory)[:2] != ['available_archive_ids', 'visible_spans']:
        raise ValueError('unexpected memory layout; refusing an adaptive rewrite')
    body['memory'] = {key: value for key, value in memory.items()
                      if key != 'available_archive_ids'}
    body['memory']['available_archive_ids'] = memory['available_archive_ids']
    result['messages'][-1]['content'] = json.dumps(
        body, ensure_ascii=False, separators=(',', ':'))
    if json.loads(result['messages'][-1]['content']) != json.loads(
            payload['messages'][-1]['content']):
        raise ValueError('rewriting the layout changed information')
    return result


def tokenize_payload(payload, config):
    template = post(config, '/apply-template', payload, 60)
    tokens = post(config, '/tokenize', {
        'content': template['prompt'], 'add_special': False, 'parse_special': True}, 60)
    if not isinstance(tokens.get('tokens'), list) or any(
            type(token) is not int for token in tokens['tokens']):
        raise ValueError('unexpected tokenizer output')
    return tokens['tokens']


def memory_sizes(directory, tokenize_text):
    usage = read(directory / 'usage.json')
    config = read(directory / 'plan.json')
    updates = []
    for index, call in enumerate(usage):
        if call['role'] == 'agent':
            continue
        if index and usage[index - 1]['role'] != 'agent':
            continue
        last = index
        while last + 1 < len(usage) and usage[last + 1]['role'] != 'agent':
            last += 1
        following = usage[last + 1] if last + 1 < len(usage) else None
        row = {'first_call': call['id'], 'last_call': usage[last]['id'],
               'next_call': following['id'] if following else None,
               'after_memory_tokens': None, 'after_above_trigger': None,
               'source_hashes': {}}
        for label, which in (('before', call), ('after', following)):
            if which is None:
                continue
            path = directory / which['id'] / 'request.json'
            memory = json.loads(read(path)['messages'][-1]['content'])['memory']
            tokens = tokenize_text(json.dumps(memory, ensure_ascii=False, separators=(',', ':')))
            row[label + '_memory_tokens'] = len(tokens)
            row[label + '_span_count'] = len(memory['visible_spans'])
            row[label + '_ledger_items'] = len(memory.get('working_ledger', {}).get('items', []))
            row['source_hashes'][label] = digest(path)
        if following is not None:
            row['after_above_trigger'] = row['after_memory_tokens'] > config['compression_trigger_tokens']
        updates.append(row)
    return {'run_id': directory.name, 'trigger_tokens': config['compression_trigger_tokens'],
            'updates': updates, 'source_hashes': {
                name: digest(directory / name) for name in ('usage.json', 'plan.json')},
            'scope': 'Before and next-executor memory inputs; no new action between them. '
                     'Absent next request is unmeasured, not zero. Sizes are not semantic correctness.'}


def audit(directory, tokenizer=None):
    summary = read(directory / 'summary.json')  # completed runs only
    usage = read(directory / 'usage.json')
    spans = read(directory / 'spans.json')
    sources = {name: digest(directory / name) for name in (
        'summary.json', 'usage.json', 'spans.json', 'events.json', 'plan.json')}
    errors, roles, calls = [], {}, []
    previous = {'original': None, 'archive_last': None}
    for call in usage:
        role = roles.setdefault(call['role'], {
            'calls': 0, 'known_usage_calls': 0, 'unknown_usage_calls': 0,
            'input_tokens': 0, 'output_tokens': 0, 'cached_input_tokens': 0,
            'processed_input_tokens': 0, 'timing_calls': 0,
            'prompt_seconds': 0.0, 'decode_seconds': 0.0, 'call_wall_seconds': 0.0})
        role['calls'] += 1
        role['call_wall_seconds'] += call['wall_seconds']
        out = directory / call['id']
        response = read(out / 'response.json')
        row = {key: call.get(key) for key in (
            'id', 'role', 'status', 'input_tokens', 'output_tokens',
            'predicted_input_tokens', 'wall_seconds', 'finish_reason')}
        row['source_hashes'] = {name: digest(out / name)
                                for name in ('request.json', 'response.json')}
        if call['status'] == 'ok':
            role['known_usage_calls'] += 1
            role['input_tokens'] += call['input_tokens']
            role['output_tokens'] += call['output_tokens']
            timing = response.get('timings')
            if timing is not None:
                cache, processed = timing['cache_n'], timing['prompt_n']
                if cache + processed != call['input_tokens']:
                    errors.append(call['id'] + ': cache + processed differs from input')
                if cache != call.get('cached_input_tokens'):
                    errors.append(call['id'] + ': cache metadata disagrees')
                role['timing_calls'] += 1
                role['cached_input_tokens'] += cache
                role['processed_input_tokens'] += processed
                role['prompt_seconds'] += timing['prompt_ms'] / 1000
                role['decode_seconds'] += timing['predicted_ms'] / 1000
                row.update(cached_input_tokens=cache, processed_input_tokens=processed,
                           prompt_seconds=timing['prompt_ms'] / 1000,
                           decode_seconds=timing['predicted_ms'] / 1000)
        else:
            role['unknown_usage_calls'] += 1
        if tokenizer is not None:
            original = read(out / 'request.json')
            transformed = archive_last(original)
            for variant, payload in (('original', original), ('archive_last', transformed)):
                tokens = tokenizer(payload)
                if variant == 'original' and len(tokens) != call['predicted_input_tokens']:
                    raise ValueError(call['id'] + ': live tokens differ from frozen count')
                row[variant + '_input_tokens'] = len(tokens)
                row[variant + '_previous_input_prefix_tokens'] = (
                    prefix_length(previous[variant], tokens)
                    if previous[variant] is not None else None)
                previous[variant] = tokens
            row['parsed_information_equal'] = True
        calls.append(row)

    operations = dict(format_errors=0, bridge_errors=0, api_execution_errors=0,
                      archive_reads=0, documentation_requests=0,
                      multiple_call_format_rejections=0)
    for span in spans.values():
        obs = span['observation']
        operations['format_errors'] += int('format_error' in obs)
        operations['bridge_errors'] += int('api_error' in obs)
        # These are AppWorld execution errors inside successful bridge transport;
        # they must not be conflated with outer bridge validation errors.
        operations['api_execution_errors'] += int(
            isinstance(obs.get('observation'), str)
            and obs['observation'].startswith('Execution failed.'))
        action = span.get('action') or {}
        operations['archive_reads'] += int(action.get('name') == 'read_span')
        try:
            args = json.loads(action.get('arguments', '{}'))
            app = (args.get('app') if action.get('name') == 'appworld_api'
                   else action.get('name', '').split('__')[0])
            operations['documentation_requests'] += int(app == 'api_docs')
        except (ValueError, AttributeError):
            pass
    for event in read(directory / 'events.json'):
        obs = spans[event['span_id']]['observation']
        if obs.get('format_error') != 'choose exactly one tool call':
            continue
        response = read(directory / event['call'] / 'response.json')
        operations['multiple_call_format_rejections'] += int(
            len(response.get('message', {}).get('tool_calls') or []) > 1)
    known = sum(r['input_tokens'] + r['output_tokens'] for r in roles.values())
    if known != summary['known_total_tokens']:
        errors.append('role total differs from summary')
    if len(usage) != summary['model_calls']:
        errors.append('call count differs from summary')
    return {'run_id': summary['run_id'], 'arm': summary['arm'],
            'stop_reason': summary['stop_reason'], 'known_total_tokens': known,
            'wall_seconds': summary['wall_seconds'], 'roles': roles, 'operations': operations,
            'calls': calls, 'audit_errors': errors, 'source_hashes': sources}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--runs', nargs='+', required=True)
    parser.add_argument('--model-plan', type=Path)
    parser.add_argument('--memory-sizes-only', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    tokenizer, identity = None, None
    if args.model_plan:
        plan = read(args.model_plan)
        runtime = read(args.storage_root / '.runtime/model_server.json')
        with urllib.request.urlopen(plan['model']['base_url'] + '/props', timeout=10) as response:
            props = json.load(response)
        check_live_model(plan['model_selection'], runtime, props, root=args.storage_root,
                         expected_ctx=plan['model']['num_ctx'], expected_cache=('q8_0', 'q8_0'))
        tokenizer = lambda payload: tokenize_payload(payload, plan['model'])
        identity = {key: runtime[key] for key in ('model_revision', 'model_alias', 'quantization')}
        identity['runtime_commit'] = runtime['runtime']['commit']
    if args.memory_sizes_only:
        if not args.model_plan:
            raise ValueError('memory sizes require the pinned live tokenizer')
        def tokenize_text(text):
            return post(plan['model'], '/tokenize', {'content': text}, 60)['tokens']
        rows = [memory_sizes(args.storage_root / 'records/context_pilot' / run, tokenize_text)
                for run in args.runs]
        requests = sum(1 + int(update['next_call'] is not None)
                       for row in rows for update in row['updates'])
    else:
        rows = [audit(args.storage_root / 'records/context_pilot' / run, tokenizer)
                for run in args.runs]
        requests = sum(len(row['calls']) for row in rows) * 4 if tokenizer else 0
    result = {
        'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'trials': rows, 'model_identity': identity,
        'script_sha256': digest(Path(__file__)),
        'model_inference_calls': 0, 'api_execution_calls': 0, 'evaluators_loaded': False,
        'template_and_tokenize_requests': requests,
        'scope': ('Memory sizes immediately before and after a completed compression. '
                  'No new environment action intervenes. Missing next input is unmeasured, '
                  'not zero. Unknown usage remains unknown.' if args.memory_sizes_only else
                 'Recorded timing, cost and structural errors. Key-order alternative has equal '
                 'parsed values; input prefix lengths are not measured cache hits, speedup or '
                 'evidence of unchanged model behavior. Unknown terminal usage remains unknown.'),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'runs': len(rows), 'audit_errors': sum(len(r.get('audit_errors', [])) for r in rows),
                      'template_and_tokenize_requests': result['template_and_tokenize_requests']}))


if __name__ == '__main__':
    main()
