"""P88: two explicit ordinary reasoning budgets, four new paired task runs."""
from budget_observation import notification
from budget_observation_worker import worker_config as base_worker_config
from budget_visibility_comparison import ERROR_POLICY, validate_plan as validate_base
from audit_budget_visibility_comparison import development_gate
from late_clock_comparison import initial_conversation

POLICIES = ('unlimited', 'half')
BUDGETS = dict(zip(POLICIES, (-1, 2048)))
REQUIRED_SOURCES = (
    'configs/P82_late_clock_comparison_v01.json', 'reports/P82_comparison.json',
    'configs/P87_fixed_reasoning_budget_v01.json', 'reports/P87_fixed_reasoning_budget_replay.json',
    'reports/P87_execution_closure_20261024.json', 'reports/P87_results_provenance_20261024.json',
    'reports/output_budget_backend_scope_20261024.json',
    'reports/budget_completion_prior_sources_20261024.json')


def run_order():
    return [(n, policy) for n in range(1, 5)
            for policy in (POLICIES if n % 2 else POLICIES[::-1])]


def cell_id(number, policy):
    if type(number) is not int or number not in range(1, 5) or policy not in POLICIES:
        raise ValueError('outside_fixed_P88_comparison')
    return f'BOC_P88_{number:02d}_{policy.upper()}'


def worker_config(original, plan, task_id, arm, run_id, reasoning_policy):
    if reasoning_policy not in POLICIES:
        raise ValueError('explicit_P88_reasoning_policy_required')
    config = base_worker_config(original, plan, task_id, arm, run_id, 'not_exposed')
    config['protocol_reference_policy'] = 'source_protocol_fields_before_rendering'
    config['reasoning_policy'] = reasoning_policy
    config['model']['reasoning_budget_tokens'] = BUDGETS[reasoning_policy]
    if (config['model']['call_timeout_seconds'] != 600 or config['model']['num_ctx'] != 65536
            or config['model'].get('thinking_mode', 'enabled') != 'enabled'
            or config['max_output_tokens'] != 4096):
        raise ValueError('existing_full_task_model_limits_required')
    return config


def config_for(original, plan, task_id, policy):
    number = [t['task_id'] for t in plan['known_tasks']].index(task_id) + 1
    return worker_config(original, plan, task_id, ERROR_POLICY, cell_id(number, policy), policy)


def make_notification(messages, state, policy, *, wall_limit):
    if policy not in POLICIES:
        raise ValueError('explicit_P88_reasoning_policy_required')
    return notification(messages, state, 'not_exposed')


def validate_plan(plan):
    expected = dict(experiment='P88', batch_id='P88_batch_v01', reasoning_policies=list(POLICIES),
        reasoning_budget_tokens=[-1, 2048], time_visibility='not_exposed',
        repetitions=1, max_cells=8, max_model_calls=640, max_reserved_tokens=3600000,
        server_max_lifetime_seconds=21600, fresh_seed_search=False, threshold_search=False,
        new_task_requirements_read=0, protocol_references='source_protocol_fields_before_rendering',
        primary_question='ordinary_reasoning_budget_whole_task_cost_and_quality',
        required_closed_diagnostic='reports/P87_fixed_reasoning_budget_replay.json',
        no_P87_replacement_or_retry=True)
    if any(type(plan.get(k)) is not type(v) or plan[k] != v for k, v in expected.items()):
        raise ValueError('fixed_P88_scope_changed')
    for name in REQUIRED_SOURCES:
        value = plan.get('source_sha256', {}).get(name)
        if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('closed_dependency_must_be_hash_bound')
    validate_base({**plan, 'experiment': 'P80', 'batch_id': 'P80_batch_v01',
                   'time_policies': ['measured', 'not_exposed'],
                   'protocol_references': 'canonical_in_both_before_counting'})


def summarize(rows, errors):
    tasks = list(dict.fromkeys(r['task_id'] for r in rows))
    expected = {(t, p) for t in tasks for p in POLICIES}
    actual = [(r['task_id'], r['reasoning_policy']) for r in rows]
    if len(tasks) != 4 or len(actual) != 8 or set(actual) != expected:
        raise ValueError('all_eight_new_conditions_required')
    aliases = dict(zip(POLICIES, ('measured', 'not_exposed')))
    common = development_gate([{**r, 'time_visibility': aliases[r['reasoning_policy']]}
                               for r in rows], errors)

    def renamed(value):
        if isinstance(value, dict):
            return {k.replace('not_exposed', 'half').replace('measured', 'unlimited'): renamed(v)
                    for k, v in value.items()}
        if isinstance(value, list):
            return [renamed(v) for v in value]
        return value

    result = renamed(common)
    result['development_gate_met'] = bool(result['development_gate_met']
        and result['paired_successful_tasks'] and result['paired_successful_tasks'] > 0)
    complete = result['all_eight_complete_with_known_usage']
    result['paired_successful_token_difference'] = sum(p['half_minus_unlimited_tokens']
        for p in result['paired_results'] if p['both_successful']) if complete else None
    result['both_failed_token_difference'] = sum(p['half_minus_unlimited_tokens']
        for p in result['paired_results'] if p['both_evaluated']
        and not p['unlimited_success'] and not p['half_success']) if complete else None
    return {**result, 'planned_rows': 8, 'independent_tasks': 4, 'repetitions': 1,
        'time_visibility': 'not_exposed', 'reasoning_budget_tokens': [-1, 2048],
        'P87_missing_slots_filled': False,
        'interpretation': 'One new paired cohort of two ordinary budgets on four known tasks. '
            'All eight evaluations and usages, no success loss, at least one paired success, '
            'and lower aggregate full logical cost are required. '
            'No novelty, restored historical quality or general quality guarantee is established.'}
