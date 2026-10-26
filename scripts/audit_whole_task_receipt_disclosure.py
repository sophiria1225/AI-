"""Closed P128: all sixteen fixed receipt-disclosure conditions, including failures.

Runtime/API reconstruction reuses the unchanged P127 auditor; original raw
history independently drives disclosure and rolling-input reconstruction.
No saved Python program, model, tokenizer, API or evaluator is executed.
"""
import argparse
from pathlib import Path
import subprocess

from api_error_comparison import disposition
from audit_receipt_checkpoint_trace import audit_trace
from audit_whole_task_region_projection import audit_runtime, equal, require
from budget_signal import digest
from inspect_appworld_api_schemas import load_public_tools
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from whole_task_receipt_disclosure import (ACTIVATION, PLAN, PREFLIGHT, ERROR_POLICY, MODES, SEEDS, cell_id,
    config_for, initial_conversation, run_order, summarize)


def preflight_conditions(rows, prepared):
    require(type(rows) is list and len(rows) == len(SEEDS) * len(prepared),
            'all_fixed_replication_task_preflights_required')
    mapping = {}
    for row in rows:
        rep = row['replication']
        require(type(rep) is int and 1 <= rep <= len(SEEDS)
                and type(row['model_seed']) is int and row['model_seed'] == SEEDS[rep - 1]
                and set(row['conditions']) == set(MODES), 'preflight_replication_identity_changed')
        key = (rep, row['task_id'])
        require(key not in mapping, 'duplicate_preflight_condition')
        mapping[key] = row
    require(set(mapping) == {(rep, item['task_id']) for rep in range(1, len(SEEDS) + 1)
                            for item in prepared}, 'preflight_task_replication_set_changed')
    return mapping


def validate_closed_batch(batch):
    expected = {cell_id(rep, number, mode) for rep, number, mode in run_order()}
    completed, rows = batch['completed'], batch['rows']
    require(batch['phase'] == 'P128' and batch['status'] in ('complete', 'stopped')
            and type(completed) is list and len(completed) == len(set(completed))
            and set(completed) <= expected and type(rows) is list
            and len(rows) == len({r['run_id'] for r in rows})
            and {r['run_id'] for r in rows} <= expected
            and (batch.get('active') is None or batch['active'] in expected),
            'closed_P128_batch_identity_changed')
    require(batch['status'] != 'complete' or (set(completed) == expected
            and batch.get('active') is None), 'complete_batch_missing_fixed_conditions')
    return expected


def audit_cell(folder, root, plan, original, item, mode, replication, pre, evaluated, *, tools=None):
    folder, root = Path(folder), Path(root)
    require(mode in MODES and type(replication) is int and 1 <= replication <= len(SEEDS),
            'fixed_P128_replication_mode_required')
    summary = read(folder / 'summary.json')
    config = config_for(original, plan, item['task_id'], mode, replication)
    require(read(folder / 'plan.json') == config and read(folder / 'comparison_plan.json') == plan
        and read(folder / 'public_task.json') == item['public_task'] and summary['arm'] == ERROR_POLICY
        and summary['time_visibility'] == 'not_exposed' and summary['checkpoint_policy'] == 'rolling_separate'
        and summary['projection_policy'] == 'explicit_joined_fields'
        and summary['receipt_disclosure_policy'] == mode
        and type(summary['replication']) is int and summary['replication'] == replication
        and type(summary['model_seed']) is int and summary['model_seed'] == SEEDS[replication - 1]
        and summary['world_seed'] == plan['world_seed'] and summary['reasoning_budget_tokens'] == -1
        and summary['task_id'] == item['task_id'] and summary['run_id'] == folder.name
        and summary['prefix_api_requests'] == 0 and summary['phase'] == 'P128',
        'executed_P128_condition_changed')
    conversation = initial_conversation(original, item['public_task'], mode, execution_scope=folder.name)
    initial, _ = conversation.for_model(config['observation_page_characters'])
    require(digest(initial) == pre['base_messages_sha256'], 'initial_input_differs_from_preflight')
    checked = audit_trace(folder, config, conversation)
    if tools is None:
        tools = load_public_tools(folder.parents[2] / '.runtime/appworld/r18_probe_01/data')[0]
    runtime = audit_runtime(folder, config, tools)
    require(not evaluated or disposition(summary) != 'stop_batch', 'evaluation_after_invalid_cell')
    success = None
    if evaluated:
        evaluation = read(folder / 'evaluation.json')
        require(evaluation['execution_summary_sha256'] == sha(folder / 'summary.json')
            and evaluation['evaluation_returned_to_model'] is False and type(evaluation['official_success']) is bool
            and evaluation['evaluation_script_sha256'] == sha(root / 'scripts/evaluate_context_trial.py'),
            'independent_evaluation_link_changed')
        dbs = (folder.parents[2] / '.runtime/appworld/r18_probe_01/experiments/outputs'
               / folder.name / 'tasks' / item['task_id'] / 'dbs')
        hashes = {str(p.relative_to(dbs)): sha(p) for p in sorted(dbs.rglob('*')) if p.is_file()}
        require(bool(hashes) and hashes == evaluation['frozen_database_hashes'], 'evaluated_database_hashes_changed')
        success = evaluation['official_success']
    known = [call for call in read(folder / 'usage.json') if call['status'] == 'ok']
    return {**checked, **runtime, 'run_id': folder.name, 'task_id': item['task_id'],
        'time_visibility': 'not_exposed', 'checkpoint_policy': 'rolling_separate', 'projection_policy': 'explicit_joined_fields',
        'replication': replication, 'model_seed': SEEDS[replication - 1], 'receipt_mode': mode,
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
    from run_whole_task_receipt_disclosure import frozen_hashes, sources
    storage, root = Path(storage), Path(root)
    target = root / 'reports/P128_comparison.json'
    if target.exists():
        raise FileExistsError('preserve_all_P128_audit_attempts')
    pipeline_dir = storage / 'records/context_pilot/P128_pipeline_v01'
    pipeline, server = read(pipeline_dir / 'status.json'), read(pipeline_dir / 'server_final.json')
    require(pipeline['status'] in ('complete', 'stopped') and pipeline.get('server_stopped')
        and server['status'] == 'stopped' and server['supervisor_pid'] == pipeline['server_supervisor_pid'],
        'owned_P128_pipeline_must_be_closed_before_audit')
    for key in ('pid', 'supervisor_pid'):
        require(type(server[key]) is int and server[key] > 0, 'positive_owned_server_PID_required')
        process = subprocess.run(['ps', '-p', str(server[key]), '-o', 'command='],
                                 capture_output=True, text=True, timeout=10)
        require(process.returncode == 1 and not process.stdout.strip(), 'owned_P128_process_still_exists')
    plan, original, tools, prepared = sources(storage, root)
    activation, pre = read(root / ACTIVATION), read(root / PREFLIGHT)
    require(activation['source_hashes'] == frozen_hashes(root)
        and activation['preflight_sha256'] == sha(root / PREFLIGHT), 'P128_frozen_sources_changed')
    batch = read(storage / 'records/context_pilot' / plan['batch_id'] / 'status.json')
    expected = validate_closed_batch(batch)
    actual = {p.name for p in (storage / 'records/context_pilot').glob('BOC_P128_*') if p.is_dir()}
    require(actual <= expected, 'unplanned_P128_condition_records_present')
    pre_rows = preflight_conditions(pre['rows'], prepared)
    rows, errors = [], []
    for replication, number, mode in run_order():
        item = prepared[number - 1]
        rid = cell_id(replication, number, mode)
        folder = storage / 'records/context_pilot' / rid
        row = dict(run_id=rid, task_id=item['task_id'], time_visibility='not_exposed',
            checkpoint_policy='rolling_separate', projection_policy='explicit_joined_fields',
            replication=replication, model_seed=SEEDS[replication - 1], receipt_mode=mode,
            receipt_disclosure_audit_complete=None, receipt_disclosure_contract_intact=None,
            receipt_disclosures=None, receipt_disclosure_contract_failed=None,
            record_status='not_run',
            success=None, known_total_tokens=None, unknown_usage_calls=None,
            projection_hits=None, projection_contract_failed=None)
        if (folder / 'summary.json').exists():
            try:
                row = audit_cell(folder, root, plan, original, item, mode, replication,
                    pre_rows[(replication, item['task_id'])]['conditions'][mode], rid in batch['completed'], tools=tools)
            except Exception as error:
                row.update(record_status='audit_error', success=None, known_total_tokens=None,
                           unknown_usage_calls=None, projection_hits=None, projection_contract_failed=None)
                errors.append(dict(run_id=rid, type=type(error).__name__, reason=str(error)
                    if type(error) is ValueError else 'malformed_or_missing_audit_input'))
        elif folder.exists() or batch.get('active') == rid:
            # The parent records activation before spawning the worker. A
            # startup failure may leave no trial directory, but is not proof
            # that the slot was never attempted or had zero execution cost.
            row['record_status'] = 'incomplete_worker'
        rows.append(row)
    result = dict(phase='P128', batch_status=batch['status'], rows=rows, audit_errors=errors,
        **summarize(rows, errors), pipeline_status_sha256=sha(pipeline_dir / 'status.json'),
        server_final_sha256=sha(pipeline_dir / 'server_final.json'), owned_processes_absent=True,
        plan_sha256=sha(root / PLAN), activation_sha256=sha(root / ACTIVATION), auditor_sha256=sha(Path(__file__)),
        additional_model_calls=0, additional_api_calls=0, additional_evaluator_calls=0,
        additional_tokenizer_calls=0,
        reserved_scenarios_read=0, private_reasoning_inspected_semantically=False,
        database_contents_inspected=False, generated_code_executed_by_auditor=False)
    require(activation['source_hashes'] == frozen_hashes(root), 'P128_sources_changed_during_audit')
    write_json(target, result)
    print({k: result[k] for k in ('batch_status', 'audit_errors', 'development_gate_met')})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    arguments = parser.parse_args()
    run(arguments.storage_root, arguments.repo_root)
