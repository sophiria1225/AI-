"""One-field counterfactual requests and conservative paired interpretation."""
import copy

from budget_signal import digest
from inspect_full_control_variation import without_transport_ids


def requests(originals, plan):
    if (plan['schedule'] != [335, 336, 336, 335] or plan['max_calls'] != 4
            or plan['seed'] != 51 or plan['max_output_tokens'] != 4096
            or plan['cache_prompt'] is not False
            or plan['max_total_tokens'] != 100000 or plan['max_wall_seconds'] != 1200
            or plan['call_timeout_seconds'] != 240 or plan['max_tokenizer_requests'] != 2):
        raise ValueError('outside the fixed four-call calibration')
    if len(originals) != 2:
        raise ValueError('both historical negative controls required')
    left, right = copy.deepcopy(originals)
    for value in (left, right):
        if (value['cache_prompt'] is not True or value['stream'] is not False
                or value['seed'] != plan['seed'] or value['max_tokens'] != plan['max_output_tokens']
                or value['messages'][-1]['role'] != 'user'
                or not value['messages'][-1]['content'].startswith('<harness_residual_budget_v1>')):
            raise ValueError('source request format or generation parameters changed')
    token = '"wall_seconds_at_snapshot":335'
    original_notice = left['messages'][-1]['content']
    if original_notice.count(token) != 1:
        raise ValueError('the unique original clock literal is missing')
    patched = copy.deepcopy(left)
    patched['messages'][-1]['content'] = original_notice.replace(token, '"wall_seconds_at_snapshot":336')
    normalized = []
    for value in (patched, right):
        value = copy.deepcopy(value)
        value['messages'] = without_transport_ids(value['messages'])
        normalized.append(value)
    if normalized[0] != normalized[1]:
        raise ValueError('historical controls differ beyond one clock literal and transport IDs')
    variants = {}
    for seconds in (335, 336):
        value = copy.deepcopy(left if seconds == 335 else patched)
        value['cache_prompt'] = False
        variants[seconds] = value
    return variants


def message_hash(message):
    return digest(without_transport_ids([message]))


def compare(rows):
    complete = ([r['wall_snapshot_seconds'] for r in rows] == [335, 336, 336, 335]
        and all(r.get('status') == 'ok' and r.get('cache_confirmed') for r in rows))
    groups = {seconds: [r for r in rows if r['wall_snapshot_seconds'] == seconds] for seconds in (335, 336)}
    within = {str(s): (group[0]['message_sha256'] == group[1]['message_sha256']
                       if complete and len(group) == 2 else None) for s, group in groups.items()}
    between = (groups[335][0]['message_sha256'] == groups[336][0]['message_sha256']
               if complete and all(within.values()) else None)
    return {'all_four_confirmed': complete, 'within_literal_repeats_equal': within,
        'between_literal_messages_equal_if_repeats_stable': between,
        'local_sensitivity_observed': (not between if between is not None else None),
        'historical_P55_cause_identified': False, 'task_quality_effect_measured': False}
