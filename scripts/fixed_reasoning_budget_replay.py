"""P87: one ordinary per-block budget contrast on two saved CSV contexts.

No adaptive controller, semantic reasoning inspection, or generated execution.
Complete code syntax is a local endpoint, not evidence of intended task effects.
"""
import ast
import copy
import json

from clock_notice_replay import digest, output_fingerprints

CASES = ('TRUNCATED_UNLIMITED', 'TRUNCATED_HALF', 'NO_ACTION_UNLIMITED', 'NO_ACTION_HALF')
COUNTS = (17696, 17696, 31211, 31211)
SEEDS = (69, 69, 74, 74)
BUDGETS = (-1, 2048, -1, 2048)
CONTEXTS = ('TRUNCATED', 'TRUNCATED', 'NO_ACTION', 'NO_ACTION')
ORDERS = ((0, 1, 3, 2), (1, 0, 2, 3))
FIXED = dict(phase='P87', batch_id='P87_fixed_reasoning_budget_v01', max_calls=8,
    max_total_tokens=250000, max_output_tokens=4096, call_timeout_seconds=480,
    max_wall_seconds=5400, max_preflight_seconds=300, max_idle_seconds=60,
    server_max_lifetime_seconds=7200, cache_prompt=False, automatic_retries=0,
    environment_api_requests=0, evaluations=0, reserved_scenarios_read=0,
    novel_method_claim=False, threshold_search=False, fresh_seed_search=False,
    required_closed_pipeline='records/context_pilot/P84_pipeline_v01',
    independent_tasks=1, saved_contexts=2, per_block_budgets=[-1,2048])


def schedule():
    return [dict(id=f'call_{(rep-1)*4+i+1:03d}', case=CASES[index], repetition=rep)
            for rep,order in enumerate(ORDERS,1) for i,index in enumerate(order)]


def request_for(original, case_id):
    index = CASES.index(case_id)
    if (original.get('seed') != SEEDS[index] or original.get('max_tokens') != 4096
            or original.get('cache_prompt') is not True or original.get('stream') is not False
            or original.get('temperature') != 1.0 or original.get('model') != 'minimax-m3-iq4xs'
            or original.get('chat_template_kwargs') != {'thinking_mode':'enabled'}
            or any(k in original for k in ('reasoning_budget_tokens','thinking_budget_tokens',
                                          'reasoning_budget_message','reasoning_control','reasoning_effort'))):
        raise ValueError('fixed_closed_source_controls_required')
    result = copy.deepcopy(original)
    result.update(cache_prompt=False, reasoning_budget_tokens=BUDGETS[index])
    return result


def reserve_tokens(counts):
    if tuple(counts) != COUNTS or any(type(v) is not int for v in counts):
        raise ValueError('all_four_fixed_source_input_counts_required')
    total = 2 * sum(v + FIXED['max_output_tokens'] for v in counts)
    if total > FIXED['max_total_tokens']:
        raise ValueError('fixed_reservation_exceeded')
    return total


def validate_plan(plan):
    if (any(type(plan.get(k)) is not type(v) or plan[k] != v for k,v in FIXED.items())
            or plan.get('schedule') != schedule()):
        raise ValueError('fixed_P87_scope_budget_or_order_changed')
    cases = plan.get('cases',[])
    if (len(cases) != 4 or [c['id'] for c in cases] != list(CASES)
            or [c['expected_input_tokens'] for c in cases] != list(COUNTS)
            or [c['context'] for c in cases] != list(CONTEXTS)
            or [c['reasoning_budget_tokens'] for c in cases] != list(BUDGETS)
            or [c['seed'] for c in cases] != list(SEEDS)):
        raise ValueError('all_four_fixed_context_budget_cases_required')
    if plan.get('reserved_total_tokens') != reserve_tokens(COUNTS):
        raise ValueError('fixed_reservation_changed')


def code_completion(response):
    """Apply the public run_python argument shape and AST parsing, never exec.

    Does not check referenced span availability, API preconditions or intention.
    Other tool names remain visible as a separate outcome, not guessed as code.
    """
    unknown = dict(tool_calls=None, python_calls=None, malformed_json_calls=None,
        shape_invalid_calls=None, syntax_invalid_calls=None, other_tool_calls=None,
        complete_code_submission=None, task_quality_established=False)
    if response.get('status') != 'ok': return unknown
    calls = response['message'].get('tool_calls') or []
    result = dict(tool_calls=len(calls),python_calls=0,malformed_json_calls=0,
        shape_invalid_calls=0,syntax_invalid_calls=0,other_tool_calls=0,
        complete_code_submission=False,task_quality_established=False)
    for call in calls:
        fn = call['function']
        if fn['name'] != 'run_python':
            result['other_tool_calls'] += 1
            continue
        result['python_calls'] += 1
        try: args = json.loads(fn['arguments'])
        except (TypeError, ValueError):
            result['malformed_json_calls'] += 1
            continue
        if (type(args) is not dict or set(args) != {'code','span_ids'}
                or type(args['code']) is not str or not 0 < len(args['code']) <= 20000
                or type(args['span_ids']) is not list or len(args['span_ids']) > 160
                or any(type(x) is not str for x in args['span_ids'])
                or len(args['span_ids']) != len(set(args['span_ids']))):
            result['shape_invalid_calls'] += 1
            continue
        try:
            if not ast.parse(args['code']).body:
                result['syntax_invalid_calls'] += 1
        except (SyntaxError,ValueError):
            result['syntax_invalid_calls'] += 1
    result['complete_code_submission'] = bool(calls and response['done_reason'] != 'length'
        and result['python_calls'] == len(calls)
        and not any(result[k] for k in ('malformed_json_calls','shape_invalid_calls','syntax_invalid_calls')))
    return result


def equality_summary(rows):
    planned = {r['id']:r for r in schedule()}
    if (len({r['id'] for r in rows}) != len(rows)
            or any(r['id'] not in planned or any(r[k] != planned[r['id']][k]
                for k in ('case','repetition')) for r in rows)):
        raise ValueError('unique_fixed_replay_rows_required')
    groups = {}
    for case in CASES:
        selected = [r for r in rows if r['case']==case and r.get('status') not in ('unattempted',None)]
        known = [r for r in selected if r.get('status')=='ok']
        groups[case] = dict(attempted=len(selected), known=len(known),
            complete_code_submissions=sum(r['complete_code_submission'] is True for r in known),
            finish_lengths=sum(r['done_reason']=='length' for r in known),
            public_outputs_equal=(known[0]['public_output_sha256']==known[1]['public_output_sha256']) if len(known)==2 else None,
            known_input_tokens=sum(r['input_tokens'] for r in known),
            known_output_tokens=sum(r['output_tokens'] for r in known))
    full = len(rows)==8 and all(r.get('status')=='ok' for r in rows)
    comparisons = []
    for context,base,half in [('TRUNCATED',CASES[0],CASES[1]),('NO_ACTION',CASES[2],CASES[3])]:
        b,h = groups[base],groups[half]
        known = b['known']==h['known']==2
        comparisons.append(dict(context=context, all_four_known=known,
            half_minus_unlimited_complete_submissions=h['complete_code_submissions']-b['complete_code_submissions'] if known else None,
            half_minus_unlimited_output_tokens=h['known_output_tokens']-b['known_output_tokens'] if known else None,
            both_baseline_failures_to_both_half_completions=(b['complete_code_submissions']==0 and h['complete_code_submissions']==2) if known else None))
    return dict(groups=groups,comparisons=comparisons,all_eight_terminal_usages_known=full,
        both_contexts_local_completion_improved=all(c['both_baseline_failures_to_both_half_completions'] for c in comparisons) if full else None,
        independent_tasks=1,saved_contexts=2,replications_are_independent_tasks=False,
        original_warm_state_recreated=False,novel_method_claim=False,
        task_quality_measured=False,whole_task_savings_measured=False,
        private_reasoning_inspected_semantically=False)
