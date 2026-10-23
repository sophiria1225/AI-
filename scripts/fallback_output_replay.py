"""Fixed saved-input replay of P83's six cases, with no generated action run."""
import copy
from itertools import combinations

from clock_notice_replay import digest, output_fingerprints

CASES = ('P83_P80_ORIGINAL', 'P83_R2_ORIGINAL', 'P83_P80_NORMALIZED',
         'P83_R2_NORMALIZED', 'P83_NATIVE_IDS_CONTROL', 'P83_CONTENT_CONTROL')
COUNTS = (22669, 22667, 22650, 22650, 22669, 22676)
ORDERS = ((0, 1, 2, 3, 4, 5), (5, 4, 3, 2, 1, 0), (2, 5, 0, 3, 1, 4))
FIXED = dict(phase='P84', batch_id='P84_fallback_output_v01', max_calls=18,
    max_total_tokens=500000, max_output_tokens=4096, seed=70, call_timeout_seconds=480,
    max_wall_seconds=10800, max_preflight_seconds=300, max_idle_seconds=60,
    server_max_lifetime_seconds=12600, cache_prompt=False, automatic_retries=0,
    environment_api_requests=0, evaluations=0, reserved_scenarios_read=0,
    novel_method_claim=False, required_closed_pipeline='records/context_pilot/P82_pipeline_v01',
    source_archive='records/context_pilot/P83_fallback_prompt_v01',
    source_report='reports/P83_fallback_prompt.json')


def schedule():
    return [dict(id=f'call_{(rep-1)*6+i+1:03d}', case=CASES[index], repetition=rep)
            for rep, order in enumerate(ORDERS, 1) for i, index in enumerate(order)]


def request_for(original):
    if (original.get('seed') != FIXED['seed'] or original.get('max_tokens') != 4096
            or original.get('cache_prompt') is not True or original.get('stream') is not False
            or original.get('temperature') != 1.0 or original.get('model') != 'minimax-m3-iq4xs'):
        raise ValueError('fixed_P83_source_controls_required')
    result = copy.deepcopy(original)
    result['cache_prompt'] = False
    return result


def reserve_tokens(counts):
    if tuple(counts) != COUNTS or any(type(v) is not int for v in counts):
        raise ValueError('all_six_fixed_source_input_counts_required')
    total = 3 * sum(v + FIXED['max_output_tokens'] for v in counts)
    if total > FIXED['max_total_tokens']:
        raise ValueError('fixed_reservation_exceeded')
    return total


def validate_plan(plan):
    if any(plan.get(k) != v for k, v in FIXED.items()) or plan.get('schedule') != schedule():
        raise ValueError('fixed_P84_scope_budget_or_order_changed')
    cases = plan.get('cases', [])
    if [c['id'] for c in cases] != list(CASES) or [c['expected_input_tokens'] for c in cases] != list(COUNTS):
        raise ValueError('all_six_fixed_P83_inputs_required')
    if reserve_tokens([c['expected_input_tokens'] for c in cases]) != plan.get('reserved_total_tokens'):
        raise ValueError('fixed_reservation_changed')


def equality_summary(rows):
    planned = {r['id']: r for r in schedule()}
    if (len({r['id'] for r in rows}) != len(rows)
            or any(r['id'] not in planned or any(r[k] != planned[r['id']][k]
                   for k in ('case', 'repetition')) for r in rows)):
        raise ValueError('unique_fixed_replay_rows_required')
    groups, within, cross = {}, {}, []
    for case in CASES:
        group = [r for r in rows if r['case'] == case and r.get('status') not in ('unattempted', None)]
        known = [r for r in group if r.get('status') == 'ok']
        usable = len(known) == len(group) == 3 and all(
            r.get('has_public_output') and r.get('complete_generation') for r in known)
        pairs = list(combinations(known, 2))
        groups[case] = known
        within[case] = dict(attempted=len(group), known=len(known), compared_pairs=len(pairs),
            equal_public_pairs=sum(a['public_output_sha256'] == b['public_output_sha256'] for a, b in pairs),
            equal_opaque_pairs=sum(a['opaque_message_sha256'] == b['opaque_message_sha256'] for a, b in pairs),
            all_three_complete_nonempty=usable,
            all_three_public_outputs_equal=(len({r['public_output_sha256'] for r in known}) == 1) if usable else None)
    for left, right in combinations(CASES, 2):
        pairs = [(a, b) for a in groups[left] for b in groups[right]]
        usable = all(within[c]['all_three_complete_nonempty'] for c in (left, right))
        cross.append(dict(left=left, right=right, compared_pairs=len(pairs),
            equal_public_pairs=sum(a['public_output_sha256'] == b['public_output_sha256'] for a, b in pairs),
            equal_opaque_pairs=sum(a['opaque_message_sha256'] == b['opaque_message_sha256'] for a, b in pairs),
            complete_nonempty_pair_groups=usable, pairs_are_independent_samples=False))
    pair = lambda left, right: next(c for c in cross if (c['left'], c['right']) == (left, right))
    stable = all(within[c]['all_three_public_outputs_equal'] is True for c in CASES)
    full = len(rows) == 18 and all(r.get('status') == 'ok' for r in rows)
    controls = (stable and pair(CASES[0], CASES[4])['equal_public_pairs'] == 9
                and pair(CASES[2], CASES[3])['equal_public_pairs'] == 9)
    return dict(within=within, cross=cross, all_18_terminal_usages_known=full,
        stable_complete_public_outputs_and_equivalent_input_controls=controls if full else None,
        original_fallback_ID_pair_public_outputs_differ=(pair(CASES[0], CASES[1])['equal_public_pairs'] == 0)
            if full and controls else None,
        local_saved_context_only=True, actual_original_warm_state_replayed=False,
        task_quality_measured=False, whole_task_savings_measured=False,
        novel_method_claim=False, private_reasoning_inspected_semantically=False)
