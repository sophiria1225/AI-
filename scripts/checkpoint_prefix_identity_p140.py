"""P140 protocol-reference identity; never change the frozen P139 strict test.

Selected after the closed P139 ID-only diagnostic. This is exact recorded-value
comparison modulo validated transport references, not semantic normalization.
The caller reconstructs records and archival history from trusted saved inputs.
Only hashes/counts leave this module; no program or model is executed.
"""
from copy import deepcopy

from budget_visibility_comparison import canonical_messages
from native_conversation import recover_turn
from receipt_reasoning_history import digest
from reasoning_history import public_assistant
from whole_task_checkpoint_representation_p139 import representation_prefix_match as strict_match


VERSION = 'P140_validated_transport_reference_identity_v1'
EVIDENCE_FIELD = 'protocol_prefix_identity'


class PrefixIdentityError(ValueError):
    """Invalid/incomplete identity evidence; caller must retain an ineligible row."""


def require(value, reason):
    if not value:
        raise PrefixIdentityError(reason)


def valid_hash(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def equal(left, right):
    return digest(left) == digest(right)


def _message(message):
    require(type(message) is dict and set(message) <= {
        'role', 'content', 'reasoning_content', 'tool_calls'}, 'unsupported_assistant_fields')
    require(message.get('role') == 'assistant', 'assistant_role_required')
    require(message.get('content') is None or type(message.get('content')) is str,
            'content_type')
    require(message.get('reasoning_content') is None or
            type(message.get('reasoning_content')) is str, 'reasoning_type')
    calls = message.get('tool_calls')
    require(calls is None or type(calls) is list, 'tool_calls_type')
    for call in calls or []:
        require(type(call) is dict and set(call) == {'id', 'type', 'function'},
                'tool_call_fields')
        require(type(call['id']) is str and bool(call['id']) and
                call['type'] == 'function', 'tool_call_identity')
        function = call['function']
        require(type(function) is dict and set(function) == {'name', 'arguments'} and
                type(function['name']) is str and bool(function['name']) and
                type(function['arguments']) is str, 'function_fields')
    return calls or []


def canonical_prefix_evidence(records, archival_messages):
    """Bind all known terminal outputs to a complete, raw, validated archive.

    records: sequential {call_id, role, status, request_sha256, message}; focus
    outputs stay in the output sequence but are not appended to actor history.
    archival_messages is conversation.messages(), never a compacted actor view.
    Invalid references raise PrefixIdentityError; they are not quietly dropped.
    """
    require(type(records) is list and bool(records), 'known_records_required')
    require(type(archival_messages) is list and len(archival_messages) >= 2,
            'complete_archive_required')
    for item, role in zip(archival_messages[:2], ('system', 'user')):
        require(type(item) is dict and set(item) == {'role', 'content'} and
                item['role'] == role and type(item['content']) is str, 'initial_archive_roles')
    offset = 2
    positions = {}
    agent_calls = focus_calls = protocol_calls = 0
    for index, record in enumerate(records, 1):
        require(type(record) is dict and set(record) == {
            'call_id', 'role', 'status', 'request_sha256', 'message'}, 'record_fields')
        require(record['call_id'] == f'call_{index:03d}' and
                record['role'] in ('agent', 'focus') and record['status'] == 'ok' and
                valid_hash(record['request_sha256']), 'known_sequential_record_required')
        message = record['message']
        calls = _message(message)
        if record['role'] == 'focus':
            focus_calls += 1
            require(not calls, 'focus_has_protocol_call')
            continue
        agent_calls += 1
        require(offset < len(archival_messages), 'missing_actor_turn')
        expected = public_assistant(message)
        if 'reasoning_content' in message:
            expected['reasoning_content'] = message['reasoning_content']
        require(equal(archival_messages[offset], expected), 'actor_archive_not_bound')
        size = 1 + (len(calls) or 1)
        turn = archival_messages[offset:offset + size]
        require(len(turn) == size, 'unclosed_actor_turn')
        for call, result in zip(calls, turn[1:]):
            require(type(result) is dict and set(result) == {
                'role', 'tool_call_id', 'name', 'content'} and result['role'] == 'tool' and
                result['tool_call_id'] == call['id'] and
                result['name'] == call['function']['name'] and
                type(result['content']) is str, 'ordered_tool_result_required')
        if not calls:
            require(type(turn[1]) is dict and set(turn[1]) == {'role', 'content'} and
                    turn[1]['role'] == 'user' and type(turn[1]['content']) is str,
                    'ordinary_no_tool_receipt_required')
        try:
            recover_turn(turn)  # Existing receipt/turn grammar, no action execution.
        except (KeyError, TypeError, ValueError) as error:
            raise PrefixIdentityError('invalid_recorded_turn_grammar') from error
        positions[index - 1] = offset
        protocol_calls += len(calls)
        offset += size
    require(offset == len(archival_messages), 'unbound_archive_suffix')
    try:
        normalized = canonical_messages(archival_messages)
    except (KeyError, TypeError, ValueError) as error:
        raise PrefixIdentityError('invalid_protocol_reference_bijection') from error
    sequence = []
    for index, record in enumerate(records):
        normalized_output = deepcopy(record['message'])
        if index in positions:
            original_calls = normalized_output.get('tool_calls') or []
            canonical_calls = normalized[positions[index]].get('tool_calls') or []
            require(len(original_calls) == len(canonical_calls), 'canonical_call_count_changed')
            for original, canonical in zip(original_calls, canonical_calls):
                original['id'] = canonical['id']
        sequence.append({k: record[k] for k in ('call_id', 'role', 'status', 'request_sha256')} | {
            'raw_assistant_message_sha256': digest(record['message']),
            'canonical_assistant_message_sha256': digest(normalized_output)})
    return dict(version=VERSION, validation_status='valid', record_count=len(records),
                agent_calls=agent_calls, focus_calls=focus_calls,
                protocol_call_count=protocol_calls,
                raw_archive_sha256=digest(archival_messages),
                canonical_archive_sha256=digest(normalized), sequence=sequence)


def _canonical_row(row):
    second = row.get('representation_second_opportunity')
    require(type(second) is dict, 'second_opportunity_required')
    evidence = second.get(EVIDENCE_FIELD)
    require(type(evidence) is dict and set(evidence) == {
        'version', 'validation_status', 'record_count', 'agent_calls', 'focus_calls',
        'protocol_call_count', 'raw_archive_sha256', 'canonical_archive_sha256', 'sequence'},
        'complete_identity_evidence_required')
    require(evidence['version'] == VERSION and evidence['validation_status'] == 'valid',
            'validated_identity_required')
    prior = second.get('prior_request_output_sequence')
    require(type(prior) is list and bool(prior) and all(type(x) is dict for x in prior) and
            type(evidence['sequence']) is list and
            len(prior) == len(evidence['sequence']), 'bound_output_sequence_required')
    for key in ('record_count', 'agent_calls', 'focus_calls', 'protocol_call_count'):
        require(type(evidence[key]) is int and evidence[key] >= 0, 'identity_count_type')
    require(evidence['record_count'] == len(prior) and
            evidence['agent_calls'] == sum(x.get('role') == 'agent' for x in prior) and
            evidence['focus_calls'] == sum(x.get('role') == 'focus' for x in prior),
            'identity_counts_disagree')
    require(all(valid_hash(evidence[k]) for k in ('raw_archive_sha256',
                                                'canonical_archive_sha256')), 'archive_digest_required')
    result = deepcopy(row)
    target = result['representation_second_opportunity']['prior_request_output_sequence']
    for original, bound, changed in zip(prior, evidence['sequence'], target):
        require(type(original) is dict and type(bound) is dict and set(bound) == {
            'call_id', 'role', 'status', 'request_sha256', 'raw_assistant_message_sha256',
            'canonical_assistant_message_sha256'}, 'identity_sequence_fields')
        require(all(equal(original.get(k), bound[k]) for k in
                    ('call_id', 'role', 'status', 'request_sha256')) and
                original.get('known_assistant_message_sha256') == bound['raw_assistant_message_sha256']
                and valid_hash(bound['raw_assistant_message_sha256']) and
                valid_hash(bound['canonical_assistant_message_sha256']), 'raw_output_digest_not_bound')
        changed['known_assistant_message_sha256'] = bound['canonical_assistant_message_sha256']
    return result, evidence


def representation_prefix_comparison(left, right):
    """Keep strict evidence; permit only the separately validated ID bijection."""
    if type(left) is not dict or type(right) is not dict:
        return dict(strict_match=False, canonical_match=False,
                    reason='invalid_prefix_record', version=VERSION)
    try:
        original = strict_match(left, right)
    except (AttributeError, KeyError, TypeError, ValueError):
        # Malformed evidence is not an absent boundary or an equal prefix.
        return dict(strict_match=False, canonical_match=False,
                    reason='invalid_fixed_prefix_fields', version=VERSION)
    if (left.get('representation_second_opportunity') is None or
            right.get('representation_second_opportunity') is None):
        return dict(strict_match=original, canonical_match=None, reason='boundary_absent',
                    version=VERSION)
    if (type(left['representation_second_opportunity']) is not dict or
            type(right['representation_second_opportunity']) is not dict):
        return dict(strict_match=original, canonical_match=False,
                    reason='invalid_boundary_record', version=VERSION)
    try:
        a, ea = _canonical_row(left)
        b, eb = _canonical_row(right)
        require(ea['canonical_archive_sha256'] == eb['canonical_archive_sha256'] and
                ea['protocol_call_count'] == eb['protocol_call_count'], 'canonical_archive_differs')
        match = strict_match(a, b)
        return dict(strict_match=original, canonical_match=match,
                    reason='equal_modulo_validated_transport_references' if match else
                    'other_fixed_prefix_fields_differ', version=VERSION)
    except PrefixIdentityError as error:
        return dict(strict_match=original, canonical_match=False, reason=str(error), version=VERSION)


def canonical_representation_prefix_match(left, right):
    return representation_prefix_comparison(left, right)['canonical_match']
