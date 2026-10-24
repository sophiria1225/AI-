"""Conditional cost intervals for a closed cohort; never impute missing usage.

The lower bound of a terminally unknown attempt is zero because dispatch is
not proof of server receipt. Its upper bound is conditional on the recorded
input count and requested output cap being honored. This is ordinary interval
arithmetic, not a new controller or a replacement for a predeclared gate.
"""
from itertools import combinations


def integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError('nonnegative_integer_required')
    return value


def difference(left, right):
    """Bounds on left minus right without independence assumptions."""
    for interval in (left, right):
        if (len(interval) != 2 or any(type(x) is not int for x in interval)
                or interval[0] > interval[1]):
            raise ValueError('ordered_integer_interval_required')
    bounds = [left[0] - right[1], left[1] - right[0]]
    sign = ('positive' if bounds[0] > 0 else 'negative' if bounds[1] < 0
            else 'zero' if bounds == [0, 0] else 'not_identified')
    return {'bounds': bounds, 'sign_under_assumptions': sign}


def analyze_cell(original, usage, request_caps, limits):
    """Accept only scalar accounting and request caps, never prompt text."""
    context = integer(limits['context_tokens'], 1)
    output = integer(limits['output_tokens'], 1)
    budget = integer(limits['cell_tokens'], 1)
    if (original['record_status'] != 'evaluated' or type(original['success']) is not bool
            or len(usage) != original['model_calls'] or not 0 < len(usage) <= limits['max_calls']):
        raise ValueError('all_evaluated_original_attempts_required')
    expected_ids = [f'call_{i + 1:03d}' for i in range(len(usage))]
    if ([c['id'] for c in usage] != expected_ids
            or list(request_caps) != expected_ids
            or [c['call_id'] for c in original['request_checks']] != expected_ids):
        raise ValueError('complete_ordered_unique_attempts_required')
    known = unknown = request_upper = context_upper = 0
    calls = []
    for i, (call, check) in enumerate(zip(usage, original['request_checks'], strict=True)):
        predicted = integer(call.get('predicted_input_tokens'), 1)
        cap = integer(call.get('output_cap'), 1)
        expected_cap = min(output, max(0, budget - known - predicted))
        if (cap != expected_cap or integer(request_caps[call['id']], 1) != cap
                or predicted + cap > context or predicted + cap > budget - known):
            raise ValueError('recorded_request_or_residual_reservation_mismatch')
        if check['status'] != call['status'] or not check['request_sha256']:
            raise ValueError('original_request_receipt_required')
        terminal = call['status'] == 'ok'
        # The original field records even a timeout/error row. It does NOT
        # establish known usage; preserve it without conflating these meanings.
        if (type(check['terminal_usage_recorded']) is not bool
                or terminal and not check['terminal_usage_recorded']):
            raise ValueError('known_usage_requires_original_terminal_record')
        if terminal:
            input_count = integer(call.get('input_tokens'), 1)
            output_count = integer(call.get('output_tokens'))
            if input_count != predicted or output_count > cap:
                raise ValueError('known_terminal_violates_proposed_bound')
            observed = input_count + output_count
            known += observed
            interval = [observed, observed]
            context_interval = interval.copy()
        else:
            if (call['status'] != 'error' or i != len(usage) - 1
                    or call.get('input_tokens') is not None
                    or call.get('output_tokens') is not None):
                raise ValueError('unknown_usage_must_remain_unknown_and_terminal')
            observed = None
            unknown += 1
            request_upper += predicted + cap
            context_upper += context
            interval = [0, predicted + cap]
            context_interval = [0, context]
        calls.append({'call_id': call['id'], 'status': call['status'],
            'predicted_input_tokens': predicted, 'requested_output_cap': cap,
            'observed_logical_tokens': observed,
            'terminal_record_present': check['terminal_usage_recorded'],
            'conditional_request_interval': interval,
            'conditional_context_interval': context_interval,
            'request_sha256': check['request_sha256'],
            'response_sha256': check.get('response_sha256')})
    if known != original['known_total_tokens'] or unknown != original['unknown_usage_calls']:
        raise ValueError('original_accounting_totals_changed')
    return {**{k: original[k] for k in ('run_id', 'task_id', 'notice_policy',
        'success', 'record_status', 'stop_reason', 'model_calls', 'api_requests',
        'known_total_tokens', 'unknown_usage_calls', 'usage_sha256')},
        'conditional_request_interval': [known, known + request_upper],
        'conditional_context_interval': [known, known + context_upper], 'calls': calls}


def aggregate(rows):
    return {'cells': len(rows), 'successes': sum(r['success'] for r in rows),
        'model_attempts': sum(r['model_calls'] for r in rows),
        'API_requests': sum(r['api_requests'] for r in rows),
        'known_logical_tokens': sum(r['known_total_tokens'] for r in rows),
        'unknown_usage_attempts': sum(r['unknown_usage_calls'] for r in rows),
        **{key: [sum(r[key][i] for r in rows) for i in (0, 1)]
           for key in ('conditional_request_interval', 'conditional_context_interval')}}


def comparisons(rows, policies):
    by_policy = {r['notice_policy']: r for r in rows}
    return [{'minuend': right, 'subtrahend': left,
        **{key: difference(by_policy[right][key], by_policy[left][key])
           for key in ('conditional_request_interval', 'conditional_context_interval')}}
        for left, right in combinations(policies, 2)]


def summarize(rows, tasks, policies):
    expected = {(task, policy) for task in tasks for policy in policies}
    if (len(expected) != len(tasks) * len(policies) or len(rows) != len(expected)
            or {(r['task_id'], r['notice_policy']) for r in rows} != expected):
        raise ValueError('complete_task_policy_cartesian_product_required')
    totals = []
    for policy in policies:
        cells = [r for r in rows if r['notice_policy'] == policy]
        totals.append({'notice_policy': policy, **aggregate(cells),
            'successful': aggregate([r for r in cells if r['success']]),
            'unsuccessful': aggregate([r for r in cells if not r['success']])})
    pairs = []
    for task in tasks:
        cells = [r for r in rows if r['task_id'] == task]
        for pair in comparisons(cells, policies):
            flags = {r['notice_policy']: r['success'] for r in cells}
            pairs.append({'task_id': task, **pair,
                'minuend_success': flags[pair['minuend']],
                'subtrahend_success': flags[pair['subtrahend']]})
    return {'totals': totals, 'whole_cohort_differences': comparisons(totals, policies),
            'all_task_differences': pairs, 'all_conditions': aggregate(rows)}
