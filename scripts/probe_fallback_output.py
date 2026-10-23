"""Bounded P84 generations of archived P83 requests; generated actions stay inert."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import signal
import subprocess
import time

from fallback_output_replay import CASES, COUNTS, digest, equality_summary, output_fingerprints, request_for, reserve_tokens, schedule, validate_plan
from inference_cache_control import cache_measurement
from inspect_input_exposure import check_resume, frozen_sources
from local_llama import parse_response, post
from probe_inference_cache import live_identity
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from run_reasoning_history_comparison import wait_idle

PLAN = 'configs/P84_fallback_output_v01.json'
PREFLIGHT = 'reports/P84_initial_checks.json'


def sources(storage, root):
    plan = read(root / PLAN)
    validate_plan(plan)
    for name, expected in plan['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('fixed_source_changed:' + name)
    provenance = read(root / 'reports/P81_P83_results_provenance_20261024.json')
    for name, expected in provenance['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('closed_P81_P83_source_changed:' + name)
    report = read(root / plan['source_report'])
    if (report['status'] != 'complete' or report['completed_renderings'] != 6
            or not report['original_sources_unchanged']
            or not all(report['normalized_pair_equal'].values())
            or not all(report['native_reference_control_equal'].values())):
        raise ValueError('closed_all_six_P83_renderings_required')
    requests = {}
    for case, expected_count in zip(plan['cases'], COUNTS, strict=True):
        path = storage / plan['source_archive'] / (case['id'] + '_request_private.json')
        source = report['rendered'][case['id']]
        if (sha(path) != source['private_request_sha256']
                or sha(path) != case['source_request_sha256']
                or source['input_tokens'] != expected_count
                or case['rendered_prompt_sha256'] != source['prompt_sha256']
                or case['rendered_tokens_sha256'] != source['tokens_sha256']):
            raise ValueError('closed_saved_input_identity_changed')
        payload = request_for(read(path))
        if digest(payload) != case['cold_payload_sha256']:
            raise ValueError('fixed_cold_payload_changed')
        requests[case['id']] = payload
    if requests[CASES[2]] != requests[CASES[3]]:
        raise ValueError('identical_normalized_inputs_required')
    return plan, read(root / 'configs/P29_stateful_code_v01.json'), requests


def previous_session_closed(storage, plan):
    folder = storage / plan['required_closed_pipeline']
    pipeline = read(folder / 'status.json')
    if pipeline['status'] not in ('complete', 'stopped') or not pipeline.get('server_stopped'):
        raise ValueError('P82_pipeline_and_owned_server_must_be_closed')
    server = read(folder / 'server_final.json')
    if (server['status'] != 'stopped'
            or server['supervisor_pid'] != pipeline['server_supervisor_pid']):
        raise ValueError('P82_pipeline_and_owned_server_must_be_closed')
    record = Path(server['record_directory'])
    if not record.is_absolute():
        record = storage / record
    if read(record / 'summary.json') != server:
        raise ValueError('P82_final_owned_server_record_mismatch')
    for pid in {server['pid'], server['supervisor_pid']}:
        check = subprocess.run(['ps', '-p', str(pid), '-o', 'pid='], capture_output=True, text=True, timeout=10)
        if check.returncode != 1 or check.stdout.strip():
            raise ValueError('P82_owned_process_still_exists')
    return {'pipeline_sha256': sha(folder / 'status.json'),
            'server_final_sha256': sha(folder / 'server_final.json'), 'owned_processes_absent': True}


def frozen_hashes(root, plan):
    paths = list((root / 'scripts').glob('*.py')) + list((root / 'tests').glob('test_*.py'))
    paths += [root / p for p in (PLAN, 'docs/experiments/P84_fallback_output.md')]
    return {str(p.relative_to(root)): sha(p) for p in sorted(paths)}


def check_stop(storage):
    if (storage / '.runtime/P84.stop').exists():
        raise InterruptedError('P84_user_stop')


def preflight(storage, root):
    plan, original, requests = sources(storage, root)
    previous = previous_session_closed(storage, plan)
    target, folder = root / PREFLIGHT, storage / 'records/context_pilot/P84_preflight_v01'
    if target.exists() or folder.exists():
        raise FileExistsError('preserve_P84_preflight_attempts')
    hashes = frozen_hashes(root, plan)
    head = frozen_sources(root, tuple(hashes))
    check_stop(storage)
    identity, end = live_identity(storage, original, 360)
    folder.mkdir(parents=True)
    began = time.monotonic()
    result = dict(phase='P84_preflight', status='running', rows=[], git_commit=head,
        source_sha256=hashes, model_identity=identity, server_lease_end=end, P82_closure=previous,
        research_resume=check_resume(storage), input_count_requests=0, model_generations=0,
        environment_api_requests=0, evaluations=0, reserved_scenarios_read=0)
    def save():
        result['wall_seconds'] = time.monotonic() - began
        write_json(folder / 'status.json', result)
    try:
        save()
        for case, expected in zip(CASES, COUNTS, strict=True):
            check_stop(storage)
            remaining = plan['max_preflight_seconds'] - (time.monotonic() - began)
            if remaining <= 0:
                raise TimeoutError('P84_preflight_budget')
            row = dict(case=case, payload_sha256=digest(requests[case]), status='count_requested')
            result['rows'].append(row); result['input_count_requests'] += 1; save()
            start = time.monotonic()
            counted = post({'base_url': 'http://127.0.0.1:8011'}, '/v1/chat/completions/input_tokens',
                           requests[case], min(30, remaining))
            row.update(input_tokens=counted.get('input_tokens'), count_wall_seconds=time.monotonic() - start)
            if row['input_tokens'] != expected:
                raise ValueError('P84_actual_input_count_differs_from_closed_P83')
            row['status'] = 'counted'; save()
        result['reserved_total_tokens'] = reserve_tokens([r['input_tokens'] for r in result['rows']])
        result['status'] = 'complete'
    except Exception as error:
        result.update(status='stopped', error_type=type(error).__name__)
        (folder / 'error_private.txt').write_text(str(error))
    finally:
        save(); write_json(target, result)
    print({k: result.get(k) for k in ('status', 'input_count_requests', 'reserved_total_tokens', 'wall_seconds')})
    return 0 if result['status'] == 'complete' else 1


def run(storage, root):
    plan, original, requests = sources(storage, root)
    activation = read(root / PREFLIGHT)
    if (activation['status'] != 'complete' or activation['source_sha256'] != frozen_hashes(root, plan)
            or activation['P82_closure'] != previous_session_closed(storage, plan)):
        raise ValueError('successful_unchanged_P84_preflight_required')
    identity, end = live_identity(storage, original, plan['max_wall_seconds'] + 90)
    if identity != activation['model_identity']:
        raise ValueError('same_owned_runtime_required')
    folder = storage / 'records/context_pilot' / plan['batch_id']
    folder.mkdir(parents=True, exist_ok=False)
    write_json(folder / 'plan.json', plan); write_json(folder / 'preflight.json', activation)
    started = time.monotonic()
    rows = []
    state = dict(phase='P84', status='running', active=None, rows=rows,
        git_commit=activation['git_commit'], source_sha256=activation['source_sha256'],
        model_identity=identity, server_lease_end=end, started_at=datetime.now(timezone.utc).isoformat(),
        environment_api_requests=0, generated_programs_executed=0, evaluations=0,
        reserved_scenarios_read=0, automatic_retries=0, known_total_tokens=0, unknown_usage_calls=0)
    def save():
        state['wall_seconds'] = time.monotonic() - started
        state['model_calls_attempted'] = len(rows)
        write_json(folder / 'status.json', state)
    try:
        save()
        for item in schedule():
            check_stop(storage)
            remaining = plan['max_wall_seconds'] - (time.monotonic() - started)
            if remaining < plan['call_timeout_seconds'] + 75:
                raise TimeoutError('insufficient_full_call_and_idle_budget')
            current, _ = live_identity(storage, original, plan['call_timeout_seconds'] + 75)
            if current != identity:
                raise ValueError('runtime_identity_changed')
            case = next(c for c in plan['cases'] if c['id'] == item['case'])
            count, payload = case['expected_input_tokens'], requests[item['case']]
            if (state['known_total_tokens'] + count + plan['max_output_tokens'] > plan['max_total_tokens']
                    or digest(payload) != case['cold_payload_sha256']):
                raise ValueError('fixed_budget_or_payload_changed')
            call = folder / item['id']; call.mkdir()
            write_json(call / 'request.json', payload)
            state['active'] = item['id']
            row = {**item, 'status': 'attempting', 'input_tokens': None, 'output_tokens': None,
                   'request_sha256': sha(call / 'request.json'), 'payload_sha256': digest(payload),
                   **output_fingerprints({'status': 'error'})}
            rows.append(row); save()
            record = dict(status='error', input_tokens=None, output_tokens=None)
            began = time.monotonic()
            signal.alarm(plan['call_timeout_seconds'])
            try:
                raw = post({'base_url': 'http://127.0.0.1:8011'}, '/v1/chat/completions', payload,
                           plan['call_timeout_seconds'])
                write_json(call / 'raw_response.json', raw)
                record.update(parse_response(raw))
            except Exception as error:
                record['error_type'] = type(error).__name__
                (call / 'error_private.txt').write_text(str(error))
            finally:
                signal.alarm(0)
                record['wall_seconds'] = time.monotonic() - began
                write_json(call / 'response.json', record)
            row.update({k: record.get(k) for k in ('status', 'input_tokens', 'output_tokens', 'done_reason', 'wall_seconds')})
            row['response_sha256'] = sha(call / 'response.json')
            if record['status'] != 'ok':
                state['unknown_usage_calls'] += 1; save()
                raise ValueError('unknown_terminal_usage_no_replacement')
            state['known_total_tokens'] += record['input_tokens'] + record['output_tokens']; save()
            if record['output_tokens'] > plan['max_output_tokens'] or state['known_total_tokens'] > plan['max_total_tokens']:
                raise ValueError('observed_generation_exceeded_reserved_budget')
            row.update(output_fingerprints(record))
            row['cache'] = cache_measurement('cold_1', record, count)
            if not row['cache']['state_confirmed']:
                raise ValueError('input_reuse_detected')
            row['idle'] = wait_idle(storage, original, identity, plan['max_idle_seconds']); save()
            if not row['idle']['one_slot_idle']:
                raise ValueError('idle_not_confirmed')
            print({k: row[k] for k in ('id', 'case', 'repetition', 'status', 'input_tokens', 'output_tokens', 'done_reason')}, flush=True)
        state['status'] = 'complete'
    except Exception as error:
        state.update(status='stopped', error_type=type(error).__name__)
        (folder / 'error_private.txt').write_text(str(error))
    finally:
        signal.alarm(0)
        state['active'] = None
        state['equality_summary'] = equality_summary(rows)
        state['finished_at'] = datetime.now(timezone.utc).isoformat(); save()
    return 0 if state['status'] == 'complete' else 1


def interrupt(*_):
    raise InterruptedError('bounded_P84_generation_interrupted')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    for sig in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupt)
    raise SystemExit((preflight if args.preflight else run)(args.storage_root.resolve(), args.repo_root.resolve()))
