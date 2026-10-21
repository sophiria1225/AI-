"""Account for existing server timings without reading task answers or evaluators."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLANS = ['P11_additional_baseline_v01.json', 'P12_recent_window_v01.json',
         'P13_native_focus_v01.json', 'P14_native_ledger_v01.json']


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cohort_for(plan, recovery=None):
    if plan['phase'] != 'P13':
        return plan['run_order']
    if recovery is None:
        raise ValueError('P13 requires the explicit recovery cohort')
    cohort = recovery['cohort']
    if [r[:2] for r in cohort] != [r[:2] for r in plan['run_order']]:
        raise ValueError('recovery cohort changed task or arm')
    return cohort


def timing_row(usage, response):
    base = {'call_id': usage['id'], 'role': usage['role'], 'status': usage['status'],
            'input_tokens': usage['input_tokens'], 'output_tokens': usage['output_tokens'],
            'call_wall_seconds': usage['wall_seconds']}
    if any(usage[k] != response[k] for k in ('status', 'input_tokens', 'output_tokens')):
        raise ValueError('saved usage differs from response')
    if usage['status'] != 'ok':
        if usage['input_tokens'] is not None or usage['output_tokens'] is not None:
            raise ValueError('unknown usage must remain null')
        return {**base, 'timing_available': False, 'cached_tokens': None,
                'processed_input_tokens': None, 'prefill_seconds': None, 'decode_seconds': None}
    timing = response.get('timings')
    if not timing:
        return {**base, 'timing_available': False, 'cached_tokens': response.get('cached_input_tokens'),
                'processed_input_tokens': None, 'prefill_seconds': None, 'decode_seconds': None}
    cache, processed, output = [timing.get(k) for k in ('cache_n', 'prompt_n', 'predicted_n')]
    if any(type(v) is not int or v < 0 for v in (cache, processed, output)):
        raise ValueError('invalid timing token count')
    if cache != response.get('cached_input_tokens') or cache+processed != usage['input_tokens']:
        raise ValueError('cached and processed token partition differs')
    if output != usage['output_tokens']:
        raise ValueError('generated token count differs')
    times = [timing.get(k) for k in ('prompt_ms', 'predicted_ms')]
    if any(type(t) not in (int, float) or t < 0 for t in times):
        raise ValueError('invalid timing duration')
    return {**base, 'timing_available': True, 'cached_tokens': cache,
            'processed_input_tokens': processed, 'prefill_seconds': times[0]/1000,
            'decode_seconds': times[1]/1000}


def audit(storage):
    rows, hashes = [], {}
    for name in PLANS:
        plan = read(ROOT/'configs'/name)
        hashes['configs/'+name] = sha(ROOT/'configs'/name)
        recovery = None
        if plan['phase'] == 'P13':
            path = ROOT/'configs/P13_recovery_v01.json'
            recovery = read(path)
            hashes['configs/P13_recovery_v01.json'] = sha(path)
        for number, (_, _, run_id) in enumerate(cohort_for(plan, recovery), 1):
            directory = storage/'records/context_pilot'/run_id
            usages = read(directory/'usage.json')
            summary = read(directory/'summary.json')
            known_tokens = sum(u['input_tokens']+u['output_tokens'] for u in usages if u['status'] == 'ok')
            if known_tokens != summary['known_total_tokens'] or len(usages) != summary['model_calls']:
                raise ValueError('cohort usage does not match completed summary: '+run_id)
            hashes[run_id+'/usage.json'] = sha(directory/'usage.json')
            hashes[run_id+'/summary.json'] = sha(directory/'summary.json')
            previous = None
            for usage in usages:
                path = directory/usage['id']/'response.json'
                response = read(path)
                row = timing_row(usage, response)
                rows.append({**row, 'phase': plan['phase'], 'task_number': number,
                             'run_id': run_id, 'previous_role': previous,
                             'response_sha256': sha(path)})
                previous = usage['role']
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row['phase'], row['role'])].append(row)
    groups = []
    for (phase, role), group in sorted(grouped.items()):
        known = [r for r in group if r['status'] == 'ok']
        timed = [r for r in group if r['timing_available']]
        groups.append({'phase': phase, 'role': role, 'calls': len(group),
                       'known_calls': len(known), 'unknown_calls': len(group)-len(known),
                       'timed_calls': len(timed),
                       'known_total_tokens': sum(r['input_tokens']+r['output_tokens'] for r in known),
                       'timed_input_tokens': sum(r['input_tokens'] for r in timed),
                       'cached_tokens': sum(r['cached_tokens'] for r in timed),
                       'processed_input_tokens': sum(r['processed_input_tokens'] for r in timed),
                       'prefill_seconds': sum(r['prefill_seconds'] for r in timed),
                       'decode_seconds': sum(r['decode_seconds'] for r in timed),
                       'known_call_wall_seconds': sum(r['call_wall_seconds'] for r in known),
                       'unknown_call_wall_seconds': sum(r['call_wall_seconds'] for r in group if r['status'] != 'ok')})
    return {'groups': groups, 'rows': rows, 'source_hashes': hashes,
            'auditor_sha256': sha(Path(__file__)), 'new_model_calls': 0, 'environment_requests': 0,
            'scope': 'P11-P14 completed cohorts only; separate interrupted P13 run is outside this timing table. '
                     'Unknown usage remains unknown. Timings are server measurements, not total experiment time. '
                     'Role and cache associations are descriptive, not randomized causal cache effects. '
                     'No private task, response text, reasoning, credential or evaluator content exported.'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    report = audit(args.storage_root)
    with args.output.open('x') as f:
        json.dump(report, f, indent=2)
        f.write('\n')
    print(json.dumps(report['groups'], indent=2))


if __name__ == '__main__':
    main()
