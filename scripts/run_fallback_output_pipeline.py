"""Own a finite P84 model-only replay lease; no task environment is started."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from inspect_input_exposure import check_resume
from probe_fallback_output import check_stop, sources, previous_session_closed
from run_api_error_pipeline import checked_ci
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def interrupt(*_):
    raise InterruptedError('P84_pipeline_interrupted')


def run(storage, expected_commit):
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if head != expected_commit or subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise ValueError('clean_fixed_implementation_required')
    resume = check_resume(storage); check_stop(storage)
    ci = checked_ci(ROOT, head)
    plan, original, _ = sources(storage, ROOT)
    prior = previous_session_closed(storage, plan)
    out = storage / 'records/context_pilot/P84_pipeline_v01'
    out.mkdir(parents=True, exist_ok=False)
    state = {'phase': 'P84_pipeline', 'status': 'starting', 'git_commit': head, 'ci': ci,
        'research_resume': resume, 'P82_closure': prior, 'stages': [], 'started_at': datetime.now(timezone.utc).isoformat(),
        'pipeline_sha256': sha(Path(__file__)), 'server_owned': False}
    runtime_path = storage / '.runtime/model_server.json'
    server = None
    began = time.monotonic()
    def save():
        state['wall_seconds'] = time.monotonic() - began
        write_json(out / 'status.json', state)
    try:
        save()
        command = [sys.executable, str(ROOT / 'scripts/serve_research_model.py'),
            '--storage-root', str(storage), '--selection', original['model_selection'],
            '--ctx-size', '65536', '--cache-type-k', 'q8_0', '--cache-type-v', 'q8_0',
            '--max-seconds', str(plan['server_max_lifetime_seconds'])]
        with (out / 'server_supervisor.log').open('w') as log:
            server = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
        state['server_supervisor_pid'] = server.pid; state['server_owned'] = True; save()
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            check_stop(storage)
            if server.poll() is not None: raise RuntimeError('owned_server_exited_before_readiness')
            if runtime_path.exists():
                runtime = read(runtime_path)
                if runtime.get('supervisor_pid') == server.pid and runtime['status'] == 'ready':
                    state['server_record_directory'] = runtime['record_directory']
                    write_json(out / 'server_runtime.json', runtime)
                    break
            time.sleep(1)
        else:
            raise TimeoutError('owned_server_readiness_deadline')
        runner = [sys.executable, str(ROOT / 'scripts/probe_fallback_output.py'),
                  '--storage-root', str(storage), '--repo-root', str(ROOT)]
        for mode, extra, timeout in [('preflight', ['--preflight'], 360),
                                     ('generation', [], plan['max_wall_seconds'] + 90)]:
            check_stop(storage)
            state['status'] = mode; save()
            start = time.monotonic(); child = None
            with (out / (mode + '.log')).open('w') as log:
                try:
                    child = subprocess.Popen(runner + extra, stdout=log, stderr=log, start_new_session=True)
                    state['stage_pid'] = child.pid; save()
                    stage_deadline = time.monotonic() + timeout
                    while child.poll() is None:
                        check_stop(storage)
                        if time.monotonic() >= stage_deadline:
                            raise TimeoutError("P84_stage_deadline")
                        time.sleep(1)
                    code = child.returncode
                    state['stages'].append({'mode': mode, 'exit_code': code, 'wall_seconds': time.monotonic() - start})
                    save()
                    if code: raise RuntimeError('P84_stage_stopped_no_retry')
                finally:
                    if child is not None and child.poll() is None:
                        child.terminate()
                        try: child.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=15)
        state['status'] = 'complete'
    except Exception as error:
        state.update(status='stopped', error_type=type(error).__name__)
        (out / 'error_private.txt').write_text(str(error))
    finally:
        if server is not None:
            if server.poll() is None:
                server.terminate()
                try: server.wait(timeout=45)
                except subprocess.TimeoutExpired:
                    os.killpg(server.pid, signal.SIGKILL); server.wait(timeout=15)
                    state['server_forced_group_cleanup'] = True
            state['server_supervisor_exit_code'] = server.returncode
            if runtime_path.exists():
                runtime = read(runtime_path)
                if runtime.get('supervisor_pid') == server.pid:
                    write_json(out / 'server_final.json', runtime)
                    state['server_stopped'] = runtime['status'] == 'stopped'
        state['finished_at'] = datetime.now(timezone.utc).isoformat(); save()
    print({k: state.get(k) for k in ('status', 'server_stopped', 'wall_seconds')})
    return 0 if state['status'] == 'complete' and state.get('server_stopped') else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--expected-commit', required=True)
    a = p.parse_args()
    for sig in (signal.SIGTERM, signal.SIGINT): signal.signal(sig, interrupt)
    raise SystemExit(run(a.storage_root.resolve(), a.expected_commit))
