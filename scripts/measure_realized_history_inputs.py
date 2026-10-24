"""P112: finite vocabulary-only diagnosis after all P111 conditions are closed."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import time

from inspect_recorded_action_agreement import verify_ci
from measure_receipt_history import private_read, read, render, sha, write_new
from model_provenance import verified_model
from realized_history_diagnostic import prepared_views, collect_renderings, summarize_cell, accounting_decompositions
from receipt_reasoning_history import POLICIES, require
from whole_task_receipt_history import cell_id, run_order

SCOPE = 'configs/P112_realized_history_scope_v01.json'
PLAN = 'configs/P112_realized_history_inputs_v01.json'
PREPARATION = 'reports/P112_diagnostic_preparation_20261025.json'


def fixed_parameters():
    return dict(phase='P112', source_audit='reports/P111_comparison.json',
        source_session='reports/P111_server_session.json', policies=list(POLICIES),
        source_cells=12, known_tasks=4, max_saved_calls_per_cell=80, max_events_per_cell=4000,
        max_renderings=2880, max_wall_seconds=900, max_renderer_seconds=120,
        max_renderer_rss_bytes=2147483648, max_file_bytes=16777216,
        max_total_private_input_bytes=536870912,
        runtime_commit='620d2225cc436ab0b001e3200e590e3b286ef9ab',
        runtime_record='records/context_pilot/P111_pipeline_v01/server_runtime.json',
        effective_template_sha256='c56d1f3ab70881b0e2ed8f51fa6de435d37b84d6c804ebb19a0ec4986fa5ffa9',
        private_output='records/context_pilot/P112_realized_history_inputs_v01',
        stop_marker='.runtime/P112.stop', automatic_retries=0,
        selection='all_P111_attempted_requests_all_three_displays',
        budget_notices='hold_actual_pre_call_state_fixed_for_local_diagnosis',
        missing_requests='retain_all_three_slots_without_fabricating_the_request',
        unattempted_terminal_projections='record_count_but_do_not_charge_as_model_attempts',
        model_generations=0, environment_API_requests=0, saved_generated_program_executions=0,
        evaluations=0, task_databases_read=0, reserved_scenarios_read=0,
        novel_method_claim=False, new_task_quality_measured=False,
        counterfactual_trajectory_or_causal_effect_claim=False,
        P111_rules_changed=False, scope_fixed_before_P111_outcomes_inspected=True)


def check_scope(root):
    scope = read(root/SCOPE)
    require(scope == fixed_parameters(), 'fixed_P112_scope_changed')
    preparation = read(root/PREPARATION)
    require(preparation['P111_outcomes_inspected'] is False, 'pre_outcome_preparation_required')
    for rel, expected in preparation['source_sha256'].items():
        require(sha(root/rel) == expected, 'prepared_source_changed:'+rel)
    return scope, preparation


def closed_sources(storage, root):
    audit = read(root/'reports/P111_comparison.json')
    session = read(root/'reports/P111_server_session.json')
    require(not audit['audit_errors'] and audit['owned_processes_absent']
            and audit['batch_status'] in ('complete', 'stopped')
            and session['status'] == 'stopped' and session['owned_processes_absent']
            and session['audit_source_sha256'] == sha(root/'reports/P111_comparison.json'),
            'all_P111_conditions_must_be_closed_and_audited')
    require([r['run_id'] for r in audit['rows']] == [cell_id(n, p) for n, p in run_order()]
            and len({r['task_id'] for r in audit['rows']}) == 4,
            'all_twelve_P111_slots_required')
    directory = storage/'records/context_pilot/P111_pipeline_v01'
    pipeline, server = read(directory/'status.json'), read(directory/'server_final.json')
    require(pipeline['status'] in ('complete', 'stopped') and pipeline['server_stopped']
            and server['status'] == 'stopped'
            and server['supervisor_pid'] == pipeline['server_supervisor_pid']
            and sha(directory/'status.json') == audit['pipeline_status_sha256']
            and sha(directory/'server_final.json') == audit['server_final_sha256'],
            'owned_P111_closure_changed')
    for key in ('pid', 'supervisor_pid'):
        process = subprocess.run(['ps', '-p', str(server[key]), '-o', 'command='],
                                 capture_output=True, text=True, timeout=10)
        require(process.returncode == 1 and not process.stdout.strip(), 'owned_P111_process_still_exists')
    return audit, session


def bind(storage, root):
    scope, preparation = check_scope(root)
    require(not (root/PLAN).exists(), 'preserve_original_P112_binding')
    head, ci = verify_ci(root)
    audit, _ = closed_sources(storage, root)
    sources = dict(preparation['source_sha256'])
    for name in ('configs/P110_receipt_history_inputs_v01.json',
                 'configs/P111_whole_task_receipt_history_v01.json'):
        for rel, expected in read(root/name)['source_sha256'].items():
            require(sha(root/rel) == expected, 'fixed_predecessor_source_changed:'+rel)
            if rel in sources:
                require(sources[rel] == expected, 'inconsistent_source_binding')
            sources[rel] = expected
        sources[name] = sha(root/name)
    for rel in (PREPARATION, 'reports/P111_comparison.json', 'reports/P111_server_session.json',
                'reports/P110_renderer_build.json'):
        sources[rel] = sha(root/rel)
    private = {}
    missing = []
    def include(rel, expected=None):
        path = storage/rel
        path.resolve().relative_to(storage.resolve())
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= scope['max_file_bytes'],
                'bounded_regular_private_input_required')
        value = sha(path)
        require(expected is None or value == expected, 'closed_audit_input_changed:'+rel)
        private[rel] = value
    for name in ('status.json', 'server_final.json', 'server_runtime.json'):
        include('records/context_pilot/P111_pipeline_v01/'+name)
    attempts = 0
    for row in audit['rows']:
        if row['record_status'] not in ('evaluated', 'unevaluated'):
            continue
        prefix = 'records/context_pilot/'+row['run_id']+'/'
        require(len(row['request_checks']) == row['model_calls'] <= 80, 'every_attempt_required')
        attempts += row['model_calls']
        for name in ('plan', 'public_task', 'summary', 'usage', 'events', 'spans'):
            expected = row.get(name+'_sha256')
            include(prefix+name+'.json', expected)
        for name, field in (('reasoning_history_views', 'history_views_sha256'),
                            ('reasoning_execution_records', 'execution_records_sha256'),
                            ('budget_observations', None)):
            path = storage/(prefix+name+'.json')
            if path.exists():
                include(prefix+name+'.json', row.get(field) if field else None)
            else:
                require(not row.get(field), 'bound_control_record_missing')
                missing.append(prefix+name+'.json')
        for call in row['request_checks']:
            for name in ('request', 'response'):
                rel = prefix+call['call_id']+'/'+name+'.json'
                expected = call[name+'_sha256']
                if expected is None:
                    require(not (storage/rel).exists(), 'missing_source_record_was_added')
                    missing.append(rel)
                else:
                    include(rel, expected)
    require(attempts*3 <= scope['max_renderings'], 'finite_rendering_cap')
    require(sum((storage/rel).stat().st_size for rel in private)
            <= scope['max_total_private_input_bytes'], 'finite_private_input_bytes')
    value = dict(**scope, created_at=datetime.now(timezone.utc).isoformat(),
        preparation_head=head, preparation_CI=ci, source_sha256=sources,
        private_source_sha256=private, absent_private_sources=missing,
        run_ids=[r['run_id'] for r in audit['rows']], actual_model_attempts=attempts,
        planned_renderings=attempts*3)
    write_new(root/PLAN, value)
    print({'bound_private_files': len(private), 'absent_records': len(missing),
           'source_files': len(sources), 'planned_renderings': attempts*3})


def inspect(storage, root):
    scope, _ = check_scope(root)
    plan = read(root/PLAN)
    require(all(type(plan.get(k)) is type(v) and plan[k] == v for k, v in scope.items()),
            'fixed_P112_plan_changed')
    for rel, expected in plan['source_sha256'].items():
        require(sha(root/rel) == expected, 'bound_source_changed:'+rel)
    head, ci = verify_ci(root)
    audit, _ = closed_sources(storage, root)
    require([r['run_id'] for r in audit['rows']] == plan['run_ids'], 'fixed_closed_cohort_changed')
    for rel in plan['absent_private_sources']:
        require(not (storage/rel).exists(), 'missing_source_record_was_added')
    require(sum((storage/rel).stat().st_size for rel in plan['private_source_sha256'])
            <= plan['max_total_private_input_bytes'], 'total_private_input_bound')
    runtime = private_read(storage, plan, plan['runtime_record'])
    original = read(root/'configs/P29_stateful_code_v01.json')
    selection, _, model = verified_model(original['model_selection'], root=storage)
    require(runtime['runtime']['commit'] == plan['runtime_commit']
            and runtime['model_revision'] == selection['revision']
            and Path(runtime['command'][runtime['command'].index('--model')+1]) == model,
            'fixed_source_model_runtime_required')
    build = read(root/'reports/P110_renderer_build.json')
    require(build['exit_code'] == 0 and sha(storage/build['renderer_relative']) == build['renderer_sha256']
            and sha(root/'scripts/render_receipt_history.cpp') == build['source_cpp_sha256'],
            'existing_vocabulary_only_binary_required')
    for rel, expected in build['library_sha256'].items():
        require(sha(storage/rel) == expected, 'renderer_library_changed')
    for rel, expected in build['header_sha256'].items():
        require(sha(storage/build['source_tree_relative']/rel) == expected, 'renderer_header_changed')
    target = root/'reports/P112_realized_history_inputs.json'
    directory = storage/plan['private_output']
    require(not target.exists() and not directory.exists(), 'preserve_every_P112_attempt')
    directory.mkdir(parents=True)
    result = dict(**scope, source_commit=head, ci=ci, plan_sha256=sha(root/PLAN),
        started_at=datetime.now(timezone.utc).isoformat(), status='incomplete', rows=[], cells=[],
        operations=[], errors=[], source_audit_sha256=sha(root/plan['source_audit']),
        measured_additional_model_usage=0, causal_effect_estimate=None)
    result['rows'] = [dict(run_id=r['run_id'], call_id=c['call_id'], policy=p, status='not_counted')
        for r in audit['rows'] for c in r.get('request_checks', []) for p in POLICIES]
    positions = {(r['run_id'], r['call_id'], r['policy']): i for i, r in enumerate(result['rows'])}
    require(len(positions) == len(result['rows']) == plan['planned_renderings'] <= plan['max_renderings'],
            'every_original_attempt_triplet_required')
    started = time.monotonic()
    deadline = started+plan['max_wall_seconds']
    try:
        for source in audit['rows']:
            require(not (storage/plan['stop_marker']).exists(), 'explicit_P112_stop')
            require(time.monotonic() < deadline, 'P112_deadline')
            rid = source['run_id']
            if source['record_status'] not in ('evaluated', 'unevaluated'):
                result['cells'].append(summarize_cell(source, []))
                continue
            prefix = 'records/context_pilot/'+rid+'/'
            def get(name, default=None):
                rel = prefix+name+'.json'
                if rel in plan['absent_private_sources']:
                    return default
                return private_read(storage, plan, rel)
            values = {n: get(n) for n in ('plan', 'public_task', 'usage', 'events', 'spans')}
            requests = {c['call_id']: get(c['call_id']+'/request') for c in source['request_checks']}
            responses = {c['call_id']: get(c['call_id']+'/response') for c in source['request_checks']}
            views, evidence = prepared_views(original, values['public_task'], values['plan'],
                values['usage'], values['events'], values['spans'], get('budget_observations', []),
                get('reasoning_execution_records', []), get('reasoning_history_views', []), requests, responses)
            folder = directory/rid
            folder.mkdir()
            cases = []
            metadata = []
            for view in views:
                payload = view.pop('payload')
                key = view['call_id']+'_'+view['policy']
                path = folder/(key+'_request_private.json')
                if payload is not None:
                    write_new(path, payload)
                    cases.append(dict(id=key, request_path=str(path)))
                metadata.append(dict(**view, case_id=key, run_id=rid, task_id=source['task_id'],
                    request_private_sha256=sha(path) if payload is not None else None))
            if cases:
                operation = dict(run_id=rid, status='starting', renderings=0)
                result['operations'].append(operation)
                render(storage, plan, build, runtime, model, folder, cases, deadline, operation)
            rows = collect_renderings(folder, metadata)
            for row in rows:
                result['rows'][positions[(rid, row['call_id'], row['policy'])]] = row
            cell = summarize_cell(source, rows)
            cell.update(prior_turn_evidence=evidence,
                terminal_unattempted_projections=len(get('reasoning_history_views', []))-len(values['usage']))
            result['cells'].append(cell)
        require(all(r['status'] in ('counted', 'missing_recorded_request') for r in result['rows']),
                'every_planned_slot_disposition_required')
        for rel, expected in plan['private_source_sha256'].items():
            require(sha(storage/rel) == expected, 'private_source_changed_during_diagnosis')
        for rel in plan['absent_private_sources']:
            require(not (storage/rel).exists(), 'missing_source_record_was_added')
        result['accounting_decompositions'] = accounting_decompositions(result['cells'])
        result['status'] = 'complete'
    except BaseException as error:
        result['errors'].append(dict(type=type(error).__name__,
            reason=str(error) if type(error) in (ValueError, TimeoutError, InterruptedError) else 'inspect_private_log'))
        raise
    finally:
        completed = {c['run_id'] for c in result['cells']}
        for source in audit['rows']:
            if source['run_id'] not in completed:
                cell = summarize_cell(source, [])
                cell['diagnosis_status'] = 'not_completed'
                result['cells'].append(cell)
        result.update(ended_at=datetime.now(timezone.utc).isoformat(), wall_seconds=time.monotonic()-started,
            completed_renderings=sum(r['status'] == 'counted' for r in result['rows']),
            missing_request_slots=sum(r['status'] == 'missing_recorded_request' for r in result['rows']))
        write_new(target, result)
        write_new(directory/'end.json', dict(status=result['status'], report_sha256=sha(target)))
    print({k: result[k] for k in ('status', 'completed_renderings', 'missing_request_slots', 'wall_seconds')})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('bind', 'count'))
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    (bind if args.operation == 'bind' else inspect)(args.storage_root.resolve(), args.repo_root.resolve())
