"""Inspect saved assistant/tool history using only template/tokenizer endpoints.

This is a representation preflight, not a model or environment experiment. Only
the declared prefix is reconstructed; evaluator files are never read. Payloads
and rendered prompts stay in ignored records, with only counts/hashes exported.
"""
import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import urllib.request

from context_preservation import compact
from local_llama import post
from model_provenance import check_live_model
from native_conversation import NativeConversation, recover_turn


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def inspect(storage, trial, private, output):
    private.mkdir(parents=True, exist_ok=False)
    plan = read(trial / 'plan.json')
    runtime = read(storage / '.runtime/model_server.json')
    with urllib.request.urlopen(plan['model']['base_url'] + '/props', timeout=10) as response:
        props = json.load(response)
    check_live_model(plan['model_selection'], runtime, props, root=storage,
                     expected_ctx=plan['model']['num_ctx'], expected_cache=('q8_0', 'q8_0'))
    write(private / 'runtime.json', runtime)
    write(private / 'props.json', props)
    task = read(trial / 'public_task.json')
    spans = read(trial / 'spans.json')
    events = read(trial / 'events.json')
    first = read(trial / 'call_001/request.json')
    conversation = NativeConversation(first['messages'][0]['content'], task)
    history, payloads, proof = {}, [], []
    sources = {str(path.relative_to(trial)): digest(path) for path in
               (trial / 'plan.json', trial / 'public_task.json', trial / 'events.json',
                trial / 'spans.json', trial / 'call_001/request.json')}
    for number in (1, 2):
        cid = f'call_{number:03d}'
        path = trial / cid / 'response.json'
        response = read(path)
        if response['status'] != 'ok':
            raise ValueError('saved prefix must contain completed model responses')
        batch = [spans[e['span_id']] for e in events if e['call'] == cid]
        if any(len(compact(span)) > plan['observation_page_characters'] for span in batch):
            raise ValueError('oversized span needs an explicit matched pagination policy')
        old = conversation.messages()
        conversation.append(response['message'], batch)
        recovered = recover_turn(conversation.messages()[len(old):])
        if recovered != batch or conversation.messages()[:len(old)] != old:
            raise ValueError('round trip or append-only identity failed')
        history.update({s['id']: s for s in batch})
        following = trial / f'call_{number + 1:03d}/request.json'
        original = read(following)
        memory = json.loads(original['messages'][1]['content'])
        if (memory['task'] != task or memory['memory']['visible_spans'] != list(history.values())
                or memory['memory']['available_archive_ids'] != list(history)):
            raise ValueError('saved JSON input does not match the declared public prefix')
        transformed = copy.deepcopy(original)
        transformed['messages'], formatting = conversation.for_model(plan['observation_page_characters'])
        payloads.extend([(f'prefix_{number}_json', original),
                         (f'prefix_{number}_roles', transformed)])
        sources[str(path.relative_to(trial))] = digest(path)
        sources[str(following.relative_to(trial))] = digest(following)
        proof.append({'prefix_model_calls': number, 'visible_operations': len(history),
                      'round_trip_equal': True, 'earlier_messages_unchanged': True,
                      'additional_observation_text': False,
                      'formatting': formatting,
                      'supplied_tool_schemas': len(original['tools'])})
    # Check whether this model's template accepts malformed argument strings;
    # never repair or execute them. The conversation preserves the actual error.
    synthetic = NativeConversation('Test interface formatting only.', {'task': 'synthetic'})
    call = {'id': 'synthetic_call', 'type': 'function',
            'function': {'name': 'synthetic_read', 'arguments': '{'}}
    synthetic.append({'role': 'assistant', 'content': '', 'tool_calls': [call]},
                     [{'id': 'synthetic_span', 'assistant': '', 'action': call['function'],
                       'observation': {'format_error': 'unparseable arguments; not dispatched'}}])
    synthetic_payload = copy.deepcopy(first)
    synthetic_payload['messages'], synthetic_formatting = synthetic.for_model()
    synthetic_payload['tools'] = [{'type': 'function', 'function': {
        'name': 'synthetic_read', 'description': 'Synthetic format test; never execute.',
        'parameters': {'type': 'object', 'properties': {}}}}]
    payloads.append(('synthetic_malformed_arguments', synthetic_payload))
    result = {'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'source_run': trial.name, 'prefix_calls': 2, 'proof': proof,
              'model_revision': runtime['model_revision'], 'runtime': runtime['runtime'],
              'context_limit': runtime['ctx_size'], 'source_hashes': sources,
              'synthetic_formatting': synthetic_formatting,
              'model_inference_calls': 0, 'environment_requests': 0, 'rows': [],
              'scope': 'Saved public prefix and one synthetic malformed call. No generation, '
                       'state replay, evaluator access, final quality or speed claim.'}
    for name, payload in payloads:
        directory = private / name
        directory.mkdir()
        write(directory / 'payload.json', payload)
        row = {'case': name, 'payload_sha256': digest(directory / 'payload.json')}
        try:
            template = post(plan['model'], '/apply-template', payload, 60)
            write(directory / 'template.json', template)
            tokens = post(plan['model'], '/tokenize', {'content': template['prompt']}, 60)
            write(directory / 'tokens.json', tokens)
            counted = post(plan['model'], '/v1/chat/completions/input_tokens', payload, 60)
            write(directory / 'count.json', counted)
            row.update(status='accepted', input_tokens=counted['input_tokens'],
                       template_tokens=len(tokens['tokens']),
                       template_sha256=digest(directory / 'template.json'),
                       fits_with_output_reservation=(counted['input_tokens'] +
                           plan['max_output_tokens'] <= runtime['ctx_size']))
            if row['input_tokens'] != row['template_tokens']:
                row['token_count_mismatch'] = True
        except Exception as error:
            write(directory / 'error_private.json', {'type': type(error).__name__,
                                                     'message': str(error)})
            row.update(status='template_or_count_rejected', error_type=type(error).__name__)
        result['rows'].append(row)
        write(output, result)
    result['script_hashes'] = {name: digest(Path(__file__).parent / name)
                               for name in ('inspect_native_history.py', 'native_conversation.py')}
    write(output, result)
    print(json.dumps({'cases': len(result['rows']), 'model_inference_calls': 0,
                      'statuses': [r['status'] for r in result['rows']]}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--private-record', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    inspect(args.storage_root, args.trial, args.private_record, args.output)
