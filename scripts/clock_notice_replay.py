"""Pure request construction and opaque output checks for bounded P79 replay."""
import copy
import hashlib
import json

from api_error_comparison import add_notification
from inspect_api_error_divergence import public_output, without_wall_snapshot

LEVELS = ('original', 'plus_one')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def requests_for(original, state):
    without_wall_snapshot(original, state)  # Verify the exact saved notice first.
    if (original.get('seed') != 56 or original.get('max_tokens') != 4096
            or original.get('stream') is not False or original.get('cache_prompt') is not True
            or original.get('model') != 'minimax-m3-iq4xs'):
        raise ValueError('outside_the_frozen_sixth_call_inputs')
    wall = state['remaining']['wall_seconds_at_snapshot']
    if type(wall) is not int or wall < 1:
        raise ValueError('positive_integer_wall_snapshot_required')
    result = {}
    for level in LEVELS:
        request, notice = copy.deepcopy(original), copy.deepcopy(state)
        notice['remaining']['wall_seconds_at_snapshot'] = wall + (level == 'plus_one')
        request['messages'][-1] = add_notification([], notice)[0]
        request['cache_prompt'] = False
        result[level] = request
    return result


def schedule():
    result = []
    base = ('original', 'plus_one', 'plus_one', 'original', 'original', 'plus_one')
    for case in (0, 1):
        counts = {level: 0 for level in LEVELS}
        order = base if case == 0 else tuple(LEVELS[1 - LEVELS.index(level)] for level in base)
        for level in order:
            counts[level] += 1
            result.append({'case_index': case, 'level': level, 'replicate': counts[level],
                           'id': f'call_{len(result) + 1:03d}'})
    return result


def output_fingerprints(response):
    if response.get('status') != 'ok':
        return {'public_output_sha256': None, 'opaque_message_sha256': None,
                'has_public_output': None, 'complete_generation': False}
    message = copy.deepcopy(response['message'])
    for call in message.get('tool_calls') or []:
        call.pop('id', None)
    public = public_output(response)
    return {'public_output_sha256': digest(public), 'opaque_message_sha256': digest(message),
            'has_public_output': bool(public['content'] or public['functions']),
            'complete_generation': response['done_reason'] != 'length'}


def equality_summary(rows):
    result = []
    for case in (0, 1):
        groups = {level: [r for r in rows if r['case_index'] == case and r['level'] == level]
                  for level in LEVELS}
        item = {'case_index': case, 'within': {}}
        for level, group in groups.items():
            known = [r for r in group if r.get('status') == 'ok']
            complete = len(group) == len(known) == 3
            usable = complete and all(r['has_public_output'] and r['complete_generation'] for r in known)
            pairs = [(a, b) for i, a in enumerate(known) for b in known[i + 1:]]
            item['within'][level] = {'attempted': len(group), 'known': len(known),
                'compared_pairs': len(pairs),
                'equal_public_pairs': sum(a['public_output_sha256'] == b['public_output_sha256'] for a, b in pairs),
                'equal_opaque_pairs': sum(a['opaque_message_sha256'] == b['opaque_message_sha256'] for a, b in pairs),
                'all_three_complete_nonempty': usable,
                'all_three_public_outputs_equal': (len({r['public_output_sha256'] for r in known}) == 1) if usable else None}
        cross = [(a, b) for a in groups[LEVELS[0]] for b in groups[LEVELS[1]]
                 if a.get('status') == b.get('status') == 'ok']
        item['cross'] = {'compared_pairs': len(cross),
            'equal_public_pairs': sum(a['public_output_sha256'] == b['public_output_sha256'] for a, b in cross),
            'equal_opaque_pairs': sum(a['opaque_message_sha256'] == b['opaque_message_sha256'] for a, b in cross),
            'pairs_are_independent_samples': False}
        result.append(item)
    return result


def reserve_tokens(counts, max_output=4096):
    if len(counts) != 4 or any(type(v) is not int or v < 1 or v + max_output > 65536 for v in counts):
        raise ValueError('four_admitted_input_counts_required')
    total = sum(3 * (v + max_output) for v in counts)
    if total > 150000:
        raise ValueError('total_generation_reservation_exceeds_fixed_budget')
    return total
