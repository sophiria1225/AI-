"""Read and audit every planned P101 replay, including stopped/unattempted slots."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import signal
import time

from choice_context_replay import digest, equality_summary, output_summary, schedule, input_comparisons, conditions, reserve_tokens
from inference_cache_control import cache_measurement
from local_llama import parse_response
from probe_choice_context import PREFLIGHT, frozen_hashes, sources
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def audit_known_record(raw, response, row, expected_input, output_cap):
    parsed = parse_response(raw)
    if any(response.get(k) != v for k, v in parsed.items()):
        raise ValueError('parsed_response_differs_from_saved_raw')
    if parsed['output_tokens'] > output_cap:
        raise ValueError('output_cap_exceeded')
    measured = cache_measurement('cold_1', parsed, expected_input)
    if not measured['state_confirmed'] or row.get('cache') != measured:
        raise ValueError('cold_input_measurement_not_confirmed')
    fingerprints = output_summary(parsed)
    if any(row.get(k) != v for k, v in fingerprints.items()):
        raise ValueError('output_fingerprint_mismatch')
    if any(row.get(k) != parsed[k] for k in ('status', 'input_tokens', 'output_tokens', 'done_reason')):
        raise ValueError('usage_or_termination_mismatch')
    if row.get('idle', {}).get('one_slot_idle') is not True:
        raise ValueError('post_generation_idle_not_confirmed')
    return {**fingerprints, 'input_tokens': parsed['input_tokens'], 'output_tokens': parsed['output_tokens'],
        'done_reason': parsed['done_reason'], 'cache': measured,
        'known_total_tokens': parsed['input_tokens'] + parsed['output_tokens']}


def audit(storage, root):
    target = root / 'reports/P101_choice_context.json'
    if target.exists(): raise FileExistsError('preserve_P101_audit')
    plan, _, requests = sources(storage, root)
    pipeline_dir = storage / 'records/context_pilot/P101_pipeline_v01'
    pipeline = read(pipeline_dir / 'status.json')
    server = read(pipeline_dir / 'server_final.json')
    if (pipeline['status'] not in ('complete', 'stopped') or not pipeline.get('server_stopped')
            or server['status'] != 'stopped' or server['supervisor_pid'] != pipeline['server_supervisor_pid']):
        raise ValueError('closed_owned_pipeline_required')
    for key in ('pid', 'supervisor_pid'):
        p = subprocess.run(['ps', '-p', str(server[key]), '-o', 'command='], capture_output=True, text=True, timeout=10)
        if p.returncode != 1 or p.stdout.strip(): raise ValueError('owned_recorded_process_still_exists')
    runtime_records = Path(server['record_directory'])
    if not runtime_records.is_absolute(): runtime_records = storage / runtime_records
    if read(runtime_records / 'summary.json') != server: raise ValueError('server_summary_copy_changed')
    pre = read(root / PREFLIGHT)
    if pre['source_sha256'] != frozen_hashes(root, plan): raise ValueError('frozen_sources_changed')
    batch_dir = storage / 'records/context_pilot' / plan['batch_id']
    batch = read(batch_dir / 'status.json') if batch_dir.exists() else None
    rows, errors = [], []
    if pre['status'] == 'complete':
        if (pre['reserved_total_tokens'] != reserve_tokens(pre['counts'])
                or pre['input_comparisons'] != input_comparisons(pre['rendered'])):
            errors.append('complete_preflight_reservation_or_input_comparison_changed')
        if [x['condition'] for x in pre['rows']] != conditions():
            errors.append('all_twelve_preflight_counts_required')
        from probe_prompt_identity import render_summary
        for key in conditions():
            choice = key.rsplit('__',1)[1]
            folder = storage/'records/context_pilot/P101_preflight_v01'/('render_'+choice)
            rendered_path = folder/(key+'_rendered_private.json')
            expected = pre['rendered'][key]
            if (sha(rendered_path) != expected['private_rendered_sha256']
                    or render_summary(read(rendered_path)) != {k:v for k,v in expected.items() if k!='private_rendered_sha256'}
                    or expected['input_tokens'] != pre['counts'][key]):
                errors.append('rendered_private_receipt_mismatch:'+key)
            item = next(x for x in pre['rows'] if x['condition']==key)
            if (item['input_tokens'] != pre['counts'][key] or item['status']!='counted'
                    or item['payload_sha256'] != digest(requests[key])
                    or read(folder/(key+'_request_private.json')) != requests[key]):
                errors.append('counted_and_rendered_payload_mismatch:'+key)
    else:
        errors.append('preflight_not_complete_preserve_unattempted_slots')
    attempted = batch['rows'] if batch else []
    planned = schedule()
    if len(attempted) > 36 or any({k: r[k] for k in planned[i]} != planned[i] for i, r in enumerate(attempted[:36])):
        errors.append('planned_attempt_order_mismatch')
    known_total, unknown = 0, 0
    for i, item in enumerate(planned):
        row = {**item, 'source_context': 'P83_CSV_call_014', 'record_status': 'unattempted',
               'status': 'unattempted', 'input_tokens': None, 'output_tokens': None, **output_summary({'status': 'error'})}
        rows.append(row)
        if i >= len(attempted): continue
        folder = batch_dir / item['id']; recorded = attempted[i]
        response = None
        try:
            payload = read(folder / 'request.json')
            if (payload != requests[item['condition']]
                    or digest(payload) != recorded['payload_sha256']
                    or sha(folder / 'request.json') != recorded['request_sha256']):
                raise ValueError('actual_request_mismatch')
            response_path = folder / 'response.json'
            if not response_path.exists():
                row.update(record_status='unknown_missing_terminal_record', status='error'); unknown += 1
                continue
            response = read(response_path)
            if sha(response_path) != recorded['response_sha256']: raise ValueError('saved_response_hash_mismatch')
            row.update(record_status='attempted', status=response['status'],
                request_sha256=sha(folder / 'request.json'), response_sha256=sha(response_path),
                wall_seconds=response['wall_seconds'])
            if response['status'] != 'ok':
                row['record_status'] = 'unknown_usage'; unknown += 1
                if recorded['status'] != 'error' or recorded['input_tokens'] is not None or recorded['output_tokens'] is not None:
                    raise ValueError('unknown_usage_was_replaced')
                continue
            parsed = parse_response(read(folder / 'raw_response.json'))
            known_total += parsed['input_tokens'] + parsed['output_tokens']
            row.update(audit_known_record(read(folder / 'raw_response.json'), response, recorded,
                pre['counts'][item['condition']], plan['max_output_tokens']))
            row['raw_response_sha256'] = sha(folder / 'raw_response.json')
            row['record_status'] = 'audited'
        except Exception as error:
            errors.append({'id': item['id'], 'error_type': type(error).__name__, 'check': str(error) if isinstance(error, ValueError) else 'record_read_error'})
            row['record_status'] = 'audit_error'
    if batch:
        if known_total != batch['known_total_tokens']: errors.append('batch_known_total_mismatch')
        if unknown != batch['unknown_usage_calls']: errors.append('batch_unknown_usage_mismatch')
        if len(attempted) != batch['model_calls_attempted']: errors.append('batch_attempt_count_mismatch')
        if any(batch[k] for k in ('environment_api_requests', 'generated_programs_executed', 'evaluations', 'reserved_scenarios_read')):
            errors.append('forbidden_task_activity_recorded')
        if not errors and equality_summary(rows) != batch['equality_summary']:
            # Unattempted slots are shown publicly, but not counted as attempts.
            if equality_summary(rows[:len(attempted)]) != batch['equality_summary']:
                errors.append('equality_summary_mismatch')
    memory = [json.loads(line) for line in (runtime_records / 'memory.jsonl').read_text().splitlines()]
    all_complete = len(attempted) == 36 and not errors and all(r['record_status'] == 'audited' for r in rows)
    summary = equality_summary(rows[:len(attempted)])
    result = {'phase': 'P101', 'pipeline_status': pipeline['status'], 'batch_status': batch['status'] if batch else 'not_started',
        'rows': rows, 'audit_errors': errors, 'all_36_audited': all_complete,
        'model_calls_attempted': len(attempted), 'known_total_tokens': known_total, 'unknown_usage_calls': unknown,
        'equality_summary':summary,'input_rendering_comparisons':pre.get('input_comparisons'),
        'input_counts':pre.get('counts'),'rendering_operations':pre.get('rendering_operations'),
        'input_count_requests':pre.get('input_count_requests'),
        'local_saved_context_only':True,'independent_contexts':1,
        'static_submission_is_not_execution':True,
        'preflight_sha256': sha(root / PREFLIGHT), 'pipeline_status_sha256': sha(pipeline_dir / 'status.json'),
        'batch_status_sha256': sha(batch_dir / 'status.json') if batch else None,
        'source_sha256': pre['source_sha256'], 'source_request_sha256': {c['id']: c['source_request_sha256'] for c in plan['cases']},
        'server': {k: server[k] for k in ('status', 'stop_reason', 'started_at', 'wall_seconds', 'load_wall_seconds',
            'sampled_peak_rss_bytes', 'peak_system_swap_bytes', 'exit_code', 'model_revision', 'runtime', 'ctx_size',
            'cache_type_k', 'cache_type_v', 'memory_note')},
        'owned_processes_absent': True, 'baseline_system_swap_bytes': memory[0]['swap_used_bytes'],
        'server_summary_sha256': sha(runtime_records / 'summary.json'), 'memory_sha256': sha(runtime_records / 'memory.jsonl'),
        'pipeline_wall_seconds': pipeline['wall_seconds'], 'stages': pipeline['stages'],
        'generation_wall_seconds': sum(r.get('wall_seconds', 0) for r in rows),
        'timings_overlap': True, 'environment_api_requests': 0, 'generated_programs_executed': 0,
        'evaluations': 0, 'reserved_scenarios_read': 0, 'audit_additional_model_calls': 0,
        'private_reasoning_inspected_semantically': False, 'novel_method_claim': False,
        'task_quality_or_savings_measured': False, 'P81_historical_causal_effect_identified': False,
        'historical_warm_state_recreated': False, 'checked_at': datetime.now(timezone.utc).isoformat(),
        'auditor_sha256': sha(Path(__file__))}
    write_json(target, result)
    print({k: result[k] for k in ('all_36_audited', 'model_calls_attempted', 'known_total_tokens', 'unknown_usage_calls', 'audit_errors')})
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT); a = p.parse_args()
    root=a.repo_root.resolve()
    failure=root/'reports/P101_choice_context_audit_failure.json'
    if failure.exists() or (root/'reports/P101_choice_context.json').exists():
        raise FileExistsError('preserve_every_P101_audit_attempt')
    began=time.monotonic()
    def expired(*_):raise TimeoutError('finite_P101_audit_deadline')
    signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,180)
    try:
        result = audit(a.storage_root.resolve(), root)
    except BaseException as error:
        with failure.open('x') as stream:
            json.dump(dict(phase='P101_audit',status='failed',error_type=type(error).__name__,
                detail=str(error)[:300],wall_seconds=time.monotonic()-began,
                additional_model_calls=0,environment_API_requests=0,evaluations=0),stream,indent=2)
        raise
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    raise SystemExit(1 if result['audit_errors'] else 0)
