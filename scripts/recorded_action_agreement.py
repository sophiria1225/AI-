"""Bounded description of recorded responses and actual API dispatches.

Never runs saved code. Matching API prefixes are observations, not proof of
equal Python/DB state. Empty request sequences are reported separately from
nonempty API agreement. All argument values, identifiers and ordering remain.
"""
from collections import Counter
from itertools import combinations, zip_longest

from public_action_structure import digest, inspect as structure, strict_object


def response_summary(response):
    original = structure(response or {})
    fields = ('status', 'public_output_sha256', 'content_sha256',
              'json_actions_sha256', 'syntax_actions_sha256', 'tool_calls',
              'JSON_objects', 'interface_shapes_valid', 'Python_ASTs_valid')
    return {k: original.get(k) for k in fields}


def action_value(action):
    if type(action) is not dict or set(action) != {'name', 'arguments'}:
        raise ValueError('API_action_shape')
    name, arguments = action['name'], action['arguments']
    if type(name) is not str or name.count('__') != 1 or len(name) > 180:
        raise ValueError('API_name_shape')
    if type(arguments) is str:
        arguments = strict_object(arguments)
    if type(arguments) is not dict:
        raise ValueError('API_arguments_object_required')
    return dict(name=name, arguments=arguments)


def execution_kind(span):
    observation = span['observation']
    if 'format_error' in observation:
        return 'format_rejected'
    if 'not_executed' in observation:
        return 'not_executed'
    name = (span.get('action') or {}).get('name')
    if name == 'run_python':
        status = observation.get('status')
        if status in ('ok', 'execution_error'):
            return 'executed_' + status
        return 'execution_unresolved'
    if name == 'read_span':
        return 'archive_read_returned'
    raise ValueError('unclassified_outer_record')


def analyze_run(usage, events, spans, responses):
    if len(usage) > 80 or len(events) > 4000 or len(spans) != len(events):
        raise ValueError('fixed_inventory_bound')
    ids = [u['id'] for u in usage]
    if len(ids) != len(set(ids)) or set(responses) != set(ids):
        raise ValueError('all_response_slots_required')
    positions = {cid: i for i, cid in enumerate(ids)}
    ranks = [positions.get(e['call'], -1) for e in events]
    event_ids = [e['span_id'] for e in events]
    if (-1 in ranks or ranks != sorted(ranks) or len(set(event_ids)) != len(event_ids)
            or set(event_ids) != set(spans)):
        raise ValueError('chronological_complete_events_required')
    by_id = {e['span_id']: e for e in events}
    prefix = []; prefix_known = True; result = []; linked = set()
    for ordinal, u in enumerate(usage, 1):
        cid = u['id']; response = responses[cid]; known = u['status'] == 'ok'
        if known != bool(response and response.get('status') == 'ok'):
            raise ValueError('audited_response_status_changed')
        selected = [e for e in events if e['call'] == cid]
        if not known and selected:
            raise ValueError('unknown_response_has_execution')
        if any(e['stage'] not in ('model_tool', 'python_api') for e in selected):
            raise ValueError('unclassified_event_stage')
        outer = [e for e in selected if e['stage'] == 'model_tool']
        described = response_summary(response)
        functions = [c['function'] for c in (response['message'].get('tool_calls') or [])] if known else []
        if outer:
            expected = functions or [None]
            if [spans[e['span_id']]['action'] for e in outer] != expected:
                raise ValueError('submitted_and_recorded_actions_differ')
        elif selected:
            raise ValueError('inner_events_without_outer_record')
        before = digest(prefix) if prefix_known else None
        api = []; kinds = []; public_results = []
        for e in selected:
            span = spans[e['span_id']]
            if span['id'] != e['span_id'] or type(span['observation']) is not dict:
                raise ValueError('span_identity_or_observation_shape')
            if e['api_request_sent']:
                receipt = e.get('api_execution')
                if (e['stage'] != 'python_api' or type(receipt) is not dict
                        or receipt.get('bridge_request_sent') is not True
                        or receipt.get('automatic_retries') != 0
                        or receipt.get('status') not in ('returned', 'raised', 'unknown')):
                    raise ValueError('one_typed_receipt_per_actual_API_required')
                api.append(dict(action=action_value(span['action']),
                    status=receipt['status'], observation=span['observation'],
                    new_tools=e['new_tools']))
                if receipt['status'] == 'unknown':
                    prefix_known = False
            if e.get('effects_unknown'):
                prefix_known = False
            if e['stage'] != 'model_tool':
                continue
            if e['api_request_sent']:
                raise ValueError('outer_cannot_dispatch_API')
            obs = span['observation']; kinds.append(execution_kind(span))
            inner_ids = []
            for receipt in obs.get('api_receipts', []):
                sid = receipt['span_id']; inner = by_id.get(sid)
                if (sid in linked or inner is None or inner['stage'] != 'python_api'
                        or inner['call'] != cid or event_ids.index(sid) >= event_ids.index(e['span_id'])
                        or receipt['api'] != spans[sid]['action']['name']
                        or receipt['api_request_sent'] != inner['api_request_sent']):
                    raise ValueError('invalid_inner_to_outer_receipt_link')
                linked.add(sid); inner_ids.append(sid)
            if 'api_requests' in obs and obs['api_requests'] != sum(by_id[s]['api_request_sent'] for s in inner_ids):
                raise ValueError('program_API_count_mismatch')
            # Assigned span references are transport metadata, not stdout. Keep
            # returned values and errors verbatim, including archive-read data.
            public_results.append({k: v for k, v in obs.items() if k != 'api_receipts'})
        requests_known = known and not any(e.get('effects_unknown') for e in selected)
        requests_known &= all(a['status'] != 'unknown' for a in api)
        prefix.extend(api)
        executed = sum(k in ('executed_ok', 'executed_execution_error', 'archive_read_returned') for k in kinds)
        completed_submission = bool(functions and len(outer) == len(functions) and executed == len(functions))
        result.append(dict(call_id=cid, ordinal=ordinal, usage_status=u['status'],
            known_total_tokens=u['input_tokens'] + u['output_tokens'] if known else None,
            response=described, execution_kinds=dict(Counter(kinds)),
            submitted_tool_calls=len(functions) if known else None,
            completed_submission=completed_submission,
            executed_tools=executed, API_requests=len(api),
            API_status_counts=dict(Counter(a['status'] for a in api)),
            API_requests_known=requests_known,
            API_request_sequence_sha256=digest([a['action'] for a in api]) if requests_known else None,
            API_result_sequence_sha256=digest(api) if requests_known else None,
            public_tool_results_sha256=digest(public_results) if outer else None,
            prior_API_prefix_sha256=before,
            prior_API_requests=len(prefix) - len(api),
            full_process_state_equal_claim=False))
    if linked != {e['span_id'] for e in events if e['stage'] == 'python_api'}:
        raise ValueError('unlinked_inner_event')
    return result


def equal_known(a, b):
    return a == b if a is not None and b is not None else None


def compare_call(a, b):
    if a is None or b is None:
        return dict(status='one_run_ended', public_equal=None, syntax_equal=None,
            API_class='unavailable', nonempty_API_equal=None, prior_API_prefix_equal=None,
            equal_public_without_completed_submission=False,
            different_syntax_same_nonempty_API=False)
    public = equal_known(a['response']['public_output_sha256'], b['response']['public_output_sha256'])
    syntax = equal_known(a['response']['syntax_actions_sha256'], b['response']['syntax_actions_sha256'])
    comparable = a['API_requests_known'] and b['API_requests_known']
    category = ('both_nonempty' if a['API_requests'] and b['API_requests'] else
                'one_empty' if a['API_requests'] or b['API_requests'] else 'both_empty') if comparable else 'unavailable'
    api_equal = equal_known(a['API_request_sequence_sha256'], b['API_request_sequence_sha256']) if category == 'both_nonempty' else None
    return dict(status='both_recorded', public_equal=public, syntax_equal=syntax,
        API_class=category, nonempty_API_equal=api_equal,
        API_result_equal=equal_known(a['API_result_sequence_sha256'], b['API_result_sequence_sha256']) if category == 'both_nonempty' else None,
        public_tool_results_equal=equal_known(a['public_tool_results_sha256'], b['public_tool_results_sha256']),
        prior_API_prefix_equal=equal_known(a['prior_API_prefix_sha256'], b['prior_API_prefix_sha256']),
        equal_public_without_completed_submission=public is True and not (a['completed_submission'] and b['completed_submission']),
        different_syntax_same_nonempty_API=syntax is False and api_equal is True)


def summarize_pairs(rows):
    return dict(aligned_slots=len(rows), status_counts=dict(Counter(r['status'] for r in rows)),
        API_class_counts=dict(Counter(r['API_class'] for r in rows)),
        equal_public_without_completed_submission=sum(r['equal_public_without_completed_submission'] for r in rows),
        different_syntax_same_nonempty_API=sum(r['different_syntax_same_nonempty_API'] for r in rows),
        comparable_public=sum(r['public_equal'] is not None for r in rows),
        equal_public=sum(r['public_equal'] is True for r in rows),
        comparable_syntax=sum(r['syntax_equal'] is not None for r in rows),
        equal_syntax=sum(r['syntax_equal'] is True for r in rows),
        equal_nonempty_API=sum(r['nonempty_API_equal'] is True for r in rows))


def compare_runs(runs):
    groups = {}
    for r in runs:
        groups.setdefault(r['task_id'], []).append(r)
    pairs = []
    for task, group in groups.items():
        for left, right in combinations(group, 2):
            rows = [dict(ordinal=i, **compare_call(a, b)) for i, (a, b) in
                    enumerate(zip_longest(left['calls'], right['calls']), 1)]
            matched = [r for r in rows if r['prior_API_prefix_equal'] is True]
            pairs.append(dict(task_id=task, left=left['run_id'], right=right['run_id'],
                relation='same_policy_repetition' if left['time_visibility'] == right['time_visibility'] else
                    'within_repetition' if left['repetition'] == right['repetition'] else 'cross_policy_cross_repetition',
                all_aligned=summarize_pairs(rows), matched_prior_API_prefix=summarize_pairs(matched),
                rows=rows, independent_samples=False))
    return pairs
