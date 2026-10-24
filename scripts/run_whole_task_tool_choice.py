"""Finite P99 from-start comparison of ordinary tool-choice settings."""
import argparse
import datetime as dt
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from api_error_comparison import disposition, task_snapshot
from whole_task_tool_choice import POLICIES
from whole_task_tool_choice import (ERROR_POLICY, cell_id, config_for, run_order, validate_plan, make_notification, initial_conversation)
from budget_signal import digest
from inspect_appworld_api_schemas import load_public_tools
from inspect_input_exposure import check_resume, frozen_sources
from tool_choice_local_llama import count_input, payload_for
from probe_inference_cache import live_identity
from public_display import CODE_TOOLS
from residual_output_budget import admission
from run_whole_task_tool_choice_cell import run_cell
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from run_reasoning_history_comparison import wait_idle

PLAN = 'configs/P99_whole_task_tool_choice_v01.json'
PREFLIGHT = 'reports/P99_initial_checks.json'
ACTIVATION = 'reports/P99_activation_v01.json'


def sources(storage, root):
    plan = read(root / PLAN)
    validate_plan(plan)
    for name, expected in plan['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('fixed_source_changed:' + name)
    from run_late_clock_comparison import sources as original_sources
    previous, original, tools, prepared = original_sources(storage, root)
    if (plan['known_tasks'] != previous['known_tasks'] or plan['source_runs'] != previous['source_runs']
            or plan['source_plan'] != previous['source_plan'] or plan['world_seed'] != previous['world_seed']):
        raise ValueError('same_four_previously_known_public_tasks_required')
    prior = read(root / plan['required_closed_diagnostic'])
    if (prior['status'] != 'complete' or len(prior['rows']) != 24
            or prior['original_model_attempts'] != 426 or prior['original_unknown_usage_calls'] != 4
            or prior['original_API_requests'] != 1156):
        raise ValueError('complete_closed_P98_diagnostic_required')
    predecessor_closed(storage, root)
    return plan, original, tools, prepared


def predecessor_closed(storage, root):
    audit = read(root / 'reports/P97_comparison.json')
    session = read(root / 'reports/P97_server_session.json')
    pipeline = read(storage / 'records/context_pilot/P97_pipeline_v01/status.json')
    final = read(storage / 'records/context_pilot/P97_pipeline_v01/server_final.json')
    if (audit['audit_errors'] or len(audit['rows']) != 12 or not audit['owned_processes_absent']
            or session['status'] != 'stopped' or not session['owned_processes_absent']
            or session['audit_source_sha256'] != sha(root / 'reports/P97_comparison.json')
            or pipeline['status'] not in ('complete', 'stopped') or not pipeline.get('server_stopped')
            or pipeline['git_commit'] != '46dcfd3f3d2b79214b8601618f40ee6083e67452'
            or final['status'] != 'stopped'
            or final['supervisor_pid'] != pipeline['server_supervisor_pid']
            or sha(storage / 'records/context_pilot/P97_pipeline_v01/server_final.json') != audit['server_final_sha256']
            or sha(storage / 'records/context_pilot/P97_pipeline_v01/status.json') != audit['pipeline_status_sha256']):
        raise ValueError('closed_owned_audited_P97_required_before_P99')
    for key in ('pid', 'supervisor_pid'):
        process = subprocess.run(['ps', '-p', str(final[key]), '-o', 'command='],
            capture_output=True, text=True, timeout=10)
        if process.returncode != 1 or process.stdout.strip():
            raise ValueError('prior_owned_process_still_exists')
    return dict(audit_sha256=sha(root / 'reports/P97_comparison.json'),
                pipeline_status_sha256=sha(storage / 'records/context_pilot/P97_pipeline_v01/status.json'),
                server_final_sha256=sha(storage / 'records/context_pilot/P97_pipeline_v01/server_final.json'))


def frozen_hashes(root):
    paths = list((root / 'scripts').glob('*.py')) + list((root / 'tests').glob('test_*.py'))
    plan = read(root / PLAN)
    paths += [root / name for name in (PLAN, 'docs/experiments/P99_whole_task_tool_choice.md',
                                       *plan['source_sha256'])]
    return {str(p.relative_to(root)): sha(p) for p in sorted(set(paths))}


def preflight(storage, root):
    folder = storage / 'records/context_pilot/P99_preflight_v01'
    target = root / PREFLIGHT
    if folder.exists() or target.exists():
        raise FileExistsError('preserve_all_P99_preflight_attempts')
    plan, original, _, prepared = sources(storage, root)
    hashes = frozen_hashes(root)
    commit = frozen_sources(root, tuple(hashes))
    identity, end = live_identity(storage, original, 360)
    folder.mkdir(parents=True)
    started = time.monotonic()
    result = {'phase': 'P99_preflight', 'status': 'running', 'rows': [],
        'git_commit': commit, 'source_hashes': hashes, 'model_identity': identity,
        'server_lease_end': end, 'research_resume': check_resume(storage),
        'input_count_requests': 0, 'failed_input_count_requests': 0,
        'model_generations': 0, 'environment_api_requests': 0, 'evaluator_calls': 0,
        'reserved_scenarios_read': 0, 'all_eight_inputs_checked': False}
    try:
        for item in prepared:
            row = {'source_run': item['source_run'], 'task_id': item['task_id'], 'conditions': {}}
            result['rows'].append(row)
            for arm in POLICIES:
                if (storage / '.runtime/P99.stop').exists():
                    raise InterruptedError('explicit_P99_stop')
                remaining = 300 - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('P99_preflight_deadline')
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
            a, b = [row['conditions'][arm] for arm in POLICIES]
            if (a['model_messages_sha256'] != b['model_messages_sha256']
                    or a['base_messages_sha256'] != b['base_messages_sha256']
                    or a['visible_state'] != b['visible_state']):
                raise ValueError('initial_task_history_not_matched')
            requests = [read(folder / (item['source_run'] + '_' + arm + '_request_private.json'))
                        for arm in POLICIES]
            if (requests[0]['tool_choice'] != 'auto' or requests[1]['tool_choice'] != 'required'
                    or {k:v for k,v in requests[0].items() if k != 'tool_choice'}
                    != {k:v for k,v in requests[1].items() if k != 'tool_choice'}):
                raise ValueError('only_tool_choice_may_differ_in_initial_request')
            if 'wall_seconds_at_snapshot' in a['visible_state']['remaining']:
                raise ValueError('hidden_time_was_exposed')
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


def activate(storage, root):
    if (root / ACTIVATION).exists():
        raise FileExistsError('preserve_P99_activation')
    pre = read(root / PREFLIGHT)
    if (pre['status'] != 'complete' or not pre['all_eight_inputs_checked']
            or pre['input_count_requests'] != 8 or pre['failed_input_count_requests']
            or pre['source_hashes'] != frozen_hashes(root)):
        raise ValueError('P99_preparation_incomplete_or_stale')
    write_json(root / ACTIVATION, {'phase': 'P99', 'source_hashes': pre['source_hashes'],
        'preflight_sha256': sha(root / PREFLIGHT), 'research_resume': check_resume(storage),
        'all_eight_conditions_frozen_before_generation': True,
        'activated_at': dt.datetime.now(dt.timezone.utc).isoformat()})


def bounded_cell(storage, root, plan, number, arm, rid, folder):
    command = [sys.executable, str(root / 'scripts/run_whole_task_tool_choice.py'),
               '--storage-root', str(storage), '--repo-root', str(root),
               '--cell', str(number), '--arm', arm]
    with (folder / (rid + '_worker.log')).open('w') as log:
        child = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
        try:
            code = child.wait(timeout=plan['max_setup_seconds'] + plan['max_wall_seconds'] +
                              plan['max_cleanup_seconds'])
            if code:
                raise RuntimeError('P99_cell_worker_failed_no_retry')
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=180)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=15)
    return read(storage / 'records/context_pilot' / rid / 'summary.json')


def run(storage, root):
    plan, original, _, prepared = sources(storage, root)
    freeze, pre = read(root / ACTIVATION), read(root / PREFLIGHT)
    if (freeze['source_hashes'] != frozen_hashes(root)
            or freeze['preflight_sha256'] != sha(root / PREFLIGHT)
            or freeze['research_resume'] != check_resume(storage)):
        raise ValueError('frozen_P99_sources_or_resumption_changed')
    max_cell = sum(plan[key] for key in ('max_setup_seconds', 'max_wall_seconds',
        'max_cleanup_seconds', 'max_idle_wait_seconds', 'max_evaluation_seconds'))
    identity, end = live_identity(storage, original, plan['max_cells'] * max_cell)
    if identity != pre['model_identity']:
        raise ValueError('prepared_model_identity_changed')
    folder = storage / 'records/context_pilot' / plan['batch_id']
    folder.mkdir(exist_ok=False)
    for name, value in (('plan', plan), ('activation', freeze), ('preflight', pre)):
        write_json(folder / (name + '.json'), value)
    state = {'phase': 'P99', 'status': 'running', 'rows': [], 'completed': [], 'active': None,
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
            if (storage / '.runtime/P99.stop').exists():
                raise InterruptedError('explicit_P99_stop')
            current, _ = live_identity(storage, original, max_cell)
            if current != identity:
                raise ValueError('same_idle_inference_runtime_required')
            rid = cell_id(number, arm)
            state['active'] = rid; save()
            result = bounded_cell(storage, root, plan, number, arm, rid, folder)
            row = {k: result[k] for k in ('run_id', 'task_id', 'arm', 'time_visibility', 'tool_choice_policy', 'reasoning_budget_tokens', 'stop_reason', 'model_calls',
                'known_total_tokens', 'unknown_usage_calls', 'api_requests', 'wall_seconds',
                'full_wall_seconds', 'cleanup_confirmed')}
            row['disposition'] = disposition(result)
            state['rows'].append(row); save()
            if row['disposition'] == 'stop_batch':
                raise ValueError('P99_initialization_API_or_runtime_failure')
            row['idle_recovery'] = wait_idle(storage, original, identity, plan['max_idle_wait_seconds'])
            if (storage / '.runtime/P99.stop').exists():
                raise InterruptedError('explicit_P99_stop')
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
                raise ValueError('independent_P99_evaluation_failed')
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
    raise InterruptedError('bounded_P99_execution_interrupted')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--preflight', action='store_true')
    modes.add_argument('--activate', action='store_true')
    modes.add_argument('--cell', type=int, choices=range(1, 5))
    parser.add_argument('--arm', choices=POLICIES)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, interrupt); signal.signal(signal.SIGINT, interrupt)
    if args.cell is not None:
        if args.arm is None:
            parser.error('--cell requires --arm')
        plan, original, tools, prepared = sources(args.storage_root, args.repo_root)
        # Every worker requires the already frozen eight-cell activation.
        frozen = read(args.repo_root / ACTIVATION)
        if frozen['source_hashes'] != frozen_hashes(args.repo_root):
            raise ValueError('P99_worker_sources_changed')
        run_cell(args.storage_root, args.repo_root, plan, original, tools,
                 prepared[args.cell - 1], ERROR_POLICY, cell_id(args.cell, args.arm),
                 tool_choice_policy=args.arm)
    elif args.preflight:
        result = preflight(args.storage_root, args.repo_root)
        print({k: result[k] for k in ('status', 'input_count_requests', 'failed_input_count_requests')})
    elif args.activate:
        activate(args.storage_root, args.repo_root)
    else:
        raise SystemExit(run(args.storage_root, args.repo_root))
