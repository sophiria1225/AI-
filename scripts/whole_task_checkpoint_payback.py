"""P133: a past-observation payback forecast against the unchanged P123 control."""
from copy import deepcopy
import json
from pathlib import Path

from budget_observation import notification
from budget_visibility_comparison import ERROR_POLICY
from late_clock_comparison import initial_conversation
from receipt_reasoning_history import require
from whole_task_tool_choice import worker_config as original_worker_config

ROOT = Path(__file__).resolve().parents[1]
MODES = ('rolling_separate', 'empirical_payback')
SEEDS = (57, 157)
PLAN = 'configs/P133_whole_task_checkpoint_payback_v01.json'
PREFLIGHT = 'reports/P133_initial_checks.json'
ACTIVATION = 'reports/P133_activation_v01.json'


def run_order():
    return [(rep, 1, mode) for rep in (1, 2)
            for mode in (MODES if rep == 1 else MODES[::-1])]


def cell_id(replication, number, mode):
    require(type(replication) is int and replication in (1, 2)
        and type(number) is int and number == 1 and mode in MODES,
        'outside_fixed_P133_comparison')
    return f'BOC_P133_R{replication:02d}_{number:02d}_{mode.upper()}'


def worker_config(original, plan, task_id, arm, run_id, payback_mode, replication):
    require(run_id == cell_id(replication, 1, payback_mode), 'fixed_P133_cell_required')
    config = original_worker_config(original, {**plan, 'model_seed': SEEDS[replication - 1]},
                                   task_id, arm, run_id, 'auto')
    require(config['max_api_requests'] == 80 and config['draft_temperature'] == 0.7,
            'P123_CSV_API_and_summary_limits_required')
    config.update(checkpoint_policy='rolling_separate', read_views_enabled=False,
        inline_checkpoint_requirement='not_applicable', rolling_checkpoint_max_opportunities=3,
        rolling_min_fresh_turns=3, payback_mode=payback_mode,
        replication=replication, model_seed=SEEDS[replication - 1])
    return config


def config_for(original, plan, task_id, mode, replication):
    return worker_config(original, plan, task_id, ERROR_POLICY,
                         cell_id(replication, 1, mode), mode, replication)


def make_notification(messages, state, mode, *, wall_limit):
    require(mode in MODES, 'fixed_P133_payback_mode_required')
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
    value = {k: deepcopy(prior[k]) for k in keys}
    value.update(experiment='P133', batch_id='P133_batch_v01', source_runs=['P29_04_CODE'],
        payback_modes=list(MODES), checkpoint_policy='rolling_separate',
        inline_checkpoint_requirement='not_applicable', model_seeds=list(SEEDS), repetitions=2,
        max_cells=4, max_model_calls=320, max_reserved_tokens=1800000,
        max_reserved_environment_api_requests=320, max_evaluator_calls=4,
        max_summary_calls_in_batch=12, server_max_lifetime_seconds=14400,
        deadline_jst='2026-10-27T12:30:00+09:00', api_budget_by_task_slot=[80],
        primary_comparison=list(MODES), ordinary_P123_interface_preserved=True,
        first_summary_admission_unchanged=True, forecast_is_guarantee=False,
        require_P132_owned_session_closed_before_launch=True,
        user_continuation_authorization='2026-10-27_after_P132_continue_while_asleep',
        past_results_seen_before_design=True, all_original_failures_preserved=True,
        novel_method_claim=False, primary_question='past_observation_summary_payback_admission')
    return value


def validate_plan(plan):
    require(all(type(plan.get(k)) is type(v) and plan[k] == v for k, v in fixed_fields().items()),
            'fixed_P133_scope_changed')
    tasks = plan.get('known_tasks')
    require(type(tasks) is list and len(tasks) == 1 and tasks[0].get('source_run') == 'P29_04_CODE'
        and type(tasks[0].get('task_id')) is str, 'only_known_CSV_task_required')
    for name in ('configs/P123_whole_task_rolling_checkpoint_v01.json',
        'scripts/empirical_checkpoint_payback.py', 'scripts/empirical_payback_inference.py',
        'scripts/run_whole_task_checkpoint_payback_cell.py',
        'scripts/audit_whole_task_checkpoint_payback.py', 'scripts/payback_server_identity.py',
        'scripts/serve_research_model_recovery.py',
        'reports/P123_comparison.json', 'reports/P132_comparison.json',
        'docs/experiments/P133_whole_task_checkpoint_payback.md'):
        value = plan.get('source_sha256', {}).get(name)
        require(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value),
                'bound_P133_sources_required')


def summarize(rows, errors):
    require(len(rows) == 4 and len({r['task_id'] for r in rows}) == 1
        and {(r['replication'], r['payback_mode']) for r in rows}
        == {(rep, mode) for rep in (1, 2) for mode in MODES}, 'all_four_P133_slots_required')
    require(all(type(r['replication']) is int and type(r['model_seed']) is int
        and r['model_seed'] == SEEDS[r['replication'] - 1] for r in rows), 'fixed_P133_seeds_required')
    evaluated = all(r['record_status'] == 'evaluated' and type(r['success']) is bool for r in rows)
    known = evaluated and all(type(r['unknown_usage_calls']) is int and r['unknown_usage_calls'] == 0
        and type(r['known_total_tokens']) is int and r['known_total_tokens'] >= 0 for r in rows)
    pairs = []
    for rep, seed in enumerate(SEEDS, 1):
        a, b = [next(r for r in rows if r['replication'] == rep and r['payback_mode'] == m) for m in MODES]
        ready = all(r['record_status'] == 'evaluated' and type(r['success']) is bool for r in (a, b))
        paid = ready and all(r['unknown_usage_calls'] == 0 and type(r['known_total_tokens']) is int for r in (a, b))
        pairs.append(dict(replication=rep, model_seed=seed, baseline_success=a['success'],
            payback_success=b['success'], both_evaluated=ready, both_usage_known=paid,
            both_successful=a['success'] and b['success'] if ready else None,
            success_lost=a['success'] and not b['success'] if ready else None,
            empirical_minus_baseline_tokens=b['known_total_tokens'] - a['known_total_tokens'] if paid else None))
    common = {p['replication'] for p in pairs if p['both_successful']}
    interventions = [r.get('payback_rejections') for r in rows
                     if r['payback_mode'] == 'empirical_payback' and r['replication'] in common]
    exposed = sum(interventions) if interventions and all(type(n) is int and n >= 0 for n in interventions) else None
    delta = sum(p['empirical_minus_baseline_tokens'] for p in pairs) if known else None
    common_delta = sum(p['empirical_minus_baseline_tokens'] for p in pairs if p['both_successful']) if known else None
    losses = sum(p['success_lost'] for p in pairs) if evaluated else None
    intact = all(r.get('payback_contract_failed') is False and r.get('payback_accounting_complete') is True for r in rows)
    return dict(all_four_complete_with_known_usage=known, paired_results=pairs,
        paired_success_losses=losses, paired_successful_task_seed_pairs=len(common) if evaluated else None,
        empirical_minus_baseline_whole_task_tokens=delta, paired_successful_token_difference=common_delta,
        payback_rejections_on_common_success=exposed, planned_rows=4, independent_tasks=1, repetitions=2,
        model_seeds=list(SEEDS), mechanism_contracts_intact=intact,
        development_gate_met=bool(known and not errors and intact and losses == 0
            and common and delta < 0 and common_delta < 0 and exposed is not None and exposed > 0),
        prior_results_pooled=False, forecast_is_guarantee=False, novel_method_claim=False,
        general_quality_preservation_claim=False,
        interpretation='Known CSV task, two prespecified seeds, unchanged P123 ordinary interface. '
            'A past-observation forecast is not a token-payback or completion guarantee. '
            'All failures and unknown usage remain; no unseen-task or novelty claim follows.')
