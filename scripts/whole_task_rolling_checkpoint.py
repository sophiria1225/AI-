"""Preparation for P123; three fixed checkpoint policies on four known tasks.

No generation is authorized by this helper. A frozen finite plan and a closed,
reviewed P122 predecessor are required before a future batch can be launched.
"""
from budget_observation import notification
from budget_visibility_comparison import ERROR_POLICY, validate_plan as validate_base
from late_clock_comparison import initial_conversation
from receipt_reasoning_history import require
from rolling_checkpoint_history import MAX_OPPORTUNITIES, MIN_NEW_CLOSED_TURNS
from single_checkpoint_history import TRIGGER_INPUT_TOKENS, RECENT_TURNS, MAX_SUMMARY_CHARACTERS
from whole_task_tool_choice import worker_config as original_worker_config

POLICIES = ('single_checkpoint', 'rolling_separate', 'rolling_inline')


def run_order():
    return [(number, POLICIES[(number - 1 + offset) % len(POLICIES)])
            for number in range(1, 5) for offset in range(len(POLICIES))]


def cell_id(number, policy):
    require(type(number) is int and number in range(1, 5) and policy in POLICIES,
            'outside_fixed_P123_comparison')
    return f'BOC_P123_{number:02d}_{policy.upper()}'


def worker_config(original, plan, task_id, arm, run_id, checkpoint_policy):
    require(plan.get('experiment') == 'P123' and run_id.startswith('BOC_P123_'),
            'new_P123_plan_and_identity_required')
    require(checkpoint_policy in POLICIES, 'explicit_P123_checkpoint_policy_required')
    require(plan.get('rolling_checkpoint_max_opportunities') == MAX_OPPORTUNITIES
            and plan.get('rolling_min_fresh_turns') == MIN_NEW_CLOSED_TURNS
            and plan.get('inline_checkpoint_requirement') == 'required_when_run_python',
            'fixed_rolling_control_limits_required')
    config = original_worker_config(original, plan, task_id, arm, run_id, 'auto')
    require(config['draft_temperature'] == 0.7, 'fixed_summary_temperature_required')
    config.update(checkpoint_policy=checkpoint_policy, read_views_enabled=False,
        inline_checkpoint_requirement='required_when_run_python'
            if checkpoint_policy == 'rolling_inline' else 'not_applicable')
    if checkpoint_policy != 'single_checkpoint':
        config.update(rolling_checkpoint_max_opportunities=MAX_OPPORTUNITIES,
                      rolling_min_fresh_turns=MIN_NEW_CLOSED_TURNS)
    return config


def config_for(original, plan, task_id, policy):
    number = [t['task_id'] for t in plan['known_tasks']].index(task_id) + 1
    return worker_config(original, plan, task_id, ERROR_POLICY, cell_id(number, policy), policy)


def make_notification(messages, state, policy, *, wall_limit):
    require(policy in POLICIES, 'fixed_P123_policy_required')
    return notification(messages, state, 'not_exposed')


def validate_plan(plan):
    expected = dict(experiment='P123', batch_id='P123_batch_v01', checkpoint_policies=list(POLICIES),
        tool_choice='auto', reasoning_budget_tokens=-1, time_visibility='not_exposed', repetitions=1,
        max_cells=12, max_model_calls=960, max_reserved_tokens=5400000,
        max_reserved_environment_api_requests=1200, server_max_lifetime_seconds=32400,
        fresh_seed_search=False, threshold_search=False, new_task_requirements_read=0,
        protocol_references='source_protocol_fields_before_rendering',
        primary_question='rolling_inline_whole_task_cost_against_single_and_rolling_separate',
        required_closed_diagnostic='reports/P122_comparison.json', required_predecessor_phase='P122',
        read_views_enabled=False, trigger_input_tokens=TRIGGER_INPUT_TOKENS,
        retained_recent_turns=RECENT_TURNS, max_summary_characters=MAX_SUMMARY_CHARACTERS,
        rolling_checkpoint_max_opportunities=MAX_OPPORTUNITIES, rolling_min_fresh_turns=MIN_NEW_CLOSED_TURNS,
        single_checkpoint_max_opportunities=1, max_summary_calls_in_batch=16,
        max_inline_opportunities_in_batch=12, shared_model_call_and_token_budget=True,
        summary_output_cap=4096, summary_temperature=0.7,
        invalid_summary_policy='keep_current_view_charge_known_cost_require_three_fresh_turns',
        unknown_summary_usage_policy='stop_without_retry',
        inline_checkpoint_requirement='required_when_run_python',
        same_call_results_summarized=False, separate_semantic_judge=False,
        minimum_repeated_installations_per_rolling_policy=2,
        no_previous_replacement_or_retry=True, novel_method_claim=False)
    require(all(type(plan.get(k)) is type(v) and plan[k] == v for k, v in expected.items()),
            'fixed_P123_scope_changed')
    sources = ('scripts/rolling_checkpoint_history.py', 'scripts/rolling_checkpoint_inference.py',
        'scripts/run_whole_task_rolling_checkpoint_cell.py', 'scripts/audit_rolling_checkpoint_trace.py',
        'scripts/single_checkpoint_inference.py', 'scripts/inline_checkpoint_execution.py',
        'reports/P122_comparison.json', 'reports/P122_server_session.json', 'docs/P122_findings.md',
        'reports/P120_pair_controls.json', 'reports/rolling_checkpoint_core_preparation_20261025.json',
        'docs/experiments/P123_whole_task_rolling_checkpoint.md')
    for name in sources:
        value = plan.get('source_sha256', {}).get(name)
        require(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value),
                'closed_predecessor_and_rolling_sources_must_be_bound')
    require(type(plan.get('predecessor_closure')) is dict and
            set(plan['predecessor_closure']) == {'audit_sha256', 'pipeline_status_sha256', 'server_final_sha256'}
            and all(type(v) is str and len(v) == 64 and all(c in '0123456789abcdef' for c in v)
                    for v in plan['predecessor_closure'].values()), 'closed_P122_binding_required')
    validate_base({**plan, 'experiment': 'P80', 'batch_id': 'P80_batch_v01',
        'max_cells': 8, 'max_model_calls': 640, 'max_reserved_tokens': 3600000,
        'server_max_lifetime_seconds': 21600, 'time_policies': ['measured', 'not_exposed'],
        'protocol_references': 'canonical_in_both_before_counting'})


def summarize(rows, errors):
    tasks = list(dict.fromkeys(r['task_id'] for r in rows))
    actual = [(r['task_id'], r['checkpoint_policy']) for r in rows]
    require(len(tasks) == 4 and len(actual) == 12
            and set(actual) == {(t, p) for t in tasks for p in POLICIES},
            'all_twelve_P123_slots_required')
    cells = {(r['task_id'], r['checkpoint_policy']): r for r in rows}
    complete = not errors and all(r['record_status'] == 'evaluated' and type(r['success']) is bool
        and r['unknown_usage_calls'] == 0 and type(r['known_total_tokens']) is int
        and r['known_total_tokens'] >= 0 for r in rows)
    common = [t for t in tasks if all(cells[t,p]['record_status']=='evaluated'
                                    and cells[t,p]['success'] is True for p in POLICIES)]
    totals = {p: sum(cells[t,p]['known_total_tokens'] for t in tasks) if complete else None for p in POLICIES}
    shared = {p: sum(cells[t,p]['known_total_tokens'] for t in common) if complete else None for p in POLICIES}
    comparisons = []
    for baseline in POLICIES[:2]:
        pairs = []
        for task in tasks:
            a, b = cells[task,baseline], cells[task,'rolling_inline']
            known = all(r['record_status']=='evaluated' and r['unknown_usage_calls']==0
                        and type(r['known_total_tokens']) is int for r in (a,b))
            pairs.append({'task_id': task, 'baseline': baseline,
                'baseline_success': a['success'], 'rolling_inline_success': b['success'],
                'success_lost': a['success'] is True and b['success'] is False,
                'both_successful': a['success'] is True and b['success'] is True,
                'rolling_inline_minus_baseline_tokens': b['known_total_tokens']-a['known_total_tokens'] if known else None})
        lower = complete and totals['rolling_inline'] < totals[baseline]
        common_lower = complete and bool(common) and shared['rolling_inline'] < shared[baseline]
        no_loss = complete and not any(p['success_lost'] for p in pairs)
        comparisons.append({'baseline': baseline, 'paired_results': pairs,
            'no_per_task_success_loss': no_loss, 'lower_all_four_tokens': lower,
            'lower_all_three_common_success_tokens': common_lower,
            'comparison_gate_met': bool(no_loss and lower and common_lower)})
    repeated = {p: any(type(cells[t,p].get('checkpoint_installations')) is int
                       and cells[t,p]['checkpoint_installations'] >= 2 for t in tasks)
                for p in POLICIES[1:]}
    return {'planned_rows': 12, 'independent_tasks': 4, 'repetitions': 1,
        'all_twelve_complete_with_known_usage': complete,
        'success_counts': {p: sum(cells[t,p]['success'] is True for t in tasks) for p in POLICIES},
        'total_tokens_by_policy': totals, 'common_success_tasks': common,
        'common_success_tokens_by_policy': shared, 'comparisons': comparisons,
        'repeated_control_exercised': repeated,
        'development_gate_met': bool(complete and all(repeated.values())
                                     and all(c['comparison_gate_met'] for c in comparisons)),
        'all_summary_and_agent_costs_included': True, 'previous_missing_slots_filled': False,
        'novel_method_claim': False, 'general_quality_preservation_claim': False,
        'interpretation': 'A single new three-condition cohort on four known tasks. Both rolling policies must '
            'exercise repeated installation. Required inline must preserve each baseline success and lower '
            'whole-job tokens against both baselines, on all four and on tasks successful in all three. '
            'Different schedules, schema, summary allocation and later actions remain confounded. '
            'No unseen-task, noninferiority, semantic fidelity or novelty claim follows.'}
