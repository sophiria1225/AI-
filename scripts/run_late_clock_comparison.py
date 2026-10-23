"""Finite P82 from-start comparison of wall-time visibility."""
import argparse
import datetime as dt
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from api_error_comparison import disposition, task_snapshot
from stable_clock_observation import POLICIES
from late_clock_comparison import (ERROR_POLICY, cell_id, config_for, run_order, validate_plan, make_notification, initial_conversation)
from budget_signal import digest
from inspect_appworld_api_schemas import load_public_tools
from inspect_input_exposure import check_resume, frozen_sources
from local_llama import count_input
from probe_inference_cache import live_identity
from public_display import CODE_TOOLS
from residual_output_budget import admission
from run_late_clock_cell import run_cell
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from run_reasoning_history_comparison import wait_idle

PLAN = 'configs/P82_late_clock_comparison_v01.json'
PREFLIGHT = 'reports/P82_initial_checks.json'
ACTIVATION = 'reports/P82_activation_v01.json'


def sources(storage, root):
    plan = read(root / PLAN)
    validate_plan(plan)
    for name, expected in plan['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('fixed_source_changed:' + name)
    anchor = read(root / plan['prior_cohort'])
    if (anchor['audit_errors'] or anchor['batch_status'] != 'complete'
            or len(anchor['rows']) != 8
            or any(r['record_status'] != 'evaluated' for r in anchor['rows'])):
        raise ValueError('closed_full_P80_anchor_required')
    session = read(root / 'reports/P80_server_session.json')
    if (session['status'] != 'stopped' or not session['owned_processes_absent']
            or session['audit_source_sha256'] != sha(root / plan['prior_cohort'])):
        raise ValueError('P80_server_closure_required')
    prior_path = root / plan['required_closed_cohort']
    prior = read(prior_path)
    prior_session = read(root / 'reports/P81_server_session.json')
    if (prior['batch_status'] != 'complete' or prior['audit_errors'] or len(prior['rows']) != 16
            or any(r['record_status'] != 'evaluated' for r in prior['rows'])
            or prior_session['status'] != 'stopped' or not prior_session['owned_processes_absent']
            or prior_session['audit_source_sha256'] != sha(prior_path)):
        raise ValueError('full_P81_closure_required_before_P82')
    diagnostic = read(root / 'reports/P81_fallback_reference_diagnostic.json')
    if (diagnostic['partial_only'] or diagnostic['closed_cells'] != 24
            or len(diagnostic['pairs']) != 24 or diagnostic['source_cohort_sha256'] != sha(prior_path)):
        raise ValueError('full_P81_reference_diagnostic_required_before_P82')
    original = read(root / plan['source_plan'])
    if (original['task_ids'] != [item['task_id'] for item in plan['known_tasks']]
            or original['seed'] != plan['world_seed']):
        raise ValueError('known_task_order_or_initial_world_seed_changed')
    live = read(root / 'reports/public_api_live_preflight_20261023.json')
    if not live['all_checks_passed'] or live['api_requests_recorded'] != 3:
        raise ValueError('live_typed_bridge_confirmation_required')
    fixed = read(root / 'configs/public_api_live_preflight_v01.json')
    package = storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld'
    for name, expected in fixed['runtime_source_sha256'].items():
        if sha(package / name) != expected:
            raise ValueError('installed_public_runtime_changed')
    tools, schemas, _ = load_public_tools(storage / '.runtime/appworld/r18_probe_01/data')
    if schemas != fixed['public_schema_sha256']:
        raise ValueError('public_schemas_changed')
    prepared = []
    for number, item in enumerate(plan['known_tasks'], 1):
        if item['source_run'] != plan['source_runs'][number - 1]:
            raise ValueError('fixed_known_public_task_order_changed')
        path = storage / 'records/context_pilot' / item['source_run'] / 'public_task.json'
        if sha(path) != item['known_public_task_sha256']:
            raise ValueError('known_initial_public_record_changed')
        public = read(path)
        if public.get('ground_truth_loaded') is not False:
            raise ValueError('ground_truth_must_not_be_loaded')
        prepared.append({**item, 'public_task': public})
    return plan, original, tools, prepared


def frozen_hashes(root):
    paths = list((root / 'scripts').glob('*.py')) + list((root / 'tests').glob('test_*.py'))
    plan = read(root / PLAN)
    paths += [root / name for name in (PLAN, 'docs/experiments/P82_late_clock_comparison.md',
                                       *plan['source_sha256'])]
    return {str(p.relative_to(root)): sha(p) for p in sorted(set(paths))}


def preflight(storage, root):
    folder = storage / 'records/context_pilot/P82_preflight_v01'
    target = root / PREFLIGHT
    if folder.exists() or target.exists():
        raise FileExistsError('preserve_all_P82_preflight_attempts')
    plan, original, _, prepared = sources(storage, root)
    hashes = frozen_hashes(root)
    commit = frozen_sources(root, tuple(hashes))
    identity, end = live_identity(storage, original, 360)
    folder.mkdir(parents=True)
    started = time.monotonic()
    result = {'phase': 'P82_preflight', 'status': 'running', 'rows': [],
        'git_commit': commit, 'source_hashes': hashes, 'model_identity': identity,
        'server_lease_end': end, 'research_resume': check_resume(storage),
        'input_count_requests': 0, 'failed_input_count_requests': 0,
        'model_generations': 0, 'environment_api_requests': 0, 'evaluator_calls': 0,
        'reserved_scenarios_read': 0, 'all_twelve_inputs_checked': False}
    try:
        for item in prepared:
            row = {'source_run': item['source_run'], 'task_id': item['task_id'], 'conditions': {}}
            result['rows'].append(row)
            for arm in POLICIES:
                if (storage / '.runtime/P82.stop').exists():
                    raise InterruptedError('explicit_P82_stop')
                remaining = 300 - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('P82_preflight_deadline')
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
                cfg = {**original['model'], 'temperature': original['agent_temperature'],
                       'seed': plan['model_seed'], 'num_predict': original['max_output_tokens'],
                       'cache_prompt': False}
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
            a, b, c = [row['conditions'][arm] for arm in POLICIES]
            if b != c:
                # Count metadata can differ in wall duration; compare the input.
                if b['model_messages_sha256'] != c['model_messages_sha256'] or b['input_tokens'] != c['input_tokens']:
                    raise ValueError('hidden_and_late_initial_inputs_must_match')
            if a['base_messages_sha256'] != b['base_messages_sha256']:
                raise ValueError('initial_task_history_not_matched')
            if a['model_messages_sha256'] == b['model_messages_sha256']:
                raise ValueError('time_visibility_treatment_not_present')
            if 'wall_seconds_at_snapshot' in b['visible_state']['remaining']:
                raise ValueError('hidden_time_was_exposed')
        result.update(status='complete', all_twelve_inputs_checked=True)
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
        raise FileExistsError('preserve_P82_activation')
    pre = read(root / PREFLIGHT)
    if (pre['status'] != 'complete' or not pre['all_twelve_inputs_checked']
            or pre['input_count_requests'] != 12 or pre['failed_input_count_requests']
            or pre['source_hashes'] != frozen_hashes(root)):
        raise ValueError('P82_preparation_incomplete_or_stale')
    write_json(root / ACTIVATION, {'phase': 'P82', 'source_hashes': pre['source_hashes'],
        'preflight_sha256': sha(root / PREFLIGHT), 'research_resume': check_resume(storage),
        'all_twenty_four_conditions_frozen_before_generation': True,
        'activated_at': dt.datetime.now(dt.timezone.utc).isoformat()})


def bounded_cell(storage, root, plan, repetition, number, arm, rid, folder):
    command = [sys.executable, str(root / 'scripts/run_late_clock_comparison.py'),
               '--storage-root', str(storage), '--repo-root', str(root),
               '--cell', str(number), '--arm', arm, '--repetition', str(repetition)]
    with (folder / (rid + '_worker.log')).open('w') as log:
        child = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
        try:
            code = child.wait(timeout=plan['max_setup_seconds'] + plan['max_wall_seconds'] +
                              plan['max_cleanup_seconds'])
            if code:
                raise RuntimeError('P82_cell_worker_failed_no_retry')
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
        raise ValueError('frozen_P82_sources_or_resumption_changed')
    max_cell = sum(plan[key] for key in ('max_setup_seconds', 'max_wall_seconds',
        'max_cleanup_seconds', 'max_idle_wait_seconds', 'max_evaluation_seconds'))
    identity, end = live_identity(storage, original, plan['max_cells'] * max_cell)
    if identity != pre['model_identity']:
        raise ValueError('prepared_model_identity_changed')
    folder = storage / 'records/context_pilot' / plan['batch_id']
    folder.mkdir(exist_ok=False)
    for name, value in (('plan', plan), ('activation', freeze), ('preflight', pre)):
        write_json(folder / (name + '.json'), value)
    state = {'phase': 'P82', 'status': 'running', 'rows': [], 'completed': [], 'active': None,
        'planned': [cell_id(rep, n, arm) for rep, n, arm in run_order()], 'model_identity': identity,
        'server_lease_end': end, 'reserved_scenarios_read': 0,
        'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()}
    def save():
        state['updated_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        write_json(folder / 'status.json', state)
    try:
        save()
        for repetition, number, arm in run_order():
            if (storage / '.runtime/P82.stop').exists():
                raise InterruptedError('explicit_P82_stop')
            current, _ = live_identity(storage, original, max_cell)
            if current != identity:
                raise ValueError('same_idle_inference_runtime_required')
            rid = cell_id(repetition, number, arm)
            state['active'] = rid; save()
            result = bounded_cell(storage, root, plan, repetition, number, arm, rid, folder)
            row = {k: result[k] for k in ('run_id', 'task_id', 'arm', 'time_visibility', 'stop_reason', 'model_calls',
                'known_total_tokens', 'unknown_usage_calls', 'api_requests', 'wall_seconds',
                'full_wall_seconds', 'cleanup_confirmed')}
            row['repetition'] = repetition
            row['disposition'] = disposition(result)
            state['rows'].append(row); save()
            if row['disposition'] == 'stop_batch':
                raise ValueError('P82_initialization_API_or_runtime_failure')
            row['idle_recovery'] = wait_idle(storage, original, identity, plan['max_idle_wait_seconds'])
            if (storage / '.runtime/P82.stop').exists():
                raise InterruptedError('explicit_P82_stop')
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
                raise ValueError('independent_P82_evaluation_failed')
            row['success'] = read(storage / 'records/context_pilot' / rid / 'evaluation.json')['official_success']
            state['completed'].append(rid); save()
            print({k: row[k] for k in ('run_id', 'stop_reason', 'model_calls', 'known_total_tokens', 'success')}, flush=True)
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
    raise InterruptedError('bounded_P82_execution_interrupted')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--preflight', action='store_true')
    modes.add_argument('--activate', action='store_true')
    modes.add_argument('--cell', type=int, choices=range(1, 5))
    parser.add_argument('--arm', choices=POLICIES)
    parser.add_argument('--repetition', type=int, choices=(1, 2))
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, interrupt); signal.signal(signal.SIGINT, interrupt)
    if args.cell is not None:
        if args.arm is None or args.repetition is None:
            parser.error('--cell requires --arm and --repetition')
        plan, original, tools, prepared = sources(args.storage_root, args.repo_root)
        # Every worker requires the already frozen twenty-four-cell activation.
        frozen = read(args.repo_root / ACTIVATION)
        if frozen['source_hashes'] != frozen_hashes(args.repo_root):
            raise ValueError('P82_worker_sources_changed')
        run_cell(args.storage_root, args.repo_root, plan, original, tools,
                 prepared[args.cell - 1], ERROR_POLICY, cell_id(args.repetition, args.cell, args.arm),
                 time_visibility=args.arm)
    elif args.preflight:
        result = preflight(args.storage_root, args.repo_root)
        print({k: result[k] for k in ('status', 'input_count_requests', 'failed_input_count_requests')})
    elif args.activate:
        activate(args.storage_root, args.repo_root)
    else:
        raise SystemExit(run(args.storage_root, args.repo_root))
