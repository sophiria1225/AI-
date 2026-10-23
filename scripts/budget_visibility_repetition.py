"""Two prespecified same-seed repetitions of the complete P80 development cohort.

No new policy, task selection, seed search or novelty claim is introduced.
"""
from budget_observation import POLICIES
from budget_observation_worker import worker_config
from budget_visibility_comparison import ERROR_POLICY, validate_plan as validate_anchor
from audit_budget_visibility_comparison import development_gate

REPETITIONS = (2, 3)


def run_order():
    return [(rep, number, policy) for rep in REPETITIONS for number in range(1, 5)
            for policy in (POLICIES if (number + rep) % 2 == 0 else POLICIES[::-1])]


def cell_id(repetition, number, policy):
    if (type(repetition) is not int or repetition not in REPETITIONS
            or type(number) is not int or number not in range(1, 5) or policy not in POLICIES):
        raise ValueError('outside_fixed_P81_repetitions')
    return f'BOC_P81_R{repetition}_{number:02d}_{policy.upper()}'


def config_for(original, plan, task_id, policy):
    # Repetition IDs only identify records. Model/world settings remain identical.
    number = [t['task_id'] for t in plan['known_tasks']].index(task_id) + 1
    return worker_config(original, plan, task_id, ERROR_POLICY, cell_id(2, number, policy), policy)


def validate_plan(plan):
    expected = {'experiment': 'P81', 'batch_id': 'P81_batch_v01',
        'repetitions': list(REPETITIONS), 'anchor_experiment': 'P80',
        'max_cells': 16, 'max_model_calls': 1280, 'max_reserved_tokens': 7200000,
        'server_max_lifetime_seconds': 43200, 'fresh_seed_search': False,
        'new_task_requirements_read': 0,
        'primary_question': 'same_seed_trajectory_and_cost_stability',
        'prior_cohort': 'reports/P80_comparison.json'}
    if any(type(plan.get(k)) is not type(v) or plan[k] != v for k, v in expected.items()):
        raise ValueError('fixed_P81_scope_changed')
    for name in (plan['prior_cohort'], 'reports/P80_server_session.json',
                 'configs/P80_budget_visibility_v01.json'):
        value = plan.get('source_sha256', {}).get(name)
        if (type(value) is not str or len(value) != 64
                or any(c not in '0123456789abcdef' for c in value)):
            raise ValueError('closed_anchor_sources_must_be_hash_bound')
    validate_anchor({**plan, 'experiment': 'P80', 'batch_id': 'P80_batch_v01',
        'max_cells': 8, 'max_model_calls': 640, 'max_reserved_tokens': 3600000,
        'server_max_lifetime_seconds': 21600})


def summarize_repetitions(anchor_rows, repeated_rows, audit_errors):
    rows = [{**r, 'repetition': 1} for r in anchor_rows] + repeated_rows
    tasks = list(dict.fromkeys(r['task_id'] for r in anchor_rows))
    expected = {(rep, task, policy) for rep in (1, 2, 3) for task in tasks for policy in POLICIES}
    observed = [(r['repetition'], r['task_id'], r['time_visibility']) for r in rows]
    if len(tasks) != 4 or len(observed) != 24 or set(observed) != expected:
        raise ValueError('exactly_three_repetitions_of_all_eight_conditions_required')
    reps = [{'repetition': rep, **development_gate(
        [r for r in rows if r['repetition'] == rep], audit_errors)} for rep in (1, 2, 3)]
    groups = []
    for task in tasks:
        for policy in POLICIES:
            group = sorted([r for r in rows if r['task_id'] == task and r['time_visibility'] == policy],
                           key=lambda r: r['repetition'])
            evaluated = all(r['record_status'] == 'evaluated' for r in group)
            known = evaluated and all(r['unknown_usage_calls'] == 0 for r in group)
            costs = [r['known_total_tokens'] for r in group]
            groups.append({'task_id': task, 'time_visibility': policy,
                'run_ids': [r['run_id'] for r in group],
                'success_sequence': [r['success'] for r in group],
                'known_token_sequence': costs,
                'unknown_usage_sequence': [r['unknown_usage_calls'] for r in group],
                'all_three_evaluated_with_known_usage': known,
                'successes_stable': len({r['success'] for r in group}) == 1 if evaluated else None,
                'exact_costs_stable': len(set(costs)) == 1 if known else None,
                'min_tokens': min(costs) if known else None,
                'max_tokens': max(costs) if known else None,
                'range_tokens': max(costs) - min(costs) if known else None})
    return {'planned_rows_including_anchor': 24, 'newly_planned_rows': 16,
        'repetitions': reps, 'groups': groups,
        'all_three_repetition_gates_met': all(r['development_gate_met'] for r in reps),
        'all_24_evaluated_with_known_usage': all(r['all_eight_complete_with_known_usage'] for r in reps),
        'independent_tasks': 4, 'novel_method_claim': False,
        'general_quality_preservation_claim': False,
        'interpretation': 'Same-seed repetitions on known tasks, not 24 independent tasks, a seed search, or a population estimate.'}
