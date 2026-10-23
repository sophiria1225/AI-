"""Describe every closed P78 model call using public events and usage metadata.

No model response text, private reasoning, evaluator details or database content
is read. Zero-API calls and repeated requests are not classified as unnecessary.
"""
import argparse
from collections import Counter
import csv
from pathlib import Path

from public_path_scope import exception_type
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def profile(storage, root):
    report_path = root / 'reports/P78_comparison.json'
    target = root / 'reports/P78_call_profile.json'
    if target.exists():
        raise FileExistsError('preserve_P78_profile_attempt')
    report = read(report_path)
    session = read(root / 'reports/P78_server_session.json')
    if (report['audit_errors'] or report['batch_status'] not in ('complete', 'stopped')
            or len(report['rows']) != 8 or session['status'] != 'stopped'
            or session['audit_source_sha256'] != sha(report_path)):
        raise ValueError('closed_audited_P78_records_required')
    calls, programs, fingerprints = [], [], {}
    for row in report['rows']:
        if row['record_status'] not in ('evaluated', 'unevaluated'):
            continue
        folder = storage / 'records/context_pilot' / row['run_id']
        if sha(folder / 'usage.json') != row['usage_sha256']:
            raise ValueError('audited_usage_changed')
        usage, events, spans = [read(folder / (name + '.json')) for name in ('usage', 'events', 'spans')]
        fingerprints[row['run_id']] = {name: sha(folder / name) for name in
                                     ('usage.json', 'events.json', 'spans.json')}
        local = []
        for usage_row in usage:
            selected = [e for e in events if e['call'] == usage_row['id']]
            sent = [e for e in selected if e['api_request_sent']]
            outer = [e for e in selected if e['stage'] == 'model_tool']
            known = usage_row['status'] == 'ok'
            if not known and selected:
                raise ValueError('unknown_usage_response_executed')
            entry = {'run_id': row['run_id'], 'task_id': row['task_id'], 'arm': row['arm'],
                'call_id': usage_row['id'], 'usage_status': usage_row['status'],
                **{key: usage_row.get(key) for key in
                   ('input_tokens', 'output_tokens', 'cached_input_tokens', 'wall_seconds')},
                'known_total_tokens': usage_row['input_tokens'] + usage_row['output_tokens'] if known else None,
                'api_requests': len(sent),
                'api_invocation_exceptions': sum(e.get('api_execution', {}).get('status') == 'raised' for e in sent),
                'python_execution_errors': sum(spans[e['span_id']]['observation'].get('status') == 'execution_error' for e in outer),
                'category': 'unknown_usage_unexecuted' if not known else
                            'known_with_sent_api' if sent else 'known_without_sent_api'}
            local.append(entry); calls.append(entry)
            for event in outer:
                span = spans[event['span_id']]
                if (span.get('action') or {}).get('name') != 'run_python':
                    continue
                observation = span['observation']
                programs.append({'run_id': row['run_id'], 'call_id': usage_row['id'],
                    'span_id': event['span_id'], 'status': observation.get('status', 'not_executed_or_rejected'),
                    'api_requests': observation.get('api_requests'),
                    'exception_type': exception_type(observation.get('error')),
                    'stdout_truncated': observation.get('stdout_truncated')})
        if (len(local) != row['model_calls']
                or sum(c['known_total_tokens'] or 0 for c in local) != row['known_total_tokens']
                or sum(c['usage_status'] != 'ok' for c in local) != row['unknown_usage_calls']
                or sum(c['api_requests'] for c in local) != row['api_requests']
                or sum(c['api_invocation_exceptions'] for c in local) != row['invocation_exceptions']):
            raise ValueError('all_call_totals_disagree_with_audit')
    result = {'phase': 'P78', 'all_planned_rows_accounted': len(report['rows']),
        'calls': calls, 'programs': programs, 'category_counts': dict(Counter(c['category'] for c in calls)),
        'comparison_sha256': sha(report_path), 'private_record_sha256': fingerprints,
        'script_sha256': sha(Path(__file__)), 'additional_generations': 0, 'additional_api_calls': 0,
        'additional_evaluations': 0, 'private_reasoning_read': False,
        'measured_avoidable_work': None, 'interpretation':
            'Descriptive whole-cohort accounting only. Calls without sent APIs can perform necessary computation or planning; errors and repeated requests do not prove removable work.'}
    write_json(target, result)
    out = root / 'materials/20261023_p78'
    for name, rows in (('all_model_calls.csv', calls), ('all_python_program_results.csv', programs)):
        with (out / name).open('w', newline='') as stream:
            if rows:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows)
    print({'calls': len(calls), 'programs': len(programs), 'categories': result['category_counts']})
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT)
    a = p.parse_args()
    profile(a.storage_root, a.repo_root)
