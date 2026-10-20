"""Audit a finished fixed-input cache probe; never call the model or evaluator."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

from audit_context_costs import archive_last
from local_llama import parse_response


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_call(expected_request, request, response, stage):
    errors = []
    if expected_request != request:
        errors.append('request differs from fixed input or allowed sampling settings')
    if response['status'] != 'ok':
        return errors + ['terminal usage is unknown']
    timing = response.get('timings') or {}
    input_count = response['input_tokens']
    cached, processed = response.get('cached_input_tokens'), timing.get('prompt_n')
    if (type(cached) is not int or type(processed) is not int or cached < 0 or processed < 0
            or cached + processed != input_count or timing.get('cache_n') != cached):
        errors.append('cached and processed counts do not partition input')
    if stage == 'warm' and cached != 0:
        errors.append('warm request reused a prior cache')
    if response['output_tokens'] > 1:
        errors.append('one-token output bound exceeded')
    return errors


def audit(storage, directory):
    state, plan = read(directory / 'status.json'), read(directory / 'plan.json')
    if state['status'] in ('waiting', 'running'):
        raise ValueError('probe has not finished')
    frozen = read(directory / 'freeze_record.json')
    errors, rows = [], []
    for name, digest in frozen['source_hashes'].items():
        if sha(directory / 'source' / name) != digest:
            errors.append('frozen source snapshot differs: ' + name)
    if sha(Path(__file__).parent / 'audit_context_costs.py') != frozen['source_hashes']['scripts/audit_context_costs.py']:
        raise ValueError('use the same frozen key-order transformation for audit')
    sources = []
    for item in plan['sources']:
        path = storage / 'records/context_pilot' / plan['source_run_id'] / item['call_id'] / 'request.json'
        if sha(path) != item['sha256']:
            raise ValueError('original fixed input changed')
        sources.append(read(path))
    expected_order = [(pair, variant, stage, source)
                      for pair, variant in enumerate(plan['order'], 1)
                      for stage, source in zip(('warm', 'target'), sources, strict=True)]
    if state['status'] == 'complete' and len(state['rows']) != len(expected_order):
        errors.append('completed probe does not contain the fixed eight calls')
    for number, saved in enumerate(state['rows']):
        pair, variant, stage, source = expected_order[number]
        cid = f'call_{number + 1:03d}'
        request_path, response_path = directory / cid / 'request.json', directory / cid / 'response.json'
        request, response = read(request_path), read(response_path)
        expected = archive_last(source) if variant == 'archive_last' else source
        expected = dict(expected, max_tokens=1, cache_prompt=stage == 'target')
        found = check_call(expected, request, response, stage)
        if (saved['id'], saved['pair'], saved['variant'], saved['stage']) != (cid, pair, variant, stage):
            found.append('call labels or order disagree')
        for key in ('status', 'input_tokens', 'output_tokens', 'cached_input_tokens', 'wall_seconds'):
            if saved[key] != response.get(key):
                found.append('progress disagrees with recorded response: ' + key)
        if response['status'] == 'ok':
            timing = response['timings']
            values = {'processed_input_tokens': timing['prompt_n'],
                      'prompt_seconds': timing['prompt_ms'] / 1000,
                      'decode_seconds': timing['predicted_ms'] / 1000,
                      'predicted_input_tokens': response['input_tokens']}
            for key, value in values.items():
                if saved[key] != value:
                    found.append('progress timing or pre-count disagrees: ' + key)
        if saved['request_sha256'] != sha(request_path) or saved['response_sha256'] != sha(response_path):
            found.append('progress hashes disagree with recorded files')
        if response['status'] == 'ok':
            terminal = parse_response(read(directory / cid / 'raw_response.json'))
            for key in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'timings'):
                if terminal[key] != response[key]:
                    found.append('raw terminal response disagrees: ' + key)
        errors.extend(cid + ': ' + error for error in found)
        # No message, token string, arguments, or arbitrary progress field leaves the record.
        rows.append({key: saved[key] for key in (
            'id', 'pair', 'variant', 'stage', 'status', 'input_tokens', 'output_tokens',
            'cached_input_tokens', 'processed_input_tokens', 'prompt_seconds', 'decode_seconds',
            'wall_seconds', 'request_sha256', 'response_sha256')})
    known = sum(r['input_tokens'] + r['output_tokens'] for r in rows if r['status'] == 'ok')
    unknown = sum(r['status'] != 'ok' for r in rows)
    if known != state['known_total_tokens'] or unknown != state['unknown_usage_calls']:
        errors.append('total accounting disagrees')
    aggregates = {}
    if not errors and state['status'] == 'complete':
        for variant in ('original', 'archive_last'):
            group = [r for r in rows if r['variant'] == variant and r['stage'] == 'target']
            aggregates[variant] = {'target_calls': len(group),
                                   'input_tokens_each': [r['input_tokens'] for r in group],
                                   'cached_tokens_each': [r['cached_input_tokens'] for r in group],
                                   'processed_tokens_each': [r['processed_input_tokens'] for r in group],
                                   'prompt_seconds_each': [r['prompt_seconds'] for r in group],
                                   'mean_prompt_seconds': statistics.mean(r['prompt_seconds'] for r in group)}
    return {'status': state['status'], 'run_id': directory.name, 'calls': rows,
            'known_total_tokens': known, 'unknown_usage_calls': unknown, 'audit_errors': errors,
            'target_measurements': aggregates, 'model_inference_calls_by_auditor': 0,
            'environment_operations': 0, 'final_evaluations': 0,
            'source_hashes': {name: sha(directory / name) if (directory / name).exists() else None
                              for name in ('plan.json', 'status.json', 'freeze_record.json', 'provenance.json')},
            'scope': 'Same two saved inputs, two target repetitions per layout. One-token generation, '
                     'no task completion or quality claim. Logical input totals are not reduced.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.storage_root, args.record)
    result['auditor_sha256'] = sha(Path(__file__))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'audit_errors': result['audit_errors'], 'known_total_tokens': result['known_total_tokens']}))
