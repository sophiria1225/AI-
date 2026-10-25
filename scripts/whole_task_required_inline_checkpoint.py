"""P120 prospective ordinary separate/required-inline checkpoint comparison helpers.

No batch is launched here. The P119 implementation and results stay immutable.
This comparison changes checkpoint scheduling and transport together; it does
not isolate a semantic guard or establish novelty for call fusion.
"""
from late_clock_comparison import initial_conversation
from budget_observation import notification
from budget_visibility_comparison import ERROR_POLICY, validate_plan as validate_base
from audit_budget_visibility_comparison import development_gate
from receipt_reasoning_history import require
from single_checkpoint_history import TRIGGER_INPUT_TOKENS, RECENT_TURNS, MAX_SUMMARY_CHARACTERS
from whole_task_tool_choice import worker_config as original_worker_config

POLICIES = ('single_checkpoint', 'inline_checkpoint')


def run_order():
    return [(number, policy) for number in range(1, 5)
            for policy in (POLICIES if number % 2 else POLICIES[::-1])]


def cell_id(number, policy):
    require(type(number) is int and number in range(1, 5) and policy in POLICIES,
            'outside_fixed_P120_comparison')
    return f'BOC_P120_{number:02d}_{policy.upper()}'


def worker_config(original, plan, task_id, arm, run_id, checkpoint_policy):
    require(plan.get('experiment') == 'P120' and run_id.startswith('BOC_P120_'),
            'new_P120_plan_and_identity_required')
    require(checkpoint_policy in POLICIES, 'explicit_P120_checkpoint_policy_required')
    config = original_worker_config(original, plan, task_id, arm, run_id, 'auto')
    require(config['draft_temperature'] == 0.7, 'fixed_summary_temperature_required')
    require(plan.get('inline_checkpoint_requirement') == 'required_when_run_python',
            'fixed_required_checkpoint_policy_required')
    config.update(checkpoint_policy=checkpoint_policy, read_views_enabled=False,
                  inline_checkpoint_requirement='required_when_run_python'
                  if checkpoint_policy == 'inline_checkpoint' else 'not_applicable')
    return config


def config_for(original, plan, task_id, policy):
    number = [t['task_id'] for t in plan['known_tasks']].index(task_id) + 1
    return worker_config(original, plan, task_id, ERROR_POLICY, cell_id(number, policy), policy)


def make_notification(messages, state, policy, *, wall_limit):
    require(policy in POLICIES, 'fixed_P120_checkpoint_policy_required')
    return notification(messages, state, 'not_exposed')


def validate_plan(plan):
    expected = dict(experiment='P120', batch_id='P120_batch_v01',
        checkpoint_policies=list(POLICIES), tool_choice='auto', reasoning_budget_tokens=-1,
        time_visibility='not_exposed', repetitions=1, max_cells=8, max_model_calls=640,
        max_reserved_tokens=3600000, max_reserved_environment_api_requests=800,
        server_max_lifetime_seconds=21600, fresh_seed_search=False, threshold_search=False,
        new_task_requirements_read=0, protocol_references='source_protocol_fields_before_rendering',
        primary_question='ordinary_required_inline_versus_separate_checkpoint_whole_task_cost',
        required_closed_diagnostic='reports/P119_pair_controls.json',
        required_predecessor_phase='P119', read_views_enabled=False,
        trigger_input_tokens=TRIGGER_INPUT_TOKENS, retained_recent_turns=RECENT_TURNS,
        max_summary_characters=MAX_SUMMARY_CHARACTERS, max_summary_opportunities_per_cell=1,
        max_summary_calls_in_batch=4, shared_model_call_and_token_budget=True,
        summary_output_cap=4096, summary_temperature=0.7,
        invalid_summary_policy='keep_original_no_retry_charge_known_cost',
        unknown_summary_usage_policy='stop_without_retry',
        inline_metadata_policy='required_exactly_one_run_python_old_closed_prefix_only',
        inline_checkpoint_requirement='required_when_run_python',
        tool_schema_required_scope='one_run_python_offer_only',
        minimum_inline_checkpoint_installations=1,
        inline_transport_display='remove_metadata_from_both_next_input_candidates_preserve_raw_archive',
        inline_installation='after_current_turn_closes_and_next_input_is_strictly_shorter',
        same_call_results_summarized=False, separate_semantic_judge=False,
        no_previous_replacement_or_retry=True, novel_method_claim=False)
    require(all(type(plan.get(k)) is type(v) and plan[k] == v for k, v in expected.items()),
            'fixed_P120_scope_changed')
    for name in ('scripts/required_inline_checkpoint_history.py', 'scripts/required_inline_checkpoint_inference.py',
                 'scripts/inline_checkpoint_history.py', 'scripts/inline_checkpoint_inference.py',
                 'scripts/inline_checkpoint_protocol.py', 'scripts/inline_checkpoint_execution.py',
                 'scripts/audit_required_inline_checkpoint_trace.py', 'reports/P119_comparison.json',
                 'reports/P119_server_session.json', 'reports/P119_pair_controls.json',
                 'docs/experiments/P120_whole_task_required_inline_checkpoint.md'):
        value = plan.get('source_sha256', {}).get(name)
        require(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value),
                'bound_inline_and_predecessor_sources_required')
    validate_base({**plan, 'experiment': 'P80', 'batch_id': 'P80_batch_v01',
                   'time_policies': ['measured', 'not_exposed'],
                   'protocol_references': 'canonical_in_both_before_counting'})


def summarize(rows, errors):
    tasks = list(dict.fromkeys(row['task_id'] for row in rows))
    actual = [(row['task_id'], row['checkpoint_policy']) for row in rows]
    require(len(tasks) == 4 and len(actual) == 8 and set(actual) == {(t, p) for t in tasks for p in POLICIES},
            'all_eight_P120_slots_required')
    aliases = {'single_checkpoint': 'measured', 'inline_checkpoint': 'not_exposed'}
    common = development_gate([{**r, 'time_visibility': aliases[r['checkpoint_policy']]} for r in rows], errors)

    def rename(value):
        if isinstance(value, dict):
            return {k.replace('not_exposed', 'inline_checkpoint').replace('measured', 'single_checkpoint'): rename(v)
                    for k, v in value.items()}
        if isinstance(value, list):
            return [rename(v) for v in value]
        return value

    result = rename(common)
    complete = result['all_eight_complete_with_known_usage']
    paired = sum(p['inline_checkpoint_minus_single_checkpoint_tokens'] for p in result['paired_results']
                 if p['both_successful']) if complete else None
    inline_rows = [row for row in rows if row['checkpoint_policy'] == 'inline_checkpoint']
    installed = sum(row.get('checkpoint_installed') is True for row in inline_rows)
    offered = sum(bool(call.get('inline_offered')) for row in inline_rows
                  for call in row.get('request_checks', []))
    result.update(paired_successful_token_difference=paired,
        development_gate_met=bool(result['development_gate_met'] and result['paired_successful_tasks'] > 0
                                  and paired is not None and paired < 0 and installed >= 1),
        inline_checkpoint_offer_calls=offered, inline_checkpoint_installations=installed,
        required_inline_control_exercised=installed >= 1,
        planned_rows=8, independent_tasks=4, repetitions=1,
        all_checkpoint_prompt_schema_output_and_agent_costs_included=True,
        previous_missing_slots_filled=False, novel_method_claim=False,
        general_quality_preservation_claim=False,
        interpretation='A new paired comparison of ordinary separate and required inline checkpoints on four known development tasks. '
            'Scheduling, schema, instructions, output allocation and subsequent actions may differ. '
            'It does not isolate a semantic guard or identify cost savings with eliminated summary input.')
    return result
