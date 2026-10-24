"""Describe P111 request/action divergence without inferring semantic equivalence."""
from copy import deepcopy
from itertools import combinations, zip_longest

from public_action_structure import digest
from recorded_action_agreement import compare_call, equal_known, summarize_pairs
from receipt_reasoning_history import POLICIES, require, strip_reasoning
from submission_components import components, compare as compare_components


def request_components(request):
    if request is None:
        return dict(request_available=False, request_sha256=None,
                    messages_sha256=None, request_without_reasoning_sha256=None,
                    nonmessage_parameters_sha256=None)
    require(type(request) is dict and type(request.get('messages')) is list
            and len(request['messages']) <= 2048, 'bounded_request_required')
    without = deepcopy(request)
    without['messages'] = strip_reasoning(request['messages'])
    return dict(request_available=True, request_sha256=digest(request),
        messages_sha256=digest(request['messages']),
        request_without_reasoning_sha256=digest(without),
        nonmessage_parameters_sha256=digest({k: v for k, v in request.items() if k != 'messages'}))


def describe_call(call, request, response, input_row):
    require(call['call_id'] == input_row['call_id'] and input_row['policy'] == input_row['actual_policy']
            and input_row['actual_usage_status'] == call['usage_status'], 'actual_P112_call_required')
    comp = components(response)
    require(comp['public_output_sha256'] == call['response']['public_output_sha256']
            and comp['original_syntax_actions_sha256'] == call['response']['syntax_actions_sha256'],
            'public_submission_fingerprint_changed')
    known = call['usage_status'] == 'ok'
    reasoning = (response.get('message') or {}).get('reasoning_content') if known else None
    require(reasoning is None or type(reasoning) is str, 'reasoning_text_shape')
    projection = input_row['projection']
    return dict(**call, input=request_components(request), components=comp,
        response_reasoning_sha256=digest(reasoning) if known else None,
        response_reasoning_characters=len(reasoning or '') if known else None,
        measured_input_tokens=input_row['actual_measured_input_tokens'],
        measured_output_tokens=input_row['actual_measured_output_tokens'],
        measured_cached_input_tokens=input_row['actual_measured_cached_input_tokens'],
        input_tokens_if_counted=input_row['input_tokens'],
        actual_unknown_usage_not_imputed=not known,
        history_removed_turns=projection['removed_reasoning_turns'],
        history_redisplayed_turns=projection['redisplayed_reasoning_turns'],
        local_input_omission=-input_row['delta_from_full'],
        adjacent_input_common_prefix_tokens=input_row.get('adjacent_input_common_prefix_tokens'))


def compare_position(left, right):
    original = compare_call(left, right)
    # The shared comparator intentionally has a shorter schema for an ended
    # run. Keep those comparison dimensions explicitly unavailable here.
    original.setdefault('API_result_equal', None)
    original.setdefault('public_tool_results_equal', None)
    comp = compare_components(left['components'] if left else None,
                              right['components'] if right else None, original)
    out = dict(**original, **comp)
    for field in ('request_sha256', 'messages_sha256', 'request_without_reasoning_sha256',
                  'nonmessage_parameters_sha256'):
        out[field.replace('_sha256', '_equal')] = equal_known(
            left['input'][field], right['input'][field]) if left and right else None
    for output, field in [('reasoning_equal', 'response_reasoning_sha256'),
                          ('API_sequence_including_empty_equal', 'API_request_sequence_sha256'),
                          ('API_results_including_empty_equal', 'API_result_sequence_sha256')]:
        out[output] = equal_known(left[field], right[field]) if left and right else None
    # A changed API sequence includes empty/nonempty transitions. The original
    # API_class remains present so empty agreement is never reported as work.
    out['same_request_different_public_output'] = out['request_equal'] is True and out['public_equal'] is False
    out['same_request_different_reasoning'] = out['request_equal'] is True and out['reasoning_equal'] is False
    out['only_reasoning_field_differs_in_request'] = (out['request_equal'] is False
        and out['request_without_reasoning_equal'] is True)
    out['full_process_state_equal_claim'] = False
    return out


EQUALITY_FIELDS = ('request_equal', 'request_without_reasoning_equal', 'reasoning_equal',
    'public_equal', 'Python_AST_equal', 'noncode_arguments_equal',
    'API_sequence_including_empty_equal', 'API_results_including_empty_equal',
    'public_tool_results_equal')


def equality_summary(rows, field):
    values = [row[field] for row in rows]
    prefix = 0
    for value in values:
        if value is not True:
            break
        prefix += 1
    return dict(equal=sum(v is True for v in values), different=sum(v is False for v in values),
        unavailable=sum(v is None for v in values), contiguous_equal_prefix_positions=prefix,
        first_observed_difference=next((row['ordinal'] for row in rows if row[field] is False), None),
        first_unavailable=next((row['ordinal'] for row in rows if row[field] is None), None),
        ordinal_alignment_is_not_semantic_alignment=True)


def compare_trajectories(runs):
    groups = {}
    for run in runs:
        require(run['reasoning_display_policy'] in POLICIES, 'recorded_policy_required')
        require(len(run['calls']) == run['model_calls'], 'every_original_call_required')
        require([c['ordinal'] for c in run['calls']] == list(range(1, len(run['calls'])+1)),
                'chronological_call_ordinals_required')
        groups.setdefault(run['task_id'], []).append(run)
    pairs = []
    for task, group in groups.items():
        require(len(group) == 3 and {r['reasoning_display_policy'] for r in group} == set(POLICIES),
                'all_three_policies_once_per_task_required')
        by_policy = {r['reasoning_display_policy']: r for r in group}
        for lp, rp in combinations(POLICIES, 2):
            left, right = by_policy[lp], by_policy[rp]
            rows = [dict(ordinal=i, **compare_position(a, b)) for i, (a, b) in
                    enumerate(zip_longest(left['calls'], right['calls']), 1)]
            pairs.append(dict(task_id=task, left=left['run_id'], right=right['run_id'],
                left_policy=lp, right_policy=rp, left_success=left['success'], right_success=right['success'],
                rows=rows, all_aligned=summarize_pairs(rows),
                matched_prior_API_prefix=summarize_pairs([r for r in rows if r['prior_API_prefix_equal'] is True]),
                equality={field:equality_summary(rows, field) for field in EQUALITY_FIELDS},
                same_request_different_public_output=sum(r['same_request_different_public_output'] for r in rows),
                same_request_different_reasoning=sum(r['same_request_different_reasoning'] for r in rows),
                only_reasoning_field_differs_in_request=sum(r['only_reasoning_field_differs_in_request'] for r in rows),
                pairs_independent=False, full_state_equivalence_established=False,
                causal_effect_identified=False))
    return pairs
