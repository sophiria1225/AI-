"""Account for every planned P40 cell after its prespecified stop gate fired.

This is separate from the all-eight effectiveness analysis. Missing evaluation,
unknown usage, and the unstarted eighth cell remain explicit.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

from analyze_budget_notification import audit_requests
from analyze_handoff_factors import trial_row
from audit_budget_visibility import budget_before_calls
from budget_signal import ARMS
from diagnose_code_programs import classify
from diagnose_handoff_programs import matching_prefix_requests
from run_handoff_factors import ROOT, read, sha


def run(storage, root):
    target = root / 'reports/P40_termination.json'
    if target.exists():
        raise FileExistsError('preserve the termination audit')
    plan = read(root / 'configs/P40_budget_notification_v01.json')
    original = read(root / plan['source_plan'])
    state = read(storage / 'records/context_pilot/P40_batch_v01/status.json')
    prepared = read(root / 'reports/P40_prefix_checks.json')
    if state['status'] != 'stopped':
        raise ValueError('this report is only for the declared stopped batch')
    expected_order = [f'P40_{n:02d}_{a.upper()}' for n in range(1, 5)
                      for a in (ARMS if n % 2 else ARMS[::-1])]
    attempted_ids = [r['run_id'] for r in state['rows']]
    if (attempted_ids != expected_order[:len(attempted_ids)]
            or state['completed'] != attempted_ids[:-1]
            or state['active'] != attempted_ids[-1]):
        raise ValueError('unexpected batch termination order')
    rows = []
    for n, source in enumerate(plan['source_runs'], 1):
        for arm in ARMS:
            rid = f'P40_{n:02d}_{arm.upper()}'
            folder = storage / 'records/context_pilot' / rid
            if rid not in attempted_ids:
                if folder.exists():
                    raise ValueError('unstarted cell has unexpected records')
                rows.append({'run_id': rid, 'task_id': original['task_ids'][n - 1], 'arm': arm,
                             'record_status': 'not_run_after_prespecified_stop', 'success': None,
                             'model_calls': 0, 'known_total_tokens': 0, 'unknown_usage_calls': 0,
                             'api_requests': 0, 'prefix_api_requests': 0, 'setup_api_requests': 0})
                continue
            if rid in state['completed']:
                row = trial_row(folder, original, source)
                row['record_status'] = 'evaluated'
            else:
                summary, usage, events, setup, identity = [read(folder / p) for p in
                    ('summary.json', 'usage.json', 'events.json', 'setup.json', 'source_identity.json')]
                if ((folder / 'evaluation.json').exists() or summary['evaluation'] != 'not_run'
                        or setup['status'] != 'matched_observable_prefix'
                        or not summary['python_session']['container_removed']
                        or identity['source_run'] != source):
                    raise ValueError('unexpected stopped-cell evaluation or restoration state')
                _, totals = budget_before_calls(usage, events, summary['prefix_api_requests'], read(folder / 'plan.json'))
                if (len(usage) != summary['model_calls'] or totals['known_total_tokens'] != summary['known_total_tokens']
                        or totals['unknown_usage_calls'] != summary['unknown_usage_calls']
                        or totals['suffix_api_requests'] != summary['api_requests']
                        or summary['unknown_usage_calls'] != 1 or summary['unknown_effect_requests']):
                    raise ValueError('stopped-cell counters disagree')
                row = {k: summary[k] for k in ('run_id', 'task_id', 'arm', 'model_calls', 'known_total_tokens',
                     'unknown_usage_calls', 'api_requests', 'prefix_api_requests', 'stop_reason')}
                row.update(record_status='stopped_unknown_usage_unevaluated', success=None,
                           setup_api_requests=setup['environment_replay']['api_requests'],
                           continuation_wall_seconds=summary['wall_seconds'], full_wall_seconds=summary['full_wall_seconds'],
                           source_boundary_sha256=identity['boundary_manifest_sha256'],
                           source_hashes={p: sha(folder / p) for p in
                                ('summary.json', 'events.json', 'spans.json', 'usage.json', 'setup.json',
                                 'source_identity.json', 'plan.json', 'factor_plan.json')})
            row = audit_requests(folder, row, prepared['rows'][n - 1])
            usage, events, spans = [read(folder / p) for p in ('usage.json', 'events.json', 'spans.json')]
            programs = {}; results = sorted((folder / 'programs').glob('*/result_private.json'))
            for path in results:
                programs.setdefault(path.parent.name.rsplit('_', 1)[0], []).append(read(path))
            row['diagnostics'] = classify(usage, events, spans, programs)
            row['diagnostics'].update(matching_prefix_requests(read(folder / 'prefix_events.json'),
                read(folder / 'prefix_spans.json'), events, spans))
            row['program_result_sha256'] = {str(p.relative_to(folder)): sha(p) for p in results}
            rows.append(row)
    paired = []
    for n in range(4):
        a, b = rows[n * 2:n * 2 + 2]
        if a['record_status'] == b['record_status'] == 'evaluated':
            if a['source_boundary_sha256'] != b['source_boundary_sha256']:
                raise ValueError('paired boundary differs')
            paired.append({'task_id': a['task_id'], 'plain_success': a['success'], 'notified_success': b['success'],
                           'plain_tokens': a['known_total_tokens'], 'notified_tokens': b['known_total_tokens'],
                           'notified_minus_plain_tokens': b['known_total_tokens'] - a['known_total_tokens']})
    result = {'phase': 'P40_termination', 'status': 'stopped', 'all_planned_cells_accounted': True,
              'complete_four_task_comparison': False, 'audit_errors': [], 'rows': rows,
              'record_status_counts': dict(Counter(r['record_status'] for r in rows)),
              'paired_observations_only': paired, 'four_task_winner': None,
              'attempted_totals': {k: sum(r[k] for r in rows) for k in
                  ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests',
                   'prefix_api_requests', 'setup_api_requests')},
              'novel_method_claim': False, 'general_quality_preservation_claim': False,
              'additional_model_calls': 0, 'additional_api_requests': 0, 'additional_evaluator_calls': 0,
              'limits': ['Six evaluated cells, one unevaluated timeout, one unstarted cell.',
                         'Unknown usage is additional to the known token subtotal, never zero.',
                         'Three paired task observations do not substitute for the planned four-task comparison.',
                         'No replacement trial or budget extension.', 'Budget notifications are an existing baseline.'],
              'source_sha256': {p: sha(root / p) for p in
                  ('configs/P40_budget_notification_v01.json', 'reports/P40_activation_v01.json',
                   'scripts/audit_budget_termination.py', 'scripts/analyze_budget_notification.py')},
              'batch_status_sha256': sha(storage / 'records/context_pilot/P40_batch_v01/status.json')}
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('record_status_counts', 'attempted_totals', 'paired_observations_only')}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT); a = p.parse_args()
    run(a.storage_root, a.repo_root)
