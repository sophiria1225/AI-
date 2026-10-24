"""P111: fixed from-start development comparison of the three P110 rules."""
from budget_observation import notification
from budget_visibility_comparison import ERROR_POLICY, validate_plan as validate_base
from audit_budget_visibility_comparison import development_gate
from late_clock_comparison import initial_conversation
from receipt_reasoning_history import POLICIES
from whole_task_tool_choice import worker_config as original_worker_config


def run_order():
    orders = (POLICIES, POLICIES[1:]+POLICIES[:1], POLICIES[2:]+POLICIES[:2], POLICIES[::-1])
    return [(n, policy) for n in range(1, 5) for policy in orders[n-1]]


def cell_id(number, policy):
    if type(number) is not int or number not in range(1, 5) or policy not in POLICIES:
        raise ValueError('outside_fixed_P111_comparison')
    return f'BOC_P111_{number:02d}_{policy.upper()}'


def worker_config(original, plan, task_id, arm, run_id, display_policy):
    if display_policy not in POLICIES:
        raise ValueError('explicit_P111_display_policy_required')
    config = original_worker_config(original, plan, task_id, arm, run_id, 'auto')
    config.update(reasoning_display_policy=display_policy, read_views_enabled=False)
    return config


def config_for(original, plan, task_id, policy):
    number = [t['task_id'] for t in plan['known_tasks']].index(task_id)+1
    return worker_config(original, plan, task_id, ERROR_POLICY, cell_id(number, policy), policy)


def make_notification(messages, state, policy, *, wall_limit):
    if policy not in POLICIES:
        raise ValueError('fixed_P111_display_policy_required')
    return notification(messages, state, 'not_exposed')


def validate_plan(plan):
    expected = dict(experiment='P111', batch_id='P111_batch_v01',
        reasoning_display_policies=list(POLICIES), tool_choice='auto', reasoning_budget_tokens=-1,
        time_visibility='not_exposed', repetitions=1, max_cells=12, max_model_calls=960,
        max_reserved_tokens=5400000, max_reserved_environment_api_requests=1200,
        server_max_lifetime_seconds=32400, fresh_seed_search=False, threshold_search=False,
        new_task_requirements_read=0, protocol_references='source_protocol_fields_before_rendering',
        primary_question='receipt_conditioned_reasoning_whole_task_quality_and_cost',
        required_closed_diagnostic='reports/P110_receipt_history_inputs.json',
        required_predecessor_phase='P107', read_views_enabled=False,
        immutable_P110_display_rules=True, no_previous_replacement_or_retry=True)
    if any(type(plan.get(k)) is not type(v) or plan[k] != v for k,v in expected.items()):
        raise ValueError('fixed_P111_scope_changed')
    for name in ('scripts/receipt_reasoning_history.py', 'reports/P110_receipt_history_inputs.json',
                 'configs/P110_receipt_history_inputs_v01.json', 'reports/P107_comparison.json',
                 'reports/P107_server_session.json', 'docs/experiments/P111_whole_task_receipt_history.md'):
        value=plan.get('source_sha256',{}).get(name)
        if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('bound_prior_sources_required')
    validate_base({**plan, 'experiment':'P80', 'batch_id':'P80_batch_v01',
        'time_policies':['measured','not_exposed'], 'max_cells':8, 'max_model_calls':640,
        'max_reserved_tokens':3600000, 'server_max_lifetime_seconds':21600,
        'protocol_references':'canonical_in_both_before_counting'})


def summarize(rows, errors):
    tasks=list(dict.fromkeys(r['task_id'] for r in rows))
    actual=[(r['task_id'],r['reasoning_display_policy']) for r in rows]
    if len(tasks)!=4 or len(actual)!=12 or set(actual)!={(t,p) for t in tasks for p in POLICIES}:
        raise ValueError('all_twelve_new_conditions_required')
    comparisons=[]
    for baseline in ('full','recent'):
        selected=[r for r in rows if r['reasoning_display_policy'] in (baseline,'execution_gated')]
        common=development_gate([{**r,'time_visibility':
            'not_exposed' if r['reasoning_display_policy']=='execution_gated' else 'measured'} for r in selected],errors)
        def rename(value):
            if isinstance(value,dict):
                return {k.replace('not_exposed','execution_gated').replace('measured',baseline):rename(v) for k,v in value.items()}
            if isinstance(value,list):return [rename(v) for v in value]
            return value
        gate=rename(common)
        complete=gate['all_eight_complete_with_known_usage']
        delta='execution_gated_minus_'+baseline+'_tokens'
        successful=sum(p[delta] for p in gate['paired_results'] if p['both_successful']) if complete else None
        failed=sum(p[delta] for p in gate['paired_results'] if p['both_evaluated'] and
            not p[baseline+'_success'] and not p['execution_gated_success']) if complete else None
        gate.update(paired_successful_token_difference=successful,both_failed_token_difference=failed)
        gate['development_gate_met']=bool(gate['development_gate_met'] and
            gate['paired_successful_tasks']>0 and successful is not None and successful<0)
        comparisons.append(dict(baseline=baseline,**gate))
    return dict(planned_rows=12,independent_tasks=4,repetitions=1,comparisons=comparisons,
        development_gate_met=all(c['development_gate_met'] for c in comparisons),
        all_twelve_complete_with_known_usage=all(c['all_eight_complete_with_known_usage'] for c in comparisons),
        novel_method_claim=False,general_quality_preservation_claim=False,
        interpretation='One development run per policy/task, never heldout confirmation. '
            'Must preserve each task success and reduce both all-task and paired-successful logical '
            'cost against full and recent separately, with all usage known and clean audits. '
            'Cheap failures, hypothetical P110 counts and cached tokens are not quality-preserving savings.')
