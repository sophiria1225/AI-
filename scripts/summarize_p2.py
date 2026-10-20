"""Publish compact measurements without prompts, patches, or hidden labels."""
import datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def main():
    calls = []
    probes = []
    capacities = []
    tasks = []
    for path in sorted((ROOT / 'records/p2_probes').glob('*/summary.json')):
        item = read(path)
        calls.extend(item['calls'])
        probes.append({'record': str(path.parent.relative_to(ROOT)),
                       'config': item['config'], 'assertions': item['assertions'],
                       'error': item['error'], 'calls': len(item['calls']),
                       'known_total_tokens': item['known_total_tokens']})
    for path in sorted((ROOT / 'records/p2_capacity').glob('*/summary.json')):
        item = read(path)
        config = read(path.parent / 'config.json')
        server = read(ROOT / item['server_record'] / 'summary.json')
        response = item['response']
        calls.append(response)
        capacities.append({'record': str(path.parent.relative_to(ROOT)),
                           'model': config['model'],
                           'ctx_size': config['num_ctx'],
                           'input_tokens': item['preflight_tokens'],
                           'output_tokens': response['output_tokens'],
                           'count_matches': item['count_matches'],
                           'retrieved_exact_value': item['retrieved_exact_value'],
                           'status': response['status'], 'error': response.get('error'),
                           'wall_seconds': response['wall_seconds'],
                           'timings': response.get('timings'),
                           'sampled_peak_rss_bytes': server['sampled_peak_rss_bytes'],
                           'peak_system_swap_bytes': server['peak_system_swap_bytes'],
                           'memory_scope': 'entire associated server lifetime so far, not isolated to this probe',
                           'sampling': {k: config.get(k, v) for k, v in
                                        [('top_k', 40), ('min_p', 0.05), ('repeat_penalty', 1.0)]},
                           'sampling_note': 'Missing keys in early records use the pinned server defaults.'})
    for path in sorted((ROOT / 'records/p2').glob('*/summary.json')):
        item = read(path)
        calls.extend(item['calls'])
        tasks.append({'record': str(path.parent.relative_to(ROOT)),
                      'model': item['model'],
                      'status': 'finished' if item.get('container_removed') else 'running',
                      'instance_id': item['instance_id'], 'stop_reason': item['stop_reason'],
                      'calls': len(item['calls']), 'total_recorded_tokens': item.get('total_recorded_tokens'),
                      'usage_complete': item['usage_complete'],
                      'wall_seconds': item.get('wall_seconds'),
                      'artifact_sha256': item.get('artifact_sha256'),
                      'visible_checks_all_passed': item.get('visible_checks', {}).get('all_passed')})
    known = [c for c in calls if type(c.get('input_tokens')) is int and type(c.get('output_tokens')) is int]
    without_response = [str(p.relative_to(ROOT))
                        for group in ('p2', 'p2_probes', 'p2_capacity')
                        for p in (ROOT / 'records' / group).rglob('request.json')
                        if not (p.parent / 'response.json').exists()]
    report = {'schema_version': 2, 'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'scope': 'P2 local calibration and development; not held-out research results',
              'accounting': {'recorded_calls': len(calls), 'calls_with_known_usage': len(known),
                             'calls_with_unknown_usage': len(calls) - len(known),
                             'requests_without_response_record': without_response,
                             'known_input_tokens': sum(c['input_tokens'] for c in known),
                             'known_output_tokens': sum(c['output_tokens'] for c in known),
                             'known_total_tokens': sum(c['input_tokens'] + c['output_tokens'] for c in known),
                             'note': 'All generated reasoning and cached logical input are included. '
                                     'Token-count endpoints do not generate and are not added as model calls. '
                                     'Runs without a terminal summary may still be in progress.'},
              'memory_note': 'RSS sampled every 5 seconds, not total unified GPU allocation; swap is system-wide.',
              'probes': probes, 'capacity': capacities, 'tasks': tasks}
    out = ROOT / 'reports/P2_measurements.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'report': str(out.relative_to(ROOT)), 'accounting': report['accounting'],
                      'completed_capacity_points': len(capacities), 'task_runs': len(tasks)}))


if __name__ == '__main__':
    main()
