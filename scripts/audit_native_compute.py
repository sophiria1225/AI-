"""Reconstruct ordinary-calculation inputs and costs without executing code."""
import hashlib
import json

from native_compute_session import digest
from native_data_compute import selected_receipts, validate_arguments
from container_data_python import prepare_payload


def read(path):
    return json.loads(path.read_text())


def inspect_compute(directory, usage, events, spans):
    path = directory/'compute_records.json'
    records = read(path) if path.exists() else []
    errors, previous, matched, executions = [], {}, [], 0
    by_call = {}
    for event in events:
        by_call.setdefault(event['call'], []).append(spans[event['span_id']])
    config = read(directory/'plan.json')['ordinary_compute']
    for call in usage:
        current = by_call.get(call['id'], [])
        for span in current:
            action, obs = span.get('action') or {}, span['observation']
            if action.get('name') != 'compute_data' or 'computation_status' not in obs:
                continue
            index = len(matched)
            if index >= len(records):
                errors.append('missing computation attempt record')
                continue
            entry = records[index]
            matched.append(entry)
            if (entry['attempt'] != index + 1 or entry['call_id'] != call['id']
                    or entry['receipt_sha256'] != digest(obs)
                    or entry['status'] != obs['computation_status']):
                errors.append('calculation result and attempt record disagree')
            if type(entry['wall_seconds']) not in (int, float) or entry['wall_seconds'] < 0:
                errors.append('invalid computation wall time')
            try:
                args = validate_arguments(json.loads(action['arguments']))
                public = selected_receipts(args['span_ids'], previous)
                prepare_payload(args['code'], public, config['timeout_seconds'])
            except (KeyError, ValueError, TypeError):
                if entry['status'] != 'input_error' or entry['execution_started']:
                    errors.append('invalid or future receipt was used by computation')
                continue
            if (entry.get('input_sha256') != digest(public)
                    or entry.get('source_span_ids') != args['span_ids']
                    or entry.get('code_sha256') != hashlib.sha256(args['code'].encode()).hexdigest()):
                errors.append('computation input is not the pre-response public snapshot')
            if not entry['execution_started']:
                if entry['status'] != 'not_executed' or executions < config['max_executions']:
                    errors.append('unexplained skipped calculation')
                continue
            executions += 1
            execution = entry.get('execution')
            result_path = directory/'compute'/f"attempt_{entry['attempt']:03d}"/'result_private.json'
            if execution is None or not result_path.exists():
                errors.append('missing calculation execution metadata')
                continue
            actual = read(result_path)
            if execution != {k: v for k, v in actual.items() if k != 'content'}:
                errors.append('container record differs from computation metadata')
            if actual['status'] != obs['computation_status']:
                errors.append('container status differs from returned observation')
            if actual['status'] == 'ok' and (actual.get('content') != obs.get('content')
                    or not actual.get('container_removed') or not all(actual.get('controls', {}).values())
                    or not actual.get('controls')):
                errors.append('successful computation lacks matching output or controls')
        previous.update({s['id']: s for s in current})
    if len(matched) != len(records):
        errors.append('unmatched calculation attempts')
    summary = read(directory/'summary.json')['ordinary_compute']
    counts = {s: sum(r['status'] == s for r in records) for s in sorted({r['status'] for r in records})}
    if (summary['attempts'] != len(records) or summary['executions'] != executions
            or executions > config['max_executions'] or summary['status_counts'] != counts
            or abs(summary['wall_seconds'] - sum(r['wall_seconds'] for r in records)) > 1e-8):
        errors.append('computation cost summary disagrees with attempts')
    return {'compute_audit_errors': errors, 'ordinary_compute': summary}
