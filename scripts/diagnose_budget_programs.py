"""Describe all eight closed P40 continuations using recorded public executions.

No generated program is executed. No evaluator details, arguments, object IDs,
credentials or free-form output are exported. Repetition is not called waste.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

from audit_budget_visibility import budget_before_calls
from budget_signal import ARMS
from diagnose_code_programs import classify
from diagnose_handoff_programs import matching_prefix_requests
from run_handoff_factors import ROOT, read, sha


def analyze(storage, root):
    target = root / 'reports/P40_program_diagnostics.json'
    if target.exists():
        raise FileExistsError('preserve completed diagnostics')
    report = read(root / 'reports/P40_comparison.json')
    status = read(storage / 'records/context_pilot/P40_batch_v01/status.json')
    expected = {f'P40_{n:02d}_{a.upper()}' for n in range(1, 5) for a in ARMS}
    if (not report['all_eight_reviewed'] or report['audit_errors']
            or status['status'] != 'complete' or len(report['rows']) != 8
            or {r['run_id'] for r in report['rows']} != expected
            or set(status['completed']) != expected):
        raise ValueError('require the closed and audited eight-cell cohort')
    rows = []
    for cell in report['rows']:
        folder = storage / 'records/context_pilot' / cell['run_id']
        for name in ('events.json', 'spans.json', 'usage.json', 'summary.json', 'plan.json'):
            if sha(folder / name) != cell['source_hashes'][name]:
                raise ValueError('closed execution changed: ' + name)
        events, spans, usage = [read(folder / n) for n in ('events.json', 'spans.json', 'usage.json')]
        prefix_events, prefix_spans = [read(folder / n) for n in ('prefix_events.json', 'prefix_spans.json')]
        limits = read(folder / 'plan.json')
        before, accounting = budget_before_calls(usage, events, cell['prefix_api_requests'], limits)
        if (accounting['known_total_tokens'] != cell['known_total_tokens']
                or accounting['suffix_api_requests'] != cell['api_requests']):
            raise ValueError('independent diagnosis accounting disagrees')
        programs = {}; paths = sorted((folder / 'programs').glob('*/result_private.json'))
        for path in paths:
            programs.setdefault(path.parent.name.rsplit('_', 1)[0], []).append(read(path))
        row = classify(usage, events, spans, programs)
        row.update(matching_prefix_requests(prefix_events, prefix_spans, events, spans))
        for call, budget, counts in zip(usage, before, row['call_rows']):
            selected = [e for e in events if e['call'] == call['id'] and e['api_request_sent']]
            names = Counter(spans[e['span_id']]['action']['name'] for e in selected)
            counts.update(remaining_api_before=budget['remaining_api_before'],
                          remaining_api_after=budget['remaining_api_before'] - len(selected),
                          remaining_tokens_before=budget['remaining_tokens_before'],
                          input_tokens=call.get('input_tokens'), output_tokens=call.get('output_tokens'),
                          dispatched_api_names=dict(names))
        row.update(run_id=cell['run_id'], task_id=cell['task_id'], arm=cell['arm'],
                   success=cell['success'], stop_reason=cell['stop_reason'],
                   remaining_api_at_stop=limits['max_api_requests'] - cell['prefix_api_requests'] - cell['api_requests'],
                   remaining_logical_tokens_at_stop=limits['max_total_tokens'] - cell['known_total_tokens'],
                   repeat_identical_request_excess=cell['repeat_identical_request_excess'],
                   archive_read_calls=cell['archive_read_calls'],
                   program_result_sha256={str(p.relative_to(folder)): sha(p) for p in paths},
                   source_sha256={n: sha(folder / n) for n in
                                  ('usage.json', 'events.json', 'spans.json', 'prefix_events.json',
                                   'prefix_spans.json', 'plan.json')})
        rows.append(row)
    result = {'phase': 'P40_program_diagnostics', 'all_eight_reviewed': True, 'rows': rows,
              'additional_model_calls': 0, 'additional_api_requests': 0,
              'evaluator_contents_read': False, 'reserved_scenarios_read': 0,
              'causal_remedy_identified': False,
              'limits': ['Post-hoc diagnostics on the same four development tasks.',
                         'Exact repeated requests include writes and can be legitimate.',
                         'Unused budget at stop is not necessarily sufficient for another admissible generation.',
                         'Program errors do not imply rollback of prior API effects.',
                         'Counts do not establish which information was unnecessary or a new control method.'],
              'source_sha256': {p: sha(root / p) for p in
                  ('reports/P40_comparison.json', 'scripts/diagnose_budget_programs.py',
                   'scripts/diagnose_code_programs.py', 'scripts/diagnose_handoff_programs.py',
                   'scripts/audit_budget_visibility.py')}}
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps([{'run_id': r['run_id'], 'program_errors': r['program_error_types'],
                      'repeated_requests': r['repeat_identical_request_excess'],
                      'api_left': r['remaining_api_at_stop'],
                      'tokens_left': r['remaining_logical_tokens_at_stop']} for r in rows]))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    args = parser.parse_args()
    analyze(args.storage_root, args.repo_root)
