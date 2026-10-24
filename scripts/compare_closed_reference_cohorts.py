"""Post-hoc H-only comparison across closed P80/P81 and P82 cohorts.

Uses public trace fingerprints and six frozen P83 request archives, never new
generation, tokenization, task execution, or semantic inspection of reasoning.
This historical comparison is not a randomized normalization ablation.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from budget_signal import digest
from compare_budget_visibility_repetitions import compare_traces
from run_handoff_factors import ROOT, read, sha

FILES = ('reports/P81_repetitions.json', 'reports/P82_comparison.json',
         'reports/P81_trajectory_stability.json', 'reports/P82_trajectory_stability.json',
         'reports/P83_fallback_prompt.json', 'configs/P82_late_clock_comparison_v01.json',
         'scripts/compare_budget_visibility_repetitions.py', 'scripts/compare_late_clock_trajectories.py',
         'scripts/clock_notice_replay.py', 'scripts/budget_signal.py',
         'scripts/compare_closed_reference_cohorts.py')
DEFAULT = 'materials/20261024_closed_reference_cohorts'


def equal_prefix(left, right, key):
    length = 0
    for a, b in zip(left['calls'], right['calls']):
        if a.get(key) is None or b.get(key) is None or a[key] != b[key]:
            break
        length += 1
    return length


def compare_cohorts(old, new, old_traces, new_traces, task_ids):
    if len(set(task_ids)) != 4:
        raise ValueError('four_fixed_tasks_required')
    if any(d['batch_status'] != 'complete' or d['audit_errors'] for d in (old, new)):
        raise ValueError('both_closed_audited_cohorts_required')
    cohorts = [([{**r, 'repetition': 1} for r in old['anchor_rows']] + old['rows'], old_traces, 3),
               (new['rows'], new_traces, 2)]
    selected = []
    for rows, traces, repetitions in cohorts:
        hidden = [r for r in rows if r['time_visibility'] == 'not_exposed']
        expected = {(t, r) for t in task_ids for r in range(1, repetitions + 1)}
        if (len(hidden) != 4 * repetitions or len({r['run_id'] for r in hidden}) != len(hidden)
                or {(r['task_id'], r['repetition']) for r in hidden} != expected):
            raise ValueError('all_fixed_hidden_conditions_required')
        for row in hidden:
            trace = traces[row['run_id']]
            calls = trace['calls']
            if (trace['run_id'] != row['run_id'] or len(calls) != row['model_calls']
                    or len(calls) != len(row['request_checks'])
                    or any(c['call_id'] != f'call_{i:03d}' or c['call_id'] != check['call_id']
                           or c['usage_status'] != check['status']
                           for i, (c, check) in enumerate(zip(calls, row['request_checks'], strict=True), 1))):
                raise ValueError('trace_must_match_every_audited_attempt')
            complete = (row['record_status'] == 'evaluated' and row['unknown_usage_calls'] == 0
                        and all(c['request_sha256'] is not None and c['public_output_sha256'] is not None for c in calls))
            if trace['known_complete'] != complete:
                raise ValueError('missing_usage_cannot_become_complete_trace')
        selected.append(sorted(hidden, key=lambda r: (task_ids.index(r['task_id']), r['repetition'])))
    pairs = []
    for task in task_ids:
        for a in (r for r in selected[0] if r['task_id'] == task):
            for b in (r for r in selected[1] if r['task_id'] == task):
                left, right = old_traces[a['run_id']], new_traces[b['run_id']]
                pairs.append(dict(task_id=task, old_repetition=a['repetition'], new_repetition=b['repetition'],
                    old_success=a['success'], new_success=b['success'],
                    common_equal_request_prefix=equal_prefix(left, right, 'request_sha256'),
                    common_equal_public_output_prefix=equal_prefix(left, right, 'public_output_sha256'),
                    **compare_traces(left, right)))
    if len(pairs) != 24:
        raise ValueError('all_twenty_four_dependent_pairs_required')
    return selected, pairs


def analyze(root, storage):
    began = time.monotonic()
    old, new, old_trace, new_trace, p83, plan = [read(root / n) for n in FILES[:6]]
    for report, expected_source, inspector in ((old_trace, FILES[0], FILES[6]),
                                               (new_trace, FILES[1], FILES[7])):
        if report['comparison_sha256'] != sha(root / expected_source) or report['inspector_sha256'] != sha(root / inspector):
            raise ValueError('unchanged_trace_source_and_inspector_required')
    task_ids = [t['task_id'] for t in plan['known_tasks']]
    selected, pairs = compare_cohorts(old, new, old_trace['traces'], new_trace['traces'], task_ids)
    if p83['status'] != 'complete' or len(p83['rendered']) != 6:
        raise ValueError('all_six_closed_P83_inputs_required')
    archive_checks, request_digests = [], {}
    for case in p83['planned_inputs']:
        path = storage / 'records/context_pilot/P83_fallback_prompt_v01' / (case + '_request_private.json')
        expected = p83['rendered'][case]['private_request_sha256']
        if sha(path) != expected:
            raise ValueError('frozen_P83_request_changed')
        request_digests[case] = digest(read(path))
        archive_checks.append(dict(case=case, private_request_sha256=expected,
                                   canonical_request_sha256=request_digests[case]))
    # The historical diagnostic selected call 14 of this known task; do not
    # search other calls or edit the archived request to force a match.
    csv_task = task_ids[3]
    matches = []
    for row in (r for r in selected[1] if r['task_id'] == csv_task):
        calls = new_trace['traces'][row['run_id']]['calls']
        if len(calls) < 14:
            raise ValueError('selected_historical_call_not_available')
        for case, value in request_digests.items():
            matches.append(dict(run_id=row['run_id'], call_id='call_014', case=case,
                full_saved_request_equal=calls[13]['request_sha256'] == value))
    rows = []
    for cohort, cells in zip(('P80_P81', 'P82'), selected, strict=True):
        for c in cells:
            rows.append(dict(cohort=cohort, **{k: c[k] for k in ('run_id', 'task_id', 'repetition',
                'success', 'stop_reason', 'model_calls', 'known_total_tokens', 'unknown_usage_calls',
                'api_requests', 'wall_seconds')}))
    summary = []
    for task in task_ids:
        group = [p for p in pairs if p['task_id'] == task]
        summary.append(dict(task_id=task, old_successes=sum(r['success'] for r in selected[0] if r['task_id'] == task),
            new_successes=sum(r['success'] for r in selected[1] if r['task_id'] == task), pairs=len(group),
            complete_pairs=sum(p['both_known_complete'] for p in group),
            all_requests_equal_pairs=sum(p['all_requests_equal'] is True for p in group),
            all_public_outputs_equal_pairs=sum(p['all_public_outputs_equal'] is True for p in group),
            equal_request_prefix_lengths=[p['common_equal_request_prefix'] for p in group],
            first_request_differences=[p['first_request_difference'] for p in group],
            first_public_output_differences=[p['first_public_output_difference'] for p in group]))
    return dict(phase='closed_reference_cohort_diagnosis', created_at=datetime.now(timezone.utc).isoformat(),
        posthoc=True, selection='All H runs for the same four known tasks: three P80/P81 repetitions and two P82 repetitions. H excludes current elapsed-time notices; no selection based on P84 outputs.',
        rows=rows, pairs=pairs, task_summary=summary, P83_archive_checks=archive_checks, P83_to_P82_call14_matches=matches,
        source_sha256={n: sha(root / n) for n in FILES}, independent_tasks=4, old_runs=12, new_runs=8,
        dependent_cross_cohort_pairs=24, missing_outputs_imputed=False, randomized_or_concurrent_ablation=False,
        causal_whole_task_normalization_effect_identified=False, model_visible_token_sequences_compared=False,
        historical_server_cache_or_GPU_state_replayed=False, P84_response_records_read=False,
        private_full_trajectories_read=False, private_P83_requests_read=len(archive_checks),
        private_reasoning_inspected_semantically=False, additional_generations=0,
        additional_input_counts=0, additional_api_requests=0, additional_evaluations=0,
        novel_method_claim=False, analysis_wall_seconds=time.monotonic() - began)


def write(result, output):
    output.mkdir(parents=True, exist_ok=False)
    with (output / 'comparison.json').open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2); f.write('\n')
    for name, rows in (('all_20_hidden_conditions.csv', result['rows']), ('all_24_cross_cohort_pairs.csv', result['pairs']),
                       ('all_12_saved_input_matches.csv', result['P83_to_P82_call14_matches'])):
        with (output / name).open('x', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or args.repo_root / DEFAULT
    if output.exists():
        raise FileExistsError('preserve_first_cross_cohort_analysis')
    result = analyze(args.repo_root, args.storage_root)
    write(result, output)
    print({'conditions': len(result['rows']), 'pairs': len(result['pairs']), 'task_summary': result['task_summary'],
           'saved_input_matches': result['P83_to_P82_call14_matches'], 'wall_seconds': result['analysis_wall_seconds']})
