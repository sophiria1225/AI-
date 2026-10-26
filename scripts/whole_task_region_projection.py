"""P127 finite preparation: shared explicit joined fields and rolling separate.

No plan generation or launch happens on import. Prior results remain separate.
"""
import hashlib
from region_projection_runtime import POLICIES, EXPLICIT_FIELD_GUIDE
from audit_budget_visibility_comparison import development_gate
from budget_observation import notification
from budget_visibility_comparison import ERROR_POLICY
from compact_api_receipts import RECEIPT_GUIDE
from late_clock_comparison import initial_conversation as base_conversation
from protocol_stable_history import StableReferenceConversation
from receipt_reasoning_history import require
from single_checkpoint_history import TRIGGER_INPUT_TOKENS, RECENT_TURNS, MAX_SUMMARY_CHARACTERS
from rolling_checkpoint_history import MAX_OPPORTUNITIES, MIN_NEW_CLOSED_TURNS
from whole_task_tool_choice import worker_config as base_worker_config

PLAN = 'configs/P127_whole_task_region_projection_v01.json'
PREFLIGHT = 'reports/P127_initial_checks.json'
ACTIVATION = 'reports/P127_activation_v01.json'
API_BUDGETS = (160, 80, 80, 120)
PREDECESSOR_REPORT = 'reports/P125_comparison.json'
REPLAY_REPORT = 'reports/P126_region_projection_replay.json'


def run_order():
    return [(number, policy) for number in range(1, 5)
            for policy in (POLICIES if number % 2 else POLICIES[::-1])]


def cell_id(number, policy):
    require(type(number) is int and number in range(1, 5) and policy in POLICIES,
            'outside_fixed_P127_comparison')
    return f'BOC_P127_{number:02d}_{policy.upper()}'


def initial_conversation(original, public_task):
    previous = base_conversation(original, public_task)
    return StableReferenceConversation(previous.messages()[0]['content'] + RECEIPT_GUIDE
                                       + EXPLICIT_FIELD_GUIDE, public_task)


def worker_config(original, plan, task_id, arm, run_id, projection_policy):
    require(projection_policy in POLICIES and arm == ERROR_POLICY,
            'explicit_P127_projection_and_error_policies_required')
    number = [item['task_id'] for item in plan['known_tasks']].index(task_id) + 1
    require(run_id == cell_id(number, projection_policy), 'fixed_P127_cell_identity_required')
    config = base_worker_config(original, plan, task_id, arm, run_id, 'auto')
    require(config['draft_temperature'] == 0.7, 'fixed_summary_temperature_required')
    require(plan.get('api_budget_by_task_slot') == list(API_BUDGETS),
            'prespecified_common_P127_API_budgets_required')
    config.update(checkpoint_policy='rolling_separate', read_views_enabled=False,
                  projection_policy=projection_policy, receipt_format='lossless_columns_rows_v1',
                  max_api_requests=API_BUDGETS[number - 1],
                  rolling_checkpoint_max_opportunities=MAX_OPPORTUNITIES,
                  rolling_min_fresh_turns=MIN_NEW_CLOSED_TURNS,
                  inline_checkpoint_requirement='not_applicable',
                  explicit_joined_fields_enabled=True)
    return config


def config_for(original, plan, task_id, policy):
    number = [item['task_id'] for item in plan['known_tasks']].index(task_id) + 1
    return worker_config(original, plan, task_id, ERROR_POLICY, cell_id(number, policy), policy)


def make_notification(messages, state, policy, *, wall_limit):
    require(policy in POLICIES, 'fixed_P127_projection_policy_required')
    return notification(messages, state, 'not_exposed')


def fixed_fields():
    return dict(phase='budget_observation_connection', experiment='P127', batch_id='P127_batch_v01',
        projection_policies=list(POLICIES), source_plan='configs/P29_stateful_code_v01.json',
        source_runs=[f'P29_{n:02d}_CODE' for n in range(1, 5)], model_seed=157, world_seed=42,
        max_calls=80, max_total_tokens=450000, max_wall_seconds=1800,
        max_setup_seconds=120, max_cleanup_seconds=180, max_idle_wait_seconds=60,
        max_evaluation_seconds=180, server_max_lifetime_seconds=21600,
        max_cells=8, max_model_calls=640, max_reserved_tokens=3600000,
        max_reserved_environment_api_requests=880, max_evaluator_calls=8,
        api_budget_by_task_slot=list(API_BUDGETS),
        automatic_retries=0, reserved_scenarios_read=0, repetitions=1,
        history_policy='all_returned_reasoning_from_start', catalog_policy='public_names',
        tool_choice='auto', reasoning_budget_tokens=-1, time_visibility='not_exposed',
        error_policy=ERROR_POLICY, checkpoint_policy='rolling_separate',
        trigger_input_tokens=TRIGGER_INPUT_TOKENS, retained_recent_turns=RECENT_TURNS,
        max_summary_characters=MAX_SUMMARY_CHARACTERS,
        max_summary_opportunities_per_cell=MAX_OPPORTUNITIES,
        rolling_checkpoint_max_opportunities=MAX_OPPORTUNITIES,
        rolling_min_fresh_turns=MIN_NEW_CLOSED_TURNS,
        inline_checkpoint_requirement='not_applicable',
        max_summary_calls_in_batch=8 * MAX_OPPORTUNITIES, summary_output_cap=4096, summary_temperature=0.7,
        shared_model_call_and_token_budget=True, read_views_enabled=False,
        same_ordinary_complete_cache=True, same_compact_receipts=True, same_public_schema_feedback=True,
        same_joined_authority=True, same_explicit_field_capability=True, same_explicit_field_guide=True,
        receipt_guide_sha256=hashlib.sha256(RECEIPT_GUIDE.encode()).hexdigest(),
        explicit_field_guide_sha256=hashlib.sha256(EXPLICIT_FIELD_GUIDE.encode()).hexdigest(),
        live_identifier_guard=False, fresh_seed_search=False, threshold_search=False,
        adaptive_extension=False, new_task_requirements_read=0, novel_method_claim=False,
        required_closed_predecessor='P125', required_replay='P126',
        minimum_projection_hits_on_common_success=1, require_no_projection_contract_failure=True)


def validate_plan(plan):
    fixed = fixed_fields()
    require(all(type(plan.get(k)) is type(value) and plan[k] == value for k, value in fixed.items()),
            'fixed_P127_scope_changed')
    tasks = plan.get('known_tasks')
    require(type(tasks) is list and len(tasks) == 4
            and [row.get('source_run') for row in tasks] == fixed['source_runs']
            and len({row.get('task_id') for row in tasks}) == 4,
            'all_four_known_tasks_required')
    for name in ('scripts/region_field_projection.py', 'scripts/region_projection_runtime.py',
                 'scripts/demand_joined_read_adapter.py', 'scripts/joined_public_read_views.py',
                 'scripts/compact_api_receipts.py', 'scripts/rolling_checkpoint_inference.py',
                 'scripts/audit_rolling_checkpoint_trace.py',
                 'docs/experiments/P127_whole_task_region_projection.md',
                 REPLAY_REPORT, PREDECESSOR_REPORT, 'reports/P125_server_session.json',
                 'reports/P123_comparison.json', 'reports/P123_server_session.json'):
        value = plan.get('source_sha256', {}).get(name)
        require(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value),
                'bound_P127_sources_and_predecessors_required')


def summarize(rows, errors):
    tasks = list(dict.fromkeys(row['task_id'] for row in rows))
    actual = [(row['task_id'], row['projection_policy']) for row in rows]
    require(len(tasks) == 4 and len(actual) == 8
            and set(actual) == {(task, policy) for task in tasks for policy in POLICIES},
            'all_eight_P127_slots_required')
    aliases = dict(zip(POLICIES, ('measured', 'not_exposed')))
    common = development_gate([{**row, 'time_visibility': aliases[row['projection_policy']]}
                               for row in rows], errors)

    def rename(value):
        if isinstance(value, dict):
            return {key.replace('not_exposed', 'automatic_region_joined_fields').replace('measured', 'explicit_joined_fields'):
                    rename(item) for key, item in value.items()}
        if isinstance(value, list):
            return [rename(item) for item in value]
        return value

    result = rename(common)
    complete = result['all_eight_complete_with_known_usage']
    pairs = result['paired_results']
    delta_key = 'automatic_region_joined_fields_minus_explicit_joined_fields_tokens'
    paired_delta = sum(pair[delta_key] for pair in pairs if pair['both_successful']) if complete else None
    common_success = {pair['task_id'] for pair in pairs if pair['both_successful']}
    hit_values = [row.get('projection_hits') for row in rows
                  if row['projection_policy'] == POLICIES[1] and row['task_id'] in common_success]
    hits = sum(hit_values) if all(type(value) is int and value >= 0 for value in hit_values) else None
    contract_flags_known = all(type(row.get('projection_contract_failed')) is bool for row in rows)
    contract_failures = sum(row['projection_contract_failed'] for row in rows) if contract_flags_known else None
    result.update(paired_successful_token_difference=paired_delta,
        both_failed_token_difference=sum(pair[delta_key] for pair in pairs
            if pair['both_evaluated'] and not pair['explicit_joined_fields_success']
            and not pair['automatic_region_joined_fields_success']) if complete else None,
        projection_hits_on_common_success=hits,
        projection_contract_failure_cells=contract_failures,
        mechanism_contracts_intact=contract_flags_known and contract_failures == 0,
        development_gate_met=bool(result['development_gate_met'] and common_success
            and paired_delta is not None and paired_delta < 0 and hits is not None and hits >= 1
            and contract_flags_known and contract_failures == 0),
        planned_rows=8, independent_tasks=4, repetitions=1, model_seed=157,
        summary_failure_and_recovery_costs_included=True, prior_results_pooled=False,
        general_quality_preservation_claim=False, novel_method_claim=False,
        interpretation='Known-task development comparison. Both all-task and common-success whole-job '
            'tokens must decrease, with no baseline success lost and actual projection on a common '
            'success. API savings, formatting bytes and cheap failures are not token-goal success.')
    return result
