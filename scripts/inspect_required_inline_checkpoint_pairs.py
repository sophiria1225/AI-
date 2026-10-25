"""Public-only P120 cost decomposition and pre-intervention request checks."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from inspect_inline_checkpoint_pairs import compare
from plot_receipt_history_results import read, sha, write_new, require, TASKS

PLAN = 'configs/P120_reporting_v01.json'
OUTPUT = 'reports/P120_pair_controls.json'
POLICIES = ('single_checkpoint', 'inline_checkpoint')


def run(root, storage, expected_head):
    require(not (root / OUTPUT).exists(), 'preserve_existing_pair_analysis')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    require(head == expected_head, 'fixed_analysis_head_required')
    from run_whole_task_required_inline_checkpoint_pipeline import checked_ci
    ci = checked_ci(root, head)
    plan = read(root / PLAN)
    require(plan['analysis'] == 'P120_public_reporting' and plan['planned_conditions'] == 8 and
            plan['model_calls'] == plan['API_requests'] == plan['tokenizer_requests'] == 0,
            'fixed_public_only_analysis_required')
    for rel, digest in plan['source_sha256'].items():
        require(sha(root / rel) == digest, 'fixed_pair_analysis_source_changed:' + rel)
    closed = read(storage / '.runtime/P120_closure_once_end.json')
    audit_path, session_path = root / 'reports/P120_comparison.json', root / 'reports/P120_server_session.json'
    require(sha(audit_path) == closed['audit_sha256'] and sha(session_path) == closed['session_sha256'],
            'original_closed_cohort_required')
    audit, session = read(audit_path), read(session_path)
    start = read(root / 'reports/P120_execution_start_20261025.json')
    require(start['preparation_merge']['head'] == plan['source_implementation_head'] and
            audit['plan_sha256'] == sha(root / 'configs/P120_whole_task_required_inline_checkpoint_v01.json'),
            'fixed_original_P120_implementation_required')
    require(audit['phase'] == session['phase'] == 'P120' and not audit['audit_errors'] and
            audit['owned_processes_absent'] and session['owned_processes_absent'] and
            session['status'] == 'stopped' and session['audit_source_sha256'] == sha(audit_path),
            'closed_clean_cohort_required')
    result = {'phase': 'P120_public_pair_controls', 'created_at': datetime.now(timezone.utc).isoformat(),
        'git_commit': head, 'ci': ci, 'source_audit_sha256': sha(audit_path),
        'source_session_sha256': sha(session_path), 'plan_sha256': sha(root / PLAN),
        'pairs': compare(audit['rows']), 'ordinary_control_criteria_met': audit['development_gate_met'],
        'inline_checkpoint_offer_calls': audit['inline_checkpoint_offer_calls'],
        'inline_checkpoint_installations': audit['inline_checkpoint_installations'],
        'required_inline_control_exercised': audit['required_inline_control_exercised'],
        'required_schema_is_not_installation': True,
        'all_four_tasks_retained': True, 'unknown_usage_imputed': False,
        'private_histories_or_summary_text_read': False, 'additional_model_calls': 0,
        'additional_API_requests': 0, 'additional_tokenizer_requests': 0,
        'additional_evaluations': 0, 'manuscript_changed': False,
        'causal_future_behavior_claim': False, 'novel_method_claim': False}
    write_new(root / OUTPUT, result)
    print(json.dumps({'phase': result['phase'], 'pairs': len(result['pairs']), 'additional_model_calls': 0}))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--expected-head', required=True)
    args = parser.parse_args()
    run(args.repo_root.resolve(), args.storage_root.resolve(), args.expected_head)
