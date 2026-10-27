"""Prospective P138: three checkpoint schedules on all four known tasks.

This module neither launches nor authorizes generation. A fixed source plan,
native preflight, both CI events and an owned finite server are required.
"""
from copy import deepcopy
import json
from pathlib import Path

from budget_observation import notification
from budget_visibility_comparison import ERROR_POLICY
from late_clock_comparison import initial_conversation
from receipt_reasoning_history import require
from whole_task_tool_choice import worker_config as original_worker_config

ROOT = Path(__file__).resolve().parents[1]
MODES = ('rolling_separate', 'fixed_interval', 'prefix_exposure')
PLAN = 'configs/P138_whole_task_prefix_exposure_v01.json'
PREFLIGHT = 'reports/P138_initial_checks.json'
ACTIVATION = 'reports/P138_activation_v01.json'


def run_order():
    return [(n, MODES[(n - 1 + k) % 3]) for n in range(1, 5) for k in range(3)]


def cell_id(number, mode):
    require(type(number) is int and number in range(1, 5) and mode in MODES,
            'outside_fixed_P138_comparison')
    return f'BOC_P138_{number:02d}_{mode.upper()}'


def worker_config(original, plan, task_id, arm, run_id, exposure_mode):
    tasks = [t['task_id'] for t in plan['known_tasks']]
    require(len(tasks) == len(set(tasks)) == 4 and task_id in tasks,
            'all_four_known_task_identities_required')
    require(run_id == cell_id(tasks.index(task_id) + 1, exposure_mode),
            'fixed_P138_cell_required')
    config = original_worker_config(original, plan, task_id, arm, run_id, 'auto')
    require(config['max_api_requests'] == [160, 80, 80, 80][tasks.index(task_id)]
            and config['draft_temperature'] == 0.7, 'unchanged_P123_limits_required')
    config.update(checkpoint_policy='rolling_separate', read_views_enabled=False,
        inline_checkpoint_requirement='not_applicable', rolling_checkpoint_max_opportunities=3,
        rolling_min_fresh_turns=3, prefix_exposure_mode=exposure_mode)
    return config


def config_for(original, plan, task_id, mode):
    number = [t['task_id'] for t in plan['known_tasks']].index(task_id) + 1
    return worker_config(original, plan, task_id, ERROR_POLICY, cell_id(number, mode), mode)


def make_notification(messages, state, mode, *, wall_limit):
    require(mode in MODES, 'fixed_P138_mode_required')
    return notification(messages, state, 'not_exposed')


def fixed_fields():
    prior = json.loads((ROOT / 'configs/P123_whole_task_rolling_checkpoint_v01.json').read_text())
    keys = ('phase', 'source_plan', 'source_runs', 'max_calls', 'max_total_tokens', 'max_wall_seconds',
        'max_setup_seconds', 'max_cleanup_seconds', 'max_idle_wait_seconds', 'max_evaluation_seconds',
        'world_seed', 'model_seed', 'reserved_scenarios_read', 'history_policy', 'catalog_policy',
        'automatic_retries', 'error_policy', 'protocol_references', 'reasoning_budget_tokens',
        'time_visibility', 'fresh_seed_search', 'threshold_search', 'new_task_requirements_read',
        'shared_model_call_and_token_budget', 'summary_output_cap', 'summary_temperature',
        'unknown_summary_usage_policy', 'same_call_results_summarized', 'separate_semantic_judge',
        'no_previous_replacement_or_retry', 'public_runtime_sha256', 'read_views_enabled',
        'trigger_input_tokens', 'retained_recent_turns', 'max_summary_characters', 'tool_choice',
        'rolling_checkpoint_max_opportunities', 'rolling_min_fresh_turns', 'invalid_summary_policy')
    value = {k: deepcopy(prior[k]) for k in keys}
    value.update(experiment='P138', batch_id='P138_batch_v01', prefix_exposure_modes=list(MODES),
        checkpoint_policy='rolling_separate', inline_checkpoint_requirement='not_applicable',
        repetitions=1, max_cells=12, max_model_calls=960, max_reserved_tokens=5400000,
        max_reserved_environment_api_requests=1200, max_evaluator_calls=12,
        max_summary_calls_in_batch=36, server_max_lifetime_seconds=32400,
        deadline_jst='2026-10-28T03:00:00+09:00', api_budget_by_task_slot=[160, 80, 80, 80],
        primary_comparison=['rolling_separate', 'prefix_exposure'],
        timing_control_comparison=['fixed_interval', 'prefix_exposure'],
        first_summary_admission_unchanged=True, ordinary_P123_interface_preserved=True,
        shared_shadow_counting=True, counterfactual_count_payload_generated=False,
        exposure_is_guaranteed_savings=False, competitive_ratio_claim=False,
        past_results_seen_before_design=True, all_original_failures_preserved=True,
        novel_method_claim=False, primary_question='paid_raw_prefix_exposure_repeat_checkpoint_timing')
    return value


def validate_plan(plan):
    require(all(type(plan.get(k)) is type(v) and plan[k] == v for k, v in fixed_fields().items()),
            'fixed_P138_scope_changed')
    tasks = plan.get('known_tasks')
    require(type(tasks) is list and len(tasks) == 4
        and [t.get('source_run') for t in tasks] == [f'P29_{n:02d}_CODE' for n in range(1, 5)]
        and len({t.get('task_id') for t in tasks}) == 4, 'all_four_known_tasks_required')
    for name in ('configs/P123_whole_task_rolling_checkpoint_v01.json',
        'scripts/checkpoint_prefix_exposure.py', 'scripts/prefix_exposure_inference.py',
        'scripts/run_whole_task_prefix_exposure_cell_p138.py',
        'scripts/audit_whole_task_prefix_exposure_p138.py',
        'scripts/serve_research_model_recovery.py', 'reports/P123_comparison.json',
        'reports/P137_comparison.json', 'docs/experiments/P138_prefix_exposure_draft_20261027.md'):
        digest = plan.get('source_sha256', {}).get(name)
        require(type(digest) is str and len(digest) == 64
            and all(c in '0123456789abcdef' for c in digest), 'bound_P138_sources_required')


def summarize(rows, errors):
    tasks = list(dict.fromkeys(r['task_id'] for r in rows))
    require(len(tasks) == 4 and len(rows) == 12
        and {(r['task_id'], r['prefix_exposure_mode']) for r in rows}
            == {(t, m) for t in tasks for m in MODES}, 'all_twelve_P138_slots_required')
    cells = {(r['task_id'], r['prefix_exposure_mode']): r for r in rows}
    comparisons = []
    for baseline in MODES[:2]:
        pairs = []
        for task in tasks:
            a, b = cells[task, baseline], cells[task, 'prefix_exposure']
            evaluated = all(r['record_status'] == 'evaluated' and type(r['success']) is bool for r in (a, b))
            known = evaluated and all(type(r.get('unknown_usage_calls')) is int and r['unknown_usage_calls'] == 0
                and type(r.get('known_total_tokens')) is int and r['known_total_tokens'] >= 0 for r in (a, b))
            pairs.append(dict(task_id=task, baseline=baseline,
                baseline_success=a['success'], candidate_success=b['success'],
                both_evaluated=evaluated, both_usage_known=known,
                success_lost=(a['success'] and not b['success']) if evaluated else None,
                both_successful=(a['success'] and b['success']) if evaluated else None,
                candidate_minus_baseline_tokens=b['known_total_tokens']-a['known_total_tokens'] if known else None,
                decision_differences=b.get('actual_decision_differences_from_'+baseline)))
        complete = all(p['both_usage_known'] for p in pairs)
        common = [p for p in pairs if p['both_successful'] is True]
        delta = sum(p['candidate_minus_baseline_tokens'] for p in pairs) if complete else None
        common_delta = sum(p['candidate_minus_baseline_tokens'] for p in common) if complete and common else None
        changed = any(type(p['decision_differences']) is int and p['decision_differences'] > 0 for p in common)
        intact = all(cells[t, m].get('prefix_exposure_contract_failed') is False
            and cells[t, m].get('prefix_exposure_accounting_complete') is True
            for t in tasks for m in (baseline, 'prefix_exposure'))
        gate = bool(complete and not errors and intact and common and changed
            and not any(p['success_lost'] for p in pairs) and delta < 0 and common_delta < 0)
        comparisons.append(dict(baseline=baseline, pairs=pairs,
            all_four_pairs_complete_with_known_usage=complete, all_task_token_difference=delta,
            common_success_tasks=[p['task_id'] for p in common],
            common_success_token_difference=common_delta,
            changed_decision_on_common_success=changed, comparison_gate_met=gate))
    all_known = all(r['record_status'] == 'evaluated' and type(r['success']) is bool
        and type(r.get('unknown_usage_calls')) is int and r['unknown_usage_calls'] == 0
        and type(r.get('known_total_tokens')) is int for r in rows)
    known_totals = {m: sum(r['known_total_tokens'] for r in rows
        if r['prefix_exposure_mode'] == m and type(r.get('known_total_tokens')) is int) for m in MODES}
    adopted = all(c['comparison_gate_met'] for c in comparisons)
    return dict(planned_rows=12, independent_tasks=4, repetitions=1, model_seed=57,
        all_twelve_complete_with_known_usage=all_known,
        success_counts={m: sum(r['success'] is True for r in rows if r['prefix_exposure_mode'] == m) for m in MODES},
        known_token_subtotals_by_mode=known_totals,
        total_tokens_by_mode=known_totals if all_known else {m: None for m in MODES},
        usage_count_missing_conditions=sum(type(r.get('unknown_usage_calls')) is not int for r in rows),
        recorded_unknown_usage_calls=sum(r['unknown_usage_calls'] for r in rows
            if type(r.get('unknown_usage_calls')) is int),
        comparisons=comparisons, primary_utility_gate_met=comparisons[0]['comparison_gate_met'],
        both_control_development_gate_met=adopted, development_gate_met=adopted,
        prior_results_pooled=False, unknown_usage_imputed=False,
        exposure_is_guaranteed_savings=False, competitive_ratio_claim=False,
        novel_method_claim=False, general_quality_preservation_claim=False,
        interpretation='One seed on four known development tasks. The measured P123 threshold control '
            'is primary; the previously unmeasured fixed interval is a timing control. '
            'Beating only the threshold does not establish a need for cumulative exposure.')
