"""Finite P142 known-four-task threshold recursive/object-delta comparison."""
import argparse
import datetime as dt
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from api_error_comparison import disposition, task_snapshot
from budget_observation import notification
from whole_task_threshold_object_p142 import MODES as POLICIES
from whole_task_threshold_object_p142 import (ERROR_POLICY, cell_id, config_for, run_order, validate_plan, make_notification, initial_conversation)
from budget_signal import digest
from inspect_appworld_api_schemas import load_public_tools
from inspect_input_exposure import check_resume, frozen_sources
from tool_choice_local_llama import count_input, payload_for
from fixed_budget_local_llama import count_input as count_summary_input, payload_for as summary_payload
from threshold_object_server_identity_p142 import live_identity, wait_idle
from public_display import CODE_TOOLS
from residual_output_budget import admission
from run_whole_task_threshold_object_cell_p142 import run_cell
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

PLAN = 'configs/P142_threshold_object_v01.json'
PREFLIGHT = 'reports/P142_initial_checks.json'
ACTIVATION = 'reports/P142_activation_v01.json'


def sources(storage, root):
    if root.resolve() != ROOT.resolve():
        raise ValueError('executing_P142_repository_must_match')
    plan = read(root / PLAN); validate_plan(plan)
    for rel, expected in plan['source_sha256'].items():
        if sha(root / rel) != expected: raise ValueError('fixed_source_changed:' + rel)
    from run_whole_task_tool_choice import sources as original_sources
    previous, original, tools, prepared = original_sources(storage, root)
    if (len(prepared) != 4 or plan['known_tasks'] != previous['known_tasks']
            or plan['source_runs'] != [item['source_run'] for item in prepared]
            or any(plan[k] != previous[k] for k in ('source_plan','world_seed'))):
        raise ValueError('fixed_all_four_known_tasks_required')
    if predecessor_closed(storage, root) != plan['predecessor_closure']:
        raise ValueError('frozen_P141_closure_changed')
    return plan, original, tools, prepared


def predecessor_closed(storage, root):
    folder = storage / 'records/context_pilot/P141_pipeline_v01'
    pipeline = read(folder / 'status.json'); final = read(folder / 'server_final.json')
    audit = read(root / 'reports/P141_comparison.json')
    session = read(root / 'reports/P141_server_session.json')
    from whole_task_object_timing_p141 import run_order as previous_order, cell_id as previous_id
    expected_ids = [previous_id(*slot) for slot in previous_order()]
    rows = audit.get('rows', [])
    if (pipeline['status'] not in ('complete','stopped') or pipeline.get('server_stopped') is not True
            or final['status'] != 'stopped' or final['supervisor_pid'] != pipeline['server_supervisor_pid']
            or audit.get('phase') != 'P141' or len(audit.get('rows', [])) != 3
            or session.get('phase') != 'P141'
            or [r.get('run_id') for r in rows] != expected_ids
            or any(r.get('record_status') != 'evaluated' or type(r.get('success')) is not bool for r in rows)
            or type(audit.get('audit_errors')) is not list or audit['audit_errors']
            or audit.get('owned_processes_absent') is not True
            or session['status'] != 'stopped' or session.get('owned_processes_absent') is not True
            or audit['pipeline_status_sha256'] != sha(folder / 'status.json')
            or audit['server_final_sha256'] != sha(folder / 'server_final.json')
            or session['audit_source_sha256'] != sha(root / 'reports/P141_comparison.json')):
        raise ValueError('closed_owned_audited_P141_required')
    for key in ('pid','supervisor_pid'):
        if type(final.get(key)) is not int or final[key] <= 0:
            raise ValueError('positive_previous_owned_pid_required')
        process = subprocess.run(['ps','-p',str(final[key]),'-o','command='],capture_output=True,text=True,timeout=10)
        if process.returncode != 1 or process.stdout.strip(): raise ValueError('previous_owned_process_present')
    return dict(audit_sha256=sha(root / 'reports/P141_comparison.json'),
                session_sha256=sha(root / 'reports/P141_server_session.json'),
                pipeline_status_sha256=sha(folder / 'status.json'),server_final_sha256=sha(folder / 'server_final.json'))


def frozen_hashes(root):
    paths = list((root / 'scripts').glob('*.py')) + list((root / 'tests').glob('test_*.py'))
    plan = read(root / PLAN)
    paths += [root / name for name in (PLAN, 'docs/experiments/P142_threshold_object_confirmation_20261028.md',
                                       *plan['source_sha256'])]
    return {str(p.relative_to(root)): sha(p) for p in sorted(set(paths))}


def preflight(storage, root):
    folder = storage / 'records/context_pilot/P142_preflight_v01'
    target = root / PREFLIGHT
    if folder.exists() or target.exists():
        raise FileExistsError('preserve_all_P142_preflight_attempts')
    if (storage / '.runtime/P142.stop').exists():
        raise InterruptedError('explicit_P142_stop_before_preflight')
    check_resume(storage)
    plan, original, _, prepared = sources(storage, root)
    hashes = frozen_hashes(root)
    commit = frozen_sources(root, tuple(hashes))
    identity, end = live_identity(storage, original, 480)
    folder.mkdir(parents=True)
    started = time.monotonic()
    result = {'phase': 'P142_preflight', 'status': 'running', 'rows': [],
        'git_commit': commit, 'source_hashes': hashes, 'model_identity': identity,
        'server_lease_end': end, 'research_resume': check_resume(storage),
        'input_count_requests': 0, 'summary_input_count_requests': 0, 'failed_input_count_requests': 0,
        'representation_actor_input_count_requests': 0, 'representation_transport': [],
        'model_generations': 0, 'environment_api_requests': 0, 'evaluator_calls': 0,
        'reserved_scenarios_read': 0, 'all_eight_inputs_checked': False}
    try:
        for item in prepared:
            row = {'source_run': item['source_run'], 'task_id': item['task_id'], 'conditions': {}}
            result['rows'].append(row)
            for arm in POLICIES:
                if (storage / '.runtime/P142.stop').exists():
                    raise InterruptedError('explicit_P142_stop')
                remaining = 420 - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('P142_preflight_deadline')
                base, formatting = initial_conversation(original, item['public_task']).for_model()
                if formatting != {'text_fallback_turns': 0, 'paged_spans': 0}:
                    raise ValueError('unexpected_initial_formatting')
                config = config_for(original, plan, item['task_id'], arm)
                state = task_snapshot(config, [], 0, 0)
                supplied, visible = make_notification(base, state, arm, wall_limit=plan["max_wall_seconds"])
                path = folder / (item['source_run'] + '_' + arm + '_private.json')
                write_json(path, supplied)
                entry = {'base_messages_sha256': digest(base), 'model_messages_sha256': digest(supplied),
                         'input_sha256': sha(path), 'measured_state': state, 'visible_state': visible}
                row['conditions'][arm] = entry
                cfg = {**config['model'], 'temperature': original['agent_temperature'],
                       'seed': plan['model_seed'], 'num_predict': original['max_output_tokens'],
                       'cache_prompt': False}
                request_path = folder / (item['source_run'] + '_' + arm + '_request_private.json')
                write_json(request_path, payload_for(cfg, supplied, CODE_TOOLS))
                entry['count_request_sha256'] = sha(request_path)
                entry['reasoning_budget_tokens'] = cfg['reasoning_budget_tokens']
                entry['tool_choice'] = cfg['tool_choice']
                result['input_count_requests'] += 1
                try:
                    entry.update(count_input(cfg, supplied, CODE_TOOLS, timeout=min(30, remaining)))
                except Exception:
                    result['failed_input_count_requests'] += 1
                    raise
                entry['admission'] = admission(plan['max_total_tokens'], entry['input_tokens'],
                                               cfg['num_predict'], cfg['num_ctx'], 'residual')
                if not entry['admission']['admitted']:
                    raise ValueError('initial_request_does_not_fit')
                write_json(folder / 'status.json', result)
            entries = [row['conditions'][arm] for arm in POLICIES]
            if any(e['model_messages_sha256'] != entries[0]['model_messages_sha256']
                   or e['base_messages_sha256'] != entries[0]['base_messages_sha256']
                   or e['visible_state'] != entries[0]['visible_state']
                   or e['input_tokens'] != entries[0]['input_tokens'] for e in entries):
                raise ValueError('both_initial_inputs_must_match')
            requests = [read(folder / (item['source_run'] + '_' + arm + '_request_private.json')) for arm in POLICIES]
            if any(request != requests[0] for request in requests) or requests[0]['tool_choice'] != 'auto':
                raise ValueError('same_initial_request_and_auto_tool_choice_required')
            if 'wall_seconds_at_snapshot' in entries[0]['visible_state']['remaining']:
                raise ValueError('hidden_time_was_exposed')
        # Four focus templates and two installed actor views; no generation.
        from checkpoint_threshold_object_preflight_p142 import synthetic_transport_cases
        for case in synthetic_transport_cases():
            if (storage / '.runtime/P142.stop').exists():
                raise InterruptedError('explicit_P142_stop')
            remaining = 420 - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError('P142_preflight_deadline')
            actor = case['role'] == 'agent'
            supplied = (notification(case['messages'], task_snapshot(config, [], 0, 0),
                                     'not_exposed')[0] if actor else case['messages'])
            cfg = {**config['model'], 'temperature': config['agent_temperature'] if actor
                   else config['draft_temperature'], 'seed': plan['model_seed'],
                   'num_predict': config['max_output_tokens'], 'cache_prompt': not actor}
            transport = payload_for if actor else summary_payload
            counter = count_input if actor else count_summary_input
            path = folder / (case['name'] + '_request_private.json')
            write_json(path, transport(cfg, supplied, case['tools']))
            entry = {'name': case['name'], 'role': case['role'], 'request_sha256': sha(path),
                     'synthetic_only': True}
            result['representation_transport'].append(entry)
            result['representation_actor_input_count_requests' if actor else 'summary_input_count_requests'] += 1
            try:
                entry.update(counter(cfg, supplied, case['tools'], timeout=min(30, remaining)))
            except Exception:
                result['failed_input_count_requests'] += 1
                raise
        if time.monotonic() - started > 420:
            raise TimeoutError('P142_preflight_deadline')
        result.update(status='complete', all_eight_inputs_checked=True)
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__)
        (folder / 'error_private.txt').write_text(str(error))
        raise
    finally:
        result['wall_seconds'] = time.monotonic() - started
        write_json(folder / 'status.json', result)
        write_json(target, result)
    return result


def validate_preflight(storage, root, pre, plan, original, prepared):
    """Bind saved native counts to the exact independently reconstructed payloads."""
    fixed = dict(phase='P142_preflight', status='complete', all_eight_inputs_checked=True,
        input_count_requests=8, summary_input_count_requests=4, representation_actor_input_count_requests=2,
        failed_input_count_requests=0, model_generations=0, environment_api_requests=0,
        evaluator_calls=0, reserved_scenarios_read=0)
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    if (any(type(pre.get(k)) is not type(v) or pre[k] != v for k,v in fixed.items())
            or pre.get('git_commit') != head
            or type(pre.get('wall_seconds')) not in (int,float)
            or not math.isfinite(pre['wall_seconds']) or not 0 <= pre['wall_seconds'] <= 420
            or type(pre.get('representation_transport')) is not list or len(pre['representation_transport']) != 6
            or pre['source_hashes'] != frozen_hashes(root)
            or pre.get('research_resume') != check_resume(storage)
            or len(pre.get('rows', [])) != 4 or len(prepared) != 4):
        raise ValueError('P142_preparation_incomplete_or_stale')
    folder = storage / 'records/context_pilot/P142_preflight_v01'
    if read(folder / 'status.json') != pre:
        raise ValueError('saved_preflight_report_and_status_differ')
    for item, row in zip(prepared, pre['rows'], strict=True):
        if (row['task_id'] != item['task_id'] or row['source_run'] != item['source_run']
                or set(row['conditions']) != set(POLICIES)):
            raise ValueError('all_eight_preflight_identities_required')
        payloads, counts = [], []
        for mode in POLICIES:
            config = config_for(original, plan, item['task_id'], mode)
            base, _ = initial_conversation(original, item['public_task']).for_model()
            state = task_snapshot(config, [], 0, 0)
            supplied, visible = make_notification(base, state, mode, wall_limit=plan['max_wall_seconds'])
            cfg = {**config['model'], 'temperature': original['agent_temperature'],
                'seed': plan['model_seed'], 'num_predict': original['max_output_tokens'], 'cache_prompt': False}
            payload = payload_for(cfg, supplied, CODE_TOOLS)
            stem = item['source_run'] + '_' + mode
            message_path, request_path = folder/(stem+'_private.json'), folder/(stem+'_request_private.json')
            entry = row['conditions'][mode]
            if (type(entry.get('input_tokens')) is not int or entry['input_tokens'] <= 0
                    or entry.get('base_messages_sha256') != digest(base)
                    or entry.get('model_messages_sha256') != digest(supplied)
                    or digest(entry.get('measured_state')) != digest(state)
                    or digest(entry.get('visible_state')) != digest(visible)
                    or entry.get('input_sha256') != sha(message_path) or read(message_path) != supplied
                    or entry.get('count_request_sha256') != sha(request_path) or read(request_path) != payload
                    or entry.get('reasoning_budget_tokens') != -1 or entry.get('tool_choice') != 'auto'):
                raise ValueError('preflight_count_or_payload_changed')
            expected = admission(plan['max_total_tokens'], entry['input_tokens'],
                                 cfg['num_predict'], cfg['num_ctx'], 'residual')
            if entry['admission'] != expected or not expected['admitted']:
                raise ValueError('preflight_admission_changed')
            payloads.append(payload); counts.append(entry['input_tokens'])
        if any(p != payloads[0] for p in payloads) or len(set(counts)) != 1:
            raise ValueError('two_arm_initial_input_mismatch')
    from checkpoint_threshold_object_preflight_p142 import synthetic_transport_cases
    cases = synthetic_transport_cases()
    if len(cases) != 6 or sum(c['role']=='focus' for c in cases) != 4:
        raise ValueError('six_fixed_representation_templates_required')
    for case, entry in zip(cases, pre['representation_transport'], strict=True):
        actor = case['role'] == 'agent'
        supplied = (notification(case['messages'], task_snapshot(config, [], 0, 0),
                                 'not_exposed')[0] if actor else case['messages'])
        cfg = {**config['model'], 'temperature': config['agent_temperature'] if actor else config['draft_temperature'],
            'seed': plan['model_seed'], 'num_predict': config['max_output_tokens'], 'cache_prompt': not actor}
        transport = payload_for if actor else summary_payload
        path = folder/(case['name']+'_request_private.json')
        if (entry['name'] != case['name'] or entry['role'] != case['role']
                or entry['synthetic_only'] is not True or entry['request_sha256'] != sha(path)
                or read(path) != transport(cfg, supplied, case['tools'])
                or type(entry['input_tokens']) is not int or entry['input_tokens'] <= 0):
            raise ValueError('fixed_representation_transport_changed')


def activate(storage, root):
    if (root / ACTIVATION).exists():
        raise FileExistsError('preserve_P142_activation')
    if (storage / '.runtime/P142.stop').exists():
        raise InterruptedError('explicit_P142_stop_before_activation')
    plan, original, _, prepared = sources(storage, root)
    pre = read(root / PREFLIGHT)
    validate_preflight(storage, root, pre, plan, original, prepared)
    write_json(root / ACTIVATION, {'phase': 'P142', 'source_hashes': pre['source_hashes'],
        'git_commit': pre['git_commit'],
        'preflight_sha256': sha(root / PREFLIGHT), 'research_resume': check_resume(storage),
        'all_eight_conditions_frozen_before_generation': True,
        'activated_at': dt.datetime.now(dt.timezone.utc).isoformat()})


def validate_activation(storage, root, freeze, pre):
    if (freeze.get('phase') != 'P142'
            or freeze.get('all_eight_conditions_frozen_before_generation') is not True
            or freeze.get('git_commit') != pre['git_commit']
            or freeze.get('source_hashes') != frozen_hashes(root)
            or freeze.get('preflight_sha256') != sha(root / PREFLIGHT)
            or freeze.get('research_resume') != check_resume(storage)):
        raise ValueError('frozen_P142_sources_or_resumption_changed')


def bounded_cell(storage, root, plan, number, arm, rid, folder):
    if rid != cell_id(number, arm):
        raise ValueError('fixed_P142_worker_identity_required')
    absolute_end = dt.datetime.fromisoformat(plan['deadline_jst']).timestamp()
    worker_budget = plan['max_setup_seconds']+plan['max_wall_seconds']+plan['max_cleanup_seconds']
    if time.time()+worker_budget+20 > absolute_end:
        raise TimeoutError('full_P142_worker_does_not_fit_before_absolute_deadline')
    command = [sys.executable, str(root / 'scripts/run_whole_task_threshold_object_p142.py'),
               '--storage-root', str(storage), '--repo-root', str(root),
               '--cell', str(number), '--arm', arm]
    exit_path = folder / (rid + '_worker_exit.json')
    if exit_path.exists() or (folder / (rid + '_worker.log')).exists():
        raise FileExistsError('preserve_P142_worker_exit_record')
    record = dict(run_id=rid, status='starting', returncode=None, pid=None,
        wait_timeout_seconds=worker_budget,
        timed_out=False, forced_group_kill=False, started_at=dt.datetime.now(dt.timezone.utc).isoformat())
    write_json(exit_path, record)
    with (folder / (rid + '_worker.log')).open('w') as log:
        child = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
        record.update(pid=child.pid, status='running'); write_json(exit_path, record)
        try:
            code = child.wait(timeout=min(record['wait_timeout_seconds'],
                                          max(0.001, absolute_end-time.time()-20)))
            record['returncode'] = code
            if code:
                raise RuntimeError('P142_cell_worker_failed_no_retry')
        except BaseException as error:
            record.update(error_type=type(error).__name__, timed_out=isinstance(error,subprocess.TimeoutExpired))
            raise
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=min(15, max(0.001, absolute_end-time.time())))
                except subprocess.TimeoutExpired:
                    record['forced_group_kill'] = True
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=min(5, max(0.001, absolute_end-time.time())))
            record.update(status='exited', returncode=child.poll(),
                ended_at=dt.datetime.now(dt.timezone.utc).isoformat())
            write_json(exit_path, record)
    return read(storage / 'records/context_pilot' / rid / 'summary.json')


def run(storage, root):
    if (storage / '.runtime/P142.stop').exists():
        raise InterruptedError('explicit_P142_stop_before_batch')
    plan, original, _, prepared = sources(storage, root)
    freeze, pre = read(root / ACTIVATION), read(root / PREFLIGHT)
    validate_preflight(storage, root, pre, plan, original, prepared)
    validate_activation(storage, root, freeze, pre)
    max_cell = sum(plan[key] for key in ('max_setup_seconds', 'max_wall_seconds',
        'max_cleanup_seconds', 'max_idle_wait_seconds', 'max_evaluation_seconds'))
    identity, end = live_identity(storage, original, plan['max_cells'] * max_cell)
    if identity != pre['model_identity']:
        raise ValueError('prepared_model_identity_changed')
    folder = storage / 'records/context_pilot' / plan['batch_id']
    folder.mkdir(exist_ok=False)
    for name, value in (('plan', plan), ('activation', freeze), ('preflight', pre)):
        write_json(folder / (name + '.json'), value)
    state = {'phase': 'P142', 'status': 'running', 'rows': [], 'completed': [], 'active': None,
        'planned': [cell_id(n, arm) for n, arm in run_order()], 'model_identity': identity,
        'server_lease_end': end, 'reserved_scenarios_read': 0,
        'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()}
    def save():
        state['updated_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        write_json(folder / 'status.json', state)
    try:
        save()
        for number, arm in run_order():
            if (storage / '.runtime/P142.stop').exists():
                raise InterruptedError('explicit_P142_stop')
            absolute_end = dt.datetime.fromisoformat(plan['deadline_jst']).timestamp()
            if time.time()+max_cell > absolute_end:
                raise TimeoutError('full_P142_cell_does_not_fit_before_absolute_deadline')
            current, _ = live_identity(storage, original, max_cell)
            if current != identity:
                raise ValueError('same_idle_inference_runtime_required')
            rid = cell_id(number, arm)
            state['active'] = rid; save()
            result = bounded_cell(storage, root, plan, number, arm, rid, folder)
            row = {k: result[k] for k in ('run_id', 'task_id', 'arm', 'checkpoint_representation_mode', 'time_visibility', 'checkpoint_policy', 'reasoning_budget_tokens', 'stop_reason', 'model_calls',
                'known_total_tokens', 'unknown_usage_calls', 'api_requests', 'wall_seconds',
                'full_wall_seconds', 'cleanup_confirmed')}
            row['disposition'] = disposition(result)
            state['rows'].append(row); save()
            if row['disposition'] == 'stop_batch':
                raise ValueError('P142_initialization_API_or_runtime_failure')
            row['idle_recovery_started_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
            save()
            row['idle_recovery'] = wait_idle(storage, original, identity, plan['max_idle_wait_seconds'])
            save()
            if (storage / '.runtime/P142.stop').exists():
                raise InterruptedError('explicit_P142_stop')
            row['evaluation_started_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
            save()
            evaluation_started = time.monotonic()
            try:
                evaluated = subprocess.run([str(storage / '.runtime/appworld/venv/bin/python'),
                    str(root / 'scripts/evaluate_context_trial.py'), '--appworld-root',
                    str(storage / '.runtime/appworld/r18_probe_01'), '--trial',
                    str(storage / 'records/context_pilot' / rid)], capture_output=True, text=True,
                    timeout=plan['max_evaluation_seconds'])
            finally:
                row['evaluation_wall_seconds'] = time.monotonic() - evaluation_started
                save()
            (folder / (rid + '_evaluation.log')).write_text(evaluated.stdout + evaluated.stderr)
            if evaluated.returncode:
                raise ValueError('independent_P142_evaluation_failed')
            row['success'] = read(storage / 'records/context_pilot' / rid / 'evaluation.json')['official_success']
            state['completed'].append(rid); save()
            print({k: row[k] for k in ('run_id', 'model_calls', 'known_total_tokens', 'unknown_usage_calls')}, flush=True)
        state.update(status='complete', active=None,
                     known_usage_complete=all(r['unknown_usage_calls'] == 0 for r in state['rows']))
    except Exception as error:
        state.update(status='stopped', error_type=type(error).__name__)
        (folder / 'error_private.txt').write_text(str(error))
    finally:
        state['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        state['not_run'] = [rid for rid in state['planned']
            if rid not in {r['run_id'] for r in state['rows']} and rid != state['active']]
        state['unevaluated'] = [r['run_id'] for r in state['rows'] if r['run_id'] not in state['completed']]
        save()
    return 0 if state['status'] == 'complete' else 1


def interrupt(*_):
    raise InterruptedError('bounded_P142_execution_interrupted')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--preflight', action='store_true')
    modes.add_argument('--activate', action='store_true')
    modes.add_argument('--cell', type=int, choices=(1,2,3,4))
    parser.add_argument('--arm', choices=POLICIES)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, interrupt); signal.signal(signal.SIGINT, interrupt)
    if args.cell is not None:
        if args.arm is None:
            parser.error('--cell requires --arm')
        plan, original, tools, prepared = sources(args.storage_root, args.repo_root)
        # Every worker requires the already frozen eight-cell activation.
        frozen = read(args.repo_root / ACTIVATION)
        pre = read(args.repo_root / PREFLIGHT)
        validate_preflight(args.storage_root, args.repo_root, pre, plan, original, prepared)
        validate_activation(args.storage_root, args.repo_root, frozen, pre)
        max_cell = sum(plan[k] for k in ('max_setup_seconds', 'max_wall_seconds',
            'max_cleanup_seconds', 'max_idle_wait_seconds', 'max_evaluation_seconds'))
        if live_identity(args.storage_root, original, max_cell)[0] != pre['model_identity']:
            raise ValueError('P142_worker_model_identity_changed')
        run_cell(args.storage_root, args.repo_root, plan, original, tools,
                 prepared[args.cell - 1], ERROR_POLICY, cell_id(args.cell, args.arm),
                 checkpoint_representation_mode=args.arm)
    elif args.preflight:
        result = preflight(args.storage_root, args.repo_root)
        print({k: result[k] for k in ('status', 'input_count_requests', 'failed_input_count_requests')})
    elif args.activate:
        activate(args.storage_root, args.repo_root)
    else:
        raise SystemExit(run(args.storage_root, args.repo_root))
