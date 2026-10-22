"""Post-hoc ordinary-set comparison on one already observed P24 task.

No API calls, database reads, evaluator access, generation or target export.
This does not infer the intention of later searches or certify their removal.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import signal
import time

from diagnose_p24_public_traces import read as public_rows
from run_handoff_factors import ROOT, read, sha
from run_context_comparison import write_json


def inspect(storage, data_root):
    started = time.monotonic()
    summary_path = ROOT / 'reports/P24_guidance_baseline_summary.json'
    summary = read(summary_path)
    trials = summary['trials']
    if (summary['pending'] or summary['audit_errors'] or len(trials) != 6
            or any(t['unknown_usage_calls'] or t['audit_errors'] for t in trials)):
        raise ValueError('closed complete original six required')
    selected = max(trials, key=lambda t: t['known_total_tokens'])
    if selected['run_id'] != 'P24_02_GUIDED':
        raise ValueError('fixed post-hoc scope changed')
    folder = storage / 'records/context_pilot' / selected['run_id']
    audit_path = ROOT / 'reports/P24_02_GUIDED_execution_audit.json'
    original = read(audit_path)
    for name in ('events.json', 'spans.json', 'plan.json'):
        if sha(folder / name) != original['source_hashes'][name]:
            raise ValueError('frozen public record changed: ' + name)
    provenance = read(folder / 'provenance.json')
    schemas = {}
    for app in ('phone', 'venmo'):
        name = 'api_docs/standard/' + app + '.json'
        if sha(data_root / name) != provenance['public_schema_hashes'][name]:
            raise ValueError('fixed public API contract changed')
        schemas[name] = sha(data_root / name)
    rows, _ = public_rows(storage, 'P24', 2)
    events = read(folder / 'events.json')
    by_span = {e['span_id']: e for e in events}
    if len(rows) != len(events) or len(by_span) != len(events):
        raise ValueError('every original operation must be accounted')
    contacts = [r for r in rows if r['name'] == 'phone__search_contacts'
                and r['args'].get('relationship') in ('roommate', 'coworker')]
    if (len(contacts) != 2 or {r['args']['relationship'] for r in contacts} != {'roommate', 'coworker'}
            or any(r['args'].get('query') or not isinstance(r['data'], list) for r in contacts)):
        raise ValueError('expected two unqueried relationship-filtered observations')
    member_rows = [v for r in contacts for v in r['data']]
    if any(not isinstance(v.get('email'), str) or not v['email'] for v in member_rows):
        raise ValueError('no complete observed email key')
    members = {v['email'] for v in member_rows}
    prior = {v['contact_id']: v for v in member_rows}
    pages = [r for r in rows if r['name'] == 'venmo__show_received_payment_requests']
    if any(r['args'].get('status') != 'pending' or not isinstance(r['data'], list) for r in pages):
        raise ValueError('expected pending-request pages')
    requests = [v for r in pages for v in r['data']]
    request_ids = [v['payment_request_id'] for v in requests]
    if len(request_ids) != len(set(request_ids)):
        raise ValueError('duplicate request ids require separate treatment')
    joined = {v['payment_request_id'] for v in requests if v['sender']['email'] in members}
    approvals = [r for r in rows if r['name'] == 'venmo__approve_payment_request']
    approved = {r['args']['payment_request_id'] for r in approvals}
    later = [r for r in rows if r['name'] == 'phone__search_contacts' and 'query' in r['args']]
    boundary = max(by_span[r['id']]['turn'] for r in contacts + pages)
    late_rows = []
    for r in later:
        returned = r['data']
        if not isinstance(returned, list): raise ValueError('non-list later response')
        late_rows.append({'span_id': r['id'], 'model_call': by_span[r['id']]['call'],
            'after_observed_join_inputs': by_span[r['id']]['turn'] > boundary,
            'returned_rows': len(returned),
            'rows_exactly_in_prior_relationship_results': sum(prior.get(v['contact_id']) == v for v in returned),
            'rows_with_ids_absent_from_prior_relationship_results': sum(v['contact_id'] not in prior for v in returned),
            'all_returned_rows_exactly_available_before': all(prior.get(v['contact_id']) == v for v in returned)})
    api_counts = dict(sorted(Counter(r['name'] for r in rows).items()))
    result = {'phase': 'P59', 'status': 'complete', 'kind': 'posthoc_ordinary_membership_scope',
        'selection': 'Largest known whole-work token cost among all six already completed P24 development trials.',
        'six_original_trials': [{k: t[k] for k in ('run_id', 'task_id', 'model_calls', 'known_total_tokens', 'unknown_usage_calls')} for t in trials],
        'selected_run': selected['run_id'], 'api_counts': api_counts,
        'relationship_pages': [{'span_id': r['id'], 'relationship': r['args']['relationship'],
            'page_index': r['args'].get('page_index', 0), 'page_limit': r['args'].get('page_limit', 5),
            'returned_rows': len(r['data']),
            'first_page_under_limit': r['args'].get('page_index', 0) == 0 and len(r['data']) < r['args'].get('page_limit', 5),
            'rows_contain_requested_relationship': all(r['args']['relationship'] in v['relationships'] for v in r['data'])} for r in contacts],
        'observed_relationship_rows': len(member_rows), 'observed_unique_member_emails': len(members),
        'pending_pages': [{'page_index': r['args'].get('page_index', 0), 'returned_rows': len(r['data'])} for r in pages],
        'observed_pending_requests': len(requests), 'ordinary_join_selected': len(joined),
        'observed_approval_requests': len(approvals), 'observed_unique_approval_ids': len(approved),
        'ordinary_join_matches_observed_approval_ids': joined == approved,
        'later_contact_searches': late_rows,
        'later_contact_response_rows': sum(r['returned_rows'] for r in late_rows),
        'later_contact_unique_ids': len({v['contact_id'] for r in later for v in r['data']}),
        'source_sha256': {'reports/P24_guidance_baseline_summary.json': sha(summary_path),
            'reports/P24_02_GUIDED_execution_audit.json': sha(audit_path),
            **{name: sha(folder / name) for name in ('events.json', 'spans.json', 'plan.json', 'provenance.json')},
            **schemas},
        'model_calls': 0, 'tokenizer_requests': 0, 'environment_api_requests': 0, 'evaluator_calls': 0,
        'database_reads': 0, 'reserved_scenarios_read': 0, 'script_sha256': sha(Path(__file__)),
        'limits': ['The analyst supplies the membership predicate and key; this is not autonomous requirement interpretation.',
            'A short first page is observed; population completeness and absence of external changes are assumptions, not new guarantees.',
            'Matching observed approval IDs does not prove all task requirements or an independent quality outcome.',
            'A membership answer is not an equivalent replacement for the full contact search response.',
            'No skipped-query execution, LLM token saving, safe online filter or novel method has been evaluated.']}
    result['wall_seconds'] = time.monotonic() - started
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--data-root', type=Path, required=True); args = p.parse_args()
    signal.alarm(60)
    output = ROOT / 'reports/P59_membership_scope.json'
    if output.exists(): raise FileExistsError('preserve the previous inspection')
    result = inspect(args.storage_root, args.data_root); write_json(output, result)
    print(json.dumps({k: result[k] for k in ('status', 'ordinary_join_selected', 'ordinary_join_matches_observed_approval_ids', 'later_contact_response_rows', 'wall_seconds')}))
