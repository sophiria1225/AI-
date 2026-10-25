"""P118: an ordinary bounded summary versus a contemporaneous full baseline."""
from budget_observation import notification
from budget_visibility_comparison import ERROR_POLICY, validate_plan as validate_base
from audit_budget_visibility_comparison import development_gate
from late_clock_comparison import initial_conversation
from receipt_reasoning_history import require
from single_checkpoint_history import TRIGGER_INPUT_TOKENS, RECENT_TURNS, MAX_SUMMARY_CHARACTERS
from single_checkpoint_inference import POLICIES
from whole_task_tool_choice import worker_config as original_worker_config


def run_order():
    return [(number, policy) for number in range(1, 5)
            for policy in (POLICIES if number % 2 else POLICIES[::-1])]


def cell_id(number, policy):
    require(type(number) is int and number in range(1, 5) and policy in POLICIES,
            'outside_fixed_P118_comparison')
    return f'BOC_P118_{number:02d}_{policy.upper()}'


def worker_config(original, plan, task_id, arm, run_id, checkpoint_policy):
    require(checkpoint_policy in POLICIES, 'explicit_P118_checkpoint_policy_required')
    config = original_worker_config(original, plan, task_id, arm, run_id, 'auto')
    require(config['draft_temperature'] == 0.7, 'fixed_summary_temperature_required')
    config.update(checkpoint_policy=checkpoint_policy, read_views_enabled=False)
    return config


def config_for(original, plan, task_id, policy):
    number = [t['task_id'] for t in plan['known_tasks']].index(task_id) + 1
    return worker_config(original, plan, task_id, ERROR_POLICY, cell_id(number, policy), policy)


def make_notification(messages, state, policy, *, wall_limit):
    require(policy in POLICIES, 'fixed_P118_checkpoint_policy_required')
    return notification(messages, state, 'not_exposed')


def validate_plan(plan):
    expected = dict(experiment='P118', batch_id='P118_batch_v01',
        checkpoint_policies=list(POLICIES), tool_choice='auto', reasoning_budget_tokens=-1,
        time_visibility='not_exposed', repetitions=1, max_cells=8, max_model_calls=640,
        max_reserved_tokens=3600000, max_reserved_environment_api_requests=800,
        server_max_lifetime_seconds=21600, fresh_seed_search=False, threshold_search=False,
        new_task_requirements_read=0, protocol_references='source_protocol_fields_before_rendering',
        primary_question='ordinary_single_checkpoint_including_shared_control_cost',
        required_closed_diagnostic='reports/P117_public_metadata_observations.json',
        required_predecessor_phase='P114', read_views_enabled=False,
        trigger_input_tokens=TRIGGER_INPUT_TOKENS, retained_recent_turns=RECENT_TURNS,
        max_summary_characters=MAX_SUMMARY_CHARACTERS, max_summary_opportunities_per_cell=1,
        max_summary_calls_in_batch=4, shared_model_call_and_token_budget=True,
        summary_output_cap=4096, summary_temperature=0.7,
        invalid_summary_policy='keep_original_no_retry_charge_known_cost',
        unknown_summary_usage_policy='stop_without_retry',
        no_previous_replacement_or_retry=True, novel_method_claim=False)
    require(all(type(plan.get(k)) is type(v) and plan[k] == v for k, v in expected.items()),
            'fixed_P118_scope_changed')
    for name in ('scripts/single_checkpoint_history.py', 'scripts/single_checkpoint_inference.py',
                 'reports/P114_comparison.json', 'reports/P114_server_session.json',
                 'reports/P117_public_metadata_observations.json',
                 'docs/P14_findings.md', 'docs/counterfactual_adaptation_prior_scope_20261025.md',
                 'docs/experiments/P118_whole_task_single_checkpoint.md'):
        value = plan.get('source_sha256', {}).get(name)
        require(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value),
                'bound_checkpoint_and_predecessor_sources_required')
    validate_base({**plan, 'experiment': 'P80', 'batch_id': 'P80_batch_v01',
                   'time_policies': ['measured', 'not_exposed'],
                   'protocol_references': 'canonical_in_both_before_counting'})


def summarize(rows, errors):
    tasks = list(dict.fromkeys(row['task_id'] for row in rows))
    actual = [(row['task_id'], row['checkpoint_policy']) for row in rows]
    require(len(tasks) == 4 and len(actual) == 8 and set(actual) == {(t, p) for t in tasks for p in POLICIES},
            'all_eight_P118_slots_required')
    aliases = {'full': 'measured', 'single_checkpoint': 'not_exposed'}
    common = development_gate([{**r, 'time_visibility': aliases[r['checkpoint_policy']]} for r in rows], errors)

    def rename(value):
        if isinstance(value, dict):
            return {k.replace('not_exposed', 'single_checkpoint').replace('measured', 'full'): rename(v)
                    for k, v in value.items()}
        if isinstance(value, list):
            return [rename(v) for v in value]
        return value

    result = rename(common)
    complete = result['all_eight_complete_with_known_usage']
    paired = sum(p['single_checkpoint_minus_full_tokens'] for p in result['paired_results']
                 if p['both_successful']) if complete else None
    result.update(paired_successful_token_difference=paired,
        development_gate_met=bool(result['development_gate_met'] and result['paired_successful_tasks'] > 0
                                  and paired is not None and paired < 0),
        planned_rows=8, independent_tasks=4, repetitions=1,
        summary_and_agent_costs_both_included=True, previous_missing_slots_filled=False,
        novel_method_claim=False, general_quality_preservation_claim=False,
        interpretation='A new paired comparison of two ordinary controls on four known development tasks. '
            'Both failure and summary costs count. The P111 failure of its adoption gate is unchanged; '
            'this is neither PAIR reproduction nor a novel compression method.')
    return result
