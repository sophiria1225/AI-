"""Own a finite P144 server lease and stop it after every success/failure path."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from inspect_input_exposure import check_resume
from run_handoff_factors import ROOT, read, sha
from run_context_comparison import write_json
from state_update_server_identity_p144 import LEASE_SECONDS


def interrupt(*_):
    raise InterruptedError('P144 pipeline interrupted')


def checked_ci(root, head):
    repository = 'sophiria1225/AI-'
    origin = subprocess.check_output(['git', 'remote', 'get-url', 'origin'], cwd=root, text=True).strip()
    if origin not in ('https://github.com/' + repository, 'https://github.com/' + repository + '.git'):
        raise ValueError('wrong publication repository')
    runs = json.loads(subprocess.check_output(['gh', 'api',
        'repos/' + repository + '/actions/runs?head_sha=' + head + '&per_page=30'], text=True))['workflow_runs']
    selected = [r for r in runs if r['head_sha'] == head and r['path'] == '.github/workflows/checks.yml']
    if ({r['event'] for r in selected} != {'push', 'pull_request'}
            or any(r['status'] != 'completed' or r['conclusion'] != 'success' for r in selected)):
        raise ValueError('both exact-head CI events must have passed')
    from probe_notice_calibration import confirmed_ci
    return confirmed_ci(head, [r['id'] for r in selected])


def validate_timing_limits(plan):
    """The twelve full cell budgets must fit without silently shortening a stage."""
    lease = plan.get('server_max_lifetime_seconds')
    batch = plan.get('batch_timeout_seconds')
    if (type(lease) is not int or lease != LEASE_SECONDS or lease > 24900
            or type(batch) is not int or not 12 * 2010 <= batch
            or 300 + 180 + 30 + batch > lease):
        raise ValueError('fixed_P144_all_twelve_stage_budgets_do_not_fit_lease')
    latest = datetime.fromisoformat(plan['latest_launch_jst'])
    end = datetime.fromisoformat(plan['deadline_jst'])
    if (latest.tzinfo is None or end.tzinfo is None
            or latest != datetime.fromisoformat('2026-10-28T16:15:00+09:00')
            or end != datetime.fromisoformat('2026-10-28T23:15:00+09:00')
            or latest.timestamp() + lease > end.timestamp()):
        raise ValueError('fixed_P144_user_deadlines_required')


def launch_boundary(storage, plan, resume):
    validate_timing_limits(plan)
    if (storage / '.runtime/P144.stop').exists():
        raise InterruptedError('explicit_P144_stop_before_spawn')
    if check_resume(storage) != resume:
        raise ValueError('P144_resumption_changed_before_spawn')
    if time.time() > datetime.fromisoformat(plan['latest_launch_jst']).timestamp():
        raise ValueError('fixed_P144_latest_launch_passed')
    if time.time() + plan['server_max_lifetime_seconds'] > datetime.fromisoformat(plan['deadline_jst']).timestamp():
        raise ValueError('fixed_P144_lease_would_exceed_user_deadline_before_spawn')


def run(storage, expected_commit):
    from whole_task_state_update_p144 import PLAN
    if (storage / '.runtime/P144.stop').exists():
        raise InterruptedError('explicit_P144_stop_before_server_start')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if head != expected_commit or subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise ValueError('clean fixed implementation required')
    resume = check_resume(storage)
    ci = checked_ci(ROOT, head)
    plan = read(ROOT / PLAN)
    validate_timing_limits(plan)
    deadline = datetime.fromisoformat(plan['deadline_jst']).timestamp()
    absolute_deadline = deadline
    if time.time() > datetime.fromisoformat(plan['latest_launch_jst']).timestamp():
        raise ValueError('fixed_P144_latest_launch_passed')
    if time.time() + plan['server_max_lifetime_seconds'] > deadline:
        raise ValueError('fixed_P144_lease_would_exceed_user_deadline')
    from run_whole_task_state_update_p144 import sources
    _, original, _, _ = sources(storage, ROOT)
    from run_whole_task_state_update_p144 import predecessor_closed
    predecessor = predecessor_closed(storage, ROOT)
    preceding_session = predecessor
    out = storage / 'records/context_pilot/P144_pipeline_v01'
    out.mkdir(parents=True, exist_ok=False)
    state = {'phase': 'P144_pipeline', 'status': 'starting', 'git_commit': head, 'ci': ci,
        'research_resume': resume, 'predecessor_closure': predecessor, 'launch_predecessor_closure': preceding_session, 'stages': [], 'started_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': sha(Path(__file__)), 'server_owned': False}
    runtime_path = storage / '.runtime/model_server.json'
    server = None
    started = time.monotonic()
    def save():
        state['wall_seconds'] = time.monotonic() - started
        write_json(out / 'status.json', state)
    try:
        save()
        command = [sys.executable, str(ROOT / 'scripts/serve_research_model_recovery.py'),
            '--storage-root', str(storage), '--selection', original['model_selection'],
            '--ctx-size', '65536', '--cache-type-k', 'q8_0', '--cache-type-v', 'q8_0',
            '--max-seconds', str(plan['server_max_lifetime_seconds'])]
        launch_boundary(storage, plan, resume)
        with (out / 'server_supervisor.log').open('w') as log:
            server = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
        state['server_supervisor_pid'] = server.pid; state['server_owned'] = True; save()
        deadline = time.monotonic() + min(300, max(0, absolute_deadline-time.time()))
        while time.monotonic() < deadline:
            if time.time() >= absolute_deadline:
                raise TimeoutError('P144_absolute_model_deadline_during_readiness')
            if (storage / '.runtime/P144.stop').exists():
                raise InterruptedError('explicit_P144_stop_during_server_readiness')
            if server.poll() is not None:
                raise RuntimeError('owned server exited before readiness')
            if runtime_path.exists():
                runtime = read(runtime_path)
                if runtime.get('supervisor_pid') == server.pid and runtime['status'] == 'ready':
                    state['server_record_directory'] = runtime['record_directory']
                    write_json(out / 'server_runtime.json', runtime)
                    break
            time.sleep(1)
        else:
            raise TimeoutError('owned server readiness deadline')
        runner = [sys.executable, str(ROOT / 'scripts/run_whole_task_state_update_p144.py'),
                  '--storage-root', str(storage), '--repo-root', str(ROOT)]
        for mode, extra, timeout in [('preflight', ['--preflight'], 180),
                                     ('activation', ['--activate'], 30),
                                     ('batch', [], plan['batch_timeout_seconds'])]:
            if (storage / '.runtime/P144.stop').exists():
                raise InterruptedError('explicit_P144_stop_before_stage')
            if time.time() + timeout > absolute_deadline:
                raise ValueError('full_P144_stage_would_exceed_absolute_deadline')
            state['status'] = mode; save()
            began = time.monotonic(); child = None
            stage = {'mode': mode, 'exit_code': None, 'pid': None, 'status': 'starting',
                     'wait_timeout_seconds': timeout, 'timed_out': False, 'forced_group_kill': False}
            state['stages'].append(stage)
            with (out / (mode + '.log')).open('w') as log:
                try:
                    child = subprocess.Popen(runner + extra, stdout=log, stderr=log, start_new_session=True)
                    stage.update(pid=child.pid, status='running')
                    state['stage_pid'] = child.pid; save()
                    code = child.wait(timeout=min(timeout, max(0.001, absolute_deadline-time.time())))
                    stage.update(exit_code=code, status='exited', wall_seconds=time.monotonic()-began)
                    save()
                    if code:
                        raise RuntimeError('P144 stage stopped; no retry')
                except BaseException as error:
                    if time.time() >= absolute_deadline and server is not None and server.poll() is None:
                        server.terminate()
                    stage.update(error_type=type(error).__name__, timed_out=isinstance(error, subprocess.TimeoutExpired))
                    raise
                finally:
                    if child is not None and child.poll() is None:
                        child.terminate()
                        try:
                            child.wait(timeout=min(210, max(0.001, absolute_deadline-time.time())))
                        except subprocess.TimeoutExpired:
                            if time.time() >= absolute_deadline and server is not None and server.poll() is None:
                                server.terminate()
                            stage['forced_group_kill'] = True
                            os.killpg(child.pid, signal.SIGKILL)
                            child.wait(timeout=15)
                    stage.update(status='exited' if child is not None else 'not_started',
                                 exit_code=child.poll() if child is not None else None,
                                 wall_seconds=time.monotonic()-began)
                    save()
        state['status'] = 'complete'
    except Exception as error:
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
            if runtime_path.exists():
                runtime = read(runtime_path)
                if runtime.get('supervisor_pid') == server.pid:
                    write_json(out / 'server_final.json', runtime)
                    state['server_stopped'] = runtime['status'] == 'stopped'
        state['finished_at'] = datetime.now(timezone.utc).isoformat()
        save()
    print(json.dumps({k: state.get(k) for k in ('status', 'server_stopped', 'wall_seconds')}))
    return 0 if state['status'] == 'complete' and state.get('server_stopped') else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--expected-commit', required=True)
    args = p.parse_args()
    signal.signal(signal.SIGTERM, interrupt); signal.signal(signal.SIGINT, interrupt)
    raise SystemExit(run(args.storage_root.resolve(), args.expected_commit))
