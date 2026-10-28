"""P144 fixed three-arm state-update development comparison; no novelty guarantee."""
from copy import deepcopy
from pathlib import Path

from budget_observation import notification
from budget_visibility_comparison import ERROR_POLICY
from late_clock_comparison import initial_conversation
from receipt_reasoning_history import require
from whole_task_threshold_object_p143 import fixed_fields as previous_fixed_fields
from whole_task_tool_choice import worker_config as original_worker_config

ROOT = Path(__file__).resolve().parents[1]
MODES = ('threshold_recursive', 'threshold_delta_object', 'threshold_delta_update')
TASKS = ('34d9492_1', '3c13f5a_1', '60d0b5b_1', '6104387_1')
PLAN = 'configs/P144_state_update_v01.json'
PREFLIGHT = 'reports/P144_initial_checks.json'
ACTIVATION = 'reports/P144_activation_v01.json'
MATERIAL = 'materials/20261028_p144_results'
COMPARISONS = ((MODES[0], MODES[2], 'update_vs_recursive'),
               (MODES[1], MODES[2], 'update_vs_append'),
               (MODES[0], MODES[1], 'append_vs_recursive'))
REQUIRED_SOURCES = (
    '.github/workflows/checks.yml',
    'scripts/run_research_tests.py',
    'tests/test_research_test_runner.py',
    'configs/P143_threshold_object_v01.json',
    'reports/P143_results_provenance_20261028.json',
    'reports/P143_letter_v02_provenance_20261028.json',
    'scripts/checkpoint_state_update_p144.py',
    'scripts/checkpoint_state_update_inference_p144.py',
    'scripts/audit_state_update_trace_p144.py',
    'scripts/whole_task_state_update_p144.py',
    'scripts/checkpoint_state_update_preflight_p144.py',
    'scripts/run_whole_task_state_update_cell_p144.py',
    'scripts/run_whole_task_state_update_p144.py',
    'scripts/run_whole_task_state_update_pipeline_p144.py',
    'scripts/prepare_whole_task_state_update_p144.py',
    'scripts/state_update_server_identity_p144.py',
    'scripts/audit_whole_task_state_update_p144.py',
    'scripts/inspect_whole_task_state_update_session_p144.py',
    'scripts/build_state_update_summary_p144.py',
    'scripts/serve_research_model_recovery.py',
    'tests/test_state_update_p144.py',
    'tests/test_state_update_trace_p144.py',
    'tests/test_state_update_study_p144.py',
    'tests/test_state_update_pipeline_p144.py',
    'tests/state_update_worker_fixture_p144.py',
    'docs/experiments/P144_state_update_comparison_20261028.md',
    'docs/checkpoint_state_update_prior_scope_20261028.md',
)


def factors(mode):
    require(mode in MODES, 'fixed_P144_mode_required')
    return 'threshold', ('recursive', 'delta', 'update')[MODES.index(mode)]


def run_order():
    orders = (MODES, MODES[1:]+MODES[:1], MODES[2:]+MODES[:2],
              (MODES[0], MODES[2], MODES[1]))
    return [(n, mode) for n, order in enumerate(orders, 1) for mode in order]


def cell_id(number, mode):
    require(type(number) is int and number in range(1, 5) and mode in MODES,
            'outside_fixed_P144_comparison')
    return f'BOC_P144_{number:02d}_{mode.upper()}'


def worker_config(original, plan, task_id, arm, run_id, object_timing_mode):
    require(tuple(t['task_id'] for t in plan['known_tasks']) == TASKS and task_id in TASKS,
            'fixed_four_known_tasks_required')
    number = TASKS.index(task_id) + 1
    mode = object_timing_mode
    require(run_id == cell_id(number, mode), 'fixed_P144_cell_required')
    config = original_worker_config(original, plan, task_id, arm, run_id, 'auto')
    require(config['max_api_requests'] == [160, 80, 80, 80][number-1]
            and config['draft_temperature'] == 0.7, 'unchanged_task_and_sampling_limits')
    timing, representation = factors(mode)
    config.update(checkpoint_policy='rolling_separate', read_views_enabled=False,
        inline_checkpoint_requirement='not_applicable', rolling_checkpoint_max_opportunities=2,
        rolling_min_fresh_turns=3, checkpoint_trigger_input_tokens=8192, object_timing_mode=mode,
        checkpoint_representation_mode=mode, checkpoint_timing=timing,
        checkpoint_representation=representation)
    return config


def config_for(original, plan, task_id, mode):
    return worker_config(original, plan, task_id, ERROR_POLICY,
                         cell_id(TASKS.index(task_id)+1, mode), mode)


def make_notification(messages, state, mode, *, wall_limit):
    require(mode in MODES, 'fixed_P144_mode_required')
    return notification(messages, state, 'not_exposed')


def fixed_fields():
    value = deepcopy(previous_fixed_fields())
    for key in ('original_task_slot', 'diagnostic_task_slot', 'development_gate_met',
                'timing_prefix_until_first_observed_predicate_divergence',
                'actual_dispatch_required_at_first_predicate_divergence',
                'later_attributable_boundary_search', 'same_second_focus_cutoff_required_for_timing',
                'deadline_budget_changes_common_to_both_arms'):
        value.pop(key, None)
    value.update(experiment='P144', batch_id='P144_batch_v01',
        source_runs=[f'P29_{n:02d}_CODE' for n in range(1, 5)],
        object_timing_modes=list(MODES), checkpoint_representation_modes=list(MODES),
        api_budget_by_task_slot=[160,80,80,80], model_seed=257, world_seed=42,
        max_cells=12, max_model_calls=960, max_reserved_tokens=5400000,
        max_reserved_environment_api_requests=1200, max_evaluator_calls=12,
        max_summary_calls_in_batch=24, max_wall_seconds=1800,
        max_setup_seconds=60, max_cleanup_seconds=60,
        trigger_input_tokens=8192, threshold_search=False,
        threshold_selection_after_P142_nonactivation=False,
        threshold_candidates_in_this_phase=[8192],
        threshold_inherited_from_posthoc_P143=True,
        prior_cohort_work_budget_changed=True, prior_cohort_threshold_changed=False,
        cross_cohort_causal_attribution=False, first_summary_admission_unchanged=True,
        common_first_summary_admission_preserved_between_arms=True,
        max_idle_wait_seconds=30, max_evaluation_seconds=60,
        server_max_lifetime_seconds=24900, batch_timeout_seconds=24240,
        pipeline_timeout_seconds=25200,
        latest_launch_jst='2026-10-28T16:15:00+09:00',
        deadline_jst='2026-10-28T23:15:00+09:00',
        reporting_deadline_jst='2026-10-28T23:59:00+09:00',
        primary_comparison=list(COMPARISONS[0][:2]),
        additional_controls=[list(COMPARISONS[1][:2])],
        fixed_comparisons=[list(c) for c in COMPARISONS],
        primary_question='bounded_explicit_state_edits_vs_recursive_and_append_whole_job_utility',
        diagnostic_only=False, scientific_adoption_evaluated=False,
        development_eligibility_evaluated=True,
        development_seed_selected_with_known_activation=False,
        fresh_seed_search=False,
        seed_choice='fixed_257_next_predeclared_increment_after_57_157_no_outcome_search',
        posthoc_task_selection_disclosed=True,
        execution_order_randomized=False, execution_order_balanced_by_task_parity=False,
        execution_order_rotated_by_task=True,
        native_preflight_initial_requests=12, native_preflight_focus_requests=6,
        native_preflight_post_checkpoint_actor_requests=3,
        transport_ID_canonical_prefix_required_for_attribution=True,
        deadline_budget_changes_common_to_all_three_arms=True,
        summary_reference_input_preserved=True, reference_state_content_preserved=True,
        zero_based_positions_specified_in_update_system_prompt=True, parser_and_fragment_limits_unchanged=False,
        merged_summary_and_item_limits_unchanged=True,
        incomplete_cells_retained=True, automatic_retries=0,
        update_old_item_complete_partition_required=True,
        update_default_delete=False, update_atomic_rejection=True,
        update_changed_old_item_on_common_success_required=True,
        per_comparison_requires_all_eight_known_usage=True,
        overall_development_requires_all_twelve_known_usage=True)

    return value


def validate_plan(plan):
    require(all(type(plan.get(k)) is type(v) and plan[k] == v
                for k,v in fixed_fields().items()), 'fixed_P144_scope_changed')
    tasks = plan.get('known_tasks')
    require(type(tasks) is list and len(tasks) == 4
        and all(type(t) is dict for t in tasks)
        and tuple(t.get('task_id') for t in tasks) == TASKS
        and [t.get('source_run') for t in tasks] == [f'P29_{n:02d}_CODE' for n in range(1,5)],
        'fixed_four_known_tasks_required')
    for name in REQUIRED_SOURCES:
        value = plan.get('source_sha256', {}).get(name)
        require(type(value) is str and len(value) == 64
                and all(c in '0123456789abcdef' for c in value), 'bound_P144_sources_required')


def summarize(rows, errors):
    require(type(errors) is list and type(rows) is list and len(rows) == 12,
            'all_twelve_P144_slots_required')
    require([r.get('run_id') for r in rows] == [cell_id(n,m) for n,m in run_order()]
        and all(r.get('task_id') == TASKS[n-1] and r.get('object_timing_mode') == m
            and r.get('checkpoint_representation_mode') == m for r,(n,m) in zip(rows,run_order())),
        'all_twelve_ordered_P144_slots_required')
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
    subtotals = {m:sum(r['known_total_tokens'] for r in rows if r['object_timing_mode'] == m
        and type(r.get('known_total_tokens')) is int and r['known_total_tokens'] >= 0) for m in MODES}
    comparisons = []
    for baseline, candidate, name in COMPARISONS:
        pairs = []
        for task in TASKS:
            a,b = cells[task,baseline],cells[task,candidate]
            complete, both_evaluated = known(a) and known(b), evaluated(a) and evaluated(b)
            evidence = representation_prefix_comparison(a,b)
            update = candidate == MODES[2]
            prompt = b.get('update_prompt_known_focus_calls') if update else b.get('object_prompt_known_focus_calls')
            exposure = b.get('actual_changed_old_known_actor_calls') if update else b.get('actual_delta_known_actor_calls')
            changed = b.get('changed_old_items') if update else None
            active = positive(prompt) and positive(exposure) and (positive(changed) if update else True)
            pairs.append(dict(task_id=task,baseline=baseline,candidate=candidate,
                baseline_success=a.get('success'),candidate_success=b.get('success'),
                both_evaluated=both_evaluated,both_usage_known=complete,
                success_lost=(a['success'] and not b['success']) if both_evaluated else None,
                both_successful=(a['success'] and b['success']) if both_evaluated else None,
                candidate_minus_baseline_tokens=b['known_total_tokens']-a['known_total_tokens'] if complete else None,
                candidate_prompt_known_focus_calls=prompt,candidate_changed_view_known_actor_calls=exposure,
                candidate_changed_old_items=changed,
                strict_prefix_match=evidence.get('strict_match'),canonical_prefix_match=evidence.get('canonical_match'),
                actual_intervention=bool(active and evidence.get('canonical_match') is True),
                representation_prefix_identity=evidence))
        complete = all(p['both_usage_known'] for p in pairs)
        common = [p for p in pairs if p['both_successful'] is True]
        difference = sum(p['candidate_minus_baseline_tokens'] for p in pairs) if complete else None
        common_difference = sum(p['candidate_minus_baseline_tokens'] for p in common) if complete and common else None
        paired_rows = [cells[t,m] for t in TASKS for m in (baseline,candidate)]
        intact = all(r.get(k+'_contract_failed') is False and r.get(k+'_accounting_complete') is True
                     for r in paired_rows for k in ('prefix_exposure','checkpoint_representation','delta_envelope','state_update'))
        active = any(p['actual_intervention'] for p in common)
        matched = all(p['canonical_prefix_match'] is True for p in pairs
                      if positive(p['candidate_prompt_known_focus_calls']))
        utility = bool(complete and not errors and common and not any(p['success_lost'] for p in pairs)
                       and difference < 0 and common_difference < 0)
        gate = bool(utility and intact and active and matched)
        comparisons.append(dict(name=name,baseline=baseline,candidate=candidate,pairs=pairs,
            all_pairs_complete_with_known_usage=complete,all_four_pairs_complete_with_known_usage=complete,
            all_task_token_difference=difference,
            all_task_token_difference_pct=100*difference/subtotals[baseline] if complete and subtotals[baseline] else None,
            common_success_tasks=[p['task_id'] for p in common],common_success_token_difference=common_difference,
            success_loss_tasks=[p['task_id'] for p in pairs if p['success_lost'] is True],
            changed_intervention_on_common_success=active,all_activated_canonical_prefixes_match=matched,
            observed_utility_criteria_met=utility,comparison_gate_met=gate,attribution_prefix_required=True))
    complete = all(known(r) for r in rows)
    gate = bool(complete and all(c['comparison_gate_met'] for c in comparisons[:2]))
    return dict(planned_rows=12,independent_tasks=4,repetitions=1,model_seed=257,
        all_twelve_complete_with_known_usage=complete,evaluated_conditions=sum(evaluated(r) for r in rows),
        success_counts={m:sum(evaluated(r) and r['success'] for r in rows if r['object_timing_mode']==m) for m in MODES},
        unevaluated_counts={m:sum(not evaluated(r) for r in rows if r['object_timing_mode']==m) for m in MODES},
        known_token_subtotals_by_mode=subtotals,total_tokens_by_mode=subtotals if complete else {m:None for m in MODES},
        usage_count_missing_conditions=sum(type(r.get('unknown_usage_calls')) is not int for r in rows),
        recorded_unknown_usage_calls=sum(r['unknown_usage_calls'] for r in rows if type(r.get('unknown_usage_calls')) is int),
        comparisons=comparisons,audit_errors_count=len(errors),development_gate_met=gate,
        scientific_adoption_evaluated=False,reserved_confirmation_replaced=False,
        all_original_four_task_confirmation_replaced=False,prior_results_pooled=False,unknown_usage_imputed=False,
        novel_method_claim=False,general_quality_preservation_claim=False,independent_replication_claim=False,
        exposure_is_guaranteed_savings=False,competitive_ratio_claim=False,
        interpretation='Three fixed arms on four known tasks, seed257, common threshold8192/work1800. '
        'An explicit complete keep/update/delete/add partition is applied atomically to the old four-field state. '
        'Each pairwise difference requires all eight paired cells evaluated with known usage; all twelve are required for overall eligibility. '
        'The candidate must beat both recursive and append controls without losing a paired success and with a changed old item reaching a common-success actor. '
        'This post-P143 design is not unseen confirmation or a demonstration of general quality, novelty, or a component-isolated effect. '
        'Prior cohorts are not pooled; unknown usage remains unknown.')
