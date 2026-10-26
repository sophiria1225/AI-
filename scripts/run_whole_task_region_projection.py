"""Finite P127 comparison with common cache, receipt format and checkpoint."""
import argparse
import datetime as dt
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from api_error_comparison import disposition, task_snapshot
from whole_task_region_projection import POLICIES, API_BUDGETS, REPLAY_REPORT, PREDECESSOR_REPORT
from whole_task_region_projection import (ERROR_POLICY, cell_id, config_for, run_order, validate_plan, make_notification, initial_conversation)
from budget_signal import digest
from inspect_appworld_api_schemas import load_public_tools
from inspect_input_exposure import check_resume, frozen_sources
from tool_choice_local_llama import count_input, payload_for
from fixed_budget_local_llama import count_input as count_summary_input, payload_for as summary_payload
from rolling_checkpoint_history import SUMMARY_PROMPT
from probe_inference_cache import live_identity
from public_display import CODE_TOOLS
from residual_output_budget import admission
from run_whole_task_region_projection_cell import run_cell
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from run_reasoning_history_comparison import wait_idle

PLAN = 'configs/P127_whole_task_region_projection_v01.json'
PREFLIGHT = 'reports/P127_initial_checks.json'
ACTIVATION = 'reports/P127_activation_v01.json'


def sources(storage, root):
    if root.resolve() != ROOT.resolve():
        raise ValueError('executing_P127_repository_must_match')
    plan = read(root / PLAN); validate_plan(plan)
    for rel, expected in plan['source_sha256'].items():
        if sha(root / rel) != expected: raise ValueError('fixed_source_changed:' + rel)
    from run_whole_task_tool_choice import sources as original_sources
    previous, original, tools, prepared = original_sources(storage, root)
    if any(plan[k] != previous[k] for k in ('known_tasks','source_runs','source_plan','world_seed')):
        raise ValueError('same_four_known_tasks_required')
    from joined_public_read_views import JOINED_CONTRACT_ID, verify_joined_implementation
    verified = verify_joined_implementation(storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps/spotify')
    if verified != JOINED_CONTRACT_ID:
        raise ValueError('pinned_public_read_implementation_required')
    if ([original['api_budget_by_task'][task['task_id']] for task in plan['known_tasks']] != [160, 80, 80, 80]
            or plan['api_budget_by_task_slot'] != list(API_BUDGETS)
            or sum(API_BUDGETS) * 2 != plan['max_reserved_environment_api_requests']):
        raise ValueError('prespecified_common_P127_API_budgets_required')
    if predecessor_closed(storage, root) != plan['predecessor_closure']:
        raise ValueError('P127_predecessor_closure_changed')
    return plan, original, tools, prepared


def predecessor_closed(storage, root):
    """Bind closed earlier cohorts and the finite offline frontier, never pool them."""
    from whole_task_projection import cell_id as p125_id, run_order as p125_order
    from whole_task_rolling_checkpoint import cell_id as p123_id, run_order as p123_order
    bindings = {}
    for phase, prior_id, prior_order, size in (
            ('P125', p125_id, p125_order, 8), ('P123', p123_id, p123_order, 12)):
        folder = storage / ('records/context_pilot/' + phase + '_pipeline_v01')
        pipeline, final = read(folder / 'status.json'), read(folder / 'server_final.json')
        report_path = root / ('reports/' + phase + '_comparison.json')
        session_path = root / ('reports/' + phase + '_server_session.json')
        audit, session = read(report_path), read(session_path)
        if (pipeline['status'] not in ('complete', 'stopped') or not pipeline.get('server_stopped')
                or final['status'] != 'stopped' or final['supervisor_pid'] != pipeline['server_supervisor_pid']
                or audit['audit_errors'] or not audit['owned_processes_absent']
                or audit.get('phase') != phase or session.get('phase') != phase
                or len(audit['rows']) != size or any(row['record_status'] != 'evaluated' for row in audit['rows'])
                or {row['run_id'] for row in audit['rows']} != {prior_id(n, p) for n, p in prior_order()}
                or session['status'] != 'stopped' or not session['owned_processes_absent']
                or audit['pipeline_status_sha256'] != sha(folder / 'status.json')
                or audit['server_final_sha256'] != sha(folder / 'server_final.json')
                or session['audit_source_sha256'] != sha(report_path)):
            raise ValueError('closed_owned_all_slots_' + phase + '_required')
        for key in ('pid', 'supervisor_pid'):
            process = subprocess.run(['ps', '-p', str(final[key]), '-o', 'command='],
                                     capture_output=True, text=True, timeout=10)
            if process.returncode != 1 or process.stdout.strip():
                raise ValueError('previous_owned_process_present')
        bindings[phase] = dict(audit_sha256=sha(report_path), session_sha256=sha(session_path),
                              pipeline_status_sha256=sha(folder / 'status.json'),
                              server_final_sha256=sha(folder / 'server_final.json'))
    replay = read(root / REPLAY_REPORT)
    fixed = dict(phase='P126', status='complete', all_original_sources_accounted=True,
                 unobserved_suffix_executed=False, original_sources_changed=False,
                 additional_model_calls=0, additional_API_requests=0, additional_evaluations=0,
                 normal_path_synthetic_contract_tests_passed=True, replay_audit_errors=[])
    if (any(type(replay.get(k)) is not type(v) or replay[k] != v for k, v in fixed.items())
            or type(replay.get('observed_region_partial_hits')) is not int
            or replay['observed_region_partial_hits'] <= 0):
        raise ValueError('closed_finite_prefix_P126_evidence_required')
    # The saved frontier is allowed to stop before a normal root boundary. It
    # does not establish completion, token savings, quality or unseen suffixes.
    implementation = replay.get('source_sha256')
    required = {'scripts/region_field_projection.py', 'scripts/region_projection_runtime.py',
                'scripts/demand_joined_read_adapter.py', 'scripts/joined_public_read_views.py'}
    if type(implementation) is not dict or not required.issubset(implementation):
        raise ValueError('P126_implementation_source_binding_required')
    for name, expected in implementation.items():
        path = Path(name)
        if (path.is_absolute() or '..' in path.parts or not path.parts
                or path.parts[0] not in ('scripts', 'tests')
                or not (root / path).resolve().is_relative_to(root.resolve())
                or sha(root / path) != expected):
            raise ValueError('P126_verified_implementation_changed')
    bindings['P126'] = dict(replay_report_sha256=sha(root / REPLAY_REPORT))
    return bindings


def frozen_hashes(root):
    paths = list((root / 'scripts').glob('*.py')) + list((root / 'tests').glob('test_*.py'))
    plan = read(root / PLAN)
    paths += [root / name for name in (PLAN, 'docs/experiments/P127_whole_task_region_projection.md',
                                       *plan['source_sha256'])]
    return {str(p.relative_to(root)): sha(p) for p in sorted(set(paths))}


def preflight(storage, root):
    folder = storage / 'records/context_pilot/P127_preflight_v01'
    target = root / PREFLIGHT
    if folder.exists() or target.exists():
        raise FileExistsError('preserve_all_P127_preflight_attempts')
    plan, original, _, prepared = sources(storage, root)
    hashes = frozen_hashes(root)
    commit = frozen_sources(root, tuple(hashes))
    identity, end = live_identity(storage, original, 480)
    folder.mkdir(parents=True)
    started = time.monotonic()
    result = {'phase': 'P127_preflight', 'status': 'running', 'rows': [],
        'git_commit': commit, 'source_hashes': hashes, 'model_identity': identity,
        'server_lease_end': end, 'research_resume': check_resume(storage),
        'input_count_requests': 0, 'summary_input_count_requests': 0, 'failed_input_count_requests': 0,
        'model_generations': 0, 'environment_api_requests': 0, 'evaluator_calls': 0,
        'reserved_scenarios_read': 0, 'all_eight_inputs_checked': False}
    try:
        for item in prepared:
            row = {'source_run': item['source_run'], 'task_id': item['task_id'], 'conditions': {}}
            result['rows'].append(row)
            for arm in POLICIES:
                if (storage / '.runtime/P127.stop').exists():
                    raise InterruptedError('explicit_P127_stop')
                remaining = 420 - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('P127_preflight_deadline')
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
        # A separate vocabulary-only text transport check; no summary is generated.
        sample = [{'role': 'system', 'content': SUMMARY_PROMPT}, {'role': 'user',
            'content': '{"original_instructions_and_task":[],"older_history":[],"recent_context":[]}'}]
        cfg = {**config['model'], 'temperature': config['draft_temperature'],
               'seed': plan['model_seed'], 'num_predict': config['max_output_tokens'], 'cache_prompt': True}
        path = folder / 'summary_transport_request_private.json'
        request = summary_payload(cfg, sample, [])
        if 'tools' in request or 'tool_choice' in request or request['reasoning_budget_tokens'] != -1:
            raise ValueError('text_only_summary_transport_changed')
        write_json(path, request)
        result['summary_input_count_requests'] += 1
        try:
            result['summary_transport'] = count_summary_input(cfg, sample, [], timeout=30)
        except Exception:
            result['failed_input_count_requests'] += 1
            raise
        result['summary_transport']['request_sha256'] = sha(path)
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
        raise FileExistsError('preserve_P127_activation')
    pre = read(root / PREFLIGHT)
    if (pre['status'] != 'complete' or not pre['all_eight_inputs_checked']
            or pre['input_count_requests'] != 8 or pre['summary_input_count_requests'] != 1
            or pre['failed_input_count_requests']
            or pre['source_hashes'] != frozen_hashes(root)):
        raise ValueError('P127_preparation_incomplete_or_stale')
    write_json(root / ACTIVATION, {'phase': 'P127', 'source_hashes': pre['source_hashes'],
        'preflight_sha256': sha(root / PREFLIGHT), 'research_resume': check_resume(storage),
        'all_eight_conditions_frozen_before_generation': True,
        'activated_at': dt.datetime.now(dt.timezone.utc).isoformat()})


def bounded_cell(storage, root, plan, number, arm, rid, folder):
    command = [sys.executable, str(root / 'scripts/run_whole_task_region_projection.py'),
               '--storage-root', str(storage), '--repo-root', str(root),
               '--cell', str(number), '--arm', arm]
    with (folder / (rid + '_worker.log')).open('w') as log:
        child = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
        try:
            code = child.wait(timeout=plan['max_setup_seconds'] + plan['max_wall_seconds'] +
                              plan['max_cleanup_seconds'])
            if code:
                raise RuntimeError('P127_cell_worker_failed_no_retry')
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
        raise ValueError('frozen_P127_sources_or_resumption_changed')
    max_cell = sum(plan[key] for key in ('max_setup_seconds', 'max_wall_seconds',
        'max_cleanup_seconds', 'max_idle_wait_seconds', 'max_evaluation_seconds'))
    identity, end = live_identity(storage, original, plan['max_cells'] * max_cell)
    if identity != pre['model_identity']:
        raise ValueError('prepared_model_identity_changed')
    folder = storage / 'records/context_pilot' / plan['batch_id']
    folder.mkdir(exist_ok=False)
    for name, value in (('plan', plan), ('activation', freeze), ('preflight', pre)):
        write_json(folder / (name + '.json'), value)
    state = {'phase': 'P127', 'status': 'running', 'rows': [], 'completed': [], 'active': None,
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
            if (storage / '.runtime/P127.stop').exists():
                raise InterruptedError('explicit_P127_stop')
            current, _ = live_identity(storage, original, max_cell)
            if current != identity:
                raise ValueError('same_idle_inference_runtime_required')
            rid = cell_id(number, arm)
            state['active'] = rid; save()
            result = bounded_cell(storage, root, plan, number, arm, rid, folder)
            row = {k: result[k] for k in ('run_id', 'task_id', 'arm', 'time_visibility', 'checkpoint_policy', 'projection_policy', 'reasoning_budget_tokens', 'stop_reason', 'model_calls',
                'known_total_tokens', 'unknown_usage_calls', 'api_requests', 'wall_seconds',
                'full_wall_seconds', 'cleanup_confirmed')}
            row['disposition'] = disposition(result)
            state['rows'].append(row); save()
            if row['disposition'] == 'stop_batch':
                raise ValueError('P127_initialization_API_or_runtime_failure')
            row['idle_recovery_started_at'] = dt.datetime.now(dt.timezone.utc).isoformat(); save()
            row['idle_recovery'] = wait_idle(storage, original, identity, plan['max_idle_wait_seconds'])
            if (storage / '.runtime/P127.stop').exists():
                raise InterruptedError('explicit_P127_stop')
            evaluation_started = time.monotonic()
            row['evaluation_started_at'] = dt.datetime.now(dt.timezone.utc).isoformat(); save()
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
                raise ValueError('independent_P127_evaluation_failed')
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
    raise InterruptedError('bounded_P127_execution_interrupted')


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
            raise ValueError('P127_worker_sources_changed')
        run_cell(args.storage_root, args.repo_root, plan, original, tools,
                 prepared[args.cell - 1], ERROR_POLICY, cell_id(args.cell, args.arm),
                 projection_policy=args.arm)
    elif args.preflight:
        result = preflight(args.storage_root, args.repo_root)
        print({k: result[k] for k in ('status', 'input_count_requests', 'failed_input_count_requests')})
    elif args.activate:
        activate(args.storage_root, args.repo_root)
    else:
        raise SystemExit(run(args.storage_root, args.repo_root))
