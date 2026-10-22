"""Passive diagnostics for every audited P47 condition, with shared prefix costs.

Export only counters, API names, exception types and hashes. Read no evaluator
internals and execute no saved programs. An exact repeated request is not waste.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

from audit_budget_visibility import budget_before_calls
from diagnose_code_programs import classify
from diagnose_handoff_programs import matching_prefix_requests
from contract_comparison import ARMS
from inspect_contract_feedback import schema_lookups
from run_handoff_factors import ROOT, read, sha


def require_closed(report, status):
    expected = {f'P47_{n:02d}_{arm.upper()}' for n in range(1, 5) for arm in ARMS}
    rows = report.get('rows', [])
    if (report.get('phase') != 'P47' or not report.get('all_planned_cells_accounted')
            or report.get('audit_errors') or len(rows) != 12
            or {r['run_id'] for r in rows} != expected
            or status.get('status') not in ('complete', 'stopped')
            or report.get('batch_status') != status['status']
            or set(status['planned']) != expected
            or set(status['completed']) != {r['run_id'] for r in rows if r['record_status'] == 'evaluated'}):
        raise ValueError('require all twelve audited cells from the closed batch')


def usage_total(usage):
    known = 0
    unknown = 0
    for call in usage:
        values = [call.get(k) for k in ('input_tokens', 'output_tokens')]
        if call['status'] == 'ok':
            if any(type(v) is not int or v < 0 for v in values):
                raise ValueError('known usage needs nonnegative integer counters')
            known += sum(values)
        else:
            if any(v is not None for v in values):
                raise ValueError('unknown terminal usage must not be imputed')
            unknown += 1
    return {'model_calls': len(usage), 'known_total_tokens': known, 'unknown_usage_calls': unknown}


def feedback_followups(usage, events, spans, codes, feedback_events):
    """Describe later behavior, without assigning a causal saving to feedback."""
    indices = {call['id']: i for i, call in enumerate(usage)}
    rows = []
    for feedback in feedback_events:
        index = indices[feedback['call_id']]
        following = usage[index + 1] if index + 1 < len(usage) else None
        if feedback['next_call_id'] != (following['id'] if following else None):
            raise ValueError('audited following-call identity changed')
        next_code = codes.get(following['id'], []) if following else []
        lookup = []; parsed = []
        for code in next_code:
            try:
                lookup.append(feedback['api'] in schema_lookups(code)); parsed.append(True)
            except SyntaxError:
                parsed.append(False)
        same_api = [e for e in events if e['stage'] == 'python_api'
                    and spans[e['span_id']]['action']['name'] == feedback['api']
                    and indices[e['call']] > index]
        sent = [e for e in same_api if e['api_request_sent']]
        later = usage_total(usage[index + 1:])
        rows.append({k: feedback[k] for k in ('call_id', 'span_id', 'api', 'mode', 'characters',
            'next_call_id', 'canonical_feedback_in_immediate_next_input')} | {
            'next_programs': len(next_code),
            'next_programs_all_parse': all(parsed) if parsed else None,
            'next_program_has_literal_schema_lookup': True if any(lookup) else False if parsed and all(parsed) else None,
            'next_same_api_dispatches': sum(e['call'] == following['id'] for e in sent) if following else None,
            'next_same_api_format_rejections': sum(e['call'] == following['id'] and
                'format_error' in spans[e['span_id']]['observation'] for e in same_api) if following else None,
            'first_later_same_api_dispatch_call': sent[0]['call'] if sent else None,
            'following_call_cost': usage_total([following]) if following else None,
            'all_later_calls_cost': later,
            'cost_is_claimed_savings': False,
            'same_api_dispatch_is_claimed_correct_repair': False})
    return rows


def analyze(storage, root):
    report_path = root / 'reports/P47_comparison.json'
    report = read(report_path)
    base = storage / 'records/context_pilot'
    status_path = base / 'P47_batch_v01/status.json'
    status = read(status_path)
    require_closed(report, status)
    if sha(status_path) != report['source_sha256']['batch_status']:
        raise ValueError('closed batch changed since audit')
    rows = []
    for cell in report['rows']:
        if cell['record_status'] == 'not_run_after_stop':
            rows.append({k: cell[k] for k in ('run_id', 'task_id', 'arm', 'record_status')})
            continue
        folder = base / cell['run_id']
        names = ('events.json', 'spans.json', 'usage.json', 'prefix_events.json',
                 'prefix_spans.json', 'prefix_usage.json', 'summary.json', 'plan.json')
        for name in names:
            if sha(folder / name) != cell['source_sha256'][name]:
                raise ValueError('audited execution changed: ' + name)
        events, spans, usage = [read(folder / n) for n in names[:3]]
        prefix_events, prefix_spans, prefix_usage = [read(folder / n) for n in names[3:6]]
        limits = read(folder / 'plan.json')
        before, accounting = budget_before_calls(usage, events, cell['prefix_api_requests'], limits)
        if (accounting['known_total_tokens'] != cell['known_total_tokens']
                or accounting['suffix_api_requests'] != cell['api_requests']):
            raise ValueError('diagnostic accounting disagrees with audit')
        programs = {}; codes = {}
        paths = sorted((folder / 'programs').glob('*/result_private.json'))
        for path in paths:
            call_id = path.parent.name.rsplit('_', 1)[0]
            for name in ('input_private.json', 'result_private.json', 'wire_private.jsonl'):
                source = path.parent / name
                relative = str(source.relative_to(folder))
                if sha(source) != cell['feedback_audit']['source_sha256'].get(relative):
                    raise ValueError('audited program changed: ' + relative)
            programs.setdefault(call_id, []).append(read(path))
            codes.setdefault(call_id, []).append(read(path.parent / 'input_private.json')['code'])
        row = classify(usage, events, spans, programs)
        row.update(matching_prefix_requests(prefix_events, prefix_spans, events, spans))
        row['feedback_followups'] = feedback_followups(usage, events, spans, codes,
                                                     cell['feedback_audit']['feedback_events'])
        for call, budget, counts in zip(usage, before, row['call_rows'], strict=True):
            selected = [e for e in events if e['call'] == call['id'] and e['api_request_sent']]
            names_by_call = Counter(spans[e['span_id']]['action']['name'] for e in selected)
            counts.update(remaining_api_before=budget['remaining_api_before'],
                          remaining_tokens_before=budget['remaining_tokens_before'],
                          input_tokens=call.get('input_tokens'), output_tokens=call.get('output_tokens'),
                          dispatched_api_names=dict(names_by_call))
        prefix_cost = usage_total(prefix_usage)
        suffix_cost = usage_total(usage)
        if (suffix_cost['known_total_tokens'] != cell['known_total_tokens']
                or suffix_cost['unknown_usage_calls'] != cell['unknown_usage_calls']
                or prefix_cost['known_total_tokens'] != cell['prefix_known_total_tokens']
                or prefix_cost['unknown_usage_calls'] != cell['prefix_unknown_usage_calls']):
            raise ValueError('known and unknown usage disagree with audit')
        row.update(run_id=cell['run_id'], task_id=cell['task_id'], arm=cell['arm'],
                   record_status=cell['record_status'], success=cell['success'], stop_reason=cell['stop_reason'],
                   prefix_cost=prefix_cost, continuation_cost=suffix_cost,
                   logical_task_cost={k: prefix_cost[k] + suffix_cost[k] for k in prefix_cost},
                   remaining_api_at_stop=limits['max_api_requests'] - cell['prefix_api_requests'] - cell['api_requests'],
                   remaining_logical_tokens_at_stop=limits['max_total_tokens'] - cell['known_total_tokens'],
                   archive_read_calls=cell['archive_read_calls'],
                   repeat_identical_request_excess=cell['repeat_identical_request_excess'],
                   input_counts_without_timing=cell['input_counts_without_timing'],
                   program_result_sha256={str(p.relative_to(folder)): sha(p) for p in paths},
                   source_sha256={name: sha(folder / name) for name in names})
        rows.append(row)
    totals = {}
    for arm in ARMS:
        selected = [r for r in rows if r['arm'] == arm and r['record_status'] != 'not_run_after_stop']
        totals[arm] = {'attempted_trials': len(selected)}
        for group in ('prefix_cost', 'continuation_cost', 'logical_task_cost'):
            totals[arm][group] = {k: sum(r[group][k] for r in selected)
                                 for k in ('model_calls', 'known_total_tokens', 'unknown_usage_calls')}
    return {'phase': 'P47_program_diagnostics', 'all_planned_cells_accounted': True,
            'kind': 'posthoc_closed_cohort_diagnostics', 'rows': rows, 'totals': totals,
            'additional_model_calls': 0, 'additional_api_requests': 0,
            'additional_tokenizer_requests': 0, 'evaluator_contents_read': False,
            'reserved_scenarios_read': 0, 'causal_remedy_identified': False,
            'limits': ['Logical task costs add the recorded common prefix once per condition; they are not new end-to-end runs.',
                       'Physical reconstruction and server loading are separately reported, not token-free model work.',
                       'Missing cells have no logical task estimate; unknown usage remains additional to known sums.',
                       'Exact repeated requests include writes, legitimate rechecks and documentation reads.',
                       'Program errors do not imply rollback of earlier API effects. No causal remedy is identified.',
                       'A literal schema lookup may not execute; a later same-API dispatch may change arguments and is not proof of a correct repair.',
                       'Following-call and all-later-call costs are descriptive, overlapping across feedback events and not attributable savings.'],
            'source_sha256': {'comparison': sha(report_path), 'batch_status': sha(status_path),
                              'script': sha(Path(__file__)),
                              'classifier': sha(root / 'scripts/diagnose_code_programs.py')}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    args = parser.parse_args()
    target = args.repo_root / 'reports/P47_program_diagnostics.json'
    if target.exists():
        raise FileExistsError('preserve completed diagnostics')
    result = analyze(args.storage_root, args.repo_root)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result['totals']))
