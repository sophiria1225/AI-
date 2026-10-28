"""One finite, explicitly authorized continuation after the P144 shutdown pause.

The old scientific plan and first two executions are immutable. This process
owns only a new server and the ten previously unstarted cells, in fixed order.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from api_error_comparison import disposition
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from run_whole_task_state_update_p144 import sources as original_sources
from run_whole_task_state_update_pipeline_p144 import checked_ci
from state_update_resume_config_p144r1 import REMAINING, cell_id, original_cell_id, remaining_ids
from state_update_resume_server_p144r1 import live_identity, wait_idle, LEASE_SECONDS

SPEC = 'configs/P144R1_continuation_v01.json'
PIPELINE = 'records/context_pilot/P144R1_pipeline_v01'
BATCH = 'records/context_pilot/P144R1_batch_v01'
AUTH = '.runtime/P144R1_user_resume_authorization_20261028.json'
RECOVERY = '.runtime/P144R1_saved_evaluation_recovery_20261028.json'
HANDOFF = '.runtime/P144_shutdown_pause_handoff_20261028.json'
STOP = '.runtime/P144R1.stop'
CELL_SECONDS = 2010


def now():
    return datetime.now(timezone.utc).isoformat()


def stop_check(storage):
    if (storage / STOP).exists():
        raise InterruptedError('explicit_P144R1_stop')


def validate_spec(spec):
    fixed = dict(phase='P144R1', inherited_plan='configs/P144_state_update_v01.json',
        remaining_run_ids=list(remaining_ids()),
        canonical_remaining_run_ids=[original_cell_id(n, m) for n, m in REMAINING],
        max_new_cells=10, max_new_model_calls=800, max_new_reserved_tokens=4500000,
        max_new_environment_api_requests=880, max_new_evaluator_calls=10,
        server_max_lifetime_seconds=21000, batch_timeout_seconds=20220,
        latest_launch_jst='2026-10-28T17:20:00+09:00',
        deadline_jst='2026-10-28T23:15:00+09:00',
        reporting_deadline_jst='2026-10-28T23:59:00+09:00',
        automatic_retries=0, regenerate_completed_cells=False,
        choose_conditions_from_outcomes=False, reserved_scenarios_read=0)
    if any(type(spec.get(k)) is not type(v) or spec[k] != v for k, v in fixed.items()):
        raise ValueError('fixed_ten_cell_continuation_changed')
    if LEASE_SECONDS != spec['server_max_lifetime_seconds']:
        raise ValueError('continuation_lease_mismatch')
    if 300 + 180 + 30 + spec['batch_timeout_seconds'] > LEASE_SECONDS:
        raise ValueError('complete_stage_reservations_exceed_lease')
    if datetime.fromisoformat(spec['latest_launch_jst']).timestamp() + LEASE_SECONDS > datetime.fromisoformat(spec['deadline_jst']).timestamp():
        raise ValueError('lease_exceeds_absolute_deadline')


def frozen_hashes(root):
    spec = read(root / SPEC)
    return {**spec['source_sha256'], SPEC: sha(root / SPEC)}


def verify_saved(storage, spec):
    for rel, key in ((AUTH, 'resume_authorization_sha256'),
                     (HANDOFF, 'shutdown_handoff_sha256'),
                     (RECOVERY, 'saved_evaluation_recovery_sha256')):
        if sha(storage / rel) != spec[key]:
            raise ValueError('resume_evidence_changed:' + rel)
    handoff, recovery = read(storage / HANDOFF), read(storage / RECOVERY)
    if (handoff['remaining_unstarted_conditions'] != spec['canonical_remaining_run_ids']
            or recovery['status'] != 'complete' or recovery['evaluator_attempts'] != 1
            or recovery['original_artifacts_unchanged'] is not True):
        raise ValueError('saved_execution_recovery_not_complete')
    for name, expected in handoff['operational_marker_sha256'].items():
        if sha(storage / '.runtime' / name) != expected:
            raise ValueError('original_closure_changed')
    for rid, files in handoff['preserved_trial_sha256'].items():
        trial = storage / 'records/context_pilot' / rid
        for rel, expected in files.items():
            if sha(trial / rel) != expected:
                raise ValueError('original_trial_changed')
        summary = read(trial / 'summary.json')
        dbs = storage / '.runtime/appworld/r18_probe_01/experiments/outputs' / rid / 'tasks' / summary['task_id'] / 'dbs'
        actual = {str(p.relative_to(dbs)): sha(p) for p in dbs.rglob('*') if p.is_file()}
        if actual != handoff['preserved_database_sha256'][rid]:
            raise ValueError('original_saved_world_changed')
    evaluated = storage / 'records/context_pilot' / recovery['run_id'] / 'evaluation.json'
    if sha(evaluated) != recovery['evaluation_sha256']:
        raise ValueError('recovered_evaluation_changed')
    if not (storage / '.runtime/P144.stop').exists():
        raise ValueError('historical_stop_marker_must_remain')


def sources(storage, root, *, permit_stopped=False):
    if root.resolve() != ROOT.resolve():
        raise ValueError('executing_continuation_repository_must_match')
    if not permit_stopped:
        stop_check(storage)
    spec = read(root / SPEC)
    validate_spec(spec)
    for rel, expected in spec['source_sha256'].items():
        if sha(root / rel) != expected:
            raise ValueError('continuation_source_changed:' + rel)
    if sha(root / spec['inherited_plan']) != spec['inherited_plan_sha256']:
        raise ValueError('original_scientific_plan_changed')
    verify_saved(storage, spec)
    return original_sources(storage, root)


def launch_boundary(storage, spec):
    stop_check(storage)
    validate_spec(spec)
    if time.time() > datetime.fromisoformat(spec['latest_launch_jst']).timestamp():
        raise ValueError('continuation_latest_launch_passed')
    if time.time() + LEASE_SECONDS > datetime.fromisoformat(spec['deadline_jst']).timestamp():
        raise ValueError('full_lease_does_not_fit_today')


def interrupt(*_):
    raise InterruptedError('P144R1_execution_interrupted')


@contextmanager
def retain_spawn_handle():
    """Deliver cancellation only after Popen's owned handle is retained."""
    pending = []
    signals = (signal.SIGTERM, signal.SIGINT)
    previous = {sig: signal.getsignal(sig) for sig in signals}
    # Caught handlers reset to defaults at exec; unlike a blocked signal mask,
    # this does not make the child ignore later SIGTERM during owned cleanup.
    for sig in signals:
        signal.signal(sig, lambda signum, frame: pending.append(signum))
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if pending:
            raise InterruptedError('P144R1_cancelled_after_retaining_spawn_handle')


def bounded_process(command, log_path, record, save, timeout, *, absolute_end, cleanup_seconds=90):
    child = None
    with log_path.open('x') as log:
        try:
            with retain_spawn_handle():
                child = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
                record.update(pid=child.pid, status='running', started_at=now(),
                              timed_out=False, forced_group_kill=False)
                save()
            record['returncode'] = child.wait(timeout=min(timeout, max(.001, absolute_end-time.time())))
        except BaseException as error:
            record.update(error_type=type(error).__name__, timed_out=isinstance(error, subprocess.TimeoutExpired))
            raise
        finally:
            if child is not None and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=cleanup_seconds)
                except subprocess.TimeoutExpired:
                    record['forced_group_kill'] = True
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=15)
            record.update(status='exited' if child else 'not_started',
                          returncode=child.poll() if child else None, ended_at=now())
            save()
    if record['returncode'] != 0:
        raise RuntimeError('continuation_stage_failed_no_retry')


def batch(storage, root):
    from state_update_resume_preflight_p144r1 import (PREFLIGHT, ACTIVATION,
        validate_preflight, validate_activation)
    plan, original, _, prepared = sources(storage, root)
    spec = read(root / SPEC)
    pre, activation = read(root / PREFLIGHT), read(root / ACTIVATION)
    validate_preflight(storage, root, pre, plan, original, prepared)
    validate_activation(storage, root, activation, pre)
    identity, lease_end = live_identity(storage, original, 10 * CELL_SECONDS)
    if identity != pre['model_identity']:
        raise ValueError('continuation_prepared_server_changed')
    folder = storage / BATCH
    folder.mkdir(exist_ok=False)
    state = dict(phase='P144R1', status='running', planned=list(remaining_ids()),
        completed=[], rows=[], active=None, started_at=now(), model_identity=identity,
        server_lease_end=lease_end, original_slots=spec['canonical_remaining_run_ids'])
    def save():
        state['updated_at'] = now()
        write_json(folder / 'status.json', state)
    absolute_end = datetime.fromisoformat(spec['deadline_jst']).timestamp()
    try:
        save()
        for n, mode in REMAINING:
            stop_check(storage)
            if time.time() + CELL_SECONDS > absolute_end:
                raise TimeoutError('complete_cell_does_not_fit_absolute_deadline')
            if live_identity(storage, original, CELL_SECONDS)[0] != identity:
                raise ValueError('continuation_server_changed')
            rid = cell_id(n, mode)
            trial = storage / 'records/context_pilot' / rid
            world = storage / '.runtime/appworld/r18_probe_01/experiments/outputs' / rid
            if trial.exists() or world.exists():
                raise FileExistsError('preserve_every_continuation_attempt')
            state['active'] = rid
            save()
            record = dict(run_id=rid, original_slot=original_cell_id(n, mode),
                wait_timeout_seconds=1920, returncode=None, status='starting',
                timed_out=False, forced_group_kill=False)
            exit_path = folder / (rid + '_worker_exit.json')
            def save_exit():
                write_json(exit_path, record)
            bounded_process([sys.executable, str(Path(__file__)), '--storage-root', str(storage),
                '--cell', str(n), '--arm', mode], folder / (rid + '_worker.log'),
                record, save_exit, 1920, absolute_end=absolute_end-60)
            result = read(trial / 'summary.json')
            row = {k: result[k] for k in ('run_id', 'task_id', 'stop_reason', 'model_calls',
                'known_total_tokens', 'unknown_usage_calls', 'api_requests', 'cleanup_confirmed')}
            row['original_slot'] = original_cell_id(n, mode)
            row['disposition'] = disposition(result)
            state['rows'].append(row)
            save()
            if row['disposition'] == 'stop_batch':
                raise ValueError('continuation_environment_or_runtime_failure')
            row['idle_recovery'] = wait_idle(storage, original, identity, 30)
            stop_check(storage)
            save()
            eval_record = dict(run_id=rid, status='starting', returncode=None,
                               timed_out=False, forced_group_kill=False)
            def save_eval():
                write_json(folder / (rid + '_evaluation_exit.json'), eval_record)
            bounded_process([str(storage / '.runtime/appworld/venv/bin/python'),
                str(root / 'scripts/evaluate_context_trial.py'), '--appworld-root',
                str(storage / '.runtime/appworld/r18_probe_01'), '--trial', str(trial)],
                folder / (rid + '_evaluation.log'), eval_record, save_eval, 60,
                absolute_end=absolute_end, cleanup_seconds=15)
            # Outcome is retained privately; it never selects subsequent cells.
            row['success'] = read(trial / 'evaluation.json')['official_success']
            state['completed'].append(rid)
            state['active'] = None
            save()
            print(json.dumps(dict(phase='P144R1', completed=len(state['completed']), total=10)), flush=True)
        state.update(status='complete', active=None)
    except BaseException as error:
        state.update(status='stopped', error_type=type(error).__name__)
        (folder / 'error_private.txt').write_text(str(error))
    finally:
        state.update(finished_at=now(),
            not_run=[rid for rid in state['planned'] if not (storage / 'records/context_pilot' / rid).exists()],
            unevaluated=[r['run_id'] for r in state['rows'] if r['run_id'] not in state['completed']])
        save()
    return 0 if state['status'] == 'complete' else 1


def pipeline(storage, root, expected_commit):
    spec = read(root / SPEC)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    if head != expected_commit or subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).strip():
        raise ValueError('clean_fixed_continuation_source_required')
    _, original, _, _ = sources(storage, root)
    ci = checked_ci(root, head)
    launch_boundary(storage, spec)
    for rid in remaining_ids():
        if ((storage / 'records/context_pilot' / rid).exists()
                or (storage / '.runtime/appworld/r18_probe_01/experiments/outputs' / rid).exists()):
            raise FileExistsError('continuation_namespace_used')
    out = storage / PIPELINE
    out.mkdir(exist_ok=False)
    state = dict(phase='P144R1_pipeline', status='starting', git_commit=head, ci=ci,
        source_sha256=frozen_hashes(root), spec_sha256=sha(root / SPEC),
        stages=[], started_at=now(), server_owned=False, server_stopped=False,
        resumed_after_user_shutdown=True, prior_session_continuous=False)
    server = caffeinate = None
    def save():
        state['updated_at'] = now()
        write_json(out / 'status.json', state)
    absolute_end = datetime.fromisoformat(spec['deadline_jst']).timestamp()
    try:
        save()
        with retain_spawn_handle():
            caffeinate = subprocess.Popen(['/usr/bin/caffeinate', '-i', '-m', '-w', str(os.getpid())],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            state['caffeinate_pid'] = caffeinate.pid
        launch_boundary(storage, spec)
        command = [sys.executable, str(root / 'scripts/serve_research_model_recovery.py'),
            '--storage-root', str(storage), '--selection', original['model_selection'],
            '--ctx-size', str(original['model']['num_ctx']), '--cache-type-k', 'q8_0',
            '--cache-type-v', 'q8_0', '--max-seconds', str(LEASE_SECONDS)]
        with (out / 'server_supervisor.log').open('x') as log:
            with retain_spawn_handle():
                server = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
                state.update(server_owned=True, server_supervisor_pid=server.pid)
                save()
        readiness_end = time.monotonic() + 300
        while time.monotonic() < readiness_end:
            stop_check(storage)
            if server.poll() is not None:
                raise RuntimeError('owned_continuation_server_exited')
            runtime = read(storage / '.runtime/model_server.json')
            if runtime.get('supervisor_pid') == server.pid and runtime.get('status') == 'ready':
                state['server_record_directory'] = runtime['record_directory']
                write_json(out / 'server_runtime.json', runtime)
                save()
                break
            time.sleep(1)
        else:
            raise TimeoutError('continuation_server_readiness_deadline')
        for mode, timeout in (('preflight', 180), ('activation', 30), ('batch', 20220)):
            stop_check(storage)
            if time.time() + timeout > absolute_end:
                raise TimeoutError('full_stage_does_not_fit_absolute_deadline')
            stage = dict(mode=mode, status='starting', returncode=None)
            state['stages'].append(stage)
            state['status'] = mode
            save()
            bounded_process([sys.executable, str(Path(__file__)), '--storage-root', str(storage),
                '--' + mode], out / (mode + '.log'), stage, save, timeout,
                absolute_end=absolute_end, cleanup_seconds=210)
        state['status'] = 'complete'
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
    # Reporting is data-only, once, after all owned model work is closed.
    report = dict(status='starting', started_at=now())
    report_path = out / 'reporting.json'
    write_json(report_path, report)
    try:
        if not state['server_stopped']:
            raise ValueError('server_closure_required_before_reporting')
        cmd = [sys.executable, str(root / 'scripts/audit_state_update_resume_p144r1.py'),
               '--storage-root', str(storage), '--repo-root', str(root)]
        bounded_process(cmd, out / 'closed_audit.log', report,
                        lambda: write_json(report_path, report), 900,
                        absolute_end=datetime.fromisoformat(spec['reporting_deadline_jst']).timestamp())
    except BaseException as error:
        report.update(status='failed', error_type=type(error).__name__)
        (out / 'reporting_error_private.txt').write_text(str(error))
    finally:
        report['finished_at'] = now()
        write_json(report_path, report)
    return 0 if state['status'] == 'complete' and state['server_stopped'] and report.get('returncode') == 0 else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--expected-commit')
    group = parser.add_mutually_exclusive_group()
    for mode in ('preflight', 'activation', 'batch'):
        group.add_argument('--' + mode, action='store_true')
    group.add_argument('--cell', type=int, choices=(1, 2, 3, 4))
    parser.add_argument('--arm')
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    storage = args.storage_root.resolve()
    if args.preflight or args.activation:
        from state_update_resume_preflight_p144r1 import preflight, activate
        (preflight if args.preflight else activate)(storage, ROOT)
        return 0
    if args.batch:
        return batch(storage, ROOT)
    if args.cell is not None:
        from state_update_resume_preflight_p144r1 import (PREFLIGHT, ACTIVATION,
            validate_preflight, validate_activation)
        from run_state_update_resume_cell_p144r1 import run_cell
        from whole_task_state_update_p144 import ERROR_POLICY
        rid = cell_id(args.cell, args.arm)
        plan, original, tools, prepared = sources(storage, ROOT)
        pre, activation = read(ROOT / PREFLIGHT), read(ROOT / ACTIVATION)
        validate_preflight(storage, ROOT, pre, plan, original, prepared)
        validate_activation(storage, ROOT, activation, pre)
        if time.time() + CELL_SECONDS > datetime.fromisoformat(read(ROOT / SPEC)['deadline_jst']).timestamp():
            raise TimeoutError('complete_worker_budget_does_not_fit_deadline')
        if live_identity(storage, original, CELL_SECONDS)[0] != pre['model_identity']:
            raise ValueError('worker_server_identity_changed')
        run_cell(storage, ROOT, plan, original, tools, prepared[args.cell-1], ERROR_POLICY,
                 rid, checkpoint_representation_mode=args.arm)
        return 0
    if not args.expected_commit:
        parser.error('--expected-commit required for server launch')
    return pipeline(storage, ROOT, args.expected_commit)


if __name__ == '__main__':
    raise SystemExit(main())
