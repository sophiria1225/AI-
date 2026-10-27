"""P142 fixed new-seed development comparison on all four already-known tasks."""
from copy import deepcopy
from pathlib import Path

from budget_observation import notification
from budget_visibility_comparison import ERROR_POLICY
from late_clock_comparison import initial_conversation
from receipt_reasoning_history import require
from whole_task_object_timing_p141 import fixed_fields as previous_fixed_fields
from whole_task_tool_choice import worker_config as original_worker_config

ROOT = Path(__file__).resolve().parents[1]
MODES = ('threshold_recursive', 'threshold_delta_object')
TASKS = ('34d9492_1', '3c13f5a_1', '60d0b5b_1', '6104387_1')
PLAN = 'configs/P142_threshold_object_v01.json'
PREFLIGHT = 'reports/P142_initial_checks.json'
ACTIVATION = 'reports/P142_activation_v01.json'
MATERIAL = 'materials/20261028_p142_results'
COMPARISONS = (('threshold_recursive', 'threshold_delta_object', 'representation_prompt_bundle'),)
REQUIRED_SOURCES = (
    'configs/P123_whole_task_rolling_checkpoint_v01.json',
    'configs/P141_object_timing_v01.json',
    'scripts/checkpoint_object_timing_p141.py',
    'scripts/checkpoint_object_timing_inference_p141.py',
    'scripts/audit_object_timing_trace_p141.py',
    'scripts/checkpoint_prefix_identity_p140.py',
    'scripts/whole_task_threshold_object_p142.py',
    'scripts/checkpoint_threshold_object_preflight_p142.py',
    'scripts/run_whole_task_threshold_object_cell_p142.py',
    'scripts/run_whole_task_threshold_object_p142.py',
    'scripts/run_whole_task_threshold_object_pipeline_p142.py',
    'scripts/prepare_whole_task_threshold_object_p142.py',
    'scripts/threshold_object_server_identity_p142.py',
    'scripts/audit_whole_task_threshold_object_p142.py',
    'scripts/inspect_whole_task_threshold_object_session_p142.py',
    'scripts/build_p142_results.py',
    'scripts/serve_research_model_recovery.py',
    'tests/test_threshold_object_driver_p142.py',
    'tests/test_threshold_object_pipeline_p142.py',
    'tests/test_threshold_object_prepare_p142.py',
    'tests/test_threshold_object_reporting_p142.py',
    'tests/threshold_object_worker_fixture_p142.py',
    'docs/experiments/P142_threshold_object_confirmation_20261028.md')


def factors(mode):
    require(mode in MODES, 'fixed_P142_mode_required')
    return 'threshold', 'recursive' if mode == MODES[0] else 'delta'


def run_order():
    return [(n, mode) for n in range(1, 5)
            for mode in (MODES if n % 2 else MODES[::-1])]


def cell_id(number, mode):
    require(type(number) is int and number in range(1, 5) and mode in MODES,
            'outside_fixed_P142_comparison')
    return f'BOC_P142_{number:02d}_{mode.upper()}'


def worker_config(original, plan, task_id, arm, run_id, object_timing_mode):
    require(tuple(t['task_id'] for t in plan['known_tasks']) == TASKS and task_id in TASKS,
            'fixed_four_known_tasks_required')
    number = TASKS.index(task_id) + 1
    mode = object_timing_mode
    require(run_id == cell_id(number, mode), 'fixed_P142_cell_required')
    config = original_worker_config(original, plan, task_id, arm, run_id, 'auto')
    require(config['max_api_requests'] == [160, 80, 80, 80][number-1]
            and config['draft_temperature'] == 0.7, 'unchanged_task_and_sampling_limits')
    timing, representation = factors(mode)
    config.update(checkpoint_policy='rolling_separate', read_views_enabled=False,
        inline_checkpoint_requirement='not_applicable', rolling_checkpoint_max_opportunities=2,
        rolling_min_fresh_turns=3, object_timing_mode=mode,
        checkpoint_representation_mode=mode, checkpoint_timing=timing,
        checkpoint_representation=representation)
    return config


def config_for(original, plan, task_id, mode):
    return worker_config(original, plan, task_id, ERROR_POLICY,
                         cell_id(TASKS.index(task_id)+1, mode), mode)


def make_notification(messages, state, mode, *, wall_limit):
    require(mode in MODES, 'fixed_P142_mode_required')
    return notification(messages, state, 'not_exposed')


def fixed_fields():
    value = deepcopy(previous_fixed_fields())
    for key in ('original_task_slot', 'diagnostic_task_slot', 'development_gate_met',
                'timing_prefix_until_first_observed_predicate_divergence',
                'actual_dispatch_required_at_first_predicate_divergence',
                'later_attributable_boundary_search', 'same_second_focus_cutoff_required_for_timing'):
        value.pop(key, None)
    value.update(experiment='P142', batch_id='P142_batch_v01',
        source_runs=[f'P29_{n:02d}_CODE' for n in range(1, 5)],
        object_timing_modes=list(MODES), checkpoint_representation_modes=list(MODES),
        api_budget_by_task_slot=[160,80,80,80], model_seed=157, world_seed=42,
        max_cells=8, max_model_calls=640, max_reserved_tokens=3600000,
        max_reserved_environment_api_requests=800, max_evaluator_calls=8,
        max_summary_calls_in_batch=16, max_setup_seconds=60, max_cleanup_seconds=60,
        max_idle_wait_seconds=30, max_evaluation_seconds=60,
        server_max_lifetime_seconds=18000, batch_timeout_seconds=16200,
        pipeline_timeout_seconds=18600,
        latest_launch_jst='2026-10-28T09:15:00+09:00',
        deadline_jst='2026-10-28T14:15:00+09:00',
        reporting_deadline_jst='2026-10-28T15:00:00+09:00',
        primary_comparison=list(COMPARISONS[0][:2]), additional_controls=[],
        fixed_comparisons=[list(c) for c in COMPARISONS],
        primary_question='new_seed_whole_job_utility_of_threshold_object_delta_on_known_four_tasks',
        diagnostic_only=False, scientific_adoption_evaluated=False,
        development_eligibility_evaluated=True,
        development_seed_selected_with_known_activation=False,
        seed_choice='single_fixed_157_no_seed_search',
        posthoc_task_selection_disclosed=True,
        execution_order_randomized=False, execution_order_balanced_by_task_parity=True,
        native_preflight_initial_requests=8, native_preflight_focus_requests=4,
        native_preflight_post_checkpoint_actor_requests=2,
        transport_ID_canonical_prefix_required_for_attribution=True,
        deadline_budget_changes_common_to_both_arms=True,
        incomplete_cells_retained=True, automatic_retries=0)
    return value


def validate_plan(plan):
    require(all(type(plan.get(k)) is type(v) and plan[k] == v
                for k,v in fixed_fields().items()), 'fixed_P142_scope_changed')
    tasks = plan.get('known_tasks')
    require(type(tasks) is list and len(tasks) == 4
        and all(type(t) is dict for t in tasks)
        and tuple(t.get('task_id') for t in tasks) == TASKS
        and [t.get('source_run') for t in tasks] == [f'P29_{n:02d}_CODE' for n in range(1,5)],
        'fixed_four_known_tasks_required')
    for name in REQUIRED_SOURCES:
        value = plan.get('source_sha256', {}).get(name)
        require(type(value) is str and len(value) == 64
                and all(c in '0123456789abcdef' for c in value), 'bound_P142_sources_required')


def summarize(rows, errors):
    require(type(errors) is list and type(rows) is list and len(rows) == 8,
            'all_eight_P142_slots_required')
    require([r.get('run_id') for r in rows] == [cell_id(n,m) for n,m in run_order()]
        and all(r.get('task_id') == TASKS[n-1] and r.get('object_timing_mode') == m
            and r.get('checkpoint_representation_mode') == m for r,(n,m) in zip(rows,run_order())),
        'all_eight_ordered_P142_slots_required')
    cells = {(r['task_id'],r['object_timing_mode']):r for r in rows}

    def evaluated(r):
        return r['record_status'] == 'evaluated' and type(r.get('success')) is bool

    def known(r):
        return (evaluated(r) and type(r.get('unknown_usage_calls')) is int
            and r['unknown_usage_calls'] == 0 and type(r.get('known_total_tokens')) is int
            and r['known_total_tokens'] >= 0)

    def positive(v):
        return type(v) is int and v > 0

    from checkpoint_prefix_identity_p140 import representation_prefix_comparison
    baseline, candidate, name = COMPARISONS[0]
    pairs = []
    for task in TASKS:
        a,b = cells[task,baseline],cells[task,candidate]
        complete, both_evaluated = known(a) and known(b), evaluated(a) and evaluated(b)
        evidence = representation_prefix_comparison(a,b)
        prompt, delta = b.get('object_prompt_known_focus_calls'), b.get('actual_delta_known_actor_calls')
        pairs.append(dict(task_id=task,baseline=baseline,candidate=candidate,
            baseline_success=a.get('success'),candidate_success=b.get('success'),
            both_evaluated=both_evaluated,both_usage_known=complete,
            success_lost=(a['success'] and not b['success']) if both_evaluated else None,
            both_successful=(a['success'] and b['success']) if both_evaluated else None,
            candidate_minus_baseline_tokens=b['known_total_tokens']-a['known_total_tokens'] if complete else None,
            candidate_object_prompt_known_focus_calls=prompt,candidate_delta_known_actor_calls=delta,
            strict_prefix_match=evidence.get('strict_match'),canonical_prefix_match=evidence.get('canonical_match'),
            actual_intervention=positive(prompt) and positive(delta) and evidence.get('canonical_match') is True,
            representation_prefix_identity=evidence))
    complete = all(p['both_usage_known'] for p in pairs)
    common = [p for p in pairs if p['both_successful'] is True]
    difference = sum(p['candidate_minus_baseline_tokens'] for p in pairs) if complete else None
    common_difference = sum(p['candidate_minus_baseline_tokens'] for p in common) if complete and common else None
    intact = all(r.get(k+'_contract_failed') is False and r.get(k+'_accounting_complete') is True
                 for r in rows for k in ('prefix_exposure','checkpoint_representation','delta_envelope'))
    active = any(p['actual_intervention'] for p in common)
    matched = all(p['canonical_prefix_match'] is True for p in pairs
                  if positive(p['candidate_object_prompt_known_focus_calls']))
    utility = bool(complete and not errors and common and not any(p['success_lost'] for p in pairs)
                   and difference < 0 and common_difference < 0)
    gate = bool(utility and intact and active and matched)
    subtotals = {m:sum(r['known_total_tokens'] for r in rows if r['object_timing_mode'] == m
        and type(r.get('known_total_tokens')) is int and r['known_total_tokens'] >= 0) for m in MODES}
    comparison = dict(name=name,baseline=baseline,candidate=candidate,pairs=pairs,
        all_pairs_complete_with_known_usage=complete,all_four_pairs_complete_with_known_usage=complete,
        all_task_token_difference=difference,
        all_task_token_difference_pct=100*difference/subtotals[baseline] if complete and subtotals[baseline] else None,
        common_success_tasks=[p['task_id'] for p in common],common_success_token_difference=common_difference,
        success_loss_tasks=[p['task_id'] for p in pairs if p['success_lost'] is True],
        changed_intervention_on_common_success=active,all_activated_canonical_prefixes_match=matched,
        observed_utility_criteria_met=utility,comparison_gate_met=gate,attribution_prefix_required=True)
    return dict(planned_rows=8,independent_tasks=4,repetitions=1,model_seed=157,
        all_eight_complete_with_known_usage=complete,evaluated_conditions=sum(evaluated(r) for r in rows),
        success_counts={m:sum(evaluated(r) and r['success'] for r in rows if r['object_timing_mode']==m) for m in MODES},
        unevaluated_counts={m:sum(not evaluated(r) for r in rows if r['object_timing_mode']==m) for m in MODES},
        known_token_subtotals_by_mode=subtotals,total_tokens_by_mode=subtotals if complete else {m:None for m in MODES},
        usage_count_missing_conditions=sum(type(r.get('unknown_usage_calls')) is not int for r in rows),
        recorded_unknown_usage_calls=sum(r['unknown_usage_calls'] for r in rows if type(r.get('unknown_usage_calls')) is int),
        comparisons=[comparison],audit_errors_count=len(errors),development_gate_met=gate,
        scientific_adoption_evaluated=False,reserved_confirmation_replaced=False,
        all_original_four_task_confirmation_replaced=False,prior_results_pooled=False,unknown_usage_imputed=False,
        novel_method_claim=False,general_quality_preservation_claim=False,independent_replication_claim=False,
        exposure_is_guaranteed_savings=False,competitive_ratio_claim=False,
        interpretation='Fixed seed157 development cohort on all four already-known tasks. '
        'Both arms use threshold timing. The second checkpoint changes the representation-plus-prompt bundle. '
        'All eight usages and evaluations, no task-specific success loss, lower aggregate and common-success cost, '
        'valid contracts and known delta intervention with matching canonical prefixes are required for development eligibility. '
        'This is not reserved-task confirmation or evidence of general quality preservation; no old result is pooled.')
