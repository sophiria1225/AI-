"""Aggregate P82 public receipts without inferring missing usage or log bounds."""
import argparse
import csv
import json
import math
from pathlib import Path
import time

from inspect_late_clock_usage_intervals import check_cells
from late_clock_comparison import run_order, summarize, validate_plan
from run_handoff_factors import ROOT, read, sha

COUNTS = ('model_calls', 'unknown_usage_calls', 'known_total_tokens', 'input_tokens',
          'cached_input_tokens', 'output_tokens', 'api_requests')
TIMES = ('setup_wall_seconds', 'wall_seconds', 'cleanup_wall_seconds', 'full_wall_seconds')
METRICS = ('logical_tokens', 'uncached_input_tokens', 'output_tokens')
POLICIES = ('measured', 'not_exposed', 'late_half')


def observed_rows(cells):
    check_cells(cells)
    result = []
    for c in cells:
        if any(type(c[k]) is not int or c[k] < 0 for k in COUNTS):
            raise ValueError('nonnegative_integer_counts_required')
        if any(type(c[k]) not in (int, float) or not math.isfinite(c[k]) or c[k] < 0 for k in TIMES):
            raise ValueError('finite_nonnegative_times_required')
        if c['input_tokens'] + c['output_tokens'] != c['known_total_tokens'] or c['cached_input_tokens'] > c['input_tokens']:
            raise ValueError('known_receipt_accounting_disagrees')
        row = {k: c[k] for k in ('run_id', 'repetition', 'task_id', 'time_visibility', 'success', 'stop_reason',
                                'model_calls', 'unknown_usage_calls', 'api_requests', *TIMES)}
        row.update(known_logical_tokens=c['known_total_tokens'], known_input_tokens=c['input_tokens'],
                   known_cached_input_tokens=c['cached_input_tokens'], known_output_tokens=c['output_tokens'],
                   known_uncached_input_tokens=c['input_tokens'] - c['cached_input_tokens'],
                   terminal_usage_complete=c['unknown_usage_calls'] == 0)
        result.append(row)
    return result


def aggregate(rows):
    keys = ('model_calls', 'unknown_usage_calls', 'api_requests', *TIMES,
            'known_logical_tokens', 'known_input_tokens', 'known_cached_input_tokens',
            'known_uncached_input_tokens', 'known_output_tokens')
    return dict(conditions=len(rows), successes=sum(r['success'] for r in rows),
                **{k: sum(r[k] for r in rows) for k in keys})


def difference(candidate, baseline, metric):
    known = candidate['known_' + metric] - baseline['known_' + metric]
    a, b = candidate['unknown_usage_calls'], baseline['unknown_usage_calls']
    kind = 'unidentified' if a and b else 'lower_bound' if a else 'upper_bound' if b else 'exact'
    return dict(kind=kind, value=None if a and b else known,
                known_subtotal_difference=known, missing_usage_imputed=False,
                basis='Only nonnegativity of missing counters; no server-log or token-cap inference.')


def comparisons(rows):
    result = []
    for rep in (1, 2, 'combined'):
        selected = [r for r in rows if rep == 'combined' or r['repetition'] == rep]
        for baseline in POLICIES[:2]:
            pairs = {}
            for r in selected:
                if r['time_visibility'] in (baseline, 'late_half'):
                    pairs.setdefault((r['repetition'], r['task_id']), {})[r['time_visibility']] = r
            categories = {'total': [], 'both_success': [], 'both_failure': [], 'discordant': []}
            for pair in pairs.values():
                a, b = pair[baseline]['success'], pair['late_half']['success']
                key = 'both_success' if a and b else 'both_failure' if not a and not b else 'discordant'
                categories[key].extend(pair.values()); categories['total'].extend(pair.values())
            for category, group in categories.items():
                arms = {p: aggregate([r for r in group if r['time_visibility'] == p]) for p in (baseline, 'late_half')}
                result.append(dict(repetition=rep, baseline=baseline, category=category,
                    paired_task_observations=len(group) // 2, arms=arms,
                    late_half_minus_baseline={m: difference(arms['late_half'], arms[baseline], m) for m in METRICS},
                    observed_differences={k: arms['late_half'][k] - arms[baseline][k] for k in ('api_requests', *TIMES)}))
    return result


def analyze(root):
    began = time.monotonic()
    names = ['reports/P82_comparison.json', 'reports/P82_server_session.json',
             'reports/P82_interval_failure_20261024.json', 'configs/P82_late_clock_comparison_v01.json',
             'scripts/summarize_late_clock_observed_resources.py', 'scripts/inspect_late_clock_usage_intervals.py',
             'scripts/late_clock_comparison.py', 'scripts/audit_budget_visibility_comparison.py']
    audit, session, failure, plan = (read(root / n) for n in names[:4])
    validate_plan(plan)
    for name, expected in plan['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('frozen_source_changed:' + name)
    if (audit['batch_status'] != 'complete' or audit['audit_errors'] or session['status'] != 'stopped'
            or session['owned_processes_absent'] is not True or session['evaluations_completed'] != 24
            or session['audit_source_sha256'] != sha(root / names[0])
            or audit['plan_sha256'] != sha(root / names[3])
            or audit['auditor_sha256'] != sha(root / 'scripts/audit_late_clock_comparison.py')):
        raise ValueError('closed_unchanged_audit_and_session_required')
    for (_, number, _), row in zip(run_order(), audit['rows'], strict=True):
        if row['task_id'] != plan['known_tasks'][number - 1]['task_id']:
            raise ValueError('fixed_task_identity_changed')
    rows = observed_rows(audit['rows']); decisions = summarize(audit['rows'], [])
    if any(audit.get(k) != v for k, v in decisions.items()):
        raise ValueError('original_adoption_decisions_changed')
    if (failure['original_interval_result_created'] is not False
            or failure['original_unknown_usage_calls'] != sum(r['unknown_usage_calls'] for r in rows)
            or failure['source_sha256'][names[0]] != sha(root / names[0])):
        raise ValueError('preserved_failed_interval_attempt_required')
    if not math.isclose(sum(r['full_wall_seconds'] for r in rows), session['cell_full_wall_seconds'], abs_tol=1e-6, rel_tol=0):
        raise ValueError('whole_cohort_time_disagrees')
    return dict(phase='P82_observed_resource_accounting', posthoc=True, rows=rows, comparisons=comparisons(rows),
        totals={p: aggregate([r for r in rows if r['time_visibility'] == p]) for p in POLICIES},
        original_decisions=decisions, independent_tasks=4, terminal_usage_imputed=False,
        failed_interval_method_retried=False, conditional_server_log_intervals_reported=False,
        shared_session_measures={k: session[k] for k in ('wall_seconds', 'load_wall_seconds', 'pipeline_wall_seconds',
            'evaluation_wall_seconds', 'cell_full_wall_seconds', 'batch_other_wall_seconds')},
        session_overlap_note='Do not sum overlapping measures or allocate shared session time to arms.',
        source_sha256={n: sha(root / n) for n in names}, raw_histories_read=False, server_logs_read=False,
        additional_generations=0, additional_input_counts=0, additional_api_requests=0, additional_evaluations=0,
        causal_wall_time_claim=False, gpu_flops_or_energy_measured=False, novel_method_claim=False,
        analysis_wall_seconds=time.monotonic() - began)


def write_outputs(result, output):
    output.mkdir(parents=True, exist_ok=False)
    with (output / 'observed_resources.json').open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2); f.write('\n')
    rows = result['rows']
    with (output / 'all_24_conditions.csv').open('x', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    arms = []
    for c in result['comparisons']:
        for policy, values in c['arms'].items():
            arms.append(dict(repetition=c['repetition'], baseline=c['baseline'], category=c['category'],
                             time_visibility=policy, **values))
    with (output / 'all_48_partition_arms.csv').open('x', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(arms[0])); w.writeheader(); w.writerows(arms)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, default=ROOT / 'materials/20261024_p82_observed_resources')
    args = parser.parse_args(); result = analyze(args.repo_root); write_outputs(result, args.output)
    print({'conditions': len(result['rows']), 'partition_comparisons': len(result['comparisons']),
           'unknown_usage_calls': sum(r['unknown_usage_calls'] for r in result['rows'])})
