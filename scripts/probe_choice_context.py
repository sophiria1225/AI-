"""Bounded P101 generations of archived P83 requests; generated actions stay inert."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import signal
import subprocess
import time

from choice_context_replay import CASES, COUNTS, CHOICES, condition, conditions, digest, equality_summary, output_summary, request_for, reserve_tokens, schedule, validate_plan, input_comparisons
from probe_fallback_output import sources as archived_sources
from choice_context_inputs import render_inputs
from inference_cache_control import cache_measurement
from inspect_input_exposure import check_resume, frozen_sources
from local_llama import parse_response, post
from probe_inference_cache import live_identity
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from run_reasoning_history_comparison import wait_idle

PLAN = 'configs/P101_choice_context_v01.json'
PREFLIGHT = 'reports/P101_initial_checks.json'


def sources(storage, root):
    plan = read(root / PLAN)
    validate_plan(plan)
    if plan.get('execution_ready') is not True:
        raise ValueError('final_execution_plan_required')
    preparation_path=root/'configs/P101_choice_context_preparation_v01.json'
    preparation=read(preparation_path)
    validate_plan(preparation)
    if (plan.get('preparation_plan_sha256') != sha(preparation_path)
            or any(plan['source_sha256'].get(name) != expected
                   for name,expected in preparation['source_sha256'].items())):
        raise ValueError('predeclared_preparation_sources_must_be_preserved')
    for name, expected in plan['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('fixed_source_changed:' + name)
    old_plan, original, archived = archived_sources(storage, root)
    if plan['cases'] != old_plan['cases']:
        raise ValueError('all_six_original_source_bindings_required')
    requests = {condition(case,choice):request_for(archived[case],choice)
                for case in CASES for choice in CHOICES}
    for choice in CHOICES:
        if requests[condition(CASES[2],choice)] != requests[condition(CASES[3],choice)]:
            raise ValueError('identical_normalized_payloads_required')
    return plan, original, requests


def previous_session_closed(storage, plan):
    folder = storage / plan['required_closed_pipeline']
    pipeline = read(folder / 'status.json')
    if (pipeline['status'] != 'complete' or not pipeline.get('server_stopped')
            or pipeline['git_commit'] != plan['predecessor_executed_head']):
        raise ValueError('P99_complete_pipeline_and_owned_server_must_be_closed')
    server = read(folder / 'server_final.json')
    if server['status'] != 'stopped' or server['supervisor_pid'] != pipeline['server_supervisor_pid']:
        raise ValueError('P99_final_server_identity_differs')
    record = Path(server['record_directory'])
    if not record.is_absolute(): record = storage / record
    if read(record / 'summary.json') != server:
        raise ValueError('P99_final_owned_server_record_mismatch')
    for pid in {server['pid'],server['supervisor_pid']}:
        check = subprocess.run(['ps','-p',str(pid),'-o','pid='],capture_output=True,text=True,timeout=10)
        if check.returncode != 1 or check.stdout.strip():
            raise ValueError('P99_owned_process_still_exists')
    return {'pipeline_sha256':sha(folder/'status.json'),
            'server_final_sha256':sha(folder/'server_final.json'),'owned_processes_absent':True}


def frozen_hashes(root, plan):
    paths = list((root / 'scripts').glob('*.py')) + list((root / 'tests').glob('test_*.py'))
    paths += [root / p for p in (PLAN, 'docs/experiments/P101_choice_context.md')]
    return {str(p.relative_to(root)): sha(p) for p in sorted(paths)}


def check_stop(storage):
    if (storage / '.runtime/P101.stop').exists():
        raise InterruptedError('P101_user_stop')


def preflight(storage, root):
    plan, original, requests = sources(storage, root)
    previous = previous_session_closed(storage, plan)
    target, folder = root / PREFLIGHT, storage / 'records/context_pilot/P101_preflight_v01'
    if target.exists() or folder.exists():
        raise FileExistsError('preserve_P101_preflight_attempts')
    hashes = frozen_hashes(root, plan)
    head = frozen_sources(root, tuple(hashes))
    check_stop(storage)
    identity, end = live_identity(storage, original, 360)
    folder.mkdir(parents=True)
    began = time.monotonic()
    result = dict(phase='P101_preflight', status='running', rows=[], git_commit=head,
        source_sha256=hashes, model_identity=identity, server_lease_end=end, P99_closure=previous,
        rendering_operations=[],
        research_resume=check_resume(storage), input_count_requests=0, model_generations=0,
        environment_api_requests=0, evaluations=0, reserved_scenarios_read=0)
    def save():
        result['wall_seconds'] = time.monotonic() - began
        write_json(folder / 'status.json', result)
    try:
        save()
        rendered = render_inputs(storage,root,plan,requests,folder,
            read(storage/'.runtime/model_server.json'),check_stop,result['rendering_operations'],save,
            began+plan['max_preflight_seconds'])
        result['rendered'] = rendered
        result['input_comparisons'] = input_comparisons(rendered)
        counts = {}
        for key in conditions():
            check_stop(storage)
            remaining = plan['max_preflight_seconds'] - (time.monotonic() - began)
            if remaining <= 0: raise TimeoutError('P101_preflight_budget')
            row = dict(condition=key,payload_sha256=digest(requests[key]),status='count_requested')
            result['rows'].append(row);result['input_count_requests']+=1;save()
            start = time.monotonic()
            counted = post({'base_url':'http://127.0.0.1:8011'},'/v1/chat/completions/input_tokens',
                           requests[key],min(30,remaining))
            row.update(input_tokens=counted.get('input_tokens'),count_wall_seconds=time.monotonic()-start)
            if type(row['input_tokens']) is not int or row['input_tokens'] != rendered[key]['input_tokens']:
                raise ValueError('P101_server_count_differs_from_exact_rendering')
            counts[key]=row['input_tokens'];row['status']='counted';save()
        result['reserved_total_tokens']=reserve_tokens(counts)
        result['counts']=counts
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
            or activation['P99_closure'] != previous_session_closed(storage, plan)):
        raise ValueError('successful_unchanged_P101_preflight_required')
    identity, end = live_identity(storage, original, plan['max_wall_seconds'] + 90)
    if identity != activation['model_identity']:
        raise ValueError('same_owned_runtime_required')
    folder = storage / 'records/context_pilot' / plan['batch_id']
    folder.mkdir(parents=True, exist_ok=False)
    write_json(folder / 'plan.json', plan); write_json(folder / 'preflight.json', activation)
    started = time.monotonic()
    rows = []
    state = dict(phase='P101', status='running', active=None, rows=rows,
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
            count, payload = activation['counts'][item['condition']], requests[item['condition']]
            if (state['known_total_tokens'] + count + plan['max_output_tokens'] > plan['max_total_tokens']
                    or digest(payload) != next(r['payload_sha256'] for r in activation['rows'] if r['condition']==item['condition'])):
                raise ValueError('fixed_budget_or_payload_changed')
            call = folder / item['id']; call.mkdir()
            write_json(call / 'request.json', payload)
            state['active'] = item['id']
            row = {**item, 'status': 'attempting', 'input_tokens': None, 'output_tokens': None,
                   'request_sha256': sha(call / 'request.json'), 'payload_sha256': digest(payload),
                   **output_summary({'status': 'error'})}
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
            row.update(output_summary(record))
            row['cache'] = cache_measurement('cold_1', record, count)
            if not row['cache']['state_confirmed']:
                raise ValueError('input_reuse_detected')
            row['idle'] = wait_idle(storage, original, identity, plan['max_idle_seconds']); save()
            if not row['idle']['one_slot_idle']:
                raise ValueError('idle_not_confirmed')
            print({'completed_calls':len(rows),'planned_calls':len(schedule())},flush=True)
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
    raise InterruptedError('bounded_P101_generation_interrupted')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    for sig in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupt)
    raise SystemExit((preflight if args.preflight else run)(args.storage_root.resolve(), args.repo_root.resolve()))
