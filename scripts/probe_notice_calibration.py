"""Own one finite server and four non-executed counterfactual generations."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from budget_signal import digest
from inference_cache_control import cache_measurement
from inspect_input_exposure import check_resume
from local_llama import parse_response, post
from notice_calibration import compare, message_hash, requests
from probe_completion_scope import check_ci
from probe_inference_cache import live_identity
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

PLAN = 'configs/P58_notice_calibration_v01.json'
PIPELINE = 'P58_pipeline_v01'


class ExplicitStop(BaseException):
    pass


def stop(*_):
    raise ExplicitStop('explicit interruption')


def timeout(*_):
    raise TimeoutError('fixed request deadline')


def source_material(storage):
    plan = read(ROOT / PLAN)
    if (sha(ROOT / 'reports/P55_full_control_variation.json') != plan['source_variation_report_sha256']
            or plan['source_runs'] != ['P55_03_DETAILS_OMITTED_KEEP', 'P55_03_DETAILS_AND_LISTINGS_OMITTED_KEEP']
            or plan['source_call'] != 'call_002' or plan['batch_id'] != 'P58_notice_calibration_v01'
            or plan['server_max_lifetime_seconds'] != 1800 or plan['worker_timeout_seconds'] != 1260
            or plan['server_readiness_seconds'] != 300 or plan['count_timeout_seconds'] != 30
            or plan['expected_input_tokens'] != 15588):
        raise ValueError('fixed source, clocks or resource bounds changed')
    paths = [storage / 'records/context_pilot' / rid / plan['source_call'] / 'request.json'
             for rid in plan['source_runs']]
    if [sha(p) for p in paths] != plan['source_request_sha256']:
        raise ValueError('frozen historical requests changed')
    variants = requests([read(p) for p in paths], plan)
    if plan['max_calls'] * (plan['expected_input_tokens'] + plan['max_output_tokens']) > plan['max_total_tokens']:
        raise ValueError('all fixed requests must fit the token budget')
    return plan, read(ROOT / plan['source_plan']), variants


def code_hashes():
    paths = list((ROOT / 'scripts').glob('*.py')) + list((ROOT / 'tests').glob('test_*.py'))
    paths += [ROOT / p for p in (PLAN, 'configs/P29_stateful_code_v01.json',
                                'docs/experiments/P58_notice_calibration.md')]
    return {str(p.relative_to(ROOT)): sha(p) for p in paths}


def run_worker(storage):
    plan, original, variants = source_material(storage)
    parent = read(storage / 'records/context_pilot' / PIPELINE / 'status.json')
    if (parent['status'] != 'calibration' or parent['pipeline_pid'] != os.getppid()
            or parent['code_sha256'] != code_hashes()
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != parent['git_commit']):
        raise ValueError('fixed CI-checked owning parent required')
    folder = storage / 'records/context_pilot' / plan['batch_id']
    target = ROOT / 'reports/P58_notice_calibration.json'
    if folder.exists() or target.exists():
        raise FileExistsError('preserve all attempts, including failures')
    folder.mkdir()
    began = time.monotonic()
    state = {'phase': 'P58', 'status': 'preflight', 'plan': plan, 'git_commit': parent['git_commit'],
        'ci': parent['ci'], 'code_sha256': parent['code_sha256'], 'active': None,
        'started_at': datetime.now(timezone.utc).isoformat(), 'input_count_requests': 0,
        'input_counts': {}, 'environment_api_requests': 0, 'evaluator_calls': 0, 'reserved_scenarios_read': 0,
        'rows': [{'label': f'call_{i:03d}', 'wall_snapshot_seconds': seconds,
                  'status': 'not_run', 'model_request_started': False,
                  'input_tokens': None, 'output_tokens': None}
                 for i, seconds in enumerate(plan['schedule'], 1)]}
    identity = None

    def save():
        attempted = [r for r in state['rows'] if r['model_request_started']]
        known = [r for r in attempted if r['status'] == 'ok']
        state.update(model_calls_attempted=len(attempted),
            known_total_tokens=sum(r['input_tokens'] + r['output_tokens'] for r in known),
            unknown_usage_calls=len(attempted) - len(known), wall_seconds=time.monotonic() - began)
        write_json(folder / 'status.json', state)

    save()
    try:
        identity, end = live_identity(storage, original, plan['max_wall_seconds'] + 60)
        state.update(model_identity=identity, server_lease_end=end)
        for seconds, payload in variants.items():
            if (storage / '.runtime/P58.stop').exists(): raise ExplicitStop('stop file')
            state['input_count_requests'] += 1; save()
            start = time.monotonic(); signal.alarm(plan['count_timeout_seconds'])
            try:
                count = post(original['model'], '/v1/chat/completions/input_tokens', payload,
                             plan['count_timeout_seconds'])
            finally:
                signal.alarm(0)
            if count.get('input_tokens') != plan['expected_input_tokens']:
                raise ValueError('fixed input count differs')
            state['input_counts'][str(seconds)] = {'input_tokens': count['input_tokens'],
                'wall_seconds': time.monotonic() - start, 'request_digest': digest(payload)}
            save()
        state['status'] = 'running'; save()
        for row in state['rows']:
            if (storage / '.runtime/P58.stop').exists(): raise ExplicitStop('stop file')
            if parent['code_sha256'] != code_hashes() or source_material(storage)[2] != variants:
                raise ValueError('frozen implementation or original source changed')
            remaining = plan['max_wall_seconds'] - (time.monotonic() - began)
            if remaining < plan['call_timeout_seconds'] + 10:
                raise TimeoutError('no full remaining request reservation')
            if (state['known_total_tokens'] + plan['expected_input_tokens'] + plan['max_output_tokens']
                    > plan['max_total_tokens']):
                raise ValueError('token reservation limit')
            current, _ = live_identity(storage, original, plan['call_timeout_seconds'] + 10)
            if current != identity: raise ValueError('owned server identity changed')
            trial = folder / row['label']; trial.mkdir()
            payload = variants[row['wall_snapshot_seconds']]
            write_json(trial / 'request.json', payload)
            row.update(status='in_progress', model_request_started=True)
            state['active'] = row['label']; save()
            response = {'status': 'error', 'input_tokens': None, 'output_tokens': None}
            started = time.monotonic(); signal.alarm(plan['call_timeout_seconds'])
            fatal = None
            try:
                raw = post(original['model'], '/v1/chat/completions', payload, plan['call_timeout_seconds'])
                write_json(trial / 'raw_response.json', raw)
                response.update(parse_response(raw))
            except BaseException as error:
                response['error_type'] = type(error).__name__
                (trial / 'error_private.txt').write_text(str(error))
                if isinstance(error, ExplicitStop): fatal = error
            finally:
                signal.alarm(0)
                response['wall_seconds'] = time.monotonic() - started
                write_json(trial / 'response.json', response)
                row.update(status=response['status'], input_tokens=response['input_tokens'],
                    output_tokens=response['output_tokens'], model_wall_seconds=response['wall_seconds'],
                    request_sha256=sha(trial / 'request.json'), response_sha256=sha(trial / 'response.json'))
                save()
            if fatal is not None: raise fatal
            if response['status'] != 'ok': raise ValueError('unknown terminal usage; no retry')
            measured = cache_measurement('cold_1', response, plan['expected_input_tokens'])
            row.update(cache_confirmed=measured['state_confirmed'], cache_measurement=measured,
                cached_input_tokens=response['cached_input_tokens'], finish_reason=response['done_reason'],
                message_sha256=message_hash(response['message']), raw_response_sha256=sha(trial / 'raw_response.json'))
            save()
            print(json.dumps({k: row[k] for k in ('label', 'wall_snapshot_seconds', 'input_tokens',
                'output_tokens', 'cache_confirmed', 'message_sha256')}), flush=True)
            if not row['cache_confirmed']: raise ValueError('nonzero observed input cache')
            if response['output_tokens'] > plan['max_output_tokens']:
                raise ValueError('backend exceeded fixed output cap')
        state['status'] = 'complete'
    except BaseException as error:
        state.update(status='stopped', error_type=type(error).__name__)
        (folder / 'error_private.txt').write_text(str(error))
    finally:
        signal.alarm(0)
        state['active'] = None
        state['comparison'] = compare(state['rows'])
        state['finished_at'] = datetime.now(timezone.utc).isoformat()
        save(); write_json(target, state)
    return 0 if state['status'] == 'complete' else 1


def run_pipeline(storage, expected_commit, ci_ids):
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    origin = subprocess.check_output(['git', 'remote', 'get-url', 'origin'], cwd=ROOT, text=True).strip()
    if (head != expected_commit or subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()
            or origin not in ('https://github.com/sophiria1225/AI-', 'https://github.com/sophiria1225/AI-.git')):
        raise ValueError('clean exact implementation in the authorized repository required')
    resume = check_resume(storage); ci = check_ci(head, ci_ids)
    plan, original, _ = source_material(storage)
    out = storage / 'records/context_pilot' / PIPELINE; out.mkdir(exist_ok=False)
    state = {'phase': 'P58_pipeline', 'status': 'starting', 'git_commit': head, 'ci': ci,
        'research_resume': resume, 'code_sha256': code_hashes(), 'pipeline_pid': os.getpid(),
        'started_at': datetime.now(timezone.utc).isoformat(), 'server_owned': False}
    started = time.monotonic(); server = child = None
    runtime_path = storage / '.runtime/model_server.json'
    def save():
        state['wall_seconds'] = time.monotonic() - started
        write_json(out / 'status.json', state)
    def terminate(process, grace):
        if process is not None and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=15)
                state['forced_group_cleanup'] = True
    try:
        if (storage / '.runtime/P58.stop').exists(): raise ExplicitStop('stop file')
        save()
        command = [sys.executable, str(ROOT / 'scripts/serve_research_model.py'), '--storage-root', str(storage),
            '--selection', original['model_selection'], '--ctx-size', '65536', '--cache-type-k', 'q8_0',
            '--cache-type-v', 'q8_0', '--max-seconds', str(plan['server_max_lifetime_seconds'])]
        with (out / 'server_supervisor.log').open('w') as log:
            server = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
        state.update(server_owned=True, server_supervisor_pid=server.pid); save()
        deadline = time.monotonic() + plan['server_readiness_seconds']
        while time.monotonic() < deadline:
            if (storage / '.runtime/P58.stop').exists(): raise ExplicitStop('stop file')
            if server.poll() is not None: raise RuntimeError('owned server exited before readiness')
            if runtime_path.exists():
                runtime = read(runtime_path)
                if runtime.get('supervisor_pid') == server.pid and runtime['status'] == 'ready':
                    write_json(out / 'server_initial.json', runtime); break
            time.sleep(1)
        else: raise TimeoutError('server readiness deadline')
        state['status'] = 'calibration'; save()
        with (out / 'worker.log').open('w') as log:
            child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--worker',
                '--storage-root', str(storage)], stdout=log, stderr=log, start_new_session=True)
        state['worker_pid'] = child.pid; save()
        until = time.monotonic() + plan['worker_timeout_seconds']
        while child.poll() is None:
            if (storage / '.runtime/P58.stop').exists(): raise ExplicitStop('stop file')
            if time.monotonic() >= until: raise TimeoutError('fixed worker wall budget')
            time.sleep(1)
        state['worker_exit_code'] = child.returncode
        if child.returncode: raise RuntimeError('calibration stopped; no replacement')
        state['status'] = 'complete'
    except BaseException as error:
        state.update(status='stopped', error_type=type(error).__name__)
        (out / 'error_private.txt').write_text(str(error))
    finally:
        terminate(child, 15); terminate(server, 45)
        if server is not None:
            state['server_supervisor_exit_code'] = server.returncode
            if runtime_path.exists():
                runtime = read(runtime_path)
                if runtime.get('supervisor_pid') == server.pid:
                    write_json(out / 'server_final.json', runtime)
                    state['server_stopped'] = runtime['status'] == 'stopped'
        state['finished_at'] = datetime.now(timezone.utc).isoformat(); save()
    print(json.dumps({k: state.get(k) for k in ('status', 'server_stopped', 'wall_seconds')}))
    return 0 if state['status'] == 'complete' and state.get('server_stopped') else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--worker', action='store_true'); p.add_argument('--expected-commit')
    p.add_argument('--push-ci', type=int); p.add_argument('--pr-ci', type=int); args = p.parse_args()
    signal.signal(signal.SIGALRM, timeout); signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    raise SystemExit(run_worker(args.storage_root) if args.worker else
        run_pipeline(args.storage_root, args.expected_commit, [args.push_ci, args.pr_ci]))
