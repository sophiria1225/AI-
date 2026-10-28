"""Fresh P148 identities for the fixed four-task TR vs UPDATE_INDEXED pair."""
from whole_task_state_update_p144 import (
    ERROR_POLICY, TASKS, cell_id as original_cell_id, worker_config as original_worker_config,
)
from receipt_reasoning_history import require

MODES=('threshold_recursive','threshold_delta_update')
ARM_LABELS=dict(zip(MODES,('TR','UPDATE_INDEXED')))


def fixed_fields():
    return dict(phase='budget_observation_connection',experiment='P148',batch_id='P148_batch_v01',
        object_timing_modes=list(MODES),checkpoint_representation_modes=list(MODES),
        comparison_arm_labels=ARM_LABELS,update_transport='schema_indexed_bounded',
        candidate_selection_from_results=False,candidate_for_whole_task='schema_indexed_bounded',
        required_predecessor_phase='P147',required_P147_owned_server_stopped=True,
        required_P147_probe_preflight_pass=True,max_probe_model_calls=0,max_probe_reserved_tokens=0,
        probe_call_timeout_seconds=480,max_probe_environment_api_calls=0,max_probe_evaluator_calls=0,
        model_seed=357,world_seed=42,max_calls=80,max_total_tokens=450000,max_output_tokens=4096,
        max_wall_seconds=1800,max_setup_seconds=60,max_cleanup_seconds=60,
        max_idle_wait_seconds=30,max_evaluation_seconds=60,cell_admission_seconds=2160,preflight_timeout_seconds=300,
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
        server_max_lifetime_seconds=21600,batch_timeout_seconds=17280,pipeline_timeout_seconds=21900,
        operational_model_deadline_jst='2026-10-29T11:00:00+09:00',
        operational_deadline_is_not_a_user_completion_promise=True,
        primary_comparison=list(MODES),additional_controls=[],
        fixed_comparisons=[[MODES[0],MODES[1],'indexed_update_vs_recursive']],
        primary_question='fixed_new_seed_replication_of_indexed_update_vs_recursive',
        overall_development_requires_all_twelve_known_usage=False,
        overall_development_requires_all_eight_known_usage=True,
        per_comparison_requires_all_eight_known_usage=True,
        scientific_adoption_evaluated=False,prior_results_pooled=False,
        inherited_P147_probe_evidence=True,new_probe_generations=0,
        result_dependent_stopping=False,model_seed_changes_after_launch=False,
        initial_actor_transport_unchanged=True,first_focus_transport_unchanged=True,
        recursive_transport_unchanged=True,host_update_parser_unchanged=True)


def validate_plan(plan):
    require(all(type(plan.get(k)) is type(v) and plan[k]==v for k,v in fixed_fields().items()),
        'fixed_P148_scope_changed')
    require(not any(k in plan for k in ('deadline_jst','reporting_deadline_jst')),
        'no_new_user_deadline_or_stale_P144_deadline')
    tasks=plan.get('known_tasks')
    require(type(tasks) is list and len(tasks)==4 and
        tuple(t.get('task_id') for t in tasks)==TASKS and
        [t.get('source_run') for t in tasks]==[f'P29_{n:02d}_CODE' for n in range(1,5)],
        'fixed_four_P148_known_tasks_required')
    require(plan.get('schedule')==[dict(task_slot=n,mode=m,run_id=cell_id(n,m))
        for n,m in run_order()], 'fixed_eight_P148_schedule_required')


def run_order():
    return [(n,m) for n in range(1,5) for m in (MODES if n%2 else MODES[::-1])]


def cell_id(number,mode):
    require(type(number) is int and number in range(1,5) and mode in MODES,
        'fixed_P148_four_task_pair_required')
    return f'BOC_P148_{number:02d}_{ARM_LABELS[mode]}'


def worker_config(original,plan,task_id,arm,run_id,object_timing_mode):
    validate_plan(plan)
    require(task_id in TASKS and arm==ERROR_POLICY,'fixed_P148_task_and_error_policy_required')
    number=TASKS.index(task_id)+1
    require(run_id==cell_id(number,object_timing_mode),'fixed_P148_run_identity_required')
    fixed=dict(model_seed=357,world_seed=42,max_calls=80,max_total_tokens=450000,
        max_wall_seconds=1800,max_setup_seconds=60,max_cleanup_seconds=60,
        automatic_retries=0,reserved_scenarios_read=0)
    require(all(type(plan.get(k)) is type(v) and plan[k]==v for k,v in fixed.items()),
        'unchanged_P148_pair_scientific_budgets_required')
    # The frozen constructor uses the legacy ID only for validation, and never
    # returns it in a model input or configuration. New storage IDs stay P148.
    config=original_worker_config(original,plan,task_id,arm,
        original_cell_id(number,object_timing_mode),object_timing_mode)
    require('run_id' not in config,'legacy_run_identity_must_not_escape_constructor')
    config.update(phase='P148',experiment='P148',comparison_arm=ARM_LABELS[object_timing_mode],
        update_transport='schema_indexed_bounded' if object_timing_mode==MODES[1] else 'native_unlimited',
        actor_reasoning_budget_tokens=-1,first_focus_reasoning_budget_tokens=-1,
        update_focus_reasoning_budget_tokens=2048 if object_timing_mode==MODES[1] else -1)
    return config
