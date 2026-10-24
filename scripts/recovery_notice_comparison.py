"""P97: ordinary recovery notices, twelve fresh known-task conditions."""
from budget_observation import notification
from budget_observation_worker import worker_config as base_worker_config
from budget_visibility_comparison import ERROR_POLICY, validate_plan as validate_base
from late_clock_comparison import initial_conversation
from recovery_notices import POLICIES


def run_order():
    return [(n, policy) for n in range(1, 5)
            for policy in POLICIES[(n-1) % 3:] + POLICIES[:(n-1) % 3]]


def cell_id(number, policy):
    if type(number) is not int or number not in range(1, 5) or policy not in POLICIES:
        raise ValueError('outside_fixed_P97_comparison')
    return f'BOC_P97_{number:02d}_{policy.upper()}'


def worker_config(original, plan, task_id, arm, run_id, notice_policy):
    if notice_policy not in POLICIES:
        raise ValueError('explicit_P97_notice_policy_required')
    config = base_worker_config(original, plan, task_id, arm, run_id, 'not_exposed')
    config.update(protocol_reference_policy='source_protocol_fields_before_rendering',
                  notice_policy=notice_policy)
    config['model']['reasoning_budget_tokens'] = -1
    if (config['model']['call_timeout_seconds'] != 600 or config['model']['num_ctx'] != 65536
            or config['model'].get('thinking_mode', 'enabled') != 'enabled'
            or config['max_output_tokens'] != 4096):
        raise ValueError('existing_full_task_model_limits_required')
    return config


def config_for(original, plan, task_id, policy):
    number = [t['task_id'] for t in plan['known_tasks']].index(task_id)+1
    return worker_config(original, plan, task_id, ERROR_POLICY, cell_id(number, policy), policy)


def make_notification(messages, state, policy, *, wall_limit):
    if policy not in POLICIES:
        raise ValueError('explicit_P97_notice_policy_required')
    return notification(messages, state, 'not_exposed')


def validate_plan(plan):
    expected = dict(experiment='P97', batch_id='P97_batch_v01', notice_policies=list(POLICIES),
        reasoning_budget_tokens=-1, time_visibility='not_exposed', repetitions=1,
        max_cells=12, max_model_calls=960, max_reserved_tokens=5400000,
        server_max_lifetime_seconds=32400, fresh_seed_search=False, threshold_search=False,
        new_task_requirements_read=0, protocol_references='source_protocol_fields_before_rendering',
        primary_question='ordinary_recovery_notice_whole_task_cost_and_quality',
        detector='drop_auth_argument', fixed_candidate_streak=2, max_notices_per_cell=1,
        monitor_max_entries=512, monitor_max_value_bytes=65536,
        api_elision_permitted=False, observation_replacement_permitted=False,
        required_closed_diagnostic='reports/P96_auth_origin_observations.json')
    if any(type(plan.get(k)) is not type(v) or plan[k] != v for k, v in expected.items()):
        raise ValueError('fixed_P97_scope_changed')
    for name in ('configs/P88_whole_task_reasoning_budget_v01.json', 'reports/P88_comparison.json',
                 'reports/P88_server_session.json', 'reports/P96_auth_origin_observations.json',
                 'reports/auth_origin_prior_sources_20261024.json'):
        value = plan.get('source_sha256', {}).get(name)
        if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('closed_dependency_must_be_hash_bound')
    validate_base({**plan, 'experiment':'P80', 'batch_id':'P80_batch_v01',
        'time_policies':['measured', 'not_exposed'], 'protocol_references':'canonical_in_both_before_counting',
        'max_cells':8, 'max_model_calls':640, 'max_reserved_tokens':3600000,
        'server_max_lifetime_seconds':21600})


def summarize(rows, errors):
    """All twelve slots, including missing/unknown ones, remain in the result."""
    tasks = list(dict.fromkeys(r['task_id'] for r in rows))
    if (len(tasks) != 4 or len(rows) != 12 or
            {(r['task_id'], r['notice_policy']) for r in rows} !=
            {(t, p) for t in tasks for p in POLICIES}):
        raise ValueError('all_twelve_planned_slots_required')
    complete = not errors and all(r.get('record_status') == 'evaluated'
        and r.get('unknown_usage_calls') == 0 and type(r.get('success')) is bool
        and type(r.get('known_total_tokens')) is int for r in rows)
    pairs = []
    for left, right in [('none','generic'), ('none','factual'), ('generic','factual')]:
        joined = []
        for task in tasks:
            a = next(r for r in rows if r['task_id'] == task and r['notice_policy'] == left)
            b = next(r for r in rows if r['task_id'] == task and r['notice_policy'] == right)
            joined.append(dict(task_id=task, left_success=a.get('success'),
                right_success=b.get('success'), both_successful=a.get('success') is True
                and b.get('success') is True,
                right_minus_left_tokens=b['known_total_tokens']-a['known_total_tokens'] if complete else None))
        preserves = complete and all(p['left_success'] is not True or p['right_success'] is True for p in joined)
        delta = sum(p['right_minus_left_tokens'] for p in joined) if complete else None
        pairs.append(dict(left=left, right=right, tasks=joined,
            no_per_task_success_loss=bool(preserves), aggregate_token_difference=delta,
            ordinary_control_gate_met=bool(complete and preserves and any(p['both_successful'] for p in joined)
                                          and delta < 0)))
    matched = []
    for task in tasks:
        generic = next(r for r in rows if r['task_id'] == task and r['notice_policy'] == 'generic')
        factual = next(r for r in rows if r['task_id'] == task and r['notice_policy'] == 'factual')
        if (len(generic.get('dispatched_notice_inputs', [])) == 1
                and generic['dispatched_notice_inputs'] == factual.get('dispatched_notice_inputs')):
            matched.append(task)
    return dict(all_twelve_evaluated_with_known_usage=bool(complete), pairs=pairs,
        independent_tasks=4, repetitions=1, detector_in_scope_tasks=1,
        matched_before_notice_tasks=matched,
        novel_method_established=False, general_quality_preservation_established=False,
        factual_notice_benefit_gate_met=bool(complete and matched and pairs[1]['ordinary_control_gate_met']
                                                and pairs[2]['ordinary_control_gate_met']))
