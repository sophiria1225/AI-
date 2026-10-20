"""Select complete recorded turns without fabricating or orphaning tool receipts.

This is an adapter for existing memory baselines, not a novel memory policy. The
caller decides which span IDs to request. Selecting any receipt keeps its entire
original assistant turn and every corresponding receipt; removed spans stay in
the caller's immutable archive and remain available through read_span.
"""
import copy
import json

from context_preservation import compact
from native_conversation import NativeConversation, recover_turn


def recorded_turns(conversation):
    messages = conversation.messages()
    turns, offset = [], 2
    while offset < len(messages):
        response = messages[offset]
        count = len(response.get('tool_calls') or []) or 1
        spans = recover_turn(messages[offset:offset + count + 1])
        turns.append((response, spans))
        offset += count + 1
    return turns


def retained_view(conversation, requested_span_ids, ledger=None, page_limit=24000):
    original = conversation.messages()
    turns = recorded_turns(conversation)
    available = [span['id'] for _, spans in turns for span in spans]
    if (not isinstance(requested_span_ids, list)
            or any(type(sid) is not str for sid in requested_span_ids)
            or len(set(requested_span_ids)) != len(requested_span_ids)
            or not set(requested_span_ids) <= set(available)):
        raise ValueError('selection must contain distinct original span IDs')
    if ledger is not None and not isinstance(ledger, dict):
        raise ValueError('a memory note must be a structured ledger')
    selected = NativeConversation(original[0]['content'], json.loads(original[1]['content'])['task'])
    requested, retained, retained_turns = set(requested_span_ids), [], 0
    for response, spans in turns:
        if requested.intersection(span['id'] for span in spans):
            selected.append(response, spans)
            retained.extend(span['id'] for span in spans)
            retained_turns += 1
    messages, formatting = selected.for_model(page_limit)
    if retained != available or ledger is not None:
        note = {'available_archive_ids': available,
                'retained_span_ids': retained,
                'memory_scope': 'Selected complete past turns. Removed spans remain readable. '
                                'A working ledger is fallible; recorded API errors are not successes.'}
        if ledger is not None:
            note['working_ledger'] = copy.deepcopy(ledger)
        messages.append({'role': 'user', 'content': compact({'memory_note': note})})
    return messages, {**formatting,
                      'requested_span_ids': [sid for sid in available if sid in requested],
                      'retained_span_ids': retained,
                      'retained_turns': retained_turns, 'original_turns': len(turns),
                      'additional_spans_to_preserve_call_result_pairs': len(set(retained) - requested),
                      'memory_note_added': retained != available or ledger is not None}
