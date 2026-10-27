"""Own a finite P137 server lease and stop it after every success/failure path."""
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
from whole_task_remaining_late_obligations_p137 import PLAN
from run_whole_task_late_obligations_pipeline_p136 import checked_ci


def interrupt(*_):
    raise InterruptedError('P137 pipeline interrupted')


def run(storage, expected_commit):
    if (storage / '.runtime/P137.stop').exists():
        raise InterruptedError('explicit_P137_stop_before_server_start')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if head != expected_commit or subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise ValueError('clean fixed implementation required')
    resume = check_resume(storage)
    ci = checked_ci(ROOT, head)
    plan = read(ROOT / PLAN)
    deadline = datetime.fromisoformat(plan['deadline_jst']).timestamp()
    if time.time() + 15600 > deadline:
        raise ValueError('fixed_P137_lease_would_exceed_user_deadline')
    from run_whole_task_remaining_late_obligations_p137 import sources
    _, original, _, _ = sources(storage, ROOT)
    from run_whole_task_remaining_late_obligations_p137 import predecessor_closed
    predecessor = predecessor_closed(storage, ROOT)
    from run_whole_task_remaining_late_obligations_p137 import launch_predecessor_closed
    preceding_session = launch_predecessor_closed(storage)
    out = storage / 'records/context_pilot/P137_pipeline_v01'
    out.mkdir(parents=True, exist_ok=False)
    state = {'phase': 'P137_pipeline', 'status': 'starting', 'git_commit': head, 'ci': ci,
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
        if time.time() + 15600 > datetime.fromisoformat(plan['deadline_jst']).timestamp():
            raise ValueError('fixed_P137_lease_would_exceed_user_deadline_before_spawn')
        if (storage / '.runtime/P137.stop').exists():
            raise InterruptedError('explicit_P137_stop_before_spawn')
        with (out / 'server_supervisor.log').open('w') as log:
            server = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
        state['server_supervisor_pid'] = server.pid; state['server_owned'] = True; save()
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            if (storage / '.runtime/P137.stop').exists():
                raise InterruptedError('explicit_P137_stop_during_server_readiness')
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
        runner = [sys.executable, str(ROOT / 'scripts/run_whole_task_remaining_late_obligations_p137.py'),
                  '--storage-root', str(storage), '--repo-root', str(ROOT)]
        for mode, extra, timeout in [('preflight', ['--preflight'], 480),
                                     ('activation', ['--activate'], 60),
                                     ('batch', [], 12000)]:
            if (storage / '.runtime/P137.stop').exists():
                raise InterruptedError('explicit_P137_stop_before_stage')
            state['status'] = mode; save()
            began = time.monotonic(); child = None
            with (out / (mode + '.log')).open('w') as log:
                try:
                    child = subprocess.Popen(runner + extra, stdout=log, stderr=log, start_new_session=True)
                    state['stage_pid'] = child.pid; save()
                    code = child.wait(timeout=timeout)
                    state['stages'].append({'mode': mode, 'exit_code': code,
                        'wall_seconds': time.monotonic() - began})
                    save()
                    if code:
                        raise RuntimeError('P137 stage stopped; no retry')
                finally:
                    if child is not None and child.poll() is None:
                        child.terminate()
                        try:
                            child.wait(timeout=210)
                        except subprocess.TimeoutExpired:
                            os.killpg(child.pid, signal.SIGKILL)
                            child.wait(timeout=15)
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
