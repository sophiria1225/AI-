"""Bounded reacquired-receipt retention, a simple existing-principle baseline.

This is not Pichay's full implementation. It uses exact API-request/result
equality, original complete turns and P12's 4096-token history proxy. It never
answers an API request from a cache, skips an execution, or certifies freshness.
No model call, environment access, or evaluator access occurs in this module.
"""
import json

from context_preservation import compact
from native_memory_view import recorded_turns, retained_view
from native_recent_window import recent_window


def reacquired_receipts(spans, events, views, allowed_api_names):
    """Replay past visibility and sent requests; return IDs, never value hashes.

    A repeat is a retention candidate only when the previous result predates the
    current model response, was omitted from that response's input, and exactly
    equals the newly observed result. This is an operational signal, not proof
    that forgetting caused the repeat. Changed results remove that key's pin.
    """
    visible = {}
    for view in views:
        call = view['next_call_id']
        if call in visible:
            raise ValueError('duplicate visibility record')
        visible[call] = set(view['selection']['retained_span_ids'])
    prior, pins, changes, seen = {}, {}, [], set()
    for index, event in enumerate(events):
        sid, call = event['span_id'], event['call']
        if sid in seen or sid not in spans or spans[sid]['id'] != sid:
            raise ValueError('invalid recorded span identity')
        seen.add(sid)
        if event.get('effects_unknown'):
            raise ValueError('unknown request effects cannot be used for retention')
        if not event['api_request_sent']:
            continue
        if call not in visible:
            raise ValueError('missing pre-call visibility')
        span = spans[sid]
        action = span.get('action') or {}
        name = action.get('name')
        if name not in allowed_api_names:
            raise ValueError('request is not in the public schema allowlist')
        arguments = json.loads(action['arguments'])
        if not isinstance(arguments, dict):
            raise ValueError('sent API arguments must be an object')
        # The key is local only: neither values nor per-secret hashes are returned.
        key = json.dumps([name, arguments], ensure_ascii=False, sort_keys=True)
        old = prior.get(key)
        same = old is not None and old['observation'] == span['observation']
        if old is not None and not same and key in pins:
            del pins[key]
            changes.append({'kind': 'changed_result_unpin', 'span_id': sid,
                            'previous_span_id': old['id'], 'public_api': name})
        fault = (same and old['call'] != call and old['id'] not in visible[call])
        if fault or (same and key in pins):
            first_call = pins[key]['first_fault_call'] if key in pins else call
            pins[key] = {'span_id': sid, 'public_api': name,
                         'last_request_index': index, 'first_fault_call': first_call}
            if fault:
                changes.append({'kind': 'omitted_identical_receipt_reacquired',
                                'span_id': sid, 'previous_span_id': old['id'],
                                'call': call, 'public_api': name})
        prior[key] = {'id': sid, 'call': call, 'observation': span['observation']}
    ordered = sorted(pins.values(), key=lambda pin: pin['last_request_index'], reverse=True)
    return {'pin_candidates_newest_first': ordered, 'events': changes,
            'fault_events': sum(row['kind'] == 'omitted_identical_receipt_reacquired'
                                for row in changes),
            'changed_result_unpins': sum(row['kind'] == 'changed_result_unpin'
                                        for row in changes)}


def fault_window(conversation, count_tokens, pin_ids, history_budget=4096,
                 page_limit=24000):
    """Prefer newest whole turn, then pins by recent request, then recent turns.

    Pins compete for the same proxy budget. A large pin is skipped, not silently
    admitted above the limit. Only the mandatory newest whole turn can overflow,
    exactly as in the P12 baseline. The unchanged archive remains readable.
    """
    if type(history_budget) is not int or history_budget < 1:
        raise ValueError('positive history budget required')
    turns = recorded_turns(conversation)
    groups = [[span['id'] for span in spans] for _, spans in turns]
    available = [sid for group in groups for sid in group]
    if (not isinstance(pin_ids, list) or any(type(sid) is not str for sid in pin_ids)
            or len(set(pin_ids)) != len(pin_ids) or not set(pin_ids) <= set(available)):
        raise ValueError('pins must be distinct original span IDs')
    if not pin_ids:
        messages, detail = recent_window(conversation, count_tokens, history_budget, page_limit)
        return messages, {**detail, 'prioritized_pin_span_ids': [],
                          'retained_pin_span_ids': [], 'unretained_pin_span_ids': []}
    counts = []

    def candidate(indices):
        ids = [sid for i, group in enumerate(groups) if i in indices for sid in group]
        messages, detail = retained_view(conversation, ids, page_limit=page_limit)
        tokens = count_tokens(compact(messages[2:]))
        if type(tokens) is not int or tokens < 0:
            raise ValueError('tokenizer returned an invalid length')
        counts.append({'selected_spans': len(detail['retained_span_ids']),
                       'history_tokens': tokens})
        return messages, detail, tokens

    full = candidate(set(range(len(groups))))
    if full[2] <= history_budget:
        chosen = full
    else:
        selected = {len(groups) - 1}
        chosen = candidate(selected)
        if chosen[2] <= history_budget:
            group_for = {sid: i for i, group in enumerate(groups) for sid in group}
            for sid in pin_ids:
                index = group_for[sid]
                if index in selected:
                    continue
                attempt = candidate(selected | {index})
                if attempt[2] <= history_budget:
                    selected.add(index)
                    chosen = attempt
            for index in range(len(groups) - 2, -1, -1):
                if index in selected:
                    continue
                attempt = candidate(selected | {index})
                if attempt[2] > history_budget:
                    break
                selected.add(index)
                chosen = attempt
    messages, detail, tokens = chosen
    retained = set(detail['retained_span_ids'])
    return messages, {**detail, 'history_tokens': tokens, 'history_budget': history_budget,
                      'history_budget_overflow': tokens > history_budget,
                      'token_count_requests': len(counts), 'candidate_counts': counts,
                      'prioritized_pin_span_ids': list(pin_ids),
                      'retained_pin_span_ids': [sid for sid in pin_ids if sid in retained],
                      'unretained_pin_span_ids': [sid for sid in pin_ids if sid not in retained],
                      'selection_rule': 'Full if within budget. Otherwise newest whole turn, '
                                        'then reacquired-receipt turns by latest request if they fit, '
                                        'then recent whole turns until first excess. '
                                        'Only the newest whole turn may overflow.'}
