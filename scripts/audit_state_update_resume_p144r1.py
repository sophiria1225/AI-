"""Closed-data P144 continuation accounting with explicit split-session linkage.

The frozen P144 cell/trace auditor is reused unchanged. Only copies of audited
rows receive canonical slot IDs for the frozen summarizer; physical IDs and
session provenance remain in every published row. No experiment or evaluation
is launched. Splitting the cohort across servers precludes adoption/attribution
claims, even if its descriptive numerical and contract checks pass.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess

from audit_whole_task_state_update_p144 import audit_cell
from whole_task_state_update_p144 import PLAN, TASKS, cell_id, run_order, summarize
from run_handoff_factors import ROOT, read, sha

SPEC = 'configs/P144R1_continuation_v01.json'
TARGET = 'reports/P144R1_continuation.json'


def slots():
    result = []
    for index, (number, mode) in enumerate(run_order()):
        canonical = cell_id(number, mode)
        result.append(dict(number=number, mode=mode, canonical_run_id=canonical,
            run_id=canonical if index < 2 else canonical.replace('BOC_P144_', 'BOC_P144R1_', 1),
            execution_session='original_before_shutdown' if index < 2 else 'continuation_after_resume'))
    return result


def canonical_slots(rows):
    expected = slots()
    if (type(rows) is not list or len(rows) != 12
            or [row.get('run_id') for row in rows] != [s['run_id'] for s in expected]
            or any(row.get('task_id') != TASKS[s['number'] - 1]
                   or row.get('object_timing_mode') != s['mode']
                   or row.get('checkpoint_representation_mode') != s['mode']
                   for row, s in zip(rows, expected))):
        raise ValueError('exact_twelve_physical_continuation_slots_required')
    result = deepcopy(rows)
    for row, slot in zip(result, expected):
        row['run_id'] = slot['canonical_run_id']
    return result


def descriptive_summary(rows, errors):
    result = summarize(canonical_slots(rows), errors)
    result['descriptive_development_criteria_met'] = result['development_gate_met']
    result['development_gate_met'] = False
    by_task_mode = {(TASKS[s['number'] - 1], s['mode']): s for s in slots()}
    for comparison in result['comparisons']:
        comparison['descriptive_comparison_criteria_met'] = comparison['comparison_gate_met']
        comparison['comparison_gate_met'] = False
        comparison['component_effect_attributable'] = False
        for pair in comparison['pairs']:
            before = by_task_mode[(pair['task_id'], pair['baseline'])]
            after = by_task_mode[(pair['task_id'], pair['candidate'])]
            pair['baseline_run_id'] = before['run_id']
            pair['candidate_run_id'] = after['run_id']
            pair['same_execution_session'] = before['execution_session'] == after['execution_session']
    result.update(scientific_adoption_evaluated=False, scientific_adoption_gate_met=False,
        split_server_sessions=True, original_and_continuation_slots_linked=True,
        old_cohort_reports_rewritten=False, timing_or_cache_effect_isolated=False,
        cross_session_component_effect_claim=False,
        interpretation='The original fixed twelve P144 slots are linked across a user-requested shutdown: '
        'two executions before shutdown and ten planned continuations in a new server session. '
        'The saved second execution was evaluated offline once after explicit user resumption. '
        'Original reports and artifacts remain immutable. Physical run IDs and session membership are retained; '
        'canonical IDs are used only on copies passed to the frozen P144 descriptive summarizer. '
        'Runtime restart and cache/session changes are not isolated from the method comparison. '
        'All adoption and comparison gates remain false even if descriptive criteria pass. '
        'Missing execution/evaluation/usage remains missing; no zero imputation or additional attempts. '
        'This is neither independent replication nor unseen confirmation nor a general quality/novelty claim.')
    return result


def validate_batch_status(batch, expected):
    completed = batch.get('completed')
    if (batch.get('phase') != 'P144R1' or batch.get('status') not in ('complete', 'stopped')
            or batch.get('planned') != expected or type(completed) is not list
            or completed != expected[:len(completed)]
            or (batch.get('active') is not None and batch['active'] not in expected)
            or (batch['status'] == 'complete' and (completed != expected or batch.get('active') is not None))):
        raise ValueError('closed_exact_ten_slot_continuation_batch_required')
    return completed


def validate_closed_pipeline(pipeline, server, process_check=subprocess.run):
    if (pipeline.get('phase') != 'P144R1_pipeline'
            or pipeline.get('status') not in ('complete', 'stopped')
            or pipeline.get('server_stopped') is not True or server.get('status') != 'stopped'
            or type(server.get('supervisor_pid')) is not int or server['supervisor_pid'] <= 0
            or type(server.get('pid')) is not int or server['pid'] <= 0
            or server['pid'] == server['supervisor_pid']
            or server['supervisor_pid'] != pipeline.get('server_supervisor_pid')):
        raise ValueError('owned_continuation_server_must_be_closed_before_audit')
    for key in ('pid', 'supervisor_pid'):
        process = process_check(['ps', '-p', str(server[key]), '-o', 'command='],
                                capture_output=True, text=True, timeout=10)
        if process.returncode != 1 or process.stdout.strip():
            raise ValueError('owned_continuation_process_still_exists_or_absence_unknown')


def verify_saved_artifacts(storage, spec):
    runtime = storage / '.runtime'
    handoff_path = runtime / 'P144_shutdown_pause_handoff_20261028.json'
    recovery_path = runtime / 'P144R1_saved_evaluation_recovery_20261028.json'
    if (sha(handoff_path) != spec['shutdown_handoff_sha256']
            or sha(recovery_path) != spec['saved_evaluation_recovery_sha256']):
        raise ValueError('frozen_shutdown_or_recovery_receipt_changed')
    handoff, recovery = read(handoff_path), read(recovery_path)
    second = slots()[1]['run_id']
    if (handoff.get('work_finished_evaluation_pending') != [second]
            or handoff.get('remaining_unstarted_conditions') != [s['canonical_run_id'] for s in slots()[2:]]
            or recovery.get('status') != 'complete' or recovery.get('run_id') != second
            or recovery.get('evaluator_attempts') != 1 or recovery.get('evaluator_exit_code') != 0
            or recovery.get('model_calls') != 0 or recovery.get('server_launches') != 0
            or recovery.get('original_artifacts_unchanged') is not True
            or recovery.get('evaluation_returned_to_model') is not False
            or recovery.get('handoff_sha256') != sha(handoff_path)):
        raise ValueError('saved_second_cell_one_shot_recovery_required')
    trials = storage / 'records/context_pilot'
    if sha(trials / second / 'evaluation.json') != recovery['evaluation_sha256']:
        raise ValueError('saved_second_evaluation_changed')
    checked = 0
    for name, expected in handoff['operational_marker_sha256'].items():
        if sha(runtime / name) != expected:
            raise ValueError('original_operational_marker_changed')
        checked += 1
    for run_id, mapping in handoff['preserved_trial_sha256'].items():
        for relative, expected in mapping.items():
            if sha(trials / run_id / relative) != expected:
                raise ValueError('original_trial_artifact_changed')
            checked += 1
    for run_id, mapping in handoff['preserved_database_sha256'].items():
        summary = read(trials / run_id / 'summary.json')
        dbs = runtime / 'appworld/r18_probe_01/experiments/outputs' / run_id / 'tasks' / summary['task_id'] / 'dbs'
        current = {str(p.relative_to(dbs)): sha(p) for p in dbs.rglob('*') if p.is_file()}
        if current != mapping:
            raise ValueError('original_saved_database_changed')
        checked += len(current)
    closure = read(runtime / 'P144_pipeline_once_end.json')
    for relative, expected in closure['copied_source_sha256'].items():
        for base in (Path(handoff['run_root']), Path(handoff['prep_root'])):
            if sha(base / relative) != expected:
                raise ValueError('original_closed_report_changed')
            checked += 1
    return dict(saved_artifacts_verified=checked, recovery_sha256=sha(recovery_path),
                shutdown_handoff_sha256=sha(handoff_path))


def run(storage, root):
    storage, root = Path(storage).resolve(), Path(root).resolve()
    target = root / TARGET
    if target.exists():
        raise FileExistsError('preserve_continuation_audit_attempt')
    pipeline_dir = storage / 'records/context_pilot/P144R1_pipeline_v01'
    pipeline, server = read(pipeline_dir / 'status.json'), read(pipeline_dir / 'server_final.json')
    validate_closed_pipeline(pipeline, server)
    batch_dir = storage / 'records/context_pilot/P144R1_batch_v01'
    batch = read(batch_dir / 'status.json')
    mapping = slots()
    completed = validate_batch_status(batch, [s['run_id'] for s in mapping[2:]])
    # Only now may source validation or cell auditing access closed outcomes.
    from run_state_update_resume_p144r1 import sources, frozen_hashes
    plan, original, _, prepared = sources(storage, root, permit_stopped=True)
    spec = read(root / SPEC)
    if (spec['inherited_plan_sha256'] != sha(root / PLAN)
            or spec['remaining_run_ids'] != [s['run_id'] for s in mapping[2:]]
            or spec['canonical_remaining_run_ids'] != [s['canonical_run_id'] for s in mapping[2:]]):
        raise ValueError('continuation_mapping_or_inherited_plan_changed')
    saved = verify_saved_artifacts(storage, spec)
    original_pre = read(root / 'reports/P144_initial_checks.json')
    new_pre_path = storage / 'records/context_pilot/P144R1_preflight_v01/status.json'
    new_pre = read(new_pre_path)
    activation_path = root / 'reports/P144R1_activation_v01.json'
    activation = read(activation_path)
    if (new_pre != read(root / 'reports/P144R1_initial_checks.json')
            or new_pre.get('phase') != 'P144R1_preflight' or new_pre.get('status') != 'complete'
            or activation.get('source_hashes') != frozen_hashes(root)
            or activation.get('preflight_sha256') != sha(root / 'reports/P144R1_initial_checks.json')):
        raise ValueError('continuation_preflight_or_activation_changed')
    rows, errors = [], []
    for index, slot in enumerate(mapping):
        number, mode, rid = slot['number'], slot['mode'], slot['run_id']
        item = prepared[number - 1]
        folder = storage / 'records/context_pilot' / rid
        is_original = index < 2
        evaluated = is_original or rid in completed
        pre = original_pre if is_original else new_pre
        row = dict(run_id=rid, task_id=item['task_id'], time_visibility='not_exposed',
            checkpoint_policy='rolling_separate', checkpoint_representation_mode=mode,
            object_timing_mode=mode, model_seed=plan['model_seed'], record_status='not_run',
            success=None, known_total_tokens=None, unknown_usage_calls=None)
        missing = dict(row)
        if (folder / 'summary.json').exists():
            try:
                row = audit_cell(folder, root, plan, original, item, mode,
                                 pre['rows'][number - 1]['conditions'][mode], evaluated)
                if read(folder / 'summary.json').get('phase') != ('P144' if is_original else 'P144R1'):
                    raise ValueError('incorrect_worker_phase')
                exit_dir = storage / 'records/context_pilot/P144_batch_v01' if is_original else batch_dir
                exit_path = exit_dir / (rid + '_worker_exit.json')
                exit_record = read(exit_path)
                if (exit_record.get('run_id') != rid or exit_record.get('status') != 'exited'
                        or (evaluated and (type(exit_record.get('returncode')) is not int
                            or exit_record['returncode'] != 0 or exit_record.get('timed_out') is not False
                            or exit_record.get('forced_group_kill') is not False))):
                    raise ValueError('evaluated_worker_exit_not_confirmed')
                row['worker_exit_sha256'] = sha(exit_path)
            except Exception as error:
                row = {**missing, 'record_status': 'audit_error'}
                errors.append(dict(run_id=rid, type=type(error).__name__, reason=str(error)))
        elif folder.exists():
            row['record_status'] = 'incomplete_worker'
        if evaluated and row['record_status'] != 'evaluated':
            errors.append(dict(run_id=rid, type='ValueError', reason='completed_slot_not_auditable'))
        row.update(canonical_run_id=slot['canonical_run_id'], execution_session=slot['execution_session'],
                   evaluation_recovered_after_shutdown=(index == 1))
        rows.append(row)
    result = dict(phase='P144R1', batch_status=batch['status'], rows=rows, audit_errors=errors,
        slot_mapping=mapping, **descriptive_summary(rows, errors), **saved,
        pipeline_status_sha256=sha(pipeline_dir / 'status.json'),
        server_final_sha256=sha(pipeline_dir / 'server_final.json'), batch_status_sha256=sha(batch_dir / 'status.json'),
        owned_processes_absent=True, continuation_plan_sha256=sha(root / SPEC),
        inherited_plan_sha256=sha(root / PLAN), activation_sha256=sha(activation_path),
        original_preflight_sha256=sha(root / 'reports/P144_initial_checks.json'),
        continuation_preflight_sha256=sha(new_pre_path), auditor_sha256=sha(Path(__file__)),
        original_cell_auditor_sha256=sha(root / 'scripts/audit_whole_task_state_update_p144.py'),
        additional_model_calls=0, additional_api_calls=0, additional_evaluator_calls=0,
        reserved_scenarios_read=0, private_reasoning_inspected_semantically=False,
        database_contents_inspected=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({k: result[k] for k in ('phase', 'batch_status', 'evaluated_conditions',
                                           'audit_errors_count', 'development_gate_met')}))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    arguments = parser.parse_args()
    run(arguments.storage_root, arguments.repo_root)
