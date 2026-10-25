"""P121: vocabulary-only input restoration after all P118/P119/P120 slots close."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import time

from checkpoint_realized_inputs import DISPLAYS, PHASES, prepared_views, collect_renderings, summarize_cell
from inspect_recorded_action_agreement import verify_ci
from measure_receipt_history import private_read, read, render, sha, write_new
from model_provenance import verified_model
from receipt_reasoning_history import require
from whole_task_single_checkpoint import initial_conversation

SCOPE = 'configs/P121_checkpoint_inputs_scope_v01.json'
PLAN = 'configs/P121_checkpoint_inputs_v01.json'
PREPARATION = 'reports/P121_diagnostic_preparation_20261025.json'
SOURCE_PLANS = {
    'P118': 'configs/P118_whole_task_single_checkpoint_v01.json',
    'P119': 'configs/P119_whole_task_inline_checkpoint_v01.json',
    'P120': 'configs/P120_whole_task_required_inline_checkpoint_v01.json',
}


def fixed_parameters():
    return dict(phase='P121', source_phases=list(PHASES), displays=list(DISPLAYS),
        source_cells=24, known_tasks=4, max_saved_calls_per_cell=80, max_events_per_cell=4000,
        max_renderings=3840, max_wall_seconds=900, max_renderer_seconds=120,
        max_renderer_rss_bytes=2147483648, max_file_bytes=16777216,
        max_total_private_input_bytes=1073741824,
        runtime_commit='620d2225cc436ab0b001e3200e590e3b286ef9ab',
        effective_template_sha256='c56d1f3ab70881b0e2ed8f51fa6de435d37b84d6c804ebb19a0ec4986fa5ffa9',
        private_output='records/context_pilot/P121_checkpoint_inputs_v01',
        stop_marker='.runtime/P121.stop', automatic_retries=0,
        selection='all_attempts_all_twenty_four_slots_including_failures_unknowns_and_unrun',
        budget_notices='hold_actual_pre_call_state_fixed_for_local_diagnosis',
        inline_transport='preserve_original_metadata_omission_in_both_displays',
        inactive_replacement='both_payloads_identical',
        summary_requests='retain_original_request_and_cost_in_both_displays',
        missing_requests='retain_two_slots_without_fabricating_requests',
        unattempted_terminal_projections='excluded_from_attempted_input_cost',
        model_generations=0, environment_API_requests=0, saved_generated_program_executions=0,
        evaluations=0, task_databases_read=0, reserved_scenarios_read=0,
        novel_method_claim=False, new_task_quality_measured=False,
        counterfactual_trajectory_or_causal_effect_claim=False,
        P118_outcomes_already_known=True, P119_outcomes_already_known=True,
        scope_fixed_before_P120_outcomes_inspected=True)


def check_scope(root):
    scope = read(root / SCOPE)
    require(scope == fixed_parameters(), 'fixed_P121_scope_changed')
    preparation = read(root / PREPARATION)
    require(preparation['P120_outcomes_inspected'] is False, 'pre_outcome_scope_required')
    for rel, digest in preparation['source_sha256'].items():
        require(sha(root / rel) == digest, 'prepared_source_changed:' + rel)
    return scope, preparation


def closed_sources(storage, root):
    all_rows, runtimes = [], {}
    for phase in PHASES:
        audit_path = root / 'reports' / (phase + '_comparison.json')
        audit = read(audit_path)
        session = read(root / 'reports' / (phase + '_server_session.json'))
        require(audit['phase'] == session['phase'] == phase and not audit['audit_errors']
                and audit['owned_processes_absent'] and audit['batch_status'] in ('complete', 'stopped')
                and session['status'] == 'stopped' and session['owned_processes_absent']
                and session['audit_source_sha256'] == sha(audit_path)
                and audit['plan_sha256'] == sha(root / SOURCE_PLANS[phase]),
                'all_source_conditions_must_be_closed_and_audited:' + phase)
        source_plan = read(root / SOURCE_PLANS[phase])
        policies = ('full', 'single_checkpoint') if phase == 'P118' else ('single_checkpoint', 'inline_checkpoint')
        tasks = [t['task_id'] for t in source_plan['known_tasks']]
        require(len(tasks) == len(set(tasks)) == 4 and len(audit['rows']) == 8
                and {(r['task_id'], r['checkpoint_policy']) for r in audit['rows']}
                    == {(task, policy) for task in tasks for policy in policies}, 'all_eight_source_slots_required')
        directory = storage / 'records/context_pilot' / (phase + '_pipeline_v01')
        pipeline, server = read(directory / 'status.json'), read(directory / 'server_final.json')
        require(pipeline['status'] in ('complete', 'stopped') and pipeline['server_stopped']
                and server['status'] == 'stopped' and server['supervisor_pid'] == pipeline['server_supervisor_pid']
                and sha(directory / 'status.json') == audit['pipeline_status_sha256']
                and sha(directory / 'server_final.json') == audit['server_final_sha256'],
                'original_pipeline_closure_changed:' + phase)
        for key in ('pid', 'supervisor_pid'):
            process = subprocess.run(['ps', '-p', str(server[key]), '-o', 'command='],
                                     capture_output=True, text=True, timeout=10)
            require(process.returncode == 1 and not process.stdout.strip(), 'original_server_still_exists')
        all_rows += [{'source_phase': phase, **r} for r in audit['rows']]
        runtimes[phase] = str((directory / 'server_runtime.json').relative_to(storage))
    require(len(all_rows) == 24 and len({r['run_id'] for r in all_rows}) == 24
            and len({r['task_id'] for r in all_rows}) == 4, 'all_twenty_four_known_slots_required')
    return all_rows, runtimes


def bind(storage, root):
    scope, preparation = check_scope(root)
    require(not (root / PLAN).exists(), 'preserve_original_P121_binding')
    head, ci = verify_ci(root)
    rows, runtimes = closed_sources(storage, root)
    sources = dict(preparation['source_sha256'])
    for phase in PHASES:
        for rel, digest in read(root / SOURCE_PLANS[phase])['source_sha256'].items():
            require(sha(root / rel) == digest, 'fixed_source_phase_changed:' + rel)
            require(rel not in sources or sources[rel] == digest, 'inconsistent_source_binding')
            sources[rel] = digest
        for rel in (SOURCE_PLANS[phase], f'reports/{phase}_comparison.json', f'reports/{phase}_server_session.json'):
            sources[rel] = sha(root / rel)
    for rel in (PREPARATION, 'reports/P110_renderer_build.json', 'configs/P29_stateful_code_v01.json'):
        sources[rel] = sha(root / rel)
    private, absent = {}, []
    def include(rel, expected=None, optional=False):
        path = storage / rel
        path.resolve().relative_to(storage.resolve())
        if not path.exists() and optional:
            absent.append(rel)
            return
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= scope['max_file_bytes'],
                'bounded_regular_private_source_required')
        value = sha(path)
        require(expected is None or value == expected, 'closed_audit_input_changed:' + rel)
        private[rel] = value
    for phase in PHASES:
        for name in ('status.json', 'server_final.json', 'server_runtime.json'):
            include(f'records/context_pilot/{phase}_pipeline_v01/{name}')
    attempts = 0
    for row in rows:
        if row['record_status'] not in ('evaluated', 'unevaluated'):
            continue
        prefix = 'records/context_pilot/' + row['run_id'] + '/'
        require(len(row['request_checks']) == row['model_calls'] <= 80, 'all_original_attempts_required')
        attempts += row['model_calls']
        for name in ('plan', 'public_task', 'summary', 'usage', 'events', 'spans', 'budget_observations'):
            include(prefix + name + '.json', row.get(name + '_sha256'))
        inline = row['checkpoint_policy'] == 'inline_checkpoint'
        for name in (('inline_history_views', 'inline_controls') if inline
                     else ('checkpoint_history_views', 'checkpoint_controls')):
            include(prefix + name + '.json')
        for name in ('checkpoint_private', 'conversation_private'):
            include(prefix + name + '.json', optional=True)
        for call in row['request_checks']:
            for name in ('request', 'response'):
                rel = prefix + call['call_id'] + '/' + name + '.json'
                expected = call[name + '_sha256']
                if expected is None:
                    require(not (storage / rel).exists(), 'missing_record_was_added')
                    absent.append(rel)
                else:
                    include(rel, expected)
    require(attempts * 2 <= scope['max_renderings'], 'finite_rendering_cap')
    require(sum((storage / p).stat().st_size for p in private) <= scope['max_total_private_input_bytes'],
            'finite_private_input_bytes')
    value = dict(**scope, created_at=datetime.now(timezone.utc).isoformat(), preparation_head=head,
        preparation_CI=ci, source_sha256=sources, private_source_sha256=private,
        absent_private_sources=absent, runtime_records=runtimes,
        run_ids=[r['run_id'] for r in rows], actual_model_attempts=attempts, planned_renderings=attempts * 2)
    write_new(root / PLAN, value)
    print({'source_cells': len(rows), 'bound_private_files': len(private),
           'absent_records': len(absent), 'planned_renderings': attempts * 2})


def inspect(storage, root):
    scope, _ = check_scope(root)
    plan = read(root / PLAN)
    require(all(type(plan.get(k)) is type(v) and plan[k] == v for k, v in scope.items()), 'fixed_P121_plan_changed')
    for rel, digest in plan['source_sha256'].items():
        require(sha(root / rel) == digest, 'bound_source_changed:' + rel)
    head, ci = verify_ci(root)
    sources, runtimes = closed_sources(storage, root)
    require([r['run_id'] for r in sources] == plan['run_ids'] and runtimes == plan['runtime_records'],
            'fixed_source_cohorts_changed')
    for rel in plan['absent_private_sources']:
        require(not (storage / rel).exists(), 'missing_source_record_was_added')
    require(sum((storage / p).stat().st_size for p in plan['private_source_sha256'])
            <= plan['max_total_private_input_bytes'], 'total_private_input_bound')
    original = read(root / 'configs/P29_stateful_code_v01.json')
    selection, _, model = verified_model(original['model_selection'], root=storage)
    runtime_values = {phase: private_read(storage, plan, rel) for phase, rel in runtimes.items()}
    for runtime in runtime_values.values():
        require(runtime['runtime']['commit'] == plan['runtime_commit']
                and runtime['model_revision'] == selection['revision']
                and Path(runtime['command'][runtime['command'].index('--model') + 1]) == model,
                'fixed_model_runtime_required')
    build = read(root / 'reports/P110_renderer_build.json')
    require(build['exit_code'] == 0 and sha(storage / build['renderer_relative']) == build['renderer_sha256']
            and sha(root / 'scripts/render_receipt_history.cpp') == build['source_cpp_sha256'],
            'existing_vocabulary_only_binary_required')
    for rel, digest in build['library_sha256'].items():
        require(sha(storage / rel) == digest, 'renderer_library_changed')
    for rel, digest in build['header_sha256'].items():
        require(sha(storage / build['source_tree_relative'] / rel) == digest, 'renderer_header_changed')
    target = root / 'reports/P121_checkpoint_inputs.json'
    directory = storage / plan['private_output']
    require(not target.exists() and not directory.exists(), 'preserve_every_P121_attempt')
    directory.mkdir(parents=True)
    result = dict(**scope, source_commit=head, ci=ci, plan_sha256=sha(root / PLAN),
        started_at=datetime.now(timezone.utc).isoformat(), status='incomplete', cells=[], operations=[], errors=[],
        source_audit_sha256={phase: sha(root / f'reports/{phase}_comparison.json') for phase in PHASES},
        measured_additional_model_usage=0, causal_effect_estimate=None)
    result['rows'] = [dict(run_id=r['run_id'], source_phase=r['source_phase'], call_id=c['call_id'],
        display=d, status='not_counted') for r in sources for c in r.get('request_checks', []) for d in DISPLAYS]
    positions = {(r['run_id'], r['call_id'], r['display']): i for i, r in enumerate(result['rows'])}
    require(len(positions) == len(result['rows']) == plan['planned_renderings'], 'every_attempt_pair_required')
    started = time.monotonic()
    deadline = started + plan['max_wall_seconds']
    try:
        for source in sources:
            require(not (storage / plan['stop_marker']).exists(), 'explicit_P121_stop')
            require(time.monotonic() < deadline, 'P121_deadline')
            rid, phase = source['run_id'], source['source_phase']
            if source['record_status'] not in ('evaluated', 'unevaluated'):
                result['cells'].append({'source_phase': phase, **summarize_cell(source, [])})
                continue
            prefix = 'records/context_pilot/' + rid + '/'
            def get(name, default=None):
                rel = prefix + name + '.json'
                return default if rel in plan['absent_private_sources'] else private_read(storage, plan, rel)
            config, usage = get('plan'), get('usage')
            require(len(usage) == source['model_calls']
                    and [u['id'] for u in usage] == [r['call_id'] for r in source['request_checks']],
                    'original_attempt_order_changed')
            inline = config['checkpoint_policy'] == 'inline_checkpoint'
            controls = get('inline_controls' if inline else 'checkpoint_controls')
            require(controls == source['checkpoint_controls'], 'audited_controls_changed')
            conversation = initial_conversation(original, get('public_task'))
            views = prepared_views(conversation, config, usage, get('events'), get('spans'),
                get('budget_observations'), get('inline_history_views' if inline else 'checkpoint_history_views'),
                controls, get('checkpoint_private'),
                {c['id']: get(c['id'] + '/request') for c in usage},
                {c['id']: get(c['id'] + '/response') for c in usage}, phase)
            require(get('conversation_private', conversation.messages()) == conversation.messages(),
                    'final_archive_reconstruction_changed')
            folder = directory / rid
            folder.mkdir()
            cases, metadata = [], []
            for view in views:
                payload = view.pop('payload')
                key = view['call_id'] + '_' + view['display']
                path = folder / (key + '_request_private.json')
                if payload is not None:
                    write_new(path, payload)
                    cases.append(dict(id=key, request_path=str(path)))
                metadata.append(dict(**view, case_id=key, run_id=rid, source_phase=phase,
                    task_id=source['task_id'], request_private_sha256=sha(path) if payload is not None else None))
            if cases:
                operation = dict(run_id=rid, status='starting', renderings=0)
                result['operations'].append(operation)
                render(storage, plan, build, runtime_values[phase], model, folder, cases, deadline, operation)
            rows = collect_renderings(folder, metadata)
            for row in rows:
                result['rows'][positions[rid, row['call_id'], row['display']]] = row
            result['cells'].append({'source_phase': phase, **summarize_cell(source, rows)})
        require(all(r['status'] in ('counted', 'missing_recorded_request') for r in result['rows']),
                'every_planned_input_disposition_required')
        for rel, digest in plan['private_source_sha256'].items():
            require(sha(storage / rel) == digest, 'private_source_changed_during_diagnosis')
        for rel in plan['absent_private_sources']:
            require(not (storage / rel).exists(), 'missing_source_record_was_added')
        result['status'] = 'complete'
    except BaseException as error:
        result['errors'].append(dict(type=type(error).__name__,
            reason=str(error) if type(error) in (ValueError, TimeoutError, InterruptedError) else 'inspect_private_log'))
        raise
    finally:
        completed = {c['run_id'] for c in result['cells']}
        for source in sources:
            if source['run_id'] not in completed:
                result['cells'].append({'source_phase': source['source_phase'],
                    **summarize_cell(source, []), 'diagnosis_status': 'not_completed'})
        result.update(ended_at=datetime.now(timezone.utc).isoformat(), wall_seconds=time.monotonic() - started,
            completed_renderings=sum(r['status'] == 'counted' for r in result['rows']),
            missing_request_slots=sum(r['status'] == 'missing_recorded_request' for r in result['rows']))
        write_new(target, result)
        write_new(directory / 'end.json', dict(status=result['status'], report_sha256=sha(target)))
    print({k: result[k] for k in ('status', 'completed_renderings', 'missing_request_slots', 'wall_seconds')})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('bind', 'count'))
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    (bind if args.operation == 'bind' else inspect)(args.storage_root.resolve(), args.repo_root.resolve())
