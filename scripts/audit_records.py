"""Reconcile actual terminal model usage and frozen artifacts after a pilot."""
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
audits = []
errors = []
for run in sorted((ROOT / 'records/e0').glob('*')):
    if not run.is_dir() or not (run / 'summary.json').exists():
        continue
    summary = json.loads((run / 'summary.json').read_text())
    config = json.loads((run / 'config.json').read_text())
    counts = {'input_tokens': 0, 'output_tokens': 0, 'cached_input_tokens': 0}
    known_cache = True
    terminal_count = 0
    generation_truncations = 0
    no_tool_truncations = 0
    record_errors = []
    for call in summary['calls']:
        path = run / call['path']
        terminal = None
        events_path = path / 'events.jsonl'
        for line in events_path.read_text().splitlines() if events_path.exists() else []:
            event = json.loads(line)
            if event.get('done'):
                terminal = event
        if terminal is None:
            record_errors.append('missing terminal event: ' + call['path'])
            continue
        terminal_count += 1
        response = json.loads((path / 'response.json').read_text())
        if terminal.get('done_reason') == 'length':
            generation_truncations += 1
            if not response.get('message', {}).get('tool_calls'):
                no_tool_truncations += 1
        for source, name in [('prompt_eval_count', 'input_tokens'), ('eval_count', 'output_tokens')]:
            if terminal.get(source) != call.get(name):
                record_errors.append('usage mismatch: ' + call['path'] + '/' + name)
            counts[name] += terminal.get(source, 0)
        cached = terminal.get('prompt_eval_cached_count')
        if cached is None:
            known_cache = False
        elif not 0 <= cached <= terminal['prompt_eval_count']:
            record_errors.append('cache count outside input count')
        else:
            counts['cached_input_tokens'] += cached
    total = counts['input_tokens'] + counts['output_tokens']
    if total != summary['total_recorded_tokens']:
        record_errors.append('total cost mismatch')
    snapshot = run / 'runner_snapshot.py'
    if not snapshot.exists() or hashlib.sha256(snapshot.read_bytes()).hexdigest() != summary['source_sha256']:
        record_errors.append('runner snapshot hash mismatch')
    artifact = run / 'final.patch'
    if not artifact.exists() or hashlib.sha256(artifact.read_bytes()).hexdigest() != summary.get('artifact_sha256'):
        record_errors.append('artifact hash mismatch')
    usage_complete = terminal_count == len(summary['calls']) and summary['usage_complete']
    item = {'run_id': run.name, 'config_version': config.get('version', 'v01'),
            'strategy': summary['strategy'], 'calls': len(summary['calls']),
            'terminal_count': terminal_count, 'usage': counts, 'cache_complete': known_cache,
            'total_tokens': total if usage_complete else None,
            'known_tokens': total, 'usage_complete': usage_complete,
            'generation_truncations': generation_truncations,
            'no_tool_truncations': no_tool_truncations,
            'within_token_budget': total <= config['max_total_tokens'] if usage_complete else None,
            'within_wall_budget': summary['wall_seconds'] <= config['max_wall_seconds'],
            'stop_reason': summary['stop_reason'], 'artifact_bytes': summary.get('artifact_bytes'),
            'wall_seconds': summary['wall_seconds'], 'errors': record_errors}
    audits.append(item)
    errors.extend(record_errors)
complete = all(row['usage_complete'] for row in audits)
result = {'runs': audits, 'usage_complete': complete,
          'total_E0_tokens_including_development': sum(row['known_tokens'] for row in audits) if complete else None,
          'known_E0_tokens_including_development': sum(row['known_tokens'] for row in audits),
          'errors': errors}
(ROOT / 'records/e0/audit.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
raise SystemExit(1 if errors else 0)
