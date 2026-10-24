"""P101: all six saved contexts crossed with ordinary tool-choice settings.

This is a local diagnostic. Parsing and matching output is not executing it.
"""
import copy
from itertools import combinations

from fallback_output_replay import CASES, COUNTS, ORDERS
from clock_notice_replay import digest, output_fingerprints
from public_action_structure import inspect as inspect_structure, comparison

CHOICES = ('auto', 'required')
FIXED = dict(phase='P101', batch_id='P101_choice_context_v01', max_calls=36,
    max_total_tokens=1050000, max_output_tokens=4096, max_input_tokens=24576,
    seed=70, call_timeout_seconds=480, max_wall_seconds=21600,
    max_preflight_seconds=900, max_renderer_seconds=120, max_renderer_rss_bytes=2147483648,
    max_idle_seconds=60, server_max_lifetime_seconds=25200, cache_prompt=False,
    automatic_retries=0, environment_api_requests=0, evaluations=0, reserved_scenarios_read=0,
    novel_method_claim=False, required_closed_pipeline='records/context_pilot/P99_pipeline_v01',
    required_closed_audit='reports/P99_comparison.json',
    predecessor_executed_head='02932c74f532dc1a3b48ad443223ec9d575c3ad0',
    source_archive='records/context_pilot/P83_fallback_prompt_v01',
    source_report='reports/P83_fallback_prompt.json')


def condition(case, choice):
    if case not in CASES or choice not in CHOICES:
        raise ValueError('fixed_six_inputs_and_two_choices_required')
    return case + '__' + choice


def conditions():
    return [condition(case, choice) for case in CASES for choice in CHOICES]


def schedule():
    rows = []
    for repetition, order in enumerate(ORDERS, 1):
        for index in order:
            choices = CHOICES if (repetition + index) % 2 else tuple(reversed(CHOICES))
            for choice in choices:
                rows.append(dict(id=f'call_{len(rows)+1:03d}', case=CASES[index],
                    tool_choice=choice, condition=condition(CASES[index], choice), repetition=repetition))
    return rows


def request_for(cold_original, choice):
    if (choice not in CHOICES or cold_original.get('tool_choice') != 'auto'
            or cold_original.get('seed') != 70 or cold_original.get('max_tokens') != 4096
            or cold_original.get('cache_prompt') is not False or cold_original.get('stream') is not False
            or cold_original.get('temperature') != 1.0
            or cold_original.get('model') != 'minimax-m3-iq4xs' or not cold_original.get('tools')
            or any(k in cold_original for k in ('grammar', 'json_schema', 'response_format'))):
        raise ValueError('unchanged_archived_cold_controls_required')
    payload = copy.deepcopy(cold_original)
    payload['tool_choice'] = choice
    return payload


def reserve_tokens(counts):
    if set(counts) != set(conditions()) or any(
            type(v) is not int or not 0 < v <= FIXED['max_input_tokens'] for v in counts.values()):
        raise ValueError('all_twelve_bounded_input_counts_required')
    for case, expected in zip(CASES, COUNTS, strict=True):
        if counts[condition(case, 'auto')] != expected:
            raise ValueError('archived_auto_input_count_changed')
    total = 3 * sum(v + FIXED['max_output_tokens'] for v in counts.values())
    if total > FIXED['max_total_tokens']:
        raise ValueError('fixed_full_reservation_exceeded')
    return total


def validate_plan(plan):
    if (any(plan.get(k) != v for k, v in FIXED.items())
            or plan.get('schedule') != schedule() or plan.get('conditions') != conditions()
            or [x['id'] for x in plan.get('cases', [])] != list(CASES)):
        raise ValueError('fixed_P101_scope_budget_or_order_changed')


def output_summary(response):
    structure = inspect_structure(response)
    fingerprints = output_fingerprints(response)
    static = bool(response.get('status') == 'ok' and fingerprints['complete_generation']
                  and structure.get('tool_calls') and structure.get('syntax_actions_sha256'))
    return {**fingerprints, 'structure': structure, 'complete_static_submission': static,
            'actual_execution_confirmed': False, 'task_quality_measured': False}


def input_comparisons(rendered):
    if set(rendered) != set(conditions()):
        raise ValueError('all_twelve_rendered_inputs_required')
    fields = ('prompt_sha256', 'tokens_sha256', 'session_controls_sha256',
              'parsed_non_message_parameters_sha256')
    return [{'left': a, 'right': b,
             **{key.removesuffix('_sha256') + '_equal': rendered[a][key] == rendered[b][key]
                for key in fields}}
            for a, b in combinations(conditions(), 2)]


def equality_summary(rows):
    planned = schedule()
    if len(rows) > len(planned) or any(
            any(row.get(k) != item[k] for k in ('id','case','tool_choice','condition','repetition'))
            for row, item in zip(rows, planned)):
        raise ValueError('ordered_unique_planned_prefix_required')
    missing = [{**item, 'status':'unattempted', **output_summary({'status':'error'})}
               for item in planned[len(rows):]]
    all_rows = rows + missing
    groups = []
    for key in conditions():
        group = [r for r in all_rows if r['condition'] == key]
        known = [r for r in group if r['status'] == 'ok']
        complete_public = len(known) == 3 and all(
            r['complete_generation'] and r['has_public_output'] for r in known)
        valid = len(known) == 3 and all(r['complete_static_submission'] for r in known)
        groups.append(dict(condition=key, case=group[0]['case'], tool_choice=group[0]['tool_choice'],
            attempted=sum(r['status'] != 'unattempted' for r in group), known=len(known),
            unknown=sum(r['status'] in ('error','attempting') for r in group),
            unattempted=sum(r['status'] == 'unattempted' for r in group),
            no_structured_calls=sum(r['structure'].get('tool_calls') == 0 for r in known),
            complete_static_submissions=sum(r['complete_static_submission'] for r in known),
            all_three_complete_nonempty=complete_public,
            all_three_public_outputs_equal=(len({r['public_output_sha256'] for r in known}) == 1)
                if complete_public else None,
            all_three_complete_static_submissions=valid,
            all_three_syntax_actions_equal=(len({r['structure']['syntax_actions_sha256'] for r in known}) == 1)
                if valid else None))
    # The existing comparator accepts any complete collection of three-repeat
    # groups. Keep all 12 groups and all 66 cross-group comparisons, including
    # missing outputs and two empty action lists, without calling them actions.
    contrasts = comparison([{**r, 'case':r['condition']} for r in all_rows], conditions())
    return dict(groups=groups, structural_comparisons=contrasts,
        all_36_terminal_usages_known=len(rows)==36 and all(r['status']=='ok' for r in rows),
        model_calls_attempted=len(rows), unknown_usage_calls=sum(r['status']!='ok' for r in rows),
        all_planned_slots_preserved=len(all_rows), actual_original_warm_state_replayed=False,
        local_saved_context_only=True, independent_contexts=1, repetitions_independent=False,
        task_quality_measured=False, whole_task_savings_measured=False,
        generated_actions_executed=0, novel_method_claim=False,
        static_submission_is_not_execution=True, private_reasoning_inspected_semantically=False)
