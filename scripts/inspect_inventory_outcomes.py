"""Compare audited saved application databases without reading hidden tests.

Equal application files are a useful constraint on interpretation. They do
not prove which particular evaluator requirement caused an outcome difference.
No database mutation, replay, or additional evaluation is performed.
"""
import argparse
from itertools import combinations
from pathlib import Path

from inventory_display import ARMS
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def inspect(storage):
    report = read(ROOT / 'reports/P55_comparison.json')
    if report['audit_errors'] or not report['all_planned_cells_accounted']:
        raise ValueError('audited closed comparison required')
    rows = []
    for task in dict.fromkeys(r['task_id'] for r in report['rows']):
        cells = {r['arm']: r for r in report['rows'] if r['task_id'] == task}
        for left, right in combinations(ARMS, 2):
            pair = [cells[left], cells[right]]
            row = {'task_id': task, 'arms': [left, right],
                   'run_ids': [r['run_id'] for r in pair],
                   'both_evaluated': all(r['record_status'] == 'evaluated' for r in pair)}
            rows.append(row)
            if not row['both_evaluated']: continue
            paths = [storage / 'records/context_pilot' / r['run_id'] / 'evaluation.json' for r in pair]
            if any(sha(p) != r['source_sha256']['evaluation.json'] for p, r in zip(paths, pair, strict=True)):
                raise ValueError('evaluation changed after audit')
            values = [read(p) for p in paths]
            dbs = [v['frozen_database_hashes'] for v in values]
            if set(dbs[0]) != set(dbs[1]): raise ValueError('different database file sets')
            changed = sorted(k for k in dbs[0] if dbs[0][k] != dbs[1][k])
            app_changed = [k for k in changed if k != 'model_hashes.json']
            row.update(independent_success=[r['success'] for r in pair],
                changed_saved_files=changed, changed_application_files=app_changed,
                equal_non_supervisor_app_files=not any(k != 'supervisor.jsonl' for k in app_changed),
                changes_confined_to_supervisor_file=app_changed == ['supervisor.jsonl'],
                complete_task_requests=[r.get('sent_api_names', {}).get('supervisor__complete_task', 0) for r in pair],
                source_sha256=[sha(p) for p in paths])
    return {'phase': 'P55_outcome_scope', 'rows': rows,
        'source_audit_sha256': sha(ROOT / 'reports/P55_comparison.json'),
        'inspector_sha256': sha(Path(__file__)), 'additional_model_calls': 0,
        'additional_api_requests': 0, 'additional_evaluator_calls': 0,
        'hidden_test_details_read': False,
        'limits': ['Comparison of frozen saved database files, after their live-file hashes were checked by the auditor.',
            'model_hashes.json is an aggregate hash index, not an independent application state.',
            'Different serialized files do not quantify semantic task progress.',
            'Identical non-supervisor files constrain interpretation but do not identify a failing hidden test.',
            'No completion normalization, retrospective success relabeling, or causal intervention.']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    args = p.parse_args(); target = ROOT / 'reports/P55_outcome_scope.json'
    if target.exists(): raise FileExistsError('preserve prior outcome inspection')
    result = inspect(args.storage_root); write_json(target, result)
    print('Compared', len(result['rows']), 'planned pairs; no task or evaluator calls.')
