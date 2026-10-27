"""P141: one known-task timing diagnostic, never a scientific adoption gate."""
from copy import deepcopy
from pathlib import Path

from budget_observation import notification
from budget_visibility_comparison import ERROR_POLICY
from late_clock_comparison import initial_conversation
from receipt_reasoning_history import require
from whole_task_checkpoint_delta_envelope_p140 import fixed_fields as previous_fixed_fields
from whole_task_tool_choice import worker_config as original_worker_config

ROOT = Path(__file__).resolve().parents[1]
MODES = ('threshold_recursive', 'threshold_delta_object', 'exposure_delta_object')
TASKS = ('6104387_1',)
PLAN = 'configs/P141_object_timing_v01.json'
PREFLIGHT = 'reports/P141_initial_checks.json'
ACTIVATION = 'reports/P141_activation_v01.json'
MATERIAL = 'materials/20261028_p141_results'
COMPARISONS = (('threshold_delta_object', 'exposure_delta_object', 'object_timing'),
               ('threshold_recursive', 'exposure_delta_object', 'strong_control'),
               ('threshold_recursive', 'threshold_delta_object', 'representation_prompt_bundle'))
REQUIRED_SOURCES = (
    'configs/P123_whole_task_rolling_checkpoint_v01.json',
    'configs/P140_whole_task_checkpoint_delta_envelope_v01.json',
    'scripts/whole_task_object_timing_p141.py',
    'scripts/checkpoint_object_timing_p141.py',
    'scripts/checkpoint_object_timing_inference_p141.py',
    'scripts/checkpoint_object_timing_preflight_p141.py',
    'scripts/audit_object_timing_trace_p141.py',
    'scripts/object_timing_prefix_p141.py',
    'scripts/run_whole_task_object_timing_cell_p141.py',
    'scripts/run_whole_task_object_timing_p141.py',
    'scripts/run_whole_task_object_timing_pipeline_p141.py',
    'scripts/prepare_whole_task_object_timing_p141.py',
    'scripts/object_timing_server_identity_p141.py',
    'scripts/audit_whole_task_object_timing_p141.py',
    'scripts/inspect_whole_task_object_timing_session_p141.py',
    'scripts/build_object_timing_summary_p141.py',
    'scripts/serve_research_model_recovery.py',
    'tests/test_object_timing_p141.py',
    'tests/test_object_timing_driver_p141.py',
    'tests/test_object_timing_prepare_p141.py',
    'tests/test_object_timing_worker_trace_p141.py',
    'tests/test_object_timing_reporting_p141.py',
    'tests/object_timing_worker_fixture_p141.py',
    'docs/experiments/P141_object_timing_diagnostic_20261028.md')


def factors(mode):
    require(mode in MODES, 'fixed_P141_mode_required')
    return ('exposure' if mode == MODES[2] else 'threshold',
            'recursive' if mode == MODES[0] else 'delta')


def run_order():
    return [(1, mode) for mode in MODES]


def cell_id(number, mode):
    require(type(number) is int and number == 1 and mode in MODES,
            'outside_fixed_P141_diagnostic')
    return f'BOC_P141_{number:02d}_{mode.upper()}'


def worker_config(original, plan, task_id, arm, run_id, object_timing_mode):
    require(tuple(t['task_id'] for t in plan['known_tasks']) == TASKS
            and task_id == TASKS[0]
            and [t['source_run'] for t in plan['known_tasks']] == ['P29_04_CODE'],
            'fixed_original_Task4_as_P141_slot1_required')
    mode = object_timing_mode
    require(run_id == cell_id(1, mode), 'fixed_P141_cell_required')
    config = original_worker_config(original, plan, task_id, arm, run_id, 'auto')
    require(config['max_api_requests'] == 80 and config['draft_temperature'] == 0.7,
            'unchanged_Task4_API_and_sampling_limits')
    timing, representation = factors(mode)
    config.update(checkpoint_policy='rolling_separate', read_views_enabled=False,
        inline_checkpoint_requirement='not_applicable', rolling_checkpoint_max_opportunities=2,
        rolling_min_fresh_turns=3, object_timing_mode=mode,
        checkpoint_representation_mode=mode, checkpoint_timing=timing,
        checkpoint_representation=representation)
    return config


def config_for(original, plan, task_id, mode):
    return worker_config(original, plan, task_id, ERROR_POLICY, cell_id(1, mode), mode)


def make_notification(messages, state, mode, *, wall_limit):
    require(mode in MODES, 'fixed_P141_mode_required')
    return notification(messages, state, 'not_exposed')


def fixed_fields():
    value = deepcopy(previous_fixed_fields())
    for key in ('second_opportunity_only_object_prompt_change', 'legacy_delta_control_preserved',
                'transport_ID_canonical_prefix_required_for_attribution'):
        value.pop(key, None)
    value.update(experiment='P141', batch_id='P141_batch_v01',
        source_runs=['P29_04_CODE'], object_timing_modes=list(MODES),
        checkpoint_representation_modes=list(MODES), api_budget_by_task_slot=[80],
        repetitions=1, max_cells=3, max_model_calls=240, max_reserved_tokens=1350000,
        max_reserved_environment_api_requests=240, max_evaluator_calls=3,
        max_summary_calls_in_batch=6, server_max_lifetime_seconds=9000,
        batch_timeout_seconds=7200, pipeline_timeout_seconds=9600,
        latest_launch_jst='2026-10-28T03:00:00+09:00',
        deadline_jst='2026-10-28T05:30:00+09:00',
        reporting_deadline_jst='2026-10-28T06:30:00+09:00',
        primary_comparison=list(COMPARISONS[0][:2]), additional_controls=['threshold_recursive'],
        fixed_comparisons=[list(c) for c in COMPARISONS],
        primary_question='known_Task4_object_delta_timing_diagnostic',
        original_task_slot=4, diagnostic_task_slot=1, diagnostic_only=True,
        scientific_adoption_evaluated=False, development_gate_met=False,
        all_original_four_task_confirmation_replaced=False,
        reserved_confirmation_replaced=False, prior_results_pooled=False,
        posthoc_task_selection_disclosed=True,
        execution_order_randomized=False, host_and_order_effects_excluded=False,
        logical_cached_input_deducted=False,
        timing_prefix_until_first_observed_predicate_divergence=True,
        actual_dispatch_required_at_first_predicate_divergence=True,
        later_attributable_boundary_search=False,
        same_second_focus_cutoff_required_for_timing=False,
        native_preflight_initial_requests=3, native_preflight_focus_requests=3,
        native_preflight_post_checkpoint_actor_requests=2)
    return value


def validate_plan(plan):
    require(all(type(plan.get(k)) is type(v) and plan[k] == v
                for k, v in fixed_fields().items()), 'fixed_P141_scope_changed')
    tasks = plan.get('known_tasks')
    require(type(tasks) is list and len(tasks) == 1 and type(tasks[0]) is dict
        and tasks[0].get('task_id') == TASKS[0]
        and tasks[0].get('source_run') == 'P29_04_CODE',
        'fixed_original_Task4_as_P141_slot1_required')
    for name in REQUIRED_SOURCES:
        value = plan.get('source_sha256', {}).get(name)
        require(type(value) is str and len(value) == 64
                and all(c in '0123456789abcdef' for c in value), 'bound_P141_sources_required')


def _timing_prefix(a, b):
    if not a.get('timing_decision_prefixes') or not b.get('timing_decision_prefixes'):
        return dict(boundary_present=False, after_model_calls=None, strict_match=None,
            canonical_match=None, actual_dispatch_diverged=False, both_dispatches_known=False,
            reason='timing_prefix_evidence_unavailable')
    from object_timing_prefix_p141 import timing_prefix_comparison
    return timing_prefix_comparison(a, b)


def summarize(rows, errors):
    require(type(errors) is list, 'audit_errors_list_required')
    require(type(rows) is list and len(rows) == 3
        and [r.get('run_id') for r in rows] == [cell_id(n, m) for n, m in run_order()]
        and all(r.get('task_id') == TASKS[0]
                and r.get('object_timing_mode') == mode
                and r.get('checkpoint_representation_mode') == mode
                for r, mode in zip(rows, MODES)), 'all_three_ordered_P141_slots_required')
    cells = dict(zip(MODES, rows))

    def evaluated(r):
        return r['record_status'] == 'evaluated' and type(r.get('success')) is bool

    def known(r):
        return (evaluated(r) and type(r.get('unknown_usage_calls')) is int
            and r['unknown_usage_calls'] == 0 and type(r.get('known_total_tokens')) is int
            and r['known_total_tokens'] >= 0)

    comparisons = []
    for baseline, candidate, name in COMPARISONS:
        a, b = cells[baseline], cells[candidate]
        complete, both_evaluated = known(a) and known(b), evaluated(a) and evaluated(b)
        common = both_evaluated and a['success'] and b['success']
        timing = _timing_prefix(a, b) if name == 'object_timing' else None
        representation = None
        if name == 'representation_prompt_bundle':
            from checkpoint_prefix_identity_p140 import representation_prefix_comparison
            representation = representation_prefix_comparison(a, b)
        evidence = timing if timing is not None else representation
        difference = b['known_total_tokens'] - a['known_total_tokens'] if complete else None
        pair = dict(task_id=TASKS[0], baseline=baseline, candidate=candidate,
            baseline_success=a.get('success'), candidate_success=b.get('success'),
            both_evaluated=both_evaluated, both_usage_known=complete,
            success_lost=(a['success'] and not b['success']) if both_evaluated else None,
            both_successful=common if both_evaluated else None,
            candidate_minus_baseline_tokens=difference,
            candidate_object_prompt_known_focus_calls=b.get('object_prompt_known_focus_calls'),
            candidate_delta_known_actor_calls=b.get('actual_delta_known_actor_calls'),
            strict_prefix_match=evidence.get('strict_match') if evidence else None,
            canonical_prefix_match=evidence.get('canonical_match') if evidence else None,
            actual_timing_dispatch_diverged=timing['actual_dispatch_diverged'] if timing else None,
            both_timing_dispatches_known=timing['both_dispatches_known'] if timing else None)
        comparisons.append(dict(name=name, baseline=baseline, candidate=candidate, pairs=[pair],
            descriptive_only=True, all_pairs_complete_with_known_usage=complete,
            all_task_token_difference=difference,
            common_success_tasks=list(TASKS) if common else [],
            common_success_token_difference=difference if common and complete else None,
            timing_prefix_identity=timing, representation_prefix_identity=representation,
            scientific_adoption_evaluated=False, comparison_gate_met=False))
    all_known = all(known(r) for r in rows)
    subtotals = {m: r.get('known_total_tokens') if type(r.get('known_total_tokens')) is int
                 and r['known_total_tokens'] >= 0 else None for m, r in cells.items()}
    return dict(planned_rows=3, independent_tasks=1, repetitions=1, model_seed=57,
        original_task_slot=4, diagnostic_task_slot=1, diagnostic_only=True,
        all_three_complete_with_known_usage=all_known,
        evaluated_conditions=sum(evaluated(r) for r in rows),
        success_counts={m: int(r.get('success') is True and evaluated(r)) for m, r in cells.items()},
        unevaluated_counts={m: int(not evaluated(r)) for m, r in cells.items()},
        known_token_subtotals_by_mode=subtotals,
        total_tokens_by_mode=subtotals if all_known else {m: None for m in MODES},
        usage_count_missing_conditions=sum(type(r.get('unknown_usage_calls')) is not int for r in rows),
        recorded_unknown_usage_calls=sum(r['unknown_usage_calls'] for r in rows
                                        if type(r.get('unknown_usage_calls')) is int),
        comparisons=comparisons, audit_errors_count=len(errors),
        scientific_adoption_evaluated=False, development_gate_met=False,
        prior_results_pooled=False, unknown_usage_imputed=False,
        all_original_four_task_confirmation_replaced=False, reserved_confirmation_replaced=False,
        exposure_is_guaranteed_savings=False, competitive_ratio_claim=False,
        novel_method_claim=False, general_quality_preservation_claim=False,
        independent_replication_claim=False,
        interpretation='Posthoc diagnostic on the single known original Task4, seed57, three fixed slots. '
        'All comparisons are descriptive; no result can pass a scientific adoption gate. '
        'Timing attribution compares the prefix before the first observed predicate divergence and '
        'requires differing actual dispatches at that boundary; it never searches later boundaries. '
        'Equal second-focus cutoffs are not required. '
        'The strong control and representation-plus-prompt bundle are retained. '
        'Order is not randomized; cache and host effects remain, and timing can change payloads and trajectories. '
        'No P140 outcome is pooled or replaced, and neither the original four-task scope nor reserved12 confirmation is replaced.')
