"""Aggregate the entire closed P80/P81 fallback ledger without reading traces."""
import csv
from datetime import datetime, timezone
from pathlib import Path
import time

from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

FILES = ('reports/P80_comparison.json', 'reports/P81_repetitions.json',
         'reports/P81_fallback_reference_diagnostic.json',
         'reports/P81_P83_results_provenance_20261024.json')


def run(root=ROOT):
    started = time.monotonic()
    target = root / 'reports/P81_fallback_exposure_20261024.json'
    csv_path = root / 'materials/20261024_protocol_prior_exposure/all_24_conditions.csv'
    if target.exists() or csv_path.exists():
        raise FileExistsError('preserve_first_full_exposure_aggregation')
    anchor, cohort, diagnostic, ledger = [read(root / p) for p in FILES]
    for name, expected in ledger['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('closed_source_changed:' + name)
    original = anchor['rows'] + cohort['rows']
    if (len(original) != 24 or anchor['audit_errors'] or cohort['audit_errors']
            or anchor['batch_status'] != 'complete' or cohort['batch_status'] != 'complete'
            or cohort['anchor_rows'] != anchor['rows'] or cohort['anchor_sha256'] != sha(root / FILES[0])
            or diagnostic['partial_only'] or diagnostic['closed_cells'] != 24
            or diagnostic['source_is_private_partial_checkpoint']
            or diagnostic['source_cohort_sha256'] != sha(root / FILES[1])
            or diagnostic['source_anchor_sha256'] != sha(root / FILES[0])
            or len(diagnostic['rows']) != 24
            or [r['run_id'] for r in diagnostic['rows']] != [r['run_id'] for r in original]):
        raise ValueError('all_closed_twenty_four_conditions_required')
    rows = diagnostic['rows']
    for row, source in zip(rows, original, strict=True):
        if any(row[k] != source[k] for k in ('run_id', 'task_id', 'time_visibility', 'success',
                'known_total_tokens', 'unknown_usage_calls', 'model_calls')):
            raise ValueError('exposure_cohort_row_disagrees')
        total, reconstructed, exposed = [row[k] for k in ('model_calls', 'reconstructed_request_count',
                                                         'requests_with_fallback_references')]
        first = row['first_request_with_fallback_references']
        if (any(type(n) is not int for n in (total, reconstructed, exposed))
                or not 0 <= exposed <= reconstructed <= total
                or (first is None) != (exposed == 0)
                or (first is not None and (type(first) is not int or not 1 <= first <= total))):
            raise ValueError('invalid_full_exposure_counts')
    groups = []
    for task in dict.fromkeys(r['task_id'] for r in rows):
        for policy in ('measured', 'not_exposed'):
            selected = [r for r in rows if r['task_id'] == task and r['time_visibility'] == policy]
            if len(selected) != 3: raise ValueError('three_repetitions_per_condition_required')
            groups.append(dict(task_id=task, time_visibility=policy, cells=3,
                model_calls=sum(r['model_calls'] for r in selected),
                reconstructed_requests=sum(r['reconstructed_request_count'] for r in selected),
                requests_with_fallback_references=sum(r['requests_with_fallback_references'] for r in selected),
                cells_with_exposure=sum(bool(r['requests_with_fallback_references']) for r in selected),
                successful_cells=sum(r['success'] for r in selected),
                unknown_usage_calls=sum(r['unknown_usage_calls'] for r in selected)))
    failures = [r for r in rows if not r['success']]
    result = dict(phase='P81_fallback_exposure', created_at=datetime.now(timezone.utc).isoformat(),
        rows=rows, groups=groups, independent_tasks=4, cells=24,
        model_calls=sum(r['model_calls'] for r in rows),
        reconstructed_requests=sum(r['reconstructed_request_count'] for r in rows),
        exposed_requests=sum(r['requests_with_fallback_references'] for r in rows),
        exposed_cells=sum(bool(r['requests_with_fallback_references']) for r in rows),
        unknown_usage_calls=sum(r['unknown_usage_calls'] for r in rows),
        failed_cells=len(failures), failed_cells_without_exposure=sum(not r['requests_with_fallback_references'] for r in failures),
        source_sha256={name: sha(root / name) for name in FILES}, script_sha256=sha(Path(__file__)),
        wall_seconds=time.monotonic()-started, raw_histories_read=False,
        private_reasoning_inspected_semantically=False, additional_generations=0,
        additional_input_count_requests=0, additional_api_requests=0, additional_evaluations=0,
        distinct_bug_count_identified=False, exposure_causes_failure_identified=False,
        novel_method_claim=False, interpretation='All 24 closed conditions and 429 saved requests; repeated exposure in growing histories is not a count of independent bugs or tasks. Presence and absence are descriptive, not a causal quality or cost effect.')
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    write_json(target, result)
    print({k: result[k] for k in ('cells', 'model_calls', 'reconstructed_requests', 'exposed_requests',
        'exposed_cells', 'failed_cells', 'failed_cells_without_exposure', 'wall_seconds')})
    return result


if __name__ == '__main__':
    run()
