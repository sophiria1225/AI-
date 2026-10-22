"""Read-only accounting and equality audit of a closed P58 calibration."""
import argparse
from pathlib import Path
import subprocess

from inference_cache_control import cache_measurement
from local_llama import parse_response
from notice_calibration import compare, message_hash
from probe_notice_calibration import PLAN, PIPELINE, source_material
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def audit(storage, frozen):
    report = read(frozen / 'reports/P58_notice_calibration.json')
    plan, _, variants = source_material(storage)
    folder = storage / 'records/context_pilot' / plan['batch_id']
    pipeline = storage / 'records/context_pilot' / PIPELINE
    parent = read(pipeline / 'status.json')
    if (report['status'] not in ('complete', 'stopped') or read(folder / 'status.json') != report
            or parent['status'] not in ('complete', 'stopped') or report['plan'] != plan
            or report['git_commit'] != parent['git_commit'] or report['ci'] != parent['ci']
            or not parent['server_stopped']):
        raise ValueError('closed matching report and owned-server shutdown required')
    for path, digest in report['code_sha256'].items():
        if sha(frozen / path) != digest or sha(ROOT / path) != digest:
            raise ValueError('frozen implementation changed: ' + path)
    if ([r['wall_snapshot_seconds'] for r in report['rows']] != plan['schedule']
            or len({r['label'] for r in report['rows']}) != 4):
        raise ValueError('fixed planned four rows must be retained')
    if (report['input_count_requests'] > plan['max_tokenizer_requests']
            or any(report[k] for k in ('environment_api_requests', 'evaluator_calls', 'reserved_scenarios_read'))):
        raise ValueError('outside the non-executed probe')
    rows = []; attempted = known_tokens = unknown = 0
    for row in report['rows']:
        trial = folder / row['label']
        if not row['model_request_started']:
            if row['status'] != 'not_run': raise ValueError('invalid unattempted row')
            rows.append({**row, 'audit_status': 'not_run'}); continue
        attempted += 1
        request, response = read(trial / 'request.json'), read(trial / 'response.json')
        if (request != variants[row['wall_snapshot_seconds']]
                or sha(trial / 'request.json') != row['request_sha256']
                or sha(trial / 'response.json') != row['response_sha256']
                or any(response[k] != row[k] for k in ('status', 'input_tokens', 'output_tokens'))
                or response['wall_seconds'] != row['model_wall_seconds']):
            raise ValueError('request, response or accounting mismatch')
        source = {p.name: sha(p) for p in trial.glob('*.json')}
        if row['status'] != 'ok':
            if row['input_tokens'] is not None or row['output_tokens'] is not None:
                raise ValueError('unknown usage was imputed')
            unknown += 1
            rows.append({**row, 'audit_status': 'attempted_unknown_usage', 'source_sha256': source}); continue
        raw = read(trial / 'raw_response.json'); parsed = parse_response(raw)
        if any(parsed[k] != response[k] for k in parsed):
            raise ValueError('raw terminal response differs from parsed record')
        if (sha(trial / 'raw_response.json') != row['raw_response_sha256']
                or response['output_tokens'] > plan['max_output_tokens']):
            raise ValueError('raw response or fixed output cap differs')
        measured = cache_measurement('cold_1', response, plan['expected_input_tokens'])
        if (measured != row['cache_measurement'] or measured['state_confirmed'] != row['cache_confirmed']
                or message_hash(response['message']) != row['message_sha256']):
            raise ValueError('cache state or full-message comparison differs')
        known_tokens += response['input_tokens'] + response['output_tokens']
        rows.append({**row, 'audit_status': 'known_usage_checked', 'source_sha256': source})
    if (attempted != report['model_calls_attempted'] or known_tokens != report['known_total_tokens']
            or unknown != report['unknown_usage_calls'] or attempted > plan['max_calls']
            or known_tokens > plan['max_total_tokens'] or compare(report['rows']) != report['comparison']):
        raise ValueError('whole-probe accounting or equality classification differs')
    initial, final = (read(pipeline / name) for name in ('server_initial.json', 'server_final.json'))
    if (final['supervisor_pid'] != parent['server_supervisor_pid'] or final['status'] != 'stopped'
            or final['supervisor_pid'] != initial['supervisor_pid']):
        raise ValueError('server ownership or closure differs')
    for key in ('pid', 'supervisor_pid'):
        process = subprocess.run(['ps', '-p', str(final[key]), '-o', 'command='], text=True, capture_output=True)
        if process.returncode != 1 or process.stdout.strip():
            raise ValueError('recorded server process still exists')
    record = Path(final['record_directory'])
    if not record.is_absolute(): record = storage / record
    if read(record / 'summary.json') != final:
        raise ValueError('server summary changed')
    server_fields = ('status', 'started_at', 'wall_seconds', 'load_wall_seconds', 'exit_code',
        'sampled_peak_rss_bytes', 'peak_system_swap_bytes', 'model_revision', 'runtime', 'ctx_size',
        'cache_type_k', 'cache_type_v', 'memory_note')
    return {'phase': 'P58_audit', 'batch_status': report['status'], 'audit_errors': [],
        'all_four_planned_rows_accounted': True, 'rows': rows, 'comparison': report['comparison'],
        'model_calls_attempted': attempted, 'known_total_tokens': known_tokens, 'unknown_usage_calls': unknown,
        'input_count_requests': report['input_count_requests'], 'input_counts': report['input_counts'],
        'worker_wall_seconds': report['wall_seconds'], 'pipeline_wall_seconds': parent['wall_seconds'],
        'owned_server_processes_absent': True, 'server': {k: final[k] for k in server_fields},
        'source_report_sha256': sha(frozen / 'reports/P58_notice_calibration.json'),
        'source_plan_sha256': sha(frozen / PLAN), 'source_pipeline_sha256': sha(pipeline / 'status.json'),
        'source_server_sha256': sha(record / 'summary.json'), 'source_memory_sha256': sha(record / 'memory.jsonl'),
        'auditor_sha256': sha(Path(__file__)), 'additional_model_calls': 0,
        'additional_tokenizer_calls': 0, 'additional_environment_api_requests': 0,
        'additional_evaluator_calls': 0, 'reserved_scenarios_read': 0,
        'limits': ['One known second-call input, all new generations cold, unlike the historical warm calls.',
            'The frozen clock value is a counterfactual input, not the actual remaining calibration time.',
            'Full generated messages include reasoning; a difference need not imply different actions or task outcomes.',
            'No generated tool was executed, no independent task was added, and no original outcome was relabelled.',
            'No inference about historical cause, task quality, savings or a new method.']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--frozen-root', type=Path, required=True); args = p.parse_args()
    target = ROOT / 'reports/P58_notice_audit.json'
    if target.exists(): raise FileExistsError('preserve previous audit')
    result = audit(args.storage_root, args.frozen_root); write_json(target, result)
    print({k: result[k] for k in ('batch_status', 'model_calls_attempted', 'known_total_tokens', 'unknown_usage_calls', 'comparison')})
