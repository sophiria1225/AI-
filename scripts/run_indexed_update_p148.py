"""Fixed seed357 replication of all eight P147 task/mode cells.

Reuse the frozen candidate and inherited three-probe evidence without new probe
generations. Retain all outcomes, unknown costs and unstarted cells. No retry.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
import signal
import subprocess
import sys
import time

from api_error_comparison import disposition, task_snapshot
from budget_observation import notification
from checkpoint_attempt_usage import attempt_usage
from receipt_reasoning_history import digest
from public_display import CODE_TOOLS
from residual_output_budget import admission
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from run_state_update_resume_p144r1 import bounded_process, retain_spawn_handle
from run_whole_task_state_update_p144 import sources as old_sources
from run_whole_task_state_update_pipeline_p144 import checked_ci
from run_indexed_update_p147 import probe_gate as inherited_probe_gate
from indexed_update_config_p148 import (MODES, TASKS, ERROR_POLICY, cell_id,
    run_order, worker_config, validate_plan)
from indexed_update_server_p148 import live_identity, wait_idle, LEASE_SECONDS, MODEL_DEADLINE_JST, SERVER_SHUTDOWN_RESERVE_SECONDS
from tool_choice_local_llama import count_input, payload_for
from whole_task_state_update_p144 import initial_conversation

PLAN = 'configs/P148_indexed_update_v01.json'
PIPELINE = 'records/context_pilot/P148_pipeline_v01'
BATCH = 'records/context_pilot/P148_batch_v01'
CELL_SECONDS = 2160


def now():
    return datetime.now(timezone.utc).isoformat()


def stop_check(storage):
    if (storage / '.runtime/P148.stop').exists():
        raise InterruptedError('explicit_P148_stop')


def sources(storage, root):
    plan = read(root / PLAN)
    validate_plan(plan)
    for name, expected in plan['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('P148_source_changed:' + name)
    for name, expected in plan['private_source_sha256'].items():
        if sha(storage / name) != expected:
            raise ValueError('P148_private_source_changed')
    old, original, tools, prepared = old_sources(storage, root)
    if plan['known_tasks'] != old['known_tasks'] or len(prepared) != 4:
        raise ValueError('same_four_known_tasks_required')
    return plan, original, tools, prepared


def predecessor(storage, plan):
    folder = storage / 'records/context_pilot/P147_pipeline_v01'
    state, final = read(folder/'status.json'), read(folder/'server_final.json')
    batch = read(storage/'records/context_pilot/P147_batch_v01/status.json')
    probe = read(storage/'records/context_pilot/P147_probe_v01/status.json')
    audit = read(storage/'.runtime/P147_closed_independent_20261029.json')
    expected = [row['run_id'].replace('P148','P147') for row in plan['schedule']]
    if (state['status'] != 'complete' or state.get('server_stopped') is not True
            or final['status'] != 'stopped' or final.get('exit_code') != 0
            or final['supervisor_pid'] != state['server_supervisor_pid']
            or batch['status'] != 'complete' or batch['completed'] != expected
            or [r['run_id'] for r in batch['rows']] != expected
            or any(type(r.get('success')) is not bool or r.get('unknown_usage_calls') != 0
                or r.get('cleanup_confirmed') is not True for r in batch['rows'])
            or audit.get('audit_status') != 'pass_closed_records_consistent'
            or audit.get('source_head') != state['git_commit']
            or not inherited_probe_gate(probe['rows'], probe['status'])['probe_gate_passed']):
        raise ValueError('closed_audited_P147_and_three_valid_saved_probes_required')
    # Global P147 cost reduction failed. It is deliberately not rewritten as a pass.
    if batch['development_gate_met'] is not False:
        raise ValueError('fixed_P147_primary_result_changed')
    for key in ('pid','supervisor_pid'):
        if type(final.get(key)) is not int or final[key] <= 0:
            raise ValueError('positive_previous_owned_pid_required')
        check = subprocess.run(['ps','-p',str(final[key]),'-o','pid='],capture_output=True,text=True,timeout=10)
        if check.returncode != 1 or check.stdout.strip():
            raise ValueError('previous_owned_process_still_present')
    return dict(phase='P147', pipeline_sha256=sha(folder/'status.json'),
        final_sha256=sha(folder/'server_final.json'),
        private_audit_sha256=sha(storage/'.runtime/P147_closed_independent_20261029.json'),
        inherited_probe_gate_passed=True, inherited_probe_known_total_tokens=36838,
        inherited_full_task_development_gate_met=False, new_probe_generations=0,
        prior_results_pooled=False)


def preflight(storage, root, plan, original, prepared, identity):
    folder = storage / 'records/context_pilot/P148_preflight_v01'
    folder.mkdir(exist_ok=False)
    rows = []
    for number, item in enumerate(prepared, 1):
        pair = []
        for mode in MODES:
            stop_check(storage)
            config = worker_config(original, plan, item['task_id'], ERROR_POLICY, cell_id(number, mode), mode)
            base, formatting = initial_conversation(original, item['public_task']).for_model()
            if formatting != {'text_fallback_turns': 0, 'paged_spans': 0}:
                raise ValueError('unchanged_initial_conversation_required')
            supplied, visible = notification(base, task_snapshot(config, [], 0, 0), 'not_exposed')
            cfg = dict(config['model'], temperature=config['agent_temperature'],
                seed=config['seed'], num_predict=config['max_output_tokens'], cache_prompt=False)
            request = payload_for(cfg, supplied, CODE_TOOLS)
            write_json(folder / (cell_id(number, mode) + '_request_private.json'), request)
            value = count_input(cfg, supplied, CODE_TOOLS, timeout=30)
            decision = admission(config['max_total_tokens'], value['input_tokens'],
                                 cfg['num_predict'], cfg['num_ctx'], 'residual')
            if not decision['admitted']:
                raise ValueError('P148_initial_input_not_admitted')
            row = dict(run_id=cell_id(number, mode), request_sha256=digest(request),
                       input_tokens=value['input_tokens'], visible_state=visible)
            rows.append(row)
            pair.append(row)
        if any(pair[0][k] != pair[1][k] for k in ('request_sha256', 'input_tokens', 'visible_state')):
            raise ValueError('paired_initial_inputs_differ')
    if live_identity(storage, original, CELL_SECONDS + 120)[0] != identity:
        raise ValueError('P148_prepared_server_changed')
    result = dict(phase='P148_preflight', status='pass', rows=rows,
        input_count_requests=8, model_generations=0, environment_api_calls=0, evaluator_calls=0)
    write_json(folder / 'status.json', result)
    return result


def summarize(rows, status):
    order = run_order()
    expected = [cell_id(n, m) for n, m in order]
    usage_valid = lambda r: all(type(r.get(k)) is int and r[k] >= 0
        for k in ('known_total_tokens', 'unknown_usage_calls', 'model_calls', 'api_requests'))
    contract = len(rows) == 8 and all(
        r.get('run_id') == cell_id(n,m) and r.get('task_slot') == n
        and r.get('task_id') == TASKS[n-1] and r.get('mode') == m
        and r.get('comparison_arm') == ('TR' if m == MODES[0] else 'UPDATE_INDEXED')
        and usage_valid(r) for r,(n,m) in zip(rows,order))
    complete = (status == 'complete' and contract
        and all(type(r.get('success')) is bool and r.get('unknown_usage_calls') == 0
                and r.get('cleanup_confirmed') is True for r in rows))
    totals = {mode: sum(r['known_total_tokens'] for r in rows
        if r.get('mode') == mode and type(r.get('known_total_tokens')) is int
        and r['known_total_tokens'] >= 0) for mode in MODES}
    pairs = []
    for n in range(1, 5):
        found = {r.get('mode'): r for r in rows if r.get('task_slot') == n}
        a, b = found.get(MODES[0]), found.get(MODES[1])
        both = bool(a and b and type(a.get('success')) is bool and type(b.get('success')) is bool)
        pairs.append(dict(task_slot=n, task_id=TASKS[n-1],
            TR_success=a.get('success') if a else None,
            UPDATE_INDEXED_success=b.get('success') if b else None,
            both_successful=both and a['success'] and b['success'],
            success_loss=both and a['success'] and not b['success'],
            difference=(b['known_total_tokens']-a['known_total_tokens']) if complete else None,
            actual_changed_old_known_actor_calls=b.get('actual_changed_old_known_actor_calls', 0) if b else 0))
    evidence = complete and any(p['both_successful'] and p['actual_changed_old_known_actor_calls'] > 0 for p in pairs)
    common = sum(p['difference'] for p in pairs if p['both_successful']) if complete else None
    qualifies = bool(complete and evidence and not any(p['success_loss'] for p in pairs)
        and totals[MODES[1]] < totals[MODES[0]] and common < 0)
    return dict(all_eight_evaluated_known_usage=complete, all_eight_row_contracts_valid=bool(contract), paired_results=pairs,
        known_token_subtotals=totals,
        total_tokens_by_mode=totals if complete else {mode: None for mode in MODES},
        paired_successful_token_difference=common, development_gate_met=qualifies,
        statistical_noninferiority_established=False, general_quality_preservation_established=False,
        novelty_established=False, independent_unseen_tasks=False,
        automatic_retries=0, selected_candidate_from_P145_results=False)


def cleanup_owned(server, caffeinate, storage, out, state):
    errors = []
    if server is not None:
        try:
            if server.poll() is None:
                server.terminate()
                server.wait(timeout=45)
        except BaseException as error:
            errors.append('server_stop:' + type(error).__name__)
        try:
            if server.poll() is None:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait(timeout=15)
                state['server_forced_group_cleanup'] = True
            state['server_supervisor_exit_code'] = server.poll()
        except BaseException as error:
            errors.append('server_fallback:' + type(error).__name__)
        try:
            runtime = read(storage / '.runtime/model_server.json')
            if runtime.get('supervisor_pid') != server.pid:
                raise ValueError('owned_server_final_identity_required')
            write_json(out / 'server_final.json', runtime)
            state['server_stopped'] = runtime['status'] == 'stopped' and server.poll() is not None
        except BaseException as error:
            errors.append('server_final:' + type(error).__name__)
    if caffeinate is not None:
        try:
            if caffeinate.poll() is None:
                caffeinate.terminate()
                caffeinate.wait(timeout=15)
        except BaseException as error:
            errors.append('caffeinate_stop:' + type(error).__name__)
        try:
            if caffeinate.poll() is None:
                caffeinate.kill()
                caffeinate.wait(timeout=5)
            state['caffeinate_stopped'] = caffeinate.poll() is not None
        except BaseException as error:
            errors.append('caffeinate_fallback:' + type(error).__name__)
    state['cleanup_errors'] = errors
    if errors or state.get('server_stopped') is not True:
        state['status'] = 'stopped'
    state['finished_at'] = now()
    write_json(out / 'status.json', state)


def retain_worker_attempt(trial, row, record):
    """Keep paid evidence even when the worker exits before its final summary."""
    row['worker_exit_status'] = record.get('status')
    row['worker_exit_code'] = record.get('returncode')
    try:
        if (trial / 'summary.json').exists():
            result = read(trial / 'summary.json')
            if result['run_id'] != row['run_id'] or result['task_id'] != row['task_id']:
                raise ValueError('worker_summary_identity_mismatch')
            row.update({k: result[k] for k in ('stop_reason', 'model_calls', 'known_total_tokens',
                'unknown_usage_calls', 'api_requests', 'cleanup_confirmed')})
            row.update(disposition=disposition(result), summary_sha256=sha(trial / 'summary.json'),
                usage_coverage_known=True,
                actual_changed_old_known_actor_calls=result.get('state_update_control', {}).get('actual_changed_old_known_actor_calls', 0))
        elif (trial / 'admissions.json').exists():
            terminal_path = trial / 'terminal_usage.json'
            if not terminal_path.exists():
                terminal_path = trial / 'usage.json'
            calls = read(terminal_path) if terminal_path.exists() else []
            attempts = attempt_usage(SimpleNamespace(calls=calls, admissions=read(trial / 'admissions.json')))
            known = [r for r in attempts if r['status'] == 'ok']
            if any(type(r.get(k)) is not int or r[k] < 0 for r in known for k in ('input_tokens','output_tokens')):
                raise ValueError('invalid_partial_terminal_usage')
            row.update(model_calls=len(attempts), known_total_tokens=sum(r['input_tokens']+r['output_tokens'] for r in known),
                       unknown_usage_calls=len(attempts)-len(known), usage_coverage_known=True)
    except Exception as error:
        row['attempt_read_error_type'] = type(error).__name__
        row['usage_coverage_known'] = False
    if record.get('returncode') != 0:
        row['disposition'] = 'stop_batch'


def batch(storage, root, plan, original, identity, lease_end):
    folder = storage / BATCH
    folder.mkdir(exist_ok=False)
    state = dict(phase='P148', status='running', planned=[cell_id(n,m) for n,m in run_order()],
                 completed=[], rows=[], not_started=[], active=None, started_at=now())
    def save():
        state['updated_at'] = now()
        write_json(folder / 'status.json', state)
    absolute_end = min(datetime.fromisoformat(lease_end).timestamp() - 120,
        datetime.fromisoformat(MODEL_DEADLINE_JST).timestamp() - 180)
    try:
        save()
        for n, mode in run_order():
            stop_check(storage)
            if time.time() + CELL_SECONDS > absolute_end:
                raise TimeoutError('full_P148_cell_does_not_fit_lease')
            if live_identity(storage, original, CELL_SECONDS + 60)[0] != identity:
                raise ValueError('same_P148_owned_server_required')
            rid = cell_id(n, mode)
            trial = storage / 'records/context_pilot' / rid
            world = storage / '.runtime/appworld/r18_probe_01/experiments/outputs' / rid
            if trial.exists() or world.exists():
                raise FileExistsError('preserve_every_P148_attempt')
            state['active'] = rid
            save()
            record = dict(run_id=rid, status='starting', returncode=None)
            row = dict(run_id=rid, task_id=TASKS[n-1], task_slot=n, mode=mode,
                comparison_arm='TR' if mode == MODES[0] else 'UPDATE_INDEXED',
                stop_reason='worker_not_completed', model_calls=None, known_total_tokens=0,
                unknown_usage_calls=None, api_requests=None, cleanup_confirmed=False,
                usage_coverage_known=False, disposition='stop_batch', success=None)
            state['rows'].append(row)
            save()
            try:
                bounded_process([sys.executable, str(root / 'scripts/run_indexed_update_p148.py'),
                    '--storage-root', str(storage), '--cell', str(n), '--arm', mode],
                    folder / (rid + '_worker.log'), record,
                    lambda: write_json(folder / (rid + '_worker_exit.json'), record),
                    1920, absolute_end=absolute_end - 60)
            finally:
                retain_worker_attempt(trial, row, record)
                save()
            if row['disposition'] == 'stop_batch':
                raise ValueError('P148_environment_or_runtime_failure')
            if row.get('unknown_usage_calls') != 0:
                raise ValueError('P148_unknown_usage_stops_later_model_dispatch')
            row['idle_recovery'] = wait_idle(storage, original, identity, 30)
            stop_check(storage)
            ev = dict(run_id=rid, status='starting', returncode=None)
            bounded_process([str(storage / '.runtime/appworld/venv/bin/python'),
                str(root / 'scripts/evaluate_context_trial.py'), '--appworld-root',
                str(storage / '.runtime/appworld/r18_probe_01'), '--trial', str(trial)],
                folder / (rid + '_evaluation.log'), ev,
                lambda: write_json(folder / (rid + '_evaluation_exit.json'), ev),
                60, absolute_end=absolute_end, cleanup_seconds=15)
            row.update(success=read(trial / 'evaluation.json')['official_success'],
                       evaluation_sha256=sha(trial / 'evaluation.json'))
            state['completed'].append(rid)
            state['active'] = None
            save()
            print(json.dumps(dict(phase='P148', completed=len(state['completed']), total=8)), flush=True)
        state['status'] = 'complete'
    except BaseException as error:
        state.update(status='stopped', error_type=type(error).__name__)
        (folder / 'error_private.txt').write_text(str(error))
    finally:
        attempted = {r['run_id'] for r in state['rows']}
        state['not_started'] = [dict(run_id=rid, status='not_started',
            reason=state.get('error_type','not_reached'), model_dispatched=False)
            for rid in state['planned'] if rid not in attempted]
        state.update(finished_at=now(), **summarize(state['rows'], state['status']))
        save()
    return state


def server_seconds_at(epoch):
    # The fixed supervisor stops its model within 30 seconds after its lease.
    # Reserve 120 seconds, and recheck the actual supervisor start before any generation.
    remaining = int(datetime.fromisoformat(MODEL_DEADLINE_JST).timestamp()-epoch)
    seconds = min(LEASE_SECONDS, remaining-SERVER_SHUTDOWN_RESERVE_SECONDS)
    if seconds < CELL_SECONDS + 720:
        raise TimeoutError('P148_full_cell_and_startup_do_not_fit_model_deadline')
    return seconds


def run(storage, root, head):
    if (subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()!=head
            or subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip()):
        raise ValueError('clean_fixed_P148_commit_required')
    stop_check(storage)
    plan, original, _, prepared = sources(storage,root)
    previous = predecessor(storage,plan)
    ci = checked_ci(root,head)
    out = storage/PIPELINE
    out.mkdir(exist_ok=False)
    state = dict(phase='P148_pipeline',status='starting',started_at=now(),git_commit=head,
        plan_sha256=sha(root/PLAN),ci=ci,predecessor=previous,server_owned=False,server_stopped=False,
        operational_model_deadline_jst=MODEL_DEADLINE_JST,full_task_stage_started=False)
    def save():
        write_json(out/'status.json',state)
    server = caffeinate = None
    result = None
    try:
        state['server_max_seconds']=server_seconds_at(time.time())
        save()
        with retain_spawn_handle():
            caffeinate=subprocess.Popen(['/usr/bin/caffeinate','-i','-m','-w',str(os.getpid())],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        command=[sys.executable,str(root/'scripts/serve_research_model_recovery.py'),
            '--storage-root',str(storage),'--selection',original['model_selection'],
            '--ctx-size','65536','--cache-type-k','q8_0','--cache-type-v','q8_0',
            '--max-seconds',str(state['server_max_seconds'])]
        stop_check(storage)
        with (out/'server_supervisor.log').open('x') as log:
            with retain_spawn_handle():
                server=subprocess.Popen(command,stdout=log,stderr=log,start_new_session=True)
                state.update(server_owned=True,server_supervisor_pid=server.pid)
                save()
        limit=time.monotonic()+300
        while time.monotonic()<limit:
            stop_check(storage)
            if server.poll() is not None:
                raise RuntimeError('P148_server_exited')
            runtime=read(storage/'.runtime/model_server.json')
            if runtime.get('supervisor_pid')==server.pid and runtime['status']=='ready':
                state.update(server_record_directory=runtime['record_directory'],status='preflight')
                write_json(out/'server_runtime.json',runtime)
                save()
                break
            time.sleep(1)
        else:
            raise TimeoutError('P148_server_readiness_timeout')
        identity,end=live_identity(storage,original,CELL_SECONDS+420)
        state.update(model_identity=identity,server_lease_end=end)
        save()
        from run_indexed_update_cell_p148 import _deadline
        with _deadline(time.monotonic()+plan['preflight_timeout_seconds']):
            preflight(storage,root,plan,original,prepared,identity)
        state.update(status='batch',full_task_stage_started=True)
        save()
        result=batch(storage,root,plan,original,identity,end)
        state['status']=result['status']
    except BaseException as error:
        state.update(status='stopped',error_type=type(error).__name__)
        (out/'error_private.txt').write_text(str(error))
    finally:
        cleanup_owned(server,caffeinate,storage,out,state)
    rows=result['rows'] if result is not None else []
    attempted={row['run_id'] for row in rows}
    not_started=result['not_started'] if result is not None else [
        dict(run_id=cell_id(n,m),status='not_started',reason=state.get('error_type','not_reached'),
             model_dispatched=False) for n,m in run_order() if cell_id(n,m) not in attempted]
    full=summarize(rows,state['status'])
    public=dict(phase='P148',status=state['status'],batch_status=result['status'] if result else 'not_started',
        rows=rows,not_started=not_started,**full,pipeline_status_sha256=sha(out/'status.json'),
        inherited_probe_evidence=previous,new_probe_generations=0,
        overall_known_total_tokens=sum(full['known_token_subtotals'].values()),
        plan_sha256=sha(root/PLAN),server_stopped=state['server_stopped'],model_seed=357,
        operational_model_deadline_jst=MODEL_DEADLINE_JST,prior_results_pooled=False)
    with (root/'reports/P148_comparison.json').open('x') as f:
        json.dump(public,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.write('\n')
    return 0 if state['status']=='complete' and state['server_stopped'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--expected-commit')
    parser.add_argument('--cell', type=int)
    parser.add_argument('--arm', choices=MODES)
    args = parser.parse_args()
    def interrupted(*_):
        raise InterruptedError('P148_interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    storage = args.storage_root.resolve()
    if args.cell is not None:
        from run_indexed_update_cell_p148 import run_cell
        stop_check(storage)
        plan, original, tools, prepared = sources(storage, ROOT)
        if args.cell not in range(1,5) or args.arm not in MODES:
            raise ValueError('fixed_P148_cell_required')
        _, end = live_identity(storage, original, CELL_SECONDS + 120)
        if time.time()+CELL_SECONDS > min(datetime.fromisoformat(end).timestamp()-120,
                datetime.fromisoformat(MODEL_DEADLINE_JST).timestamp()-180):
            raise TimeoutError('full_P148_child_budget_does_not_fit_deadline')
        item = prepared[args.cell-1]
        run_cell(storage, ROOT, plan, original, tools, item, ERROR_POLICY,
            cell_id(args.cell,args.arm), checkpoint_representation_mode=args.arm)
    else:
        if not args.expected_commit:
            raise ValueError('expected_commit_required')
        raise SystemExit(run(storage, ROOT, args.expected_commit))
