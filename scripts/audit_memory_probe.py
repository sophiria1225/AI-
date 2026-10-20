"""Match P7's transmitted requests and usage to the frozen nine-call design."""
import argparse
import hashlib
import json
from pathlib import Path

from probe_memory_input import outcome, transform


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(storage):
    directory = storage / 'records/memory_probe/P7_01'
    status = read(directory / 'status.json')
    if status['status'] in ('waiting', 'running'):
        raise ValueError('final audit requires terminal status')
    plan = read(directory / 'plan.json')
    original_path = storage / 'records/context_pilot' / plan['source_run_id'] / plan['source_call_id'] / 'request.json'
    if digest(original_path) != plan['source_request_sha256']:
        raise ValueError('original request changed')
    original = read(original_path)
    usage, results = read(directory / 'usage.json'), read(directory / 'results.json')
    results_by_id = {r['call_id']: r for r in results}
    seen, calls, errors = {}, [], []
    for index, u in enumerate(usage):
        variant = plan['order'][index]
        seed = plan['first_seed'] + seen.get(variant, 0)
        seen[variant] = seen.get(variant, 0) + 1
        expected = dict(original)
        expected['messages'], invalid_ids = transform(original['messages'], variant)
        expected['seed'] = seed
        request_path = directory / u['id'] / 'request.json'
        response_path = directory / u['id'] / 'response.json'
        request, response = read(request_path), read(response_path)
        if request != expected:
            errors.append(u['id'] + ': transmitted payload differs from frozen treatment')
        if u['role'] != variant:
            errors.append(u['id'] + ': role schedule differs')
        row = results_by_id.pop(u['id'], None)
        if u['status'] == 'ok':
            if row is None or row['variant'] != variant or row['seed'] != seed:
                errors.append(u['id'] + ': saved result labels differ')
            elif row['known_tokens'] != u['input_tokens'] + u['output_tokens']:
                errors.append(u['id'] + ': saved result cost differs')
            actual = outcome(response['message'], request['messages'], invalid_ids)
            if row and any(row[k] != v for k, v in actual.items()):
                errors.append(u['id'] + ': saved structural result differs')
        for field in ('status', 'input_tokens', 'output_tokens'):
            if u[field] != response[field]:
                errors.append(u['id'] + ': usage/response ' + field + ' differs')
        calls.append({
            'call_id': u['id'], 'variant': variant, 'seed': seed, 'status': u['status'],
            'input_tokens': u['input_tokens'], 'output_tokens': u['output_tokens'],
            'wall_seconds': u['wall_seconds'], 'finish_reason': u.get('finish_reason'),
            'schema_valid': row['schema_valid'] if row else None,
            'request_sha256': digest(request_path), 'response_sha256': digest(response_path)})
    if results_by_id:
        errors.append('unbound result rows')
    known = sum(u['input_tokens'] + u['output_tokens'] for u in usage if u['status'] == 'ok')
    unknown = sum(u['status'] != 'ok' for u in usage)
    if known != status['known_total_tokens'] or unknown != status['unknown_usage_calls']:
        errors.append('terminal usage disagrees')
    if status['status'] == 'complete' and len(usage) != 9:
        errors.append('incomplete schedule called complete')
    return {
        'run_id': 'P7_01', 'status': status['status'], 'calls': calls,
        'known_total_tokens': known, 'unknown_usage_calls': unknown, 'audit_errors': errors,
        'source_request_sha256': digest(original_path),
        'source_hashes': {name: digest(directory / name) for name in (
            'plan.json', 'usage.json', 'results.json', 'summary.json', 'freeze_record.json')},
        'script_sha256': digest(Path(__file__)),
        'environment_executions': 0, 'scope': 'Request, seed, treatment and usage conformance only; '
        'no semantic truth labels, evaluator access or additional inference.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.storage_root)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'calls': len(result['calls']), 'audit_errors': result['audit_errors']}))


if __name__ == '__main__':
    main()
