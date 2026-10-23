"""Audit all sixteen repeated cells and retain the eight P80 anchor cells."""
import argparse
from pathlib import Path

from audit_budget_visibility_comparison import audit_cell
from budget_visibility_repetition import cell_id, run_order, summarize_repetitions
from run_budget_visibility_repetition import ACTIVATION, PREFLIGHT, frozen_hashes, sources
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def run(storage, root):
    target = root / 'reports/P81_repetitions.json'
    if target.exists():
        raise FileExistsError('preserve_all_P81_audit_attempts')
    plan, original, _, prepared = sources(storage, root)
    anchor = read(root / plan['prior_cohort'])
    activation, pre = read(root / ACTIVATION), read(root / PREFLIGHT)
    if (activation['source_hashes'] != frozen_hashes(root)
            or activation['preflight_sha256'] != sha(root / PREFLIGHT)):
        raise ValueError('P81_frozen_sources_changed')
    batch = read(storage / 'records/context_pilot' / plan['batch_id'] / 'status.json')
    if batch['status'] not in ('complete', 'stopped'):
        raise ValueError('wait_until_repeat_batch_closes')
    rows, errors = [], []
    for repetition, number, policy in run_order():
        item = prepared[number - 1]; rid = cell_id(repetition, number, policy)
        folder = storage / 'records/context_pilot' / rid
        row = {'run_id': rid, 'task_id': item['task_id'], 'time_visibility': policy,
               'record_status': 'not_run', 'success': None, 'known_total_tokens': None,
               'unknown_usage_calls': None}
        if (folder / 'summary.json').exists():
            try:
                row = audit_cell(folder, root, plan, original, item, policy,
                    pre['rows'][number - 1]['conditions'][policy], rid in batch['completed'])
                if read(folder / 'summary.json')['phase'] != 'P81':
                    raise ValueError('wrong_repetition_worker')
            except Exception as error:
                row.update(record_status='audit_error', success=None,
                           known_total_tokens=None, unknown_usage_calls=None)
                errors.append({'run_id': rid, 'type': type(error).__name__, 'reason': str(error)})
        elif folder.exists():
            row['record_status'] = 'incomplete_worker'
        rows.append({**row, 'repetition': repetition})
    result = {'phase': 'P81', 'batch_status': batch['status'], 'rows': rows, 'audit_errors': errors,
        'anchor_rows': anchor['rows'], **summarize_repetitions(anchor['rows'], rows, errors),
        'anchor_sha256': sha(root / plan['prior_cohort']),
        'plan_sha256': sha(root / 'configs/P81_budget_visibility_repetition_v01.json'),
        'activation_sha256': sha(root / ACTIVATION), 'auditor_sha256': sha(Path(__file__)),
        'shared_cell_auditor_sha256': sha(root / 'scripts/audit_budget_visibility_comparison.py'),
        'additional_model_calls': 0, 'additional_api_calls': 0, 'additional_evaluator_calls': 0,
        'reserved_scenarios_read': 0, 'private_reasoning_inspected_semantically': False,
        'database_contents_inspected': False}
    write_json(target, result)
    print({k: result[k] for k in ('batch_status', 'audit_errors', 'all_three_repetition_gates_met')})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    args = parser.parse_args()
    run(args.storage_root, args.repo_root)
