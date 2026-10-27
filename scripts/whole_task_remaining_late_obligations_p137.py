"""P137: four originally unrun P136 slots, separate descriptive follow-up.

This cohort never replaces P136 missing rows or establishes its six-slot gate.
"""
from copy import deepcopy
import json
from pathlib import Path

from budget_observation import notification
from budget_visibility_comparison import ERROR_POLICY
from late_clock_comparison import initial_conversation as original_conversation
from public_display import CODE_TOOLS
from receipt_reasoning_history import require
from whole_task_tool_choice import worker_config as original_worker_config

ROOT = Path(__file__).resolve().parents[1]
MODES = ('raw_anchor', 'ids_only', 'entity_fields')
SEEDS = (57, 157)
SLOTS = ((1, 1, 'entity_fields'), (2, 1, 'entity_fields'),
         (2, 1, 'ids_only'), (2, 1, 'raw_anchor'))
PLAN = 'configs/P137_remaining_late_obligations_v01.json'
PREFLIGHT = 'reports/P137_initial_checks.json'
ACTIVATION = 'reports/P137_activation_v01.json'
REQUIRED_SOURCES = (
    'configs/P123_whole_task_rolling_checkpoint_v01.json',
    'configs/P135_whole_task_observed_obligations_v01.json',
    'configs/P136_whole_task_late_obligations_v01.json',
    'scripts/inference_timeout_handler.py',
    'reports/P136_comparison.json', 'reports/P136_server_session.json',
    'scripts/late_obligation_monitor_p136.py', 'scripts/late_obligation_core_p136.py',
    'scripts/late_obligation_runtime_p136.py', 'scripts/late_obligation_inference_p136.py',
    'scripts/audit_late_obligation_trace_p136.py',
    'scripts/run_whole_task_remaining_late_obligations_cell_p137.py',
    'scripts/audit_whole_task_remaining_late_obligations_p137.py',
    'scripts/remaining_late_obligation_server_identity_p137.py',
    'scripts/serve_research_model_recovery.py', 'reports/P123_comparison.json',
    'reports/P135_comparison.json', 'reports/P135_server_session.json',
    'docs/experiments/P137_remaining_late_obligations.md',
    'scripts/whole_task_remaining_late_obligations_p137.py',
    'scripts/run_whole_task_remaining_late_obligations_p137.py',
    'scripts/prepare_whole_task_remaining_late_obligations_p137.py',
    'scripts/run_whole_task_remaining_late_obligations_pipeline_p137.py',
    'scripts/inspect_whole_task_remaining_late_obligations_session_p137.py',
    'scripts/build_remaining_late_obligations_summary_p137.py',
    'tests/test_whole_task_remaining_late_obligations_p137_reporting.py',
)


def run_order():
    return list(SLOTS)


def modes_for_replication(replication):
    require(type(replication) is int and replication in (1, 2), 'fixed_P137_replication_required')
    return tuple(mode for rep, _, mode in SLOTS if rep == replication)


def cell_id(replication, number, mode):
    require(type(replication) is int and replication in (1, 2)
        and type(number) is int and number == 1 and (replication, number, mode) in SLOTS,
        'outside_fixed_P137_comparison')
    return f'BOC_P137_R{replication:02d}_{number:02d}_{mode.upper()}'


def worker_config(original, plan, task_id, arm, run_id, obligation_mode, replication):
    require(run_id == cell_id(replication, 1, obligation_mode), 'fixed_P137_cell_required')
    config = original_worker_config(original, {**plan, 'model_seed': SEEDS[replication-1]},
                                   task_id, arm, run_id, 'auto')
    require(config['max_api_requests'] == 80 and config['draft_temperature'] == 0.7,
            'P123_CSV_API_and_summary_limits_required')
    config.update(checkpoint_policy='rolling_separate', read_views_enabled=False,
        inline_checkpoint_requirement='not_applicable', rolling_checkpoint_max_opportunities=3,
        rolling_min_fresh_turns=3, obligation_mode=obligation_mode, run_id=run_id,
        replication=replication, model_seed=SEEDS[replication-1])
    return config


def config_for(original, plan, task_id, mode, replication):
    return worker_config(original, plan, task_id, ERROR_POLICY,
                         cell_id(replication, 1, mode), mode, replication)


def initial_conversation(original, public_task, mode):
    require(mode in MODES, 'fixed_P137_obligation_mode_required')
    return original_conversation(original, public_task)


def tools_for(mode):
    require(mode in MODES, 'fixed_P137_obligation_mode_required')
    return deepcopy(CODE_TOOLS)


def make_notification(messages, state, mode, *, wall_limit):
    require(mode in MODES, 'fixed_P137_obligation_mode_required')
    return notification(messages, state, 'not_exposed')


def fixed_fields():
    prior = json.loads((ROOT / 'configs/P123_whole_task_rolling_checkpoint_v01.json').read_text())
    keys = ('phase', 'source_plan', 'max_calls', 'max_total_tokens', 'max_wall_seconds',
        'max_setup_seconds', 'max_cleanup_seconds', 'max_idle_wait_seconds', 'max_evaluation_seconds',
        'world_seed', 'reserved_scenarios_read', 'history_policy', 'catalog_policy', 'automatic_retries',
        'error_policy', 'protocol_references', 'reasoning_budget_tokens', 'time_visibility',
        'fresh_seed_search', 'threshold_search', 'new_task_requirements_read',
        'shared_model_call_and_token_budget', 'summary_output_cap', 'summary_temperature',
        'unknown_summary_usage_policy', 'same_call_results_summarized', 'separate_semantic_judge',
        'no_previous_replacement_or_retry', 'public_runtime_sha256', 'read_views_enabled',
        'trigger_input_tokens', 'retained_recent_turns', 'max_summary_characters', 'tool_choice',
        'rolling_checkpoint_max_opportunities', 'rolling_min_fresh_turns', 'invalid_summary_policy')
    value = {key: deepcopy(prior[key]) for key in keys}
    value.update(experiment='P137', batch_id='P137_batch_v01', source_runs=['P29_04_CODE'],
        obligation_modes=list(MODES), checkpoint_policy='rolling_separate',
        inline_checkpoint_requirement='not_applicable', model_seeds=list(SEEDS), repetitions=2,
        max_cells=4, max_model_calls=320, max_reserved_tokens=1800000,
        max_reserved_environment_api_requests=320, max_evaluator_calls=4,
        max_summary_calls_in_batch=12, server_max_lifetime_seconds=14400,
        batch_max_seconds=12000, outer_max_seconds=15600,
        latest_start_jst='2026-10-27T13:40:00+09:00',
        deadline_jst='2026-10-27T18:00:00+09:00', api_budget_by_task_slot=[80],
        primary_comparison=['ids_only', 'entity_fields'],
        secondary_comparison=['raw_anchor', 'entity_fields'],
        raw_anchor_P123_interface_preserved=True, all_initial_capabilities_identical=True, main_pair_capabilities_identical=True,
        common_observer_and_checkpoint_capture=True, notice_json_byte_limit=2048,
        maximum_displayed_entities=16, same_ID_selector_and_row_count=True,
        query_interface_exposed=False, initial_guide_added=False,
        run_scoped_handle_exposed=False, automatic_environment_API_calls=0,
        automatic_value_writes=False, official_completion_only=True,
        payback_enabled=False, server_predict_time_limit_added=False,
        client_terminal_grace_added=False, require_P136_closed_collection_before_launch=True,
        followup_of='P136_incomplete_worker_and_unrun_slots',
        fixed_slots=[list(slot) for slot in SLOTS],
        selection_rule='originally_not_run_four_slots_only_not_task_outcomes',
        prior_P136_rows_replaced=False, prior_results_pooled=False,
        original_P136_gate_replaced=False, scientific_adoption_evaluated=False,
        timeout_handler_registered_at_worker_entry=True,
        worker_process_exit_status_persisted=True,
        prior_closed_results_used_for_design=['P123','P127','P132','P133','P135','P136'],
        user_continuation_authorization='2026-10-27_persistent_user_experiment_instruction',
        past_results_seen_before_design=True, all_original_failures_preserved=True,
        novel_method_claim=False, primary_question='field_association_beyond_same_ID_reexposure_after_checkpoint')
    return value


def validate_plan(plan):
    require(all(type(plan.get(key)) is type(value) and plan[key] == value
                for key, value in fixed_fields().items()), 'fixed_P137_scope_changed')
    tasks = plan.get('known_tasks')
    require(type(tasks) is list and len(tasks) == 1 and tasks[0].get('source_run') == 'P29_04_CODE'
        and type(tasks[0].get('task_id')) is str, 'only_known_CSV_task_required')
    mapping = plan.get('source_sha256')
    require(type(mapping) is dict and bool(mapping), 'P137_source_mapping_required')
    for name, expected in mapping.items():
        require(type(name) is str and bool(name) and not Path(name).is_absolute()
            and '..' not in Path(name).parts and '\\' not in name and str(Path(name)) == name
            and type(expected) is str and len(expected) == 64
            and all(c in '0123456789abcdef' for c in expected), 'safe_P137_source_binding_required')
    for name in REQUIRED_SOURCES:
        value = plan.get('source_sha256', {}).get(name)
        require(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value),
                'bound_P137_sources_required')



def _comparison(rows, baseline):
    rep, seed = 2, 157
    before, after = [next(row for row in rows if row['replication'] == rep
                    and row['obligation_mode'] == mode) for mode in (baseline, 'entity_fields')]
    ready = all(row['record_status'] == 'evaluated' and type(row.get('success')) is bool
                for row in (before, after))
    known = ready and all(type(row.get('unknown_usage_calls')) is int and row['unknown_usage_calls'] == 0
        and type(row.get('known_total_tokens')) is int and row['known_total_tokens'] >= 0 for row in (before, after))
    transition = ('not_both_evaluated' if not ready else 'common_success' if before['success'] and after['success']
        else 'quality_loss' if before['success'] else 'quality_gain' if after['success'] else 'both_failed')
    pair = dict(replication=rep, model_seed=seed, baseline_success=before.get('success'),
        candidate_success=after.get('success'), both_evaluated=ready, both_usage_known=known,
        both_successful=transition == 'common_success' if ready else None,
        success_lost=transition == 'quality_loss' if ready else None, quality_transition=transition,
        candidate_minus_baseline_tokens=after['known_total_tokens']-before['known_total_tokens'] if known else None)
    common = transition == 'common_success' if ready else False
    return dict(baseline=baseline, candidate='entity_fields', scope='same_cohort_seed157_only',
        paired_results=[pair], comparable_model_seeds=[157], both_pairs_evaluated=ready,
        both_pairs_usage_known=known, paired_success_losses=int(pair['success_lost']) if ready else None,
        paired_successful_task_seed_pairs=int(common) if ready else None,
        candidate_minus_baseline_whole_task_tokens=pair['candidate_minus_baseline_tokens'],
        paired_successful_token_difference=pair['candidate_minus_baseline_tokens'] if known and common else None,
        costs_by_quality_transition={name: dict(pairs=int(transition==name),
            candidate_minus_baseline_tokens=(pair['candidate_minus_baseline_tokens'] if transition==name else 0) if known else None)
            for name in ('common_success','quality_gain','quality_loss','both_failed','not_both_evaluated')})


def summarize(rows, errors):
    require(len(rows) == 4 and len({row['task_id'] for row in rows}) == 1
        and [(row['replication'],1,row['obligation_mode']) for row in rows] == run_order(),
        'all_four_ordered_P137_slots_required')
    require(all(type(row['replication']) is int and type(row['model_seed']) is int
        and row['model_seed'] == SEEDS[row['replication']-1]
        and row.get('run_id') == cell_id(row['replication'],1,row['obligation_mode'])
        for row in rows), 'fixed_P137_seeds_and_ids_required')
    evaluated = all(row['record_status']=='evaluated' and type(row.get('success')) is bool for row in rows)
    known = evaluated and all(type(row.get('unknown_usage_calls')) is int and row['unknown_usage_calls']==0
        and type(row.get('known_total_tokens')) is int and row['known_total_tokens']>=0 for row in rows)
    primary, anchor = _comparison(rows,'ids_only'), _comparison(rows,'raw_anchor')
    common = primary['paired_results'][0]['both_successful'] is True
    entity = next(row for row in rows if row['replication']==2 and row['obligation_mode']=='entity_fields')
    exposure = entity.get('obligation_field_rows_exposed')
    exposed = exposure if common and type(exposure) is int and exposure>=0 else None
    intact = all(row.get('obligation_contract_failed') is False and row.get('obligation_accounting_complete') is True
                 for row in rows)
    pair_ready = primary['both_pairs_evaluated'] and anchor['both_pairs_evaluated']
    lossless = primary['paired_success_losses']==0 and anchor['paired_success_losses']==0 if pair_ready else None
    unpaired=rows[0]
    return dict(all_four_complete_with_known_usage=known, all_four_evaluated=evaluated,
        primary_comparison=primary, raw_anchor_comparison=anchor,
        no_paired_success_loss_against_either_control=lossless,
        field_rows_exposed_on_primary_common_success=exposed, mechanism_contracts_intact=intact,
        seed57_unpaired_result={key:unpaired.get(key) for key in
            ('run_id','record_status','success','known_total_tokens','unknown_usage_calls','obligation_field_rows_exposed')},
        planned_rows=4, independent_tasks=1, repetitions=2, balanced_repetitions=False, model_seeds=list(SEEDS),
        development_gate_met=False, scientific_adoption_evaluated=False,
        original_P136_gate_replaced=False, prior_results_pooled=False,
        novel_method_claim=False, general_quality_preservation_claim=False,
        audit_errors_present=bool(errors),
        interpretation='Four originally unrun slots only; no P136 row is replaced. Seed157 has one within-cohort '
            'three-arm descriptive comparison. Seed57 entity-fields is unpaired. All failures, unknown usage, '
            'summary/disclosure costs remain. No original six-slot adoption gate is evaluated or passed.')
