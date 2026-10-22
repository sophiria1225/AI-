"""Exact, descriptive token accounting for the complete P33 cohort.

The symmetric product decomposition is an accounting identity, not four causal
effects, a proposed algorithm, or a forecast of savings on another trajectory.
No raw text, model requests or evaluator internals are read.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from diagnose_handoff_programs import require_complete
from handoff_output_views import ARMS

ROOT = Path(__file__).resolve().parents[1]


def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def describe(row):
    calls, totals = row['calls'], row['totals']
    if not calls or len(calls) != totals['calls']:
        raise ValueError('complete nonempty call list required')
    if len({c['call_id'] for c in calls}) != len(calls):
        raise ValueError('duplicate call')
    unknown = sum(c['status'] != 'ok' for c in calls)
    if unknown != totals['unknown_usage_calls']:
        raise ValueError('unknown usage count differs')
    known = [c for c in calls if c['status'] == 'ok']
    for call in known:
        if any(type(call[k]) is not int or call[k] < 0
               for k in ('input_tokens', 'output_tokens')):
            raise ValueError('known token count invalid')
    for key in ('input_tokens', 'output_tokens'):
        if sum(c[key] for c in known) != totals[key]:
            raise ValueError('profile total differs from calls')
    if totals['known_total_tokens'] != totals['input_tokens'] + totals['output_tokens']:
        raise ValueError('known total differs')
    if unknown:
        return {'all_usage_known': False, 'unknown_usage_calls': unknown,
                'exact_total_tokens': None, 'decomposition': None}
    n, initial = len(calls), calls[0]['input_tokens']
    growth = sum(c['input_tokens'] - initial for c in calls)
    output = totals['output_tokens']
    if n * initial + growth + output != totals['known_total_tokens']:
        raise ValueError('accounting identity failed')
    return {'all_usage_known': True, 'unknown_usage_calls': 0,
            'exact_total_tokens': totals['known_total_tokens'],
            'decomposition': {'calls': n, 'initial_input_tokens': initial,
                              'later_input_growth_tokens': growth, 'output_tokens': output}}


def contrast(reference, candidate):
    if reference['task_id'] != candidate['task_id']:
        raise ValueError('paired task differs')
    left, right = describe(reference), describe(candidate)
    base = {'task_id': reference['task_id'], 'reference_run_id': reference['run_id'],
            'candidate_run_id': candidate['run_id'], 'candidate_arm': candidate['arm'],
            'reference': left, 'candidate': right, 'causal_components': False}
    if not (left['all_usage_known'] and right['all_usage_known']):
        return {**base, 'exact_total_token_change': None, 'components': None,
                'reason': 'Unknown usage is not imputed as zero.'}
    a, b = left['decomposition'], right['decomposition']
    pieces = {
        'initial_input_size': (a['calls'] + b['calls']) *
                              (b['initial_input_tokens'] - a['initial_input_tokens']) / 2,
        'number_of_calls': (a['initial_input_tokens'] + b['initial_input_tokens']) *
                           (b['calls'] - a['calls']) / 2,
        'later_input_growth': b['later_input_growth_tokens'] - a['later_input_growth_tokens'],
        'output_tokens': b['output_tokens'] - a['output_tokens'],
    }
    change = right['exact_total_tokens'] - left['exact_total_tokens']
    if sum(pieces.values()) != change:
        raise ValueError('paired accounting identity failed')
    return {**base, 'exact_total_token_change': change, 'components': pieces}


def analyze(root, storage):
    rp = root / 'reports/P33_comparison.json'
    pp = root / 'reports/P33_cost_profile.json'
    report, profile = read(rp), read(pp)
    require_complete(report, read(storage / 'records/context_pilot/P33_batch_v01/status.json'), 'P33')
    if (profile.get('comparison_sha256') != sha(rp) or not profile.get('all_twelve_profiled')
            or len(profile['rows']) != 12):
        raise ValueError('complete matching cost profile required')
    measured = {(r['task_id'], r['arm']): r for r in profile['rows']}
    if len(measured) != 12 or set(measured) != {(r['task_id'], r['arm']) for r in report['rows']}:
        raise ValueError('profile cohort differs')
    for r in report['rows']:
        row = measured[(r['task_id'], r['arm'])]
        if row['run_id'] != r['run_id'] or row['totals']['known_total_tokens'] != r['known_total_tokens']:
            raise ValueError('profile row differs from audited comparison')
    pairs = [contrast(measured[(task, ARMS[0])], measured[(task, arm)])
             for task in sorted({r['task_id'] for r in report['rows']}) for arm in ARMS[1:]]
    by_arm = {}
    for arm in ARMS[1:]:
        group = [p for p in pairs if p['candidate_arm'] == arm]
        valid = all(p['components'] is not None for p in group)
        sums = Counter()
        if valid:
            for p in group: sums.update(p['components'])
        by_arm[arm] = {'complete_exact_comparison': valid,
            'exact_total_token_change': sum(p['exact_total_token_change'] for p in group) if valid else None,
            'components': dict(sums) if valid else None,
            'pairs_with_unknown_usage': sum(p['components'] is None for p in group)}
    return {'phase': 'P33', 'all_twelve_accounted': True, 'pairs': pairs, 'by_arm': by_arm,
            'identity': 'T = n * first_input + sum(input_j - first_input) + total_output; delta(n*I) = mean(n)*delta(I) + mean(I)*delta(n)',
            'interpretation': 'Descriptive algebra on observed trajectories. The terms are not separately identified causal effects or achievable savings. Input includes cache hits; this is not latency, compute or money. Unknown usage suppresses the exact paired decomposition.',
            'new_inference_calls': 0, 'new_api_requests': 0,
            'source_sha256': {str(p.relative_to(root)): sha(p) for p in (rp, pp)},
            'script_sha256': sha(Path(__file__))}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--repo-root', type=Path, default=ROOT)
    p.add_argument('--storage-root', type=Path, required=True); a = p.parse_args()
    out = a.repo_root / 'reports/P33_cost_decomposition.json'
    if out.exists(): raise FileExistsError('preserve prior decomposition')
    result = analyze(a.repo_root, a.storage_root)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result['by_arm'], ensure_ascii=False))
