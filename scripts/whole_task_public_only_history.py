"""P114: four fresh ordinary-control runs, with P111 as historical reference."""
from budget_observation import notification
from budget_visibility_comparison import ERROR_POLICY, validate_plan as validate_base
from late_clock_comparison import initial_conversation
from public_only_reasoning_history import POLICIES
from whole_task_tool_choice import worker_config as original_worker_config

HISTORICAL_POLICIES = ('full', 'recent', 'execution_gated')


def run_order():
    return [(n, 'public_only') for n in range(1, 5)]


def cell_id(number, policy):
    if type(number) is not int or number not in range(1, 5) or policy not in POLICIES:
        raise ValueError('outside_fixed_P114_control')
    return f'BOC_P114_{number:02d}_{policy.upper()}'


def worker_config(original, plan, task_id, arm, run_id, display_policy):
    if display_policy not in POLICIES:
        raise ValueError('explicit_P114_display_policy_required')
    config = original_worker_config(original, plan, task_id, arm, run_id, 'auto')
    config.update(reasoning_display_policy=display_policy, read_views_enabled=False)
    return config


def config_for(original, plan, task_id, policy):
    number = [t['task_id'] for t in plan['known_tasks']].index(task_id)+1
    return worker_config(original, plan, task_id, ERROR_POLICY, cell_id(number, policy), policy)


def make_notification(messages, state, policy, *, wall_limit):
    if policy not in POLICIES:
        raise ValueError('fixed_P114_display_policy_required')
    return notification(messages, state, 'not_exposed')


def validate_plan(plan):
    expected = dict(experiment='P114', batch_id='P114_batch_v01',
        reasoning_display_policies=list(POLICIES), tool_choice='auto', reasoning_budget_tokens=-1,
        time_visibility='not_exposed', repetitions=1, max_cells=4, max_model_calls=320,
        max_reserved_tokens=1800000, max_reserved_environment_api_requests=400,
        server_max_lifetime_seconds=14400, fresh_seed_search=False, threshold_search=False,
        new_task_requirements_read=0, protocol_references='source_protocol_fields_before_rendering',
        primary_question='public_only_from_start_ordinary_control_calibration',
        required_closed_diagnostic='reports/P113_receipt_history_trajectories.json',
        required_predecessor_phase='P111', read_views_enabled=False,
        immutable_P110_display_rules=True, no_previous_replacement_or_retry=True,
        historical_reference_phase='P111', contemporaneous_comparison=False,
        remove_latest_reasoning=True, selection_uses_receipt_eligibility=False)
    if any(type(plan.get(k)) is not type(v) or plan[k] != v for k, v in expected.items()):
        raise ValueError('fixed_P114_scope_changed')
    for name in ('scripts/receipt_reasoning_history.py', 'scripts/public_only_reasoning_history.py',
                 'reports/P111_comparison.json', 'reports/P111_server_session.json',
                 'reports/P111_initial_checks.json', 'configs/P111_whole_task_receipt_history_v01.json',
                 'reports/P113_receipt_history_trajectories.json',
                 'docs/experiments/P114_whole_task_public_only_history.md'):
        value = plan.get('source_sha256', {}).get(name)
        if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('bound_historical_sources_required')
    validate_base({**plan, 'experiment': 'P80', 'batch_id': 'P80_batch_v01',
        'time_policies': ['measured', 'not_exposed'], 'max_cells': 8, 'max_model_calls': 640,
        'max_reserved_tokens': 3600000, 'server_max_lifetime_seconds': 21600,
        'protocol_references': 'canonical_in_both_before_counting'})


def token_bounds(rows):
    """Known subtotals bound nonnegative unknown use, never absent run slots."""
    if not rows or any(r['record_status'] not in ('evaluated', 'unevaluated') or
            type(r.get('known_total_tokens')) is not int or r['known_total_tokens'] < 0 or
            type(r.get('unknown_usage_calls')) is not int or r['unknown_usage_calls'] < 0 for r in rows):
        return dict(lower=None, upper=None, exact=None)
    known = sum(r['known_total_tokens'] for r in rows)
    exact = known if all(r['unknown_usage_calls'] == 0 for r in rows) else None
    return dict(lower=known, upper=exact, exact=exact)


def delta_bounds(new, historical):
    a, b = token_bounds(new), token_bounds(historical)
    return dict(exact=a['exact']-b['exact'] if a['exact'] is not None and b['exact'] is not None else None,
        lower=a['lower']-b['upper'] if a['lower'] is not None and b['upper'] is not None else None,
        upper=a['upper']-b['lower'] if a['upper'] is not None and b['lower'] is not None else None)


def summarize(rows, errors, historical_rows):
    tasks = [r['task_id'] for r in rows]
    if len(tasks) != 4 or len(set(tasks)) != 4 or any(r['reasoning_display_policy'] != 'public_only' for r in rows):
        raise ValueError('all_four_new_control_slots_required')
    if (len(historical_rows) != 12 or
            {(r['task_id'], r['reasoning_display_policy']) for r in historical_rows} !=
            {(t, p) for t in tasks for p in HISTORICAL_POLICIES}):
        raise ValueError('all_twelve_historical_reference_slots_required')
    historical = {(r['task_id'], r['reasoning_display_policy']): r for r in historical_rows}
    comparisons = []
    for policy in HISTORICAL_POLICIES:
        old = [historical[t, policy] for t in tasks]
        pairs = []
        for new, reference in zip(rows, old, strict=True):
            evaluated = all(r['record_status'] == 'evaluated' and type(r['success']) is bool for r in (new, reference))
            pairs.append(dict(task_id=new['task_id'], public_only_success=new['success'],
                historical_success=reference['success'], both_evaluated=evaluated,
                both_successful=evaluated and new['success'] and reference['success'],
                success_loss=evaluated and reference['success'] and not new['success'],
                public_only_minus_historical_tokens=delta_bounds([new], [reference])))
        indices = [i for i, p in enumerate(pairs) if p['both_successful']]
        successful = delta_bounds([rows[i] for i in indices], [old[i] for i in indices])
        total = delta_bounds(rows, old)
        all_known = all(p['both_evaluated'] for p in pairs) and total['exact'] is not None
        criterion = bool(not errors and all_known and not any(p['success_loss'] for p in pairs)
            and indices and total['exact'] < 0 and successful['exact'] is not None and successful['exact'] < 0)
        comparisons.append(dict(historical_policy=policy, paired_results=pairs,
            public_only_tokens=token_bounds(rows), historical_tokens=token_bounds(old),
            public_only_minus_historical_tokens=total, all_eight_evaluated_with_known_usage=all_known,
            paired_successful_tasks=len(indices), paired_successful_token_difference=successful,
            descriptive_cost_quality_criterion_met=criterion, development_gate_met=False))
    return dict(planned_rows=4, historical_reference_rows=12, independent_tasks=4, repetitions=1,
        comparisons=comparisons, development_gate_met=False,
        all_four_complete_with_known_usage=not errors and all(r['record_status'] == 'evaluated'
            and type(r['success']) is bool for r in rows) and token_bounds(rows)['exact'] is not None,
        contemporaneous_comparison=False, novel_method_claim=False, general_quality_preservation_claim=False,
        interpretation='Four new ordinary-control runs compared descriptively with all twelve historical P111 rows. '
            'Outcomes of P111 were known before this plan. No confirmatory or causal claim; no change to P111 gates. '
            'A descriptive criterion requires known costs and evaluations, no success loss, '
            'and lower all-task and paired-successful costs. Unknown use is not zero; missing slots have no cost bound. '
            'The same four tasks are shared across three comparisons.')
