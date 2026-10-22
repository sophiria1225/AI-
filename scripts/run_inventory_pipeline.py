"""Own a finite P55 server lease and stop it after every success/failure path."""
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


def interrupt(*_):
    raise InterruptedError('P55 pipeline interrupted')


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
    return [{k: r[k] for k in ('id', 'head_sha', 'event', 'status', 'conclusion')} for r in selected]


def run(storage, expected_commit):
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if head != expected_commit or subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise ValueError('clean fixed implementation required')
    resume = check_resume(storage)
    ci = checked_ci(ROOT, head)
    plan = read(ROOT / 'configs/P55_inventory_comparison_v01.json')
    original = read(ROOT / plan['source_plan'])
    out = storage / 'records/context_pilot/P55_pipeline_v01'
    out.mkdir(parents=True, exist_ok=False)
    state = {'phase': 'P55_pipeline', 'status': 'starting', 'git_commit': head, 'ci': ci,
        'research_resume': resume, 'stages': [], 'started_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': sha(Path(__file__)), 'server_owned': False}
    runtime_path = storage / '.runtime/model_server.json'
    server = None
    started = time.monotonic()
    def save():
        state['wall_seconds'] = time.monotonic() - started
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
        runner = [sys.executable, str(ROOT / 'scripts/run_inventory_comparison.py'),
                  '--storage-root', str(storage), '--repo-root', str(ROOT)]
        for mode, extra, timeout in [('preflight', ['--preflight'], 360),
                                     ('activation', ['--activate'], 60),
                                     ('batch', [], plan['server_max_lifetime_seconds'] - 1200)]:
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
                        raise RuntimeError('P55 stage stopped; no retry')
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
