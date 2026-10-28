"""Fresh P146 identities for the fixed four-task TR vs UPDATE_SCHEMA pair."""
from whole_task_state_update_p144 import (
    ERROR_POLICY, TASKS, cell_id as original_cell_id, worker_config as original_worker_config,
)
from receipt_reasoning_history import require

MODES=('threshold_recursive','threshold_delta_update')
ARM_LABELS=dict(zip(MODES,('TR','UPDATE_SCHEMA')))


def fixed_fields():
    return dict(phase='budget_observation_connection',experiment='P146',batch_id='P146_batch_v01',
        object_timing_modes=list(MODES),checkpoint_representation_modes=list(MODES),
        comparison_arm_labels=ARM_LABELS,update_transport='schema_bounded',
        candidate_selection_from_results=False,required_predecessor_phase='P145',
        required_P145_mechanism_preflight_pass=True,required_P145_owned_server_stopped=True,
        model_seed=257,world_seed=42,max_calls=80,max_total_tokens=450000,max_output_tokens=4096,
        max_wall_seconds=1800,max_setup_seconds=60,max_cleanup_seconds=60,
        max_idle_wait_seconds=30,max_evaluation_seconds=60,
        max_cells=8,max_model_calls=640,max_reserved_tokens=3600000,
        max_reserved_environment_api_requests=800,max_evaluator_calls=8,max_summary_calls_in_batch=16,
        api_budget_by_task_slot=[160,80,80,80],trigger_input_tokens=8192,
        rolling_checkpoint_max_opportunities=2,rolling_min_fresh_turns=3,
        actor_reasoning_budget_tokens=-1,first_focus_reasoning_budget_tokens=-1,
        update_focus_reasoning_budget_tokens=2048,reasoning_budget_tokens=-1,
        history_policy='all_returned_reasoning_from_start',time_visibility='not_exposed',
        automatic_retries=0,reserved_scenarios_read=0,fresh_seed_search=False,threshold_search=False,
        execution_order_randomized=False,execution_order_rotated_by_task=False,
        execution_order_balanced_by_task_parity=True,
        server_max_lifetime_seconds=18000,batch_timeout_seconds=16080,pipeline_timeout_seconds=18300,
        latest_launch_jst='2026-10-29T04:00:00+09:00',
        operational_latest_launch_is_not_a_user_deadline=True,
        primary_comparison=list(MODES),additional_controls=[],
        fixed_comparisons=[[MODES[0],MODES[1],'schema_update_vs_recursive']],
        primary_question='schema_bounded_state_update_vs_recursive_whole_job_utility',
        overall_development_requires_all_twelve_known_usage=False,
        overall_development_requires_all_eight_known_usage=True,
        per_comparison_requires_all_eight_known_usage=True,
        scientific_adoption_evaluated=False,prior_results_pooled=False,
        initial_actor_transport_unchanged=True,first_focus_transport_unchanged=True,
        recursive_transport_unchanged=True,host_update_parser_unchanged=True)


def validate_plan(plan):
    require(all(type(plan.get(k)) is type(v) and plan[k]==v for k,v in fixed_fields().items()),
        'fixed_P146_scope_changed')
    require(not any(k in plan for k in ('deadline_jst','reporting_deadline_jst')),
        'no_new_user_deadline_or_stale_P144_deadline')
    tasks=plan.get('known_tasks')
    require(type(tasks) is list and len(tasks)==4 and
        tuple(t.get('task_id') for t in tasks)==TASKS and
        [t.get('source_run') for t in tasks]==[f'P29_{n:02d}_CODE' for n in range(1,5)],
        'fixed_four_P146_known_tasks_required')


def run_order():
    return [(n,m) for n in range(1,5) for m in (MODES if n%2 else MODES[::-1])]


def cell_id(number,mode):
    require(type(number) is int and number in range(1,5) and mode in MODES,
        'fixed_P146_four_task_pair_required')
    return f'BOC_P146_{number:02d}_{ARM_LABELS[mode]}'


def worker_config(original,plan,task_id,arm,run_id,object_timing_mode):
    validate_plan(plan)
    require(task_id in TASKS and arm==ERROR_POLICY,'fixed_P146_task_and_error_policy_required')
    number=TASKS.index(task_id)+1
    require(run_id==cell_id(number,object_timing_mode),'fixed_P146_run_identity_required')
    fixed=dict(model_seed=257,world_seed=42,max_calls=80,max_total_tokens=450000,
        max_wall_seconds=1800,max_setup_seconds=60,max_cleanup_seconds=60,
        automatic_retries=0,reserved_scenarios_read=0)
    require(all(type(plan.get(k)) is type(v) and plan[k]==v for k,v in fixed.items()),
        'unchanged_P146_pair_scientific_budgets_required')
    # The frozen constructor uses the legacy ID only for validation, and never
    # returns it in a model input or configuration. New storage IDs stay P146.
    config=original_worker_config(original,plan,task_id,arm,
        original_cell_id(number,object_timing_mode),object_timing_mode)
    require('run_id' not in config,'legacy_run_identity_must_not_escape_constructor')
    config.update(phase='P146',experiment='P146',comparison_arm=ARM_LABELS[object_timing_mode],
        update_transport='schema_bounded' if object_timing_mode==MODES[1] else 'native_unlimited',
        actor_reasoning_budget_tokens=-1,first_focus_reasoning_budget_tokens=-1,
        update_focus_reasoning_budget_tokens=2048 if object_timing_mode==MODES[1] else -1)
    return config
