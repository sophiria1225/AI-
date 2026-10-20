"""Cross-check completed P2 runs against raw backend records and frozen files."""
import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def memory_window(run, summary):
    runtime_path = run / 'server_runtime.json'
    if not runtime_path.exists() or not summary.get('started_at'):
        return None
    runtime = read(runtime_path)
    path = ROOT / runtime['record_directory'] / 'memory.jsonl'
    start = datetime.datetime.fromisoformat(summary['started_at'])
    end = start + datetime.timedelta(seconds=summary['wall_seconds'])
    samples = []
    for line in path.read_text().splitlines():
        value = json.loads(line)
        if start <= datetime.datetime.fromisoformat(value['at']) <= end:
            samples.append(value)
    if not samples:
        return None
    names = ['rss_bytes', 'system_wired_bytes', 'system_compressor_bytes', 'swap_used_bytes']
    return {'samples': len(samples), 'server_record': runtime['record_directory'],
            'sampled_peak': {key: max(s[key] for s in samples if s.get(key) is not None)
                             for key in names if any(s.get(key) is not None for s in samples)},
            'note': 'Approximate task window from start and duration. Five-second samples; '
                    'RSS is not GPU allocation and system memory includes other processes.'}


def audit_run(run):
    summary, config = read(run / 'summary.json'), read(run / 'config.json')
    errors, unknown = [], []
    inputs = outputs = cached = 0
    for call in summary['calls']:
        folder = run / call['path']
        response = read(folder / 'response.json')
        if response['status'] != 'ok':
            unknown.append(call['path'])
            if call.get('input_tokens') is not None or call.get('output_tokens') is not None:
                errors.append('failed call was assigned known usage: ' + call['path'])
            continue
        raw, request = read(folder / 'raw_response.json'), read(folder / 'request.json')
        usage = raw.get('usage', {})
        counts = [usage.get(k) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')]
        if any(type(n) is not int or n < 0 for n in counts) or counts[0] + counts[1] != counts[2]:
            errors.append('invalid raw counters: ' + call['path'])
            continue
        for name, value in zip(('input_tokens', 'output_tokens'), counts):
            if call.get(name) != value or response.get(name) != value:
                errors.append('raw usage disagrees: ' + call['path'] + ' ' + name)
        inputs += counts[0]
        outputs += counts[1]
        cache = usage.get('prompt_tokens_details', {}).get('cached_tokens')
        if type(cache) is int and 0 <= cache <= counts[0]:
            cached += cache
        else:
            errors.append('missing/invalid cached input counter: ' + call['path'])
        preflight = read(folder / 'preflight.json')['input_tokens']
        if preflight != counts[0] or call['precall_input_bound'] != counts[0]:
            errors.append('input count disagreement: ' + call['path'])
        if counts[1] > config['num_predict'] or counts[0] + config['num_predict'] > config['num_ctx']:
            errors.append('context/output reserve exceeded: ' + call['path'])
        settings = {'model': config['model'], 'temperature': config['temperature'],
                    'top_p': config['top_p'], 'top_k': config['top_k'], 'min_p': config['min_p'],
                    'repeat_penalty': config['repeat_penalty'], 'seed': config['seed'],
                    'max_tokens': config['num_predict']}
        if any(request.get(k) != v for k, v in settings.items()):
            errors.append('sampling settings differ: ' + call['path'])
        if request.get('chat_template_kwargs', {}).get('thinking_mode') != config['thinking_mode']:
            errors.append('thinking setting differs: ' + call['path'])
        if raw['choices'][0]['finish_reason'] != call.get('done_reason'):
            errors.append('finish reason differs: ' + call['path'])
    total = inputs + outputs
    if total != summary.get('total_recorded_tokens', 0):
        errors.append('recorded total differs from raw known usage')
    if bool(unknown) == bool(summary['usage_complete']):
        errors.append('usage completeness flag disagrees')
    if total > config['max_total_tokens'] or len(summary['calls']) > config['max_calls']:
        errors.append('total call/token budget exceeded')
    listed = {call['path'] for call in summary['calls']}
    observed = {p.parent.name for p in run.glob('call_*/request.json')}
    if listed != observed:
        errors.append('summary and request files enumerate different calls')
    for name, expected in summary['source_hashes'].items():
        if hashlib.sha256((run / name).read_bytes()).hexdigest() != expected:
            errors.append('source snapshot hash mismatch: ' + name)
    if not summary.get('artifact_frozen_at') or not summary.get('artifact_sha256'):
        errors.append('no frozen final artifact')
    elif hashlib.sha256((run / 'final.patch').read_bytes()).hexdigest() != summary['artifact_sha256']:
        errors.append('frozen artifact hash mismatch')
    evaluation = read(run / 'final_evaluation_summary.json') if (run / 'final_evaluation_summary.json').exists() else None
    if evaluation and evaluation['artifact_sha256'] != summary['artifact_sha256']:
        errors.append('evaluation used another artifact')
    return {'record': str(run.relative_to(ROOT)), 'task': config['instance_id'], 'model': config['model'],
            'calls': len(summary['calls']), 'tools': len(summary['tools']),
            'input_tokens': inputs, 'output_tokens': outputs, 'cached_input_tokens': cached,
            'known_total_tokens': total, 'unknown_usage_calls': unknown,
            'stop_reason': summary['stop_reason'], 'wall_seconds': summary['wall_seconds'],
            'model_call_wall_seconds': sum(c.get('wall_seconds', 0) for c in summary['calls']),
            'memory': memory_window(run, summary),
            'artifact_sha256': summary.get('artifact_sha256'), 'artifact_bytes': summary.get('artifact_bytes'),
            'visible_checks_all_passed': summary.get('visible_checks', {}).get('all_passed'),
            'evaluation': evaluation, 'errors': errors}


def main():
    rows, pending = [], []
    for path in sorted((ROOT / 'records/p2').glob('*/summary.json')):
        summary = read(path)
        if 'wall_seconds' not in summary or not summary.get('container_removed'):
            pending.append(str(path.parent.relative_to(ROOT)))
            continue
        rows.append(audit_run(path.parent))
    report = {'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'scope': 'Completed development runs; unknown usage and audit errors remain visible',
              'completed_runs': len(rows), 'runs': rows, 'pending': pending,
              'audit_errors': sum(len(r['errors']) for r in rows),
              'unknown_usage_calls': sum(len(r['unknown_usage_calls']) for r in rows),
              'known_task_tokens': sum(r['known_total_tokens'] for r in rows)}
    (ROOT / 'reports/P2_task_audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'runs'}))
    return report['audit_errors'] == 0


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
