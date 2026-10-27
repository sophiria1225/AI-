"""P136: late same-ID field disclosure with identical original P123 inputs."""
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
PLAN = 'configs/P136_whole_task_late_obligations_v01.json'
PREFLIGHT = 'reports/P136_initial_checks.json'
ACTIVATION = 'reports/P136_activation_v01.json'
REQUIRED_SOURCES = (
    'configs/P123_whole_task_rolling_checkpoint_v01.json',
    'configs/P135_whole_task_observed_obligations_v01.json',
    'scripts/late_obligation_monitor_p136.py', 'scripts/late_obligation_core_p136.py',
    'scripts/late_obligation_runtime_p136.py', 'scripts/late_obligation_inference_p136.py',
    'scripts/audit_late_obligation_trace_p136.py',
    'scripts/run_whole_task_late_obligations_cell_p136.py',
    'scripts/audit_whole_task_late_obligations_p136.py',
    'scripts/late_obligation_server_identity_p136.py',
    'scripts/serve_research_model_recovery.py', 'reports/P123_comparison.json',
    'reports/P135_comparison.json', 'reports/P135_server_session.json',
    'docs/experiments/P136_whole_task_late_obligations.md',
    'scripts/whole_task_late_obligations_p136.py',
    'scripts/run_whole_task_late_obligations_p136.py',
    'scripts/prepare_whole_task_late_obligations_p136.py',
    'scripts/run_whole_task_late_obligations_pipeline_p136.py',
    'scripts/inspect_whole_task_late_obligations_session_p136.py',
    'scripts/build_late_obligations_summary_p136.py',
    'tests/test_whole_task_late_obligations_p136_reporting.py',
)


def run_order():
    return [(rep, 1, mode) for rep in (1, 2)
            for mode in (MODES if rep == 1 else MODES[::-1])]


def cell_id(replication, number, mode):
    require(type(replication) is int and replication in (1, 2)
        and type(number) is int and number == 1 and mode in MODES,
        'outside_fixed_P136_comparison')
    return f'BOC_P136_R{replication:02d}_{number:02d}_{mode.upper()}'


def worker_config(original, plan, task_id, arm, run_id, obligation_mode, replication):
    require(run_id == cell_id(replication, 1, obligation_mode), 'fixed_P136_cell_required')
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
    require(mode in MODES, 'fixed_P136_obligation_mode_required')
    return original_conversation(original, public_task)


def tools_for(mode):
    require(mode in MODES, 'fixed_P136_obligation_mode_required')
    return deepcopy(CODE_TOOLS)


def make_notification(messages, state, mode, *, wall_limit):
    require(mode in MODES, 'fixed_P136_obligation_mode_required')
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
    value.update(experiment='P136', batch_id='P136_batch_v01', source_runs=['P29_04_CODE'],
        obligation_modes=list(MODES), checkpoint_policy='rolling_separate',
        inline_checkpoint_requirement='not_applicable', model_seeds=list(SEEDS), repetitions=2,
        max_cells=6, max_model_calls=480, max_reserved_tokens=2700000,
        max_reserved_environment_api_requests=480, max_evaluator_calls=6,
        max_summary_calls_in_batch=18, server_max_lifetime_seconds=21600,
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
        client_terminal_grace_added=False, require_P135_closed_collection_before_launch=True,
        prior_closed_results_used_for_design=['P123','P127','P132','P133','P135'],
        user_continuation_authorization='2026-10-27_persistent_user_experiment_instruction',
        past_results_seen_before_design=True, all_original_failures_preserved=True,
        novel_method_claim=False, primary_question='field_association_beyond_same_ID_reexposure_after_checkpoint')
    return value


def validate_plan(plan):
    require(all(type(plan.get(key)) is type(value) and plan[key] == value
                for key, value in fixed_fields().items()), 'fixed_P136_scope_changed')
    tasks = plan.get('known_tasks')
    require(type(tasks) is list and len(tasks) == 1 and tasks[0].get('source_run') == 'P29_04_CODE'
        and type(tasks[0].get('task_id')) is str, 'only_known_CSV_task_required')
    mapping = plan.get('source_sha256')
    require(type(mapping) is dict and bool(mapping), 'P136_source_mapping_required')
    for name, expected in mapping.items():
        require(type(name) is str and bool(name) and not Path(name).is_absolute()
            and '..' not in Path(name).parts and '\\' not in name and str(Path(name)) == name
            and type(expected) is str and len(expected) == 64
            and all(c in '0123456789abcdef' for c in expected), 'safe_P136_source_binding_required')
    for name in REQUIRED_SOURCES:
        value = plan.get('source_sha256', {}).get(name)
        require(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value),
                'bound_P136_sources_required')


def _comparison(rows, baseline):
    pairs = []
    for rep, seed in enumerate(SEEDS, 1):
        before, after = [next(row for row in rows if row['replication'] == rep
                        and row['obligation_mode'] == mode) for mode in (baseline, 'entity_fields')]
        ready = all(row['record_status'] == 'evaluated' and type(row.get('success')) is bool
                    for row in (before, after))
        known = ready and all(type(row.get('unknown_usage_calls')) is int and row['unknown_usage_calls'] == 0
            and type(row.get('known_total_tokens')) is int and row['known_total_tokens'] >= 0
            for row in (before, after))
        transition = ('not_both_evaluated' if not ready else 'common_success' if before['success'] and after['success']
            else 'quality_loss' if before['success'] else 'quality_gain' if after['success'] else 'both_failed')
        pairs.append(dict(replication=rep, model_seed=seed, baseline_success=before.get('success'),
            candidate_success=after.get('success'), both_evaluated=ready, both_usage_known=known,
            both_successful=transition == 'common_success' if ready else None,
            success_lost=transition == 'quality_loss' if ready else None, quality_transition=transition,
            candidate_minus_baseline_tokens=after['known_total_tokens']-before['known_total_tokens'] if known else None))
    known = all(pair['both_usage_known'] for pair in pairs)
    evaluated = all(pair['both_evaluated'] for pair in pairs)
    common = [pair for pair in pairs if pair['both_successful']]
    costs = {name: {'pairs':sum(pair['quality_transition']==name for pair in pairs),
                   'candidate_minus_baseline_tokens':sum(pair['candidate_minus_baseline_tokens'] for pair in pairs
                       if pair['quality_transition']==name) if known else None}
             for name in ('common_success','quality_gain','quality_loss','both_failed','not_both_evaluated')}
    return dict(baseline=baseline, candidate='entity_fields', paired_results=pairs,
        both_seeds_evaluated=evaluated, both_seeds_usage_known=known,
        paired_success_losses=sum(pair['success_lost'] for pair in pairs) if evaluated else None,
        paired_successful_task_seed_pairs=len(common) if evaluated else None,
        candidate_minus_baseline_whole_task_tokens=sum(pair['candidate_minus_baseline_tokens'] for pair in pairs) if known else None,
        paired_successful_token_difference=sum(pair['candidate_minus_baseline_tokens'] for pair in common) if known and common else None,
        costs_by_quality_transition=costs)


def summarize(rows, errors):
    require(len(rows) == 6 and len({row['task_id'] for row in rows}) == 1
        and {(row['replication'],row['obligation_mode']) for row in rows}
        == {(rep,mode) for rep in (1,2) for mode in MODES}, 'all_six_P136_slots_required')
    require(all(type(row['replication']) is int and type(row['model_seed']) is int
        and row['model_seed'] == SEEDS[row['replication']-1]
        and row.get('run_id') == cell_id(row['replication'],1,row['obligation_mode'])
        for row in rows), 'fixed_P136_seeds_and_ids_required')
    evaluated = all(row['record_status']=='evaluated' and type(row.get('success')) is bool for row in rows)
    known = evaluated and all(type(row.get('unknown_usage_calls')) is int and row['unknown_usage_calls']==0
        and type(row.get('known_total_tokens')) is int and row['known_total_tokens']>=0 for row in rows)
    primary, anchor = _comparison(rows,'ids_only'), _comparison(rows,'raw_anchor')
    common = {pair['replication'] for pair in primary['paired_results'] if pair['both_successful']}
    exposures = [row.get('obligation_field_rows_exposed') for row in rows
                 if row['obligation_mode']=='entity_fields' and row['replication'] in common]
    exposed = sum(exposures) if exposures and all(type(n) is int and n>=0 for n in exposures) else None
    intact = all(row.get('obligation_contract_failed') is False and row.get('obligation_accounting_complete') is True
                 for row in rows)
    lossless = (primary['paired_success_losses']==0 and anchor['paired_success_losses']==0) if evaluated else None
    delta = primary['candidate_minus_baseline_whole_task_tokens']
    common_delta = primary['paired_successful_token_difference']
    anchor_delta = anchor['candidate_minus_baseline_whole_task_tokens']
    return dict(all_six_complete_with_known_usage=known, all_six_evaluated=evaluated,
        primary_comparison=primary, raw_anchor_comparison=anchor,
        no_paired_success_loss_against_either_control=lossless,
        field_rows_exposed_on_primary_common_success=exposed, mechanism_contracts_intact=intact,
        planned_rows=6, independent_tasks=1, repetitions=2, model_seeds=list(SEEDS),
        development_gate_met=bool(known and not errors and intact and lossless and common
            and delta is not None and delta<0 and common_delta is not None and common_delta<0
            and anchor_delta is not None and anchor_delta<0 and exposed is not None and exposed>0),
        prior_results_pooled=False, novel_method_claim=False, general_quality_preservation_claim=False,
        interpretation='One known CSV task, two fixed seeds. Primary entity-field disclosure versus the same '
            'ID-only policy, with identical P123 initial messages/tools and raw anchor. All failures, unknown usage, '
            'summary/disclosure costs remain. Synthetic coverage is not official success or token benefit.')
