"""Public-only, failure-inclusive resource accounting for the closed P82 cohort.

Report separate conditional logical/input/output ranges. A difference between
known subsets is not a full-cohort lower bound when the baseline has missing usage.
"""
import argparse
import csv
import json
import math
import time
from pathlib import Path

from inspect_late_clock_usage_intervals import summarize_intervals, natural
from summarize_closed_resources import SUM_FIELDS, read, sha

ROOT = Path(__file__).resolve().parents[1]
REPORT = 'reports/P82_comparison.json'
SESSION = 'reports/P82_server_session.json'
INTERVALS = 'reports/P82_usage_intervals_20261024.json'
METRICS = ('logical_tokens', 'uncached_input_tokens', 'output_tokens')
TIMES = ('wall_seconds', 'full_wall_seconds', 'setup_wall_seconds', 'cleanup_wall_seconds')


def resource_cells(cells, calls):
    original = summarize_intervals(calls, cells)
    result = []
    for c, logical in zip(cells, original['cells'], strict=True):
        for key in SUM_FIELDS:
            value = c[key]
            valid = (type(value) in (int, float) and math.isfinite(value) and value >= 0
                     if key in TIMES else natural(value))
            if not valid:
                raise ValueError('finite_nonnegative_resource_measure_required')
        if (c['input_tokens'] + c['output_tokens'] != c['known_total_tokens']
                or c['cached_input_tokens'] > c['input_tokens']):
            raise ValueError('known_input_output_cache_accounting_disagrees')
        unknown = [r for r in calls if r['run_id'] == c['run_id'] and not r['complete_usage']]
        for r in unknown:
            i, lo, hi = (r.get(key) for key in ('input_tokens_lower_bound',
                        'generated_tokens_lower_bound', 'generated_tokens_upper_bound'))
            if (not all(natural(v) for v in (i, lo, hi)) or i == 0 or not 0 < lo <= hi <= 4096
                    or r['logical_tokens_lower_bound'] != i + lo
                    or r['logical_tokens_upper_bound'] != i + hi):
                raise ValueError('same_pinned_conditional_input_and_generation_bounds_required')
        uncached = c['input_tokens'] - c['cached_input_tokens']
        out = c['output_tokens']
        row = {key: c[key] for key in ('run_id', 'repetition', 'task_id', 'time_visibility',
                                     'success', 'stop_reason', *SUM_FIELDS)}
        for key in ('input_tokens', 'cached_input_tokens', 'output_tokens'):
            row['known_' + key] = row.pop(key)
        row.update(known_uncached_input_tokens=uncached,
                   terminal_usage_complete=c['unknown_usage_calls'] == 0,
                   logical_tokens=[logical['lower'], logical['upper']],
                   uncached_input_tokens=[uncached, uncached + sum(r['input_tokens_lower_bound'] for r in unknown)],
                   output_tokens_interval=[out + sum(r['generated_tokens_lower_bound'] for r in unknown),
                                           out + sum(r['generated_tokens_upper_bound'] for r in unknown)])
        result.append(row)
    return result, original['original_decisions']


def aggregate(rows):
    intervals = {}
    for metric in METRICS:
        key = 'output_tokens_interval' if metric == 'output_tokens' else metric
        intervals[metric] = [sum(r[key][edge] for r in rows) for edge in (0, 1)]
    return {'conditions': len(rows), 'successes': sum(r['success'] for r in rows),
            'model_calls': sum(r['model_calls'] for r in rows),
            'unknown_usage_calls': sum(r['unknown_usage_calls'] for r in rows),
            'known_total_tokens': sum(r['known_total_tokens'] for r in rows),
            'known_uncached_input_tokens': sum(r['known_uncached_input_tokens'] for r in rows),
            'known_output_tokens': sum(r['known_output_tokens'] for r in rows),
            **{key: sum(r[key] for r in rows) for key in ('api_requests', *TIMES)},
            'conditional_intervals': intervals}


def comparisons(rows):
    result = []
    for rep in (1, 2, 'combined'):
        selected = [r for r in rows if rep == 'combined' or r['repetition'] == rep]
        for baseline in ('measured', 'not_exposed'):
            paired = {}
            for r in selected:
                if r['time_visibility'] in (baseline, 'late_half'):
                    paired.setdefault((r['repetition'], r['task_id']), {})[r['time_visibility']] = r
            categories = {'total': [], 'both_success': [], 'both_failure': [], 'discordant': []}
            for pair in paired.values():
                a, b = pair[baseline]['success'], pair['late_half']['success']
                key = 'both_success' if a and b else 'both_failure' if not a and not b else 'discordant'
                categories[key].extend(pair.values()); categories['total'].extend(pair.values())
            for category, group in categories.items():
                arms = {p: aggregate([r for r in group if r['time_visibility'] == p])
                        for p in (baseline, 'late_half')}
                b, late = arms[baseline], arms['late_half']
                delta = {metric: [late['conditional_intervals'][metric][0] - b['conditional_intervals'][metric][1],
                                  late['conditional_intervals'][metric][1] - b['conditional_intervals'][metric][0]]
                         for metric in METRICS}
                result.append(dict(repetition=rep, baseline=baseline, category=category,
                    paired_task_observations=len(group)//2, arms=arms,
                    late_half_minus_baseline_intervals=delta,
                    observed_late_half_minus_baseline={key: late[key] - b[key] for key in ('api_requests', *TIMES)}))
    return result


def analyze(root):
    started = time.monotonic()
    audit, session, intervals = (read(root / name) for name in (REPORT, SESSION, INTERVALS))
    source_names = {REPORT, SESSION, INTERVALS, 'scripts/summarize_late_clock_resources.py',
                    'scripts/summarize_closed_resources.py'}
    for name, digest in intervals['source_sha256'].items():
        if sha(root / name) != digest:
            raise ValueError('closed_interval_source_changed:' + name)
        source_names.add(name)
    if (audit['batch_status'] != 'complete' or audit['audit_errors']
            or session['status'] != 'stopped' or session['owned_processes_absent'] is not True
            or session['audit_source_sha256'] != sha(root / REPORT)
            or intervals['complete_terminal_usage_recovered'] is not False
            or intervals['original_adoption_gate_changed'] is not False):
        raise ValueError('closed_audited_unmodified_cohort_required')
    rows, decisions = resource_cells(audit['rows'], intervals['rows'])
    if decisions != intervals['original_decisions'] or any(audit.get(k) != v for k, v in decisions.items()):
        raise ValueError('original_decisions_must_remain_unchanged')
    for c in audit['rows']:
        calls = [r for r in intervals['rows'] if r['run_id'] == c['run_id']]
        if len(calls) != len(c['request_checks']):
            raise ValueError('all_audited_calls_required')
        for r, check in zip(calls, c['request_checks'], strict=True):
            if (r['call_id'] != check['call_id'] or r['saved_request_sha256'] != check['request_sha256']
                    or r['status'] != check['status']):
                raise ValueError('audited_request_identity_changed')
    if (not math.isclose(sum(r['full_wall_seconds'] for r in rows),
                         session['cell_full_wall_seconds'], rel_tol=0, abs_tol=1e-6)
            or sum(r['model_calls'] for r in rows) != len(intervals['rows'])
            or sum(r['unknown_usage_calls'] for r in rows) != intervals['original_unknown_usage_preserved']):
        raise ValueError('whole_cohort_accounting_disagrees')
    return dict(phase='P82_resource_accounting', posthoc=True, rows=rows, comparisons=comparisons(rows),
        totals={p: aggregate([r for r in rows if r['time_visibility'] == p])
                for p in ('measured', 'not_exposed', 'late_half')},
        original_decisions=decisions,
        shared_session_measures={k: session[k] for k in ('wall_seconds', 'load_wall_seconds',
            'pipeline_wall_seconds', 'evaluation_wall_seconds', 'cell_full_wall_seconds', 'batch_other_wall_seconds')},
        session_note='One P82 session only. Shared load and overhead are not allocated to arms; overlapping times are not added.',
        source_sha256={name: sha(root / name) for name in sorted(source_names)},
        additional_generations=0, additional_input_count_requests=0, additional_api_requests=0,
        additional_evaluations=0, raw_histories_read=False, private_reasoning_read=False,
        terminal_usage_imputed=False, original_adoption_gate_changed=False,
        gpu_flops_or_energy_measured=False, causal_wall_time_claim=False, novel_method_claim=False,
        independent_tasks=4, analysis_wall_seconds=time.monotonic() - started,
        assumptions=intervals['assumptions'] + [
            'For an unknown call with positive generation progress, uncached input lies between zero and its same-input pre-dispatch count.',
            'Known uncached input and output totals are retained separately; a difference of two known subsets is not a bound on their full difference.',
            'Unknown accepted output uses the pinned numeric progress and request cap. No missing cache counter is imputed.',
            'Logical input, uncached input and accepted output are distinct token counters, not a sum of GPU computation or energy.',
        ])


def write_outputs(result, output):
    output.mkdir(parents=True, exist_ok=False)
    with (output / 'resource_accounting.json').open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
    rows = []
    for row in result['rows']:
        flat = {k: v for k, v in row.items() if not isinstance(v, list)}
        for key, value in row.items():
            if isinstance(value, list):
                flat[key + '_lower'], flat[key + '_upper'] = value
        rows.append(flat)
    with (output / 'all_24_conditions.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    rows = []
    for pair in result['comparisons']:
        for policy, totals in pair['arms'].items():
            row = {key: pair[key] for key in ('repetition', 'baseline', 'category')}
            row.update(time_visibility=policy)
            row.update({k: v for k, v in totals.items() if k != 'conditional_intervals'})
            for metric, value in totals['conditional_intervals'].items():
                row[metric + '_lower'], row[metric + '_upper'] = value
            rows.append(row)
    with (output / 'all_48_partition_arms.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, default=ROOT / 'materials/20261024_p82_resource_accounting')
    args = parser.parse_args()
    result = analyze(args.repo_root)
    write_outputs(result, args.output)
    print({'conditions': len(result['rows']), 'comparisons': len(result['comparisons']),
           'attempts': sum(r['model_calls'] for r in result['rows']), 'output': str(args.output)})
