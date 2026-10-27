"""Fixed P139 development factorial; no generation or automatic study selection."""
from copy import deepcopy
import json
from pathlib import Path

from budget_observation import notification
from budget_visibility_comparison import ERROR_POLICY
from late_clock_comparison import initial_conversation
from receipt_reasoning_history import require
from whole_task_prefix_exposure_p138 import fixed_fields as previous_fixed_fields
from whole_task_tool_choice import worker_config as original_worker_config

ROOT = Path(__file__).resolve().parents[1]
MODES = ('threshold_recursive', 'threshold_delta', 'exposure_recursive', 'exposure_delta')
TASKS = ('34d9492_1', '3c13f5a_1', '60d0b5b_1', '6104387_1')
PLAN = 'configs/P139_whole_task_checkpoint_representation_v01.json'
PREFLIGHT = 'reports/P139_initial_checks.json'
ACTIVATION = 'reports/P139_activation_v01.json'
COMPARISONS = (
    ('threshold_recursive', 'exposure_delta', 'primary_utility'),
    ('exposure_recursive', 'exposure_delta', 'representation_at_exposure'),
    ('threshold_delta', 'exposure_delta', 'timing_with_delta'),
    ('threshold_recursive', 'threshold_delta', 'representation_at_threshold'),
    ('threshold_recursive', 'exposure_recursive', 'timing_with_recursive'),
)


def factors(mode):
    require(mode in MODES, 'fixed_P139_mode_required')
    return tuple(mode.split('_'))


def run_order():
    return [(n, MODES[(n - 1 + k) % 4]) for n in range(1, 5) for k in range(4)]


def cell_id(number, mode):
    require(type(number) is int and number in range(1, 5) and mode in MODES,
            'outside_fixed_P139_comparison')
    return f'BOC_P139_{number:02d}_{mode.upper()}'


def worker_config(original, plan, task_id, arm, run_id, checkpoint_representation_mode):
    tasks = [t['task_id'] for t in plan['known_tasks']]
    require(tuple(tasks) == TASKS and task_id in tasks, 'fixed_four_known_tasks_required')
    mode = checkpoint_representation_mode
    require(run_id == cell_id(tasks.index(task_id) + 1, mode), 'fixed_P139_cell_required')
    config = original_worker_config(original, plan, task_id, arm, run_id, 'auto')
    require(config['max_api_requests'] == [160, 80, 80, 80][tasks.index(task_id)]
            and config['draft_temperature'] == 0.7, 'unchanged_task_and_sampling_limits')
    timing, representation = factors(mode)
    config.update(checkpoint_policy='rolling_separate', read_views_enabled=False,
        inline_checkpoint_requirement='not_applicable', rolling_checkpoint_max_opportunities=2,
        rolling_min_fresh_turns=3, checkpoint_representation_mode=mode,
        checkpoint_timing=timing, checkpoint_representation=representation)
    return config


def config_for(original, plan, task_id, mode):
    return worker_config(original, plan, task_id, ERROR_POLICY,
                         cell_id(TASKS.index(task_id) + 1, mode), mode)


def make_notification(messages, state, mode, *, wall_limit):
    require(mode in MODES, 'fixed_P139_mode_required')
    return notification(messages, state, 'not_exposed')


def fixed_fields():
    value = deepcopy(previous_fixed_fields())
    for key in ('prefix_exposure_modes', 'timing_control_comparison'):
        value.pop(key, None)
    value.update(experiment='P139', batch_id='P139_batch_v01',
        checkpoint_representation_modes=list(MODES), rolling_checkpoint_max_opportunities=2,
        repetitions=1, max_cells=16, max_model_calls=1280, max_reserved_tokens=7200000,
        max_reserved_environment_api_requests=1600, max_evaluator_calls=16,
        max_summary_calls_in_batch=32, server_max_lifetime_seconds=43200,
        batch_timeout_seconds=40000, pipeline_timeout_seconds=44400,
        latest_launch_jst='2026-10-27T20:00:00+09:00',
        deadline_jst='2026-10-28T08:00:00+09:00',
        primary_comparison=['threshold_recursive', 'exposure_delta'],
        additional_controls=['exposure_recursive', 'threshold_delta'],
        factorial_comparisons=[list(c) for c in COMPARISONS],
        second_opportunity_only_representation_change=True,
        combined_summary_characters=8192, combined_field_items=32,
        individual_summary_item_characters=2048,
        summary_reference_input_preserved=True,
        primary_question='checkpoint_timing_by_second_summary_representation',
        development_seed_selected_with_known_activation=True,
        independent_replication_claim=False, original_max3_control_reproduced=False,
        representation_prefix_match_required_for_attribution=True,
        native_preflight_initial_requests=16, native_preflight_focus_requests=4,
        native_preflight_post_checkpoint_actor_requests=2)
    return value


def validate_plan(plan):
    require(all(type(plan.get(k)) is type(v) and plan[k] == v for k, v in fixed_fields().items()),
            'fixed_P139_scope_changed')
    tasks = plan.get('known_tasks')
    require(type(tasks) is list and len(tasks) == 4
        and tuple(t.get('task_id') for t in tasks) == TASKS
        and [t.get('source_run') for t in tasks] == [f'P29_{n:02d}_CODE' for n in range(1, 5)],
        'fixed_four_known_tasks_required')
    for name in ('configs/P123_whole_task_rolling_checkpoint_v01.json',
        'scripts/checkpoint_representation_p139.py',
        'scripts/checkpoint_representation_inference_p139.py',
        'scripts/checkpoint_representation_preflight_p139.py',
        'scripts/run_whole_task_checkpoint_representation_cell_p139.py',
        'scripts/audit_checkpoint_representation_trace_p139.py',
        'scripts/audit_whole_task_checkpoint_representation_p139.py',
        'scripts/serve_research_model_recovery.py',
        'reports/P138_comparison.json', 'reports/P138_server_session.json',
        'reports/P138_task4_API_progress_metadata_20261027.json',
        'docs/experiments/P139_checkpoint_representation_draft_20261027.md'):
        digest = plan.get('source_sha256', {}).get(name)
        require(type(digest) is str and len(digest) == 64
            and all(c in '0123456789abcdef' for c in digest), 'bound_P139_sources_required')


PREFIX_FIELDS = ('after_model_calls', 'previous_cutoff', 'candidate_cutoff',
    'accumulated_exposure', 'previous_focus_cost', 'first_checkpoint',
    'prior_request_output_sequence', 'all_prior_terminal_usage_known',
    'prior_summary_notes_sha256')


def representation_prefix_match(a, b):
    """Exclude treatment-specific focus prompt/delta flag; absence is not equality."""
    left, right = (r.get('representation_second_opportunity') for r in (a, b))
    if not isinstance(left, dict) or not isinstance(right, dict):
        return None
    if not all(k in x for x in (left, right) for k in PREFIX_FIELDS):
        return False
    if any(x['all_prior_terminal_usage_known'] is not True or x['first_checkpoint'] is None
           for x in (left, right)):
        return False
    for x in (left, right):
        if any(type(x[k]) is not int or x[k] < 0 for k in
               ('after_model_calls', 'previous_cutoff', 'candidate_cutoff', 'accumulated_exposure')):
            return False
        if type(x['previous_focus_cost']) is not int or x['previous_focus_cost'] <= 0:
            return False
        if not isinstance(x['first_checkpoint'], dict) or not isinstance(x['prior_request_output_sequence'], list):
            return False
        first = x['first_checkpoint']
        required = ('cutoff', 'opportunity_index', 'after_model_calls',
                    'summary_note_sha256', 'summary_notes_sha256', 'fragment_budget')
        if not all(k in first for k in required):
            return False
        if any(type(first[k]) is not int for k in ('cutoff', 'opportunity_index', 'after_model_calls')):
            return False
        if (first['opportunity_index'] != 1 or first['cutoff'] != x['previous_cutoff']
                or not 0 < first['after_model_calls'] <= x['after_model_calls']
                or x['candidate_cutoff'] <= x['previous_cutoff']
                or len(x['prior_request_output_sequence']) != x['after_model_calls']):
            return False
        def valid_hash(v):
            return type(v) is str and len(v) == 64 and all(c in '0123456789abcdef' for c in v)
        if not all(valid_hash(v) for v in (first['summary_note_sha256'],
                first['summary_notes_sha256'], x['prior_summary_notes_sha256'])):
            return False
        if first['summary_notes_sha256'] != x['prior_summary_notes_sha256']:
            return False
        if not isinstance(first['fragment_budget'], dict) or not first['fragment_budget']:
            return False
        for index, record in enumerate(x['prior_request_output_sequence'], 1):
            if (not isinstance(record, dict) or record.get('call_id') != f'call_{index:03d}'
                    or record.get('role') not in ('agent', 'focus') or record.get('status') != 'ok'
                    or not valid_hash(record.get('request_sha256'))
                    or not valid_hash(record.get('known_assistant_message_sha256'))):
                return False
    # JSON preserves bool/int/float distinctions, including nested evidence.
    return json.dumps({k:left[k] for k in PREFIX_FIELDS}, sort_keys=True, allow_nan=False) == \
        json.dumps({k:right[k] for k in PREFIX_FIELDS}, sort_keys=True, allow_nan=False)


def positive(value):
    return type(value) is int and value > 0


def summarize(rows, errors):
    require(type(errors) is list, 'audit_errors_list_required')
    require(len(rows) == 16 and len({(r['task_id'], r['checkpoint_representation_mode']) for r in rows}) == 16
        and {(r['task_id'], r['checkpoint_representation_mode']) for r in rows}
            == {(t, m) for t in TASKS for m in MODES}, 'all_sixteen_P139_slots_required')
    cells = {(r['task_id'], r['checkpoint_representation_mode']): r for r in rows}
    comparisons = []
    for baseline, candidate, label in COMPARISONS:
        ta, ra = factors(baseline); tb, rb = factors(candidate)
        representation_only, timing_only = ta == tb and ra != rb, ta != tb and ra == rb
        pairs = []
        for task in TASKS:
            a, b = cells[task, baseline], cells[task, candidate]
            evaluated = all(r['record_status'] == 'evaluated' and type(r['success']) is bool for r in (a, b))
            known = evaluated and all(type(r.get('unknown_usage_calls')) is int and r['unknown_usage_calls'] == 0
                and type(r.get('known_total_tokens')) is int and r['known_total_tokens'] >= 0 for r in (a, b))
            timing_change = b.get('actual_decision_differences_from_' + ta) if ta != tb else 0
            delta_calls = b.get('actual_delta_known_actor_calls') if rb != ra else 0
            prefix_match = representation_prefix_match(a, b) if representation_only else None
            intervention = (positive(delta_calls) and prefix_match is True if representation_only
                else positive(timing_change) if timing_only else positive(delta_calls) or positive(timing_change))
            pairs.append(dict(task_id=task, baseline=baseline, candidate=candidate,
                baseline_success=a['success'], candidate_success=b['success'],
                both_evaluated=evaluated, both_usage_known=known,
                success_lost=(a['success'] and not b['success']) if evaluated else None,
                both_successful=(a['success'] and b['success']) if evaluated else None,
                candidate_minus_baseline_tokens=b['known_total_tokens']-a['known_total_tokens'] if known else None,
                actual_timing_decision_differences=timing_change,
                candidate_delta_known_actor_calls=delta_calls,
                representation_prefix_match=prefix_match, actual_intervention=intervention))
        complete = all(p['both_usage_known'] for p in pairs)
        common = [p for p in pairs if p['both_successful'] is True]
        delta = sum(p['candidate_minus_baseline_tokens'] for p in pairs) if complete else None
        common_delta = sum(p['candidate_minus_baseline_tokens'] for p in common) if complete and common else None
        changed = any(p['actual_intervention'] for p in common)
        intact = all(cells[t, m].get('prefix_exposure_contract_failed') is False
            and cells[t, m].get('prefix_exposure_accounting_complete') is True
            and cells[t, m].get('checkpoint_representation_contract_failed') is False
            and cells[t, m].get('checkpoint_representation_accounting_complete') is True
            for t in TASKS for m in (baseline, candidate))
        prefixes = (all(p['representation_prefix_match'] is True for p in pairs
            if positive(p['candidate_delta_known_actor_calls'])) if representation_only else None)
        gate = bool(complete and not errors and intact and common and changed
            and not any(p['success_lost'] for p in pairs) and delta < 0 and common_delta < 0
            and (not representation_only or prefixes is True))
        comparisons.append(dict(name=label, baseline=baseline, candidate=candidate, pairs=pairs,
            representation_only=representation_only, timing_only=timing_only,
            all_four_pairs_complete_with_known_usage=complete, all_task_token_difference=delta,
            common_success_tasks=[p['task_id'] for p in common], common_success_token_difference=common_delta,
            changed_intervention_on_common_success=changed,
            all_activated_representation_prefixes_match=prefixes, comparison_gate_met=gate))
    all_known = all(r['record_status'] == 'evaluated' and type(r['success']) is bool
        and type(r.get('unknown_usage_calls')) is int and r['unknown_usage_calls'] == 0
        and type(r.get('known_total_tokens')) is int and r['known_total_tokens'] >= 0 for r in rows)
    totals = {m: sum(r['known_total_tokens'] for r in rows if r['checkpoint_representation_mode'] == m
                    and type(r.get('known_total_tokens')) is int) for m in MODES}
    adopted = all(c['comparison_gate_met'] for c in comparisons[:3])
    return dict(planned_rows=16, independent_tasks=4, repetitions=1, model_seed=57,
        all_sixteen_complete_with_known_usage=all_known,
        success_counts={m: sum(r['success'] is True for r in rows if r['checkpoint_representation_mode'] == m) for m in MODES},
        known_token_subtotals_by_mode=totals, total_tokens_by_mode=totals if all_known else {m: None for m in MODES},
        usage_count_missing_conditions=sum(type(r.get('unknown_usage_calls')) is not int for r in rows),
        recorded_unknown_usage_calls=sum(r['unknown_usage_calls'] for r in rows if type(r.get('unknown_usage_calls')) is int),
        comparisons=comparisons, primary_utility_gate_met=comparisons[0]['comparison_gate_met'],
        both_control_development_gate_met=adopted, combination_development_gate_met=adopted,
        development_gate_met=adopted, prior_results_pooled=False, unknown_usage_imputed=False,
        exposure_is_guaranteed_savings=False, competitive_ratio_claim=False, novel_method_claim=False,
        general_quality_preservation_claim=False, independent_replication_claim=False,
        interpretation='Known four-task seed57 development factorial, maximum two opportunities. '
            'Threshold-plus-delta is included. All failures, prefix mismatches and inactive cells remain. '
            'Prefix agreement is recorded evidence, not a general causal or semantic guarantee.')
