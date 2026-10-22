"""Own a finite P66 server and two fresh-task ordinary completion conditions."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from inference_cache_control import require_idle
from inspect_input_exposure import check_resume
from completion_control_comparison import PLAN, sources, can_continue_batch
from probe_inference_cache import get, live_identity
from probe_notice_calibration import confirmed_ci
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from run_completion_control import run_condition

PIPELINE = 'P66_pipeline_v01'


def interrupt(*_): raise KeyboardInterrupt('P66 interrupted')


def public_summary(summary):
    """Whitelist counts; private interpreter results may contain task values."""
    keys = ('run_id', 'task_id', 'arm', 'stop_reason', 'declared_complete', 'finished_at',
            'model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests',
            'unknown_effect_requests', 'unknown_effect_events', 'setup',
            'interface_preparation_wall_seconds', 'wall_seconds', 'full_wall_seconds',
            'history_formatting', 'explicit_stop', 'novel_method_claim',
            'controller_checks', 'controller_wall_seconds', 'controller_completion_attempts',
            'controller_declared_complete')
    result = {k: summary[k] for k in keys}
    session = summary['python_session']
    result['python'] = None if session is None else {
        'program_count': len(session['programs']), 'status': session['status'],
        'container_removed': session['container_removed']}
    return result


def hashes():
    paths = list((ROOT / 'scripts').glob('*.py')) + list((ROOT / 'tests').glob('test_*.py'))
    paths += [ROOT / p for p in (PLAN, 'configs/P24_generic_guidance_v01.json',
        'configs/P29_stateful_code_v01.json', 'configs/python_export_image_v01.json',
        'docs/experiments/P66_ordinary_completion.md')]
    return {str(p.relative_to(ROOT)): sha(p) for p in paths}


def idle(storage, seconds):
    began = time.monotonic()
    while True:
        if (storage / '.runtime/P66.stop').exists(): raise KeyboardInterrupt('stop file')
        try:
            require_idle(get('/slots')); return time.monotonic()-began
        except ValueError:
            if time.monotonic()-began >= seconds: raise TimeoutError('bounded idle wait')
            time.sleep(1)


def worker(storage):
    plan, original, tasks, tools = sources(storage)
    folder = storage / 'records/context_pilot' / PIPELINE
    parent = read(folder / 'status.json')
    if (parent['status'] != 'running' or parent['pipeline_pid'] != os.getppid()
            or parent['code_sha256'] != hashes()
            or parent['git_commit'] != subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()):
        raise ValueError('fixed owning parent required')
    target = ROOT / 'reports/P66_ordinary_completion.json'
    if target.exists(): raise FileExistsError('preserve original report')
    state = {'phase': 'P66', 'status': 'running', 'active': None, 'git_commit': parent['git_commit'],
        'code_sha256': parent['code_sha256'], 'plan_sha256': sha(ROOT / PLAN), 'ci': parent['ci'],
        'rows': [{'task_id': tid, 'arm': arm, 'run_id': rid, 'status': 'not_run'} for tid, arm, rid in plan['run_order']],
        'model_calls': 0, 'known_total_tokens': 0, 'unknown_usage_calls': 0,
        'api_requests': 0, 'evaluator_calls': 0,
        'reserved_scenarios_read': 0, 'novel_method_claim': False, 'started_at': datetime.now(timezone.utc).isoformat()}
    began = time.monotonic()
    def save():
        state['wall_seconds'] = time.monotonic()-began
        write_json(folder / 'worker_status.json', state)
    save()
    try:
        identity, end = live_identity(storage, original, plan['worker_timeout_seconds'])
        state.update(model_identity=identity, server_lease_end=end)
        for row in state['rows']:
            if (storage / '.runtime/P66.stop').exists(): raise KeyboardInterrupt('stop file')
            state['active'] = row['run_id']; save()
            idle(storage, plan['max_idle_wait_seconds'])
            current, _ = live_identity(storage, original, plan['max_wall_seconds']+plan['max_setup_seconds']+plan['max_evaluation_seconds']+120)
            if current != identity: raise ValueError('model server changed')
            summary = run_condition(storage, plan, original, tasks, tools, row['task_id'], row['arm'], row['run_id'])
            row.update(status='executed', summary=public_summary(summary))
            state['model_calls'] += summary['model_calls']
            state['known_total_tokens'] += summary['known_total_tokens']
            state['unknown_usage_calls'] += summary['unknown_usage_calls']
            state['api_requests'] += summary['api_requests']
            save()
            if not can_continue_batch(summary):
                raise RuntimeError('unsafe or inconsistent condition; stop remaining schedule')
            row['idle_wait_seconds'] = idle(storage, plan['max_idle_wait_seconds'])
            trial = storage / 'records/context_pilot' / row['run_id']
            state['evaluator_calls'] += 1; row['evaluation_attempted'] = True; save()
            result = subprocess.run([str(storage / '.runtime/appworld/venv/bin/python'),
                str(ROOT / 'scripts/evaluate_context_trial.py'), '--appworld-root',
                str(storage / '.runtime/appworld/r18_probe_01'), '--trial', str(trial)],
                capture_output=True, text=True, timeout=plan['max_evaluation_seconds'])
            (trial / 'evaluation_stdout_private.txt').write_text(result.stdout)
            (trial / 'evaluation_stderr_private.txt').write_text(result.stderr)
            if result.returncode: raise RuntimeError('single evaluation failed')
            evaluation = read(trial / 'evaluation.json')
            row['evaluation'] = {k: evaluation[k] for k in ('official_success', 'pass_count', 'fail_count',
                'evaluation_returned_to_model', 'execution_summary_sha256', 'appworld_version')}
            row['evaluation_sha256'] = sha(trial / 'evaluation.json')
            row['summary_sha256'] = sha(trial / 'summary.json')
            row['status'] = 'evaluated'; save()
        state['status'] = 'complete'
    except BaseException as error:
        state.update(status='stopped', error_type=type(error).__name__)
        (folder / 'worker_error_private.txt').write_text(str(error))
    finally:
        state['active'] = None; state['finished_at'] = datetime.now(timezone.utc).isoformat()
        save(); write_json(target, state)
    return 0 if state['status'] == 'complete' else 1


def pipeline(storage, expected_commit, ci_ids):
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    origin = subprocess.check_output(['git', 'remote', 'get-url', 'origin'], cwd=ROOT, text=True).strip()
    if (head != expected_commit or subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()
            or origin not in ('https://github.com/sophiria1225/AI-', 'https://github.com/sophiria1225/AI-.git')):
        raise ValueError('clean exact implementation in authorized repository required')
    resume = check_resume(storage); ci = confirmed_ci(head, ci_ids)
    plan, original, _, _ = sources(storage)
    if {k: plan[k] for k in ('server_max_lifetime_seconds', 'server_readiness_seconds', 'worker_timeout_seconds',
                            'max_evaluation_seconds', 'max_idle_wait_seconds')} != {
            'server_max_lifetime_seconds': 5280, 'server_readiness_seconds': 300, 'worker_timeout_seconds': 4800,
            'max_evaluation_seconds': 180, 'max_idle_wait_seconds': 60}:
        raise ValueError('fixed owning process bounds changed')
    out = storage / 'records/context_pilot' / PIPELINE; out.mkdir(exist_ok=False)
    state = {'phase': PIPELINE, 'status': 'starting', 'git_commit': head, 'ci': ci,
        'research_resume': resume, 'code_sha256': hashes(), 'pipeline_pid': os.getpid(),
        'started_at': datetime.now(timezone.utc).isoformat(), 'server_owned': False}
    server = child = None; began = time.monotonic()
    runtime_path = storage / '.runtime/model_server.json'
    def save():
        state['wall_seconds'] = time.monotonic()-began; write_json(out / 'status.json', state)
    def terminate(process, grace):
        if process is not None and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=15)
                state['forced_group_cleanup'] = True
    try:
        if (storage / '.runtime/P66.stop').exists(): raise KeyboardInterrupt('stop file')
        save()
        command = [sys.executable, str(ROOT / 'scripts/serve_research_model.py'), '--storage-root', str(storage),
            '--selection', original['model_selection'], '--ctx-size', '65536', '--cache-type-k', 'q8_0',
            '--cache-type-v', 'q8_0', '--max-seconds', str(plan['server_max_lifetime_seconds'])]
        with (out / 'server_supervisor.log').open('w') as log:
            server = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
        state.update(server_owned=True, server_supervisor_pid=server.pid); save()
        until = time.monotonic()+plan['server_readiness_seconds']
        while time.monotonic() < until:
            if (storage / '.runtime/P66.stop').exists(): raise KeyboardInterrupt('stop file')
            if server.poll() is not None: raise RuntimeError('owned server exited before readiness')
            if runtime_path.exists():
                runtime = read(runtime_path)
                if runtime.get('supervisor_pid') == server.pid and runtime['status'] == 'ready':
                    write_json(out / 'server_initial.json', runtime); break
            time.sleep(1)
        else: raise TimeoutError('server readiness deadline')
        state['status'] = 'running'; save()
        with (out / 'worker.log').open('w') as log:
            child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--worker',
                '--storage-root', str(storage)], stdout=log, stderr=log, start_new_session=True)
        state['worker_pid'] = child.pid; save()
        until = time.monotonic()+plan['worker_timeout_seconds']
        while child.poll() is None:
            if (storage / '.runtime/P66.stop').exists(): raise KeyboardInterrupt('stop file')
            if time.monotonic() >= until: raise TimeoutError('fixed worker lifetime')
            time.sleep(1)
        state['worker_exit_code'] = child.returncode
        if child.returncode: raise RuntimeError('comparison stopped; no replacement')
        state['status'] = 'complete'
    except BaseException as error:
        state.update(status='stopped', error_type=type(error).__name__)
        (out / 'error_private.txt').write_text(str(error))
    finally:
        terminate(child, 45); terminate(server, 45)
        if server is not None:
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
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--worker', action='store_true'); p.add_argument('--expected-commit')
    p.add_argument('--push-ci', type=int); p.add_argument('--pr-ci', type=int); args = p.parse_args()
    signal.signal(signal.SIGTERM, interrupt); signal.signal(signal.SIGINT, interrupt)
    raise SystemExit(worker(args.storage_root) if args.worker else
        pipeline(args.storage_root, args.expected_commit, [args.push_ci, args.pr_ci]))
