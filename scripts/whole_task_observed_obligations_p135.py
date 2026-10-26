"""P135: bounded entity-field disclosure against counts and original P123 anchor."""
from copy import deepcopy
import json
from pathlib import Path

from budget_observation import notification
from budget_visibility_comparison import ERROR_POLICY
from late_clock_comparison import initial_conversation as original_conversation
from observed_obligation_tools import GUIDE, OBLIGATION_TOOLS
from protocol_stable_history import StableReferenceConversation
from public_display import CODE_TOOLS
from receipt_reasoning_history import require
from whole_task_tool_choice import worker_config as original_worker_config

ROOT = Path(__file__).resolve().parents[1]
MODES = ('raw_anchor', 'counts_only', 'entity_fields')
SEEDS = (57, 157)
PLAN = 'configs/P135_whole_task_observed_obligations_v01.json'
PREFLIGHT = 'reports/P135_initial_checks.json'
ACTIVATION = 'reports/P135_activation_v01.json'
REQUIRED_SOURCES = (
    'configs/P123_whole_task_rolling_checkpoint_v01.json',
    'scripts/partitioned_export_monitor.py', 'scripts/observed_field_obligations.py',
    'scripts/observed_obligation_tools.py', 'scripts/observed_obligation_runtime.py',
    'scripts/observed_obligation_execution.py', 'scripts/observed_obligation_inference.py',
    'scripts/audit_observed_obligation_trace.py',
    'scripts/run_whole_task_observed_obligations_cell_p135.py',
    'scripts/audit_whole_task_observed_obligations_p135.py', 'scripts/obligation_server_identity_p135.py',
    'scripts/serve_research_model_recovery.py', 'reports/P123_comparison.json',
    'reports/P132_comparison.json', 'docs/experiments/P135_whole_task_observed_obligations.md',
    'configs/P134_whole_task_observed_obligations_v01.json',
    'scripts/whole_task_observed_obligations_p135.py',
    'scripts/run_whole_task_observed_obligations_p135.py',
    'scripts/prepare_whole_task_observed_obligations_p135.py',
    'scripts/run_whole_task_observed_obligations_pipeline_p135.py',
    'scripts/inspect_whole_task_observed_obligations_session_p135.py',
    'scripts/build_observed_obligations_summary_p135.py',
)


def run_order():
    return [(rep, 1, mode) for rep in (1, 2)
            for mode in (MODES if rep == 1 else MODES[::-1])]


def cell_id(replication, number, mode):
    require(type(replication) is int and replication in (1, 2)
        and type(number) is int and number == 1 and mode in MODES,
        'outside_fixed_P135_comparison')
    return f'BOC_P135_R{replication:02d}_{number:02d}_{mode.upper()}'


def worker_config(original, plan, task_id, arm, run_id, obligation_mode, replication):
    require(run_id == cell_id(replication, 1, obligation_mode), 'fixed_P135_cell_required')
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
    require(mode in MODES, 'fixed_P135_obligation_mode_required')
    previous = original_conversation(original, public_task)
    if mode == 'raw_anchor':
        return previous
    return StableReferenceConversation(previous.messages()[0]['content'] + '\n' + GUIDE, public_task)


def tools_for(mode):
    require(mode in MODES, 'fixed_P135_obligation_mode_required')
    return deepcopy(CODE_TOOLS if mode == 'raw_anchor' else OBLIGATION_TOOLS)


def make_notification(messages, state, mode, *, wall_limit):
    require(mode in MODES, 'fixed_P135_obligation_mode_required')
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
    value.update(experiment='P135', batch_id='P135_batch_v01', source_runs=['P29_04_CODE'],
        obligation_modes=list(MODES), checkpoint_policy='rolling_separate',
        inline_checkpoint_requirement='not_applicable', model_seeds=list(SEEDS), repetitions=2,
        max_cells=6, max_model_calls=480, max_reserved_tokens=2700000,
        max_reserved_environment_api_requests=480, max_evaluator_calls=6,
        max_summary_calls_in_batch=18, server_max_lifetime_seconds=21600,
        deadline_jst='2026-10-27T18:00:00+09:00', api_budget_by_task_slot=[80],
        primary_comparison=['counts_only', 'entity_fields'],
        secondary_comparison=['raw_anchor', 'entity_fields'],
        raw_anchor_P123_interface_preserved=True, main_pair_capabilities_identical=True,
        common_observer_and_checkpoint_capture=True, notice_json_byte_limit=2048,
        query_response_byte_limit=8192, maximum_displayed_entities=16,
        query_maximum_page_rows=32, automatic_environment_API_calls=0,
        automatic_value_writes=False, official_completion_only=True,
        payback_enabled=False, require_P133_reporting_recovery_before_launch=True,
        require_P134_unstarted_queue_failure_before_launch=True,
        same_conditions_as_prepared_P134=True,
        original_prepared_P134_head='dda97636b88ad3126647e101af9e720f745e5ec7',
        original_prepared_P134_plan_sha256='6e0b2ebb457005bb430c16fb25e599793e51b6c9480ff63dd8d51ae65846d98f',
        P133_outcomes_used_for_design=False, prior_closed_results_used_for_design=['P123','P127','P132'],
        user_continuation_authorization='2026-10-27_after_P132_continue_while_asleep',
        past_results_seen_before_design=True, all_original_failures_preserved=True,
        novel_method_claim=False, primary_question='bounded_entity_field_obligations_after_checkpoint')
    return value


def validate_plan(plan):
    require(all(type(plan.get(key)) is type(value) and plan[key] == value
                for key, value in fixed_fields().items()), 'fixed_P135_scope_changed')
    tasks = plan.get('known_tasks')
    require(type(tasks) is list and len(tasks) == 1 and tasks[0].get('source_run') == 'P29_04_CODE'
        and type(tasks[0].get('task_id')) is str, 'only_known_CSV_task_required')
    for name in REQUIRED_SOURCES:
        value = plan.get('source_sha256', {}).get(name)
        require(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value),
                'bound_P135_sources_required')


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
        == {(rep,mode) for rep in (1,2) for mode in MODES}, 'all_six_P135_slots_required')
    require(all(type(row['replication']) is int and type(row['model_seed']) is int
        and row['model_seed'] == SEEDS[row['replication']-1]
        and row.get('run_id') == cell_id(row['replication'],1,row['obligation_mode'])
        for row in rows), 'fixed_P135_seeds_and_ids_required')
    evaluated = all(row['record_status']=='evaluated' and type(row.get('success')) is bool for row in rows)
    known = evaluated and all(type(row.get('unknown_usage_calls')) is int and row['unknown_usage_calls']==0
        and type(row.get('known_total_tokens')) is int and row['known_total_tokens']>=0 for row in rows)
    primary, anchor = _comparison(rows,'counts_only'), _comparison(rows,'raw_anchor')
    common = {pair['replication'] for pair in primary['paired_results'] if pair['both_successful']}
    exposures = [row.get('obligation_entity_rows_exposed') for row in rows
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
        entity_rows_exposed_on_primary_common_success=exposed, mechanism_contracts_intact=intact,
        planned_rows=6, independent_tasks=1, repetitions=2, model_seeds=list(SEEDS),
        development_gate_met=bool(known and not errors and intact and lossless and common
            and delta is not None and delta<0 and common_delta is not None and common_delta<0
            and anchor_delta is not None and anchor_delta<0 and exposed is not None and exposed>0),
        prior_results_pooled=False, novel_method_claim=False, general_quality_preservation_claim=False,
        interpretation='One known CSV task, two fixed seeds. Primary entity-field disclosure versus the same '
            'evidence/capability counts policy, with unchanged P123 raw anchor. All failures, unknown usage, '
            'summary/query/disclosure costs remain. Synthetic coverage is not official success or token benefit.')
