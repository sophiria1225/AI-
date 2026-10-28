"""Finite, inert saved-input factorial: format x reasoning allowance, 12 calls.

No generated programs, task APIs or evaluators are executed. This is a
mechanism diagnostic, not whole-task cost or quality evidence.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from checkpoint_update_schema_p145 import structured_payload, parse_and_apply
from checkpoint_state_update_p144 import summary_note
from receipt_reasoning_history import digest
from local_llama import post, parse_response
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from run_state_update_resume_p144r1 import retain_spawn_handle
from run_whole_task_state_update_pipeline_p144 import checked_ci
from update_transport_server_p145 import live_identity, wait_idle, LEASE_SECONDS

PLAN = 'configs/P145_update_transport_v01.json'
PIPELINE = 'records/context_pilot/P145_pipeline_v01'
BATCH = 'records/context_pilot/P145_replay_v01'
ARMS = ('native_unlimited', 'schema_unlimited', 'native_bounded', 'schema_bounded')
CASES = ((1, 'BOC_P144R1_01_THRESHOLD_DELTA_UPDATE', 'call_014'),
         (2, 'BOC_P144R1_02_THRESHOLD_DELTA_UPDATE', 'call_015'),
         (4, 'BOC_P144R1_04_THRESHOLD_DELTA_UPDATE', 'call_009'))
BASE = {'base_url': 'http://127.0.0.1:8011'}


def now():
    return datetime.now(timezone.utc).isoformat()


def schedule():
    return [(number, arm) for offset, (number, _, _) in enumerate(CASES)
            for arm in ARMS[offset:] + ARMS[:offset]]


def payload(saved, old, arm):
    if arm not in ARMS:
        raise ValueError('fixed_P145_factorial_arm')
    budget = 2048 if arm.endswith('_bounded') else -1
    # The schema builder also authenticates the original -1/4096 request.
    result = structured_payload(saved, old, budget)
    if arm.startswith('native_'):
        result.pop('response_format')
    if result['messages'] != saved['messages'] or result['max_tokens'] != 4096:
        raise ValueError('unchanged_saved_messages_and_output_cap_required')
    return result


def stop_check(storage):
    if (storage / '.runtime/P145.stop').exists():
        raise InterruptedError('explicit_P145_stop')


def validate_plan(plan):
    expected = dict(phase='P145', max_model_calls=12, max_total_tokens=450000,
        output_cap=4096, call_timeout_seconds=480, server_max_lifetime_seconds=8100,
        max_environment_api_calls=0, max_evaluator_calls=0, automatic_retries=0,
        candidate_for_whole_task='schema_bounded', candidate_selection_from_results=False)
    if any(type(plan.get(k)) is not type(v) or plan[k] != v for k, v in expected.items()):
        raise ValueError('fixed_P145_budget_or_scope_changed')
    if plan['schedule'] != [dict(task_slot=n, arm=a) for n, a in schedule()]:
        raise ValueError('fixed_P145_order_changed')
    if [(x['task_slot'], x['source_run'], x['source_call']) for x in plan['cases']] != list(CASES):
        raise ValueError('fixed_three_saved_inputs_required')


def sources(storage, root):
    plan = read(root / PLAN)
    validate_plan(plan)
    for name, expected in plan['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('P145_source_changed:' + name)
    for name, expected in plan['private_source_sha256'].items():
        if sha(storage / name) != expected:
            raise ValueError('P145_saved_input_or_authorization_changed')
    data = {}
    for case in plan['cases']:
        trial = storage / 'records/context_pilot' / case['source_run']
        request = read(trial / case['source_call'] / 'request.json')
        packet = json.loads(request['messages'][1]['content'])
        old = packet['previous_checkpoint']
        ordinary = read(trial / case['next_actor_call'] / 'request.json')
        plain = packet['original_instructions_and_task'] + [summary_note(old)] + packet['older_history'] + packet['recent_context']
        if ordinary['messages'][:-1] != plain or '<whole_task_budget_v1>' not in ordinary['messages'][-1]['content']:
            raise ValueError('saved_full_actor_view_does_not_match_second_focus_packet')
        if request['max_tokens'] != 4096 or request['reasoning_budget_tokens'] != -1:
            raise ValueError('fixed_original_focus_cap_or_reasoning_required')
        data[case['task_slot']] = dict(saved=request, old=old, packet=packet,
                                      ordinary=ordinary, original_slot=case['source_run'])
    return plan, read(root / 'configs/P29_stateful_code_v01.json'), data


def verify_predecessor(storage):
    folder = storage / 'records/context_pilot/P144R1_pipeline_v01'
    pipeline, final = read(folder / 'status.json'), read(folder / 'server_final.json')
    if pipeline['status'] != 'complete' or pipeline.get('server_stopped') is not True or final['status'] != 'stopped':
        raise ValueError('closed_P144R1_required')
    for pid in (final['pid'], final['supervisor_pid']):
        p = subprocess.run(['ps', '-p', str(pid), '-o', 'pid='], capture_output=True, text=True, timeout=10)
        if p.returncode != 1 or p.stdout.strip():
            raise ValueError('previous_server_absence_not_verified')


def native_count(request):
    value = post(BASE, '/v1/chat/completions/input_tokens', request, 30).get('input_tokens')
    if type(value) is not int or not 0 < value < 65536:
        raise ValueError('positive_native_count_required')
    return value


def assess(message, finish, data):
    """Strict host validation; native full actor counting is a separate step."""
    state, counts = parse_and_apply(message, finish, data['old'])
    compacted = deepcopy(data['ordinary'])
    packet = data['packet']
    compacted['messages'] = (deepcopy(packet['original_instructions_and_task']) +
        [summary_note(state)] + deepcopy(packet['recent_context']) +
        [deepcopy(data['ordinary']['messages'][-1])])
    return compacted, dict(patch_valid=True, old_state_changed=digest(state) != digest(data['old']),
        operation_counts=counts, materialized_state_sha256=digest(state),
        changed_old_items=counts['changed_old_items'], semantics_verified=False)


def summarize(rows, batch_status):
    chosen = [r for r in rows if r['arm'] == 'schema_bounded']
    qualified = (batch_status == 'complete' and len(rows) == 12 and len(chosen) == 3 and
        all(r.get('status') == 'ok' and r.get('usage_verified') is True
            and r.get('finished_at') for r in rows) and
        all(r.get('patch_valid') is True and r.get('shorter_full_actor_input') is True for r in chosen) and
        any(r.get('changed_old_items', 0) > 0 and r.get('old_state_changed') is True for r in chosen))
    known = sum(r['input_tokens'] + r['output_tokens'] for r in rows if r.get('status') == 'ok')
    return dict(candidate_for_whole_task='schema_bounded', candidate_selection_from_results=False,
        mechanism_preflight_passed=qualified, task_success_evaluated=False,
        whole_task_savings_established=False, general_quality_preservation_established=False,
        novelty_established=False, known_total_tokens=known,
        unknown_usage_calls=sum(r.get('model_dispatched') is True and r.get('status') != 'ok' for r in rows),
        environment_api_calls=0, evaluator_calls=0, generated_programs_executed=0)


def run_batch(storage, root, plan, original, data, identity, absolute_end):
    folder = storage / BATCH
    folder.mkdir(exist_ok=False)
    state = dict(phase='P145', status='preflight', rows=[], counts=[], active=None,
                 started_at=now(), planned=[dict(task_slot=n, arm=a) for n, a in schedule()])
    def save():
        state['updated_at'] = now()
        write_json(folder / 'status.json', state)
    try:
        save()
        for n, arm in schedule():
            stop_check(storage)
            request = payload(data[n]['saved'], data[n]['old'], arm)
            count = native_count(request)
            if count + 4096 > 65536:
                raise ValueError('focus_request_not_admitted')
            state['counts'].append(dict(task_slot=n, arm=arm, input_tokens=count, request_sha256=digest(request)))
            save()
        reservation = sum(r['input_tokens'] + 4096 for r in state['counts'])
        if reservation > 450000:
            raise ValueError('fixed_focus_reservation_exceeded')
        state.update(status='running', reserved_tokens=reservation)
        save()
        for n, arm in schedule():
            stop_check(storage)
            if time.time() + 600 > absolute_end:
                raise TimeoutError('full_focus_request_does_not_fit_lease')
            if live_identity(storage, original, 600)[0] != identity:
                raise ValueError('same_owned_P145_server_required')
            call = folder / f'T{n}_{arm}'
            call.mkdir(exist_ok=False)
            request = payload(data[n]['saved'], data[n]['old'], arm)
            counted = next(r for r in state['counts'] if (r['task_slot'], r['arm']) == (n, arm))
            if digest(request) != counted['request_sha256']:
                raise ValueError('counted_and_generated_payload_differ')
            write_json(call / 'request_private.json', request)
            row = dict(task_slot=n, arm=arm, status='pending', patch_valid=False,
                started_at=now(), input_tokens=None, output_tokens=None, model_dispatched=False)
            state['rows'].append(row)
            state['active'] = call.name
            save()
            began = time.monotonic()
            try:
                row['model_dispatched'] = True
                save()
                from inference_timeout_handler import inference_timeout_handler
                with inference_timeout_handler():
                    signal.alarm(480)
                    try:
                        raw = post(BASE, '/v1/chat/completions', request, 480)
                    finally:
                        signal.alarm(0)
                write_json(call / 'raw_response_private.json', raw)
                parsed = parse_response(raw)
                write_json(call / 'response_private.json', parsed)
                row.update({k: parsed[k] for k in ('status', 'input_tokens', 'output_tokens', 'cached_input_tokens', 'done_reason')})
                if row['input_tokens'] != counted['input_tokens'] or row['output_tokens'] > 4096:
                    raise ValueError('native_usage_or_output_cap_mismatch')
                row['usage_verified'] = True
            except BaseException as error:
                row.update(error_type=type(error).__name__)
                if row['status'] == 'pending':
                    row['status'] = 'unknown'
                raise
            finally:
                row['generation_wall_seconds'] = time.monotonic() - began
                save()
            wait_idle(storage, original, identity, 30)
            try:
                compacted, outcome = assess(parsed['message'], parsed['done_reason'], data[n])
            except (ValueError, TypeError, RecursionError) as error:
                row.update(patch_valid=False, rejection_type=type(error).__name__)
                # Private parser detail is kept locally; public results use labels.
                (call / 'parser_error_private.txt').write_text(str(error))
            else:
                row.update(outcome)
                write_json(call / 'compacted_actor_request_private.json', compacted)
                row['ordinary_actor_input_tokens'] = native_count(data[n]['ordinary'])
                row['compacted_actor_input_tokens'] = native_count(compacted)
                row['shorter_full_actor_input'] = row['compacted_actor_input_tokens'] < row['ordinary_actor_input_tokens']
            row['finished_at'] = now()
            state['active'] = None
            save()
            print(json.dumps(dict(phase='P145', finished=len(state['rows']), planned=12)), flush=True)
        state['status'] = 'complete'
    except BaseException as error:
        state.update(status='stopped', error_type=type(error).__name__)
        (folder / 'error_private.txt').write_text(str(error))
    finally:
        state.update(finished_at=now(), **summarize(state['rows'], state['status']))
        save()
    return state


def run(storage, root, head):
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip() != head:
        raise ValueError('fixed_source_head_required')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).strip():
        raise ValueError('clean_P145_source_required')
    stop_check(storage)
    plan, original, data = sources(storage, root)
    verify_predecessor(storage)
    ci = checked_ci(root, head)
    if time.time() > datetime.fromisoformat(plan['latest_launch_jst']).timestamp():
        raise TimeoutError('P145_launch_window_expired')
    out = storage / PIPELINE
    out.mkdir(exist_ok=False)
    state = dict(phase='P145_pipeline', status='starting', started_at=now(), git_commit=head,
                 ci=ci, plan_sha256=sha(root / PLAN), server_owned=False, server_stopped=False)
    def save():
        write_json(out / 'status.json', state)
    server = caffeinate = None
    result = None
    try:
        save()
        with retain_spawn_handle():
            caffeinate = subprocess.Popen(['/usr/bin/caffeinate', '-i', '-m', '-w', str(os.getpid())],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        command = [sys.executable, str(root / 'scripts/serve_research_model_recovery.py'),
            '--storage-root', str(storage), '--selection', original['model_selection'],
            '--ctx-size', '65536', '--cache-type-k', 'q8_0', '--cache-type-v', 'q8_0',
            '--max-seconds', str(LEASE_SECONDS)]
        stop_check(storage)
        with (out / 'server_supervisor.log').open('x') as log:
            with retain_spawn_handle():
                server = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
                state.update(server_owned=True, server_supervisor_pid=server.pid)
                save()
        end = time.monotonic() + 300
        while time.monotonic() < end:
            stop_check(storage)
            if server.poll() is not None:
                raise RuntimeError('P145_owned_server_exited')
            runtime = read(storage / '.runtime/model_server.json')
            if runtime.get('supervisor_pid') == server.pid and runtime['status'] == 'ready':
                state.update(server_record_directory=runtime['record_directory'], status='preflight')
                write_json(out / 'server_runtime.json', runtime)
                save()
                break
            time.sleep(1)
        else:
            raise TimeoutError('P145_server_readiness_timeout')
        identity, lease_end = live_identity(storage, original, 12 * 570 + 360 + 60)
        state.update(status='batch', model_identity=identity, server_lease_end=lease_end)
        save()
        result = run_batch(storage, root, plan, original, data, identity, datetime.fromisoformat(lease_end).timestamp())
        state['status'] = result['status']
    except BaseException as error:
        state.update(status='stopped', error_type=type(error).__name__)
        (out / 'error_private.txt').write_text(str(error))
    finally:
        if server is not None:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=45)
                except subprocess.TimeoutExpired:
                    os.killpg(server.pid, signal.SIGKILL)
                    server.wait(timeout=15)
                    state['server_forced_group_cleanup'] = True
            state['server_supervisor_exit_code'] = server.returncode
            runtime = read(storage / '.runtime/model_server.json')
            if runtime.get('supervisor_pid') == server.pid:
                write_json(out / 'server_final.json', runtime)
                state['server_stopped'] = runtime['status'] == 'stopped'
        if caffeinate is not None and caffeinate.poll() is None:
            caffeinate.terminate()
            caffeinate.wait(timeout=15)
        state['finished_at'] = now()
        save()
    if result is not None:
        # Saved scalar report only; raw prompt/completion bodies remain private.
        target = root / 'reports/P145_update_transport.json'
        public = dict(phase='P145', status=result['status'], rows=result['rows'],
            **summarize(result['rows'], result['status']), plan_sha256=sha(root / PLAN),
            server_stopped=state['server_stopped'], pipeline_status_sha256=sha(out / 'status.json'),
            source_inputs_selected_after_failure=True, full_task_replay=False,
            candidate_is_routine_transport_control=True, automatic_retries=0)
        with target.open('x') as f:
            json.dump(public, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')
    return 0 if state['status'] == 'complete' and state['server_stopped'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--expected-commit', required=True)
    args = parser.parse_args()
    def interrupted(*_):
        raise InterruptedError('P145_interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    raise SystemExit(run(args.storage_root.resolve(), ROOT, args.expected_commit))
