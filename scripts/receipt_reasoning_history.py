"""Experimental reasoning display policies driven by trusted execution receipts.

Successful execution is a selection heuristic, never a semantic redundancy
certificate. Actions, observations, instructions and archival history remain.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json

POLICIES = ('full', 'recent', 'execution_gated')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def require(condition, label):
    if not condition:
        raise ValueError(label)


def execution_evidence(events, spans, *, pending_reads):
    """Use host records, never claims embedded in stdout or returned API values."""
    require(type(pending_reads) is int and pending_reads >= 0, 'explicit_pending_read_count_required')
    require(type(events) is list and len(events) <= 4000 and type(spans) is dict, 'bounded_turn_records')
    ids = [e['span_id'] for e in events]
    require(len(ids) == len(set(ids)) and set(ids) == set(spans), 'complete_turn_record_mapping')
    require(len({e['call'] for e in events}) <= 1, 'one_model_turn_required')
    require(all(e['stage'] in ('model_tool', 'python_api') for e in events), 'known_event_stage')
    inners = {e['span_id']: e for e in events if e['stage'] == 'python_api'}
    outers = [e for e in events if e['stage'] == 'model_tool']
    reasons = set(); linked = set(); functions = []
    if not outers:
        reasons.add('no_recorded_action')
    if pending_reads:
        reasons.add('pending_reads')
    for event in outers:
        require(event['api_request_sent'] is False, 'outer_record_cannot_send_API')
        span = spans[event['span_id']]; action = span.get('action'); obs = span['observation']
        require(type(obs) is dict, 'outer_observation_object')
        if type(action) is dict:
            functions.append(deepcopy(action))
        if not action or action.get('name') != 'run_python':
            reasons.add('non_python_or_no_action')
        if obs.get('status') != 'ok':
            reasons.add('execution_not_confirmed_ok')
        if 'format_error' in obs or 'not_executed' in obs:
            reasons.add('rejected_or_not_executed')
        if obs.get('stdout_truncated'):
            reasons.add('truncated_execution_output')
        linked_here = []
        for receipt in obs.get('api_receipts', []):
            sid = receipt['span_id']; inner = inners.get(sid)
            require(inner is not None and sid not in linked and ids.index(sid) < ids.index(event['span_id']),
                    'unique_prior_inner_receipt_required')
            require(receipt['api_request_sent'] == inner['api_request_sent'] and
                    receipt['api'] == spans[sid]['action']['name'], 'inner_receipt_link_changed')
            linked.add(sid); linked_here.append(inner)
        if 'api_requests' in obs:
            require(type(obs['api_requests']) is int and obs['api_requests'] ==
                    sum(e['api_request_sent'] for e in linked_here), 'outer_API_count_changed')
    require(linked == set(inners), 'all_inner_records_linked')
    sent = sum(e['api_request_sent'] for e in inners.values())
    if not sent:
        reasons.add('no_actual_API_request')
    for event in events:
        if event.get('effects_unknown'):
            reasons.add('effects_unknown')
        if event['stage'] != 'python_api':
            continue
        if event['api_request_sent'] is not True:
            reasons.add('API_not_sent')
            continue
        receipt = event.get('api_execution') or {}
        if (receipt.get('status') != 'returned' or receipt.get('bridge_request_sent') is not True
                or receipt.get('automatic_retries') != 0):
            reasons.add('API_return_not_confirmed')
    return dict(eligible=not reasons, reasons=sorted(reasons), outer_records=len(outers),
        API_records=len(inners), actual_API_requests=sent, pending_reads=pending_reads,
        public_function_signature_sha256=digest(functions),
        trusted_record_sha256=digest(dict(events=events, spans=spans)),
        semantic_redundancy_certified=False)


def strip_reasoning(messages):
    result = deepcopy(messages)
    for message in result:
        if message.get('role') == 'assistant':
            message.pop('reasoning_content', None)
    return result


def project(messages, evidence, policy):
    """Re-render from full archival history; restored text is never synthesized."""
    require(policy in POLICIES, 'fixed_history_policy_required')
    require(type(messages) is list and len(messages) <= 2048, 'bounded_history_required')
    assistants = [m for m in messages if m.get('role') == 'assistant']
    require(len(assistants) == len(evidence), 'one_receipt_record_per_assistant_turn')
    bindings = []
    for message, entry in zip(assistants, evidence, strict=True):
        require(type(entry.get('eligible')) is bool and type(entry.get('reasons')) is list,
                'trusted_eligibility_shape')
        require(entry['eligible'] == (not entry['reasons']) and
                entry.get('semantic_redundancy_certified') is False, 'heuristic_evidence_required')
        value = message.get('reasoning_content')
        require(value is None or type(value) is str, 'recorded_reasoning_text_required')
        functions = [c['function'] for c in message.get('tool_calls') or []]
        bindings.append(digest(functions) == entry['public_function_signature_sha256'])
    latest_closed = bool(evidence and evidence[-1]['eligible'] and bindings[-1])
    removed = []; kept = []; unbound = []
    for i, (message, entry, bound) in enumerate(zip(assistants, evidence, bindings, strict=True)):
        number = i + 1
        if not bound:
            unbound.append(number)
        remove = i < len(assistants)-1 and (policy == 'recent' or
            policy == 'execution_gated' and latest_closed and entry['eligible'] and bound)
        (removed if remove and 'reasoning_content' in message else kept).append(number)
    result = deepcopy(messages)
    output_assistants = [m for m in result if m.get('role') == 'assistant']
    for number in removed:
        output_assistants[number-1].pop('reasoning_content', None)
    require(strip_reasoning(result) == strip_reasoning(messages), 'non_reasoning_history_changed')
    original_characters = sum(len(m.get('reasoning_content') or '') for m in assistants)
    supplied_characters = sum(len(m.get('reasoning_content') or '') for m in output_assistants)
    return result, dict(policy=policy, prior_turns=len(evidence), latest_execution_eligible=latest_closed,
        removed_reasoning_turns=removed, retained_reasoning_turns=kept,
        signature_unbound_turns=unbound, original_reasoning_characters=original_characters,
        supplied_reasoning_characters=supplied_characters,
        removed_reasoning_characters=original_characters-supplied_characters,
        public_history_sha256=digest(strip_reasoning(messages)),
        original_history_sha256=digest(messages), supplied_history_sha256=digest(result),
        latest_reasoning_preserved=True, full_archive_unchanged=True,
        semantic_redundancy_certified=False, task_quality_established=False)
