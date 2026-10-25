"""P122: whole-cohort audit after server closure; no generated work or reruns."""
import argparse
from pathlib import Path
import subprocess

from api_error_comparison import disposition
from audit_required_inline_checkpoint_trace import audit_trace
from budget_signal import digest
from whole_task_checkpoint_replication import (ERROR_POLICY, SEEDS, cell_id, config_for, run_order, summarize, initial_conversation)
from run_whole_task_checkpoint_replication import ACTIVATION, PREFLIGHT, frozen_hashes, sources
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def audit_cell(folder, root, plan, original, item, arm, pre, evaluated, repetition):
    summary = read(folder / 'summary.json')
    config = config_for(original, plan, item['task_id'], arm, repetition)
    if (read(folder / 'plan.json') != config or read(folder / 'comparison_plan.json') != plan
            or read(folder / 'public_task.json') != item['public_task']
            or summary['arm'] != ERROR_POLICY or summary['time_visibility'] != 'not_exposed'
            or summary['checkpoint_policy'] != arm or summary['reasoning_budget_tokens'] != -1
            or summary['task_id'] != item['task_id'] or summary['run_id'] != folder.name
            or summary['prefix_api_requests'] != 0
            or summary['repetition'] != repetition or summary['model_seed'] != SEEDS[repetition - 1]):
        raise ValueError('executed_P122_condition_changed')
    conversation = initial_conversation(original, item['public_task'])
    initial, _ = conversation.for_model(config['observation_page_characters'])
    if digest(initial) != pre['base_messages_sha256']:
        raise ValueError('initial_input_differs_from_preflight')
    checked = audit_trace(folder, config, conversation)
    if evaluated and disposition(summary) == 'stop_batch':
        raise ValueError('evaluation_after_invalid_cell')
    success = None
    if evaluated:
        evaluation = read(folder / 'evaluation.json')
        if (evaluation['execution_summary_sha256'] != sha(folder / 'summary.json')
                or evaluation['evaluation_returned_to_model'] or type(evaluation['official_success']) is not bool
                or evaluation['evaluation_script_sha256'] != sha(root / 'scripts/evaluate_context_trial.py')):
            raise ValueError('independent_evaluation_link_changed')
        dbs = folder.parents[2] / '.runtime/appworld/r18_probe_01/experiments/outputs' / folder.name / 'tasks' / item['task_id'] / 'dbs'
        hashes = {str(p.relative_to(dbs)): sha(p) for p in sorted(dbs.rglob('*')) if p.is_file()}
        if not hashes or hashes != evaluation['frozen_database_hashes']:
            raise ValueError('evaluated_database_hashes_changed')
        success = evaluation['official_success']
    usage = read(folder / 'usage.json')
    known = [c for c in usage if c['status'] == 'ok']
    return {**checked, 'run_id': folder.name, 'task_id': item['task_id'],
        'repetition': repetition, 'model_seed': SEEDS[repetition - 1],
        'time_visibility': 'not_exposed', 'checkpoint_policy': arm,
        'record_status': 'evaluated' if evaluated else 'unevaluated', 'success': success,
        **{k: summary[k] for k in ('stop_reason', 'model_calls', 'known_total_tokens', 'unknown_usage_calls',
                                  'api_requests', 'wall_seconds', 'full_wall_seconds', 'cleanup_wall_seconds')},
        'input_tokens': sum(c['input_tokens'] for c in known),
        'output_tokens': sum(c['output_tokens'] for c in known),
        'cached_input_tokens': sum(c['cached_input_tokens'] for c in known)
            if all(type(c.get('cached_input_tokens')) is int for c in known) else None,
        'setup_wall_seconds': summary['setup']['wall_seconds'],
        'summary_sha256': sha(folder / 'summary.json'), 'usage_sha256': sha(folder / 'usage.json'),
        'evaluation_sha256': sha(folder / 'evaluation.json') if evaluated else None}


def run(storage, root):
    target = root / 'reports/P122_comparison.json'
    if target.exists():
        raise FileExistsError('preserve_all_P122_audit_attempts')
    plan, original, _, prepared = sources(storage, root)
    pipeline_dir = storage / 'records/context_pilot/P122_pipeline_v01'
    pipeline, server = read(pipeline_dir / 'status.json'), read(pipeline_dir / 'server_final.json')
    if (pipeline['status'] not in ('complete', 'stopped') or not pipeline.get('server_stopped')
            or server['status'] != 'stopped'
            or server['supervisor_pid'] != pipeline['server_supervisor_pid']):
        raise ValueError('owned_P122_pipeline_must_be_closed_before_audit')
    for key in ('pid', 'supervisor_pid'):
        process = subprocess.run(['ps', '-p', str(server[key]), '-o', 'command='],
                                 capture_output=True, text=True, timeout=10)
        if process.returncode != 1 or process.stdout.strip():
            raise ValueError('owned_P122_process_still_exists')
    activation, pre = read(root / ACTIVATION), read(root / PREFLIGHT)
    if (activation['source_hashes'] != frozen_hashes(root)
            or activation['preflight_sha256'] != sha(root / PREFLIGHT)):
        raise ValueError('P122_frozen_sources_changed')
    batch = read(storage / 'records/context_pilot' / plan['batch_id'] / 'status.json')
    if batch['status'] not in ('complete', 'stopped'):
        raise ValueError('wait_until_budget_batch_closes')
    rows, errors = [], []
    for repetition, number, policy in run_order():
        item = prepared[number - 1]; rid = cell_id(repetition, number, policy)
        folder = storage / 'records/context_pilot' / rid
        row = {'run_id': rid, 'task_id': item['task_id'], 'time_visibility': 'not_exposed', 'checkpoint_policy': policy,
               'repetition': repetition, 'model_seed': SEEDS[repetition - 1],
               'record_status': 'not_run', 'success': None, 'known_total_tokens': None,
               'unknown_usage_calls': None}
        if (folder / 'summary.json').exists():
            try:
                row = audit_cell(folder, root, plan, original, item, policy,
                    pre['rows'][(repetition - 1) * 4 + number - 1]['conditions'][policy], rid in batch['completed'], repetition)
                if read(folder / 'summary.json')['phase'] != 'P122':
                    raise ValueError('wrong_budget_worker')
            except Exception as error:
                row.update(record_status='audit_error', success=None,
                           known_total_tokens=None, unknown_usage_calls=None)
                errors.append({'run_id': rid, 'type': type(error).__name__, 'reason': str(error)})
        elif folder.exists():
            row['record_status'] = 'incomplete_worker'
        rows.append(row)
    result = {'phase': 'P122', 'batch_status': batch['status'], 'rows': rows, 'audit_errors': errors,
        **summarize(rows, errors),
        'pipeline_status_sha256': sha(pipeline_dir / 'status.json'),
        'server_final_sha256': sha(pipeline_dir / 'server_final.json'),
        'owned_processes_absent': True,
        'plan_sha256': sha(root / 'configs/P122_checkpoint_replication_v01.json'),
        'activation_sha256': sha(root / ACTIVATION), 'auditor_sha256': sha(Path(__file__)),
        'additional_model_calls': 0, 'additional_api_calls': 0, 'additional_evaluator_calls': 0,
        'reserved_scenarios_read': 0, 'private_reasoning_inspected_semantically': False,
        'database_contents_inspected': False}
    write_json(target, result)
    print({k: result[k] for k in ('batch_status', 'audit_errors', 'replication_gate_met')})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    args = parser.parse_args()
    run(args.storage_root, args.repo_root)
