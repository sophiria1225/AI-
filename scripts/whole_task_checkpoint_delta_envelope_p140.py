"""P140 known-task development test of an explicit delta-object prompt contract."""
from copy import deepcopy
from pathlib import Path

from budget_observation import notification
from budget_visibility_comparison import ERROR_POLICY
from late_clock_comparison import initial_conversation
from receipt_reasoning_history import require
from whole_task_checkpoint_representation_p139 import (fixed_fields as previous_fixed_fields,
    representation_prefix_match as strict_prefix_match)
from whole_task_tool_choice import worker_config as original_worker_config

ROOT = Path(__file__).resolve().parents[1]
MODES = ('threshold_recursive', 'exposure_delta', 'exposure_delta_object')
TASKS = ('34d9492_1', '3c13f5a_1', '60d0b5b_1', '6104387_1')
PLAN = 'configs/P140_whole_task_checkpoint_delta_envelope_v01.json'
PREFLIGHT = 'reports/P140_initial_checks.json'
ACTIVATION = 'reports/P140_activation_v01.json'
MATERIAL = 'materials/20261028_p140_results'
COMPARISONS = (('threshold_recursive', 'exposure_delta_object', 'primary_utility'),
               ('exposure_delta', 'exposure_delta_object', 'object_contract_at_exposure'))
REQUIRED_SOURCES = (
    'configs/P123_whole_task_rolling_checkpoint_v01.json',
    'configs/P139_whole_task_checkpoint_representation_v01.json',
    'scripts/checkpoint_delta_envelope_p140.py',
    'scripts/checkpoint_prefix_identity_p140.py',
    'scripts/checkpoint_delta_envelope_inference_p140.py',
    'scripts/checkpoint_delta_envelope_preflight_p140.py',
    'scripts/run_whole_task_checkpoint_delta_envelope_cell_p140.py',
    'scripts/audit_checkpoint_delta_envelope_trace_p140.py',
    'scripts/audit_whole_task_checkpoint_delta_envelope_p140.py',
    'scripts/serve_research_model_recovery.py',
    'reports/P139_comparison.json', 'reports/P139_server_session.json',
    'reports/P139_results_provenance_20261027.json',
    'docs/experiments/P140_checkpoint_delta_envelope_draft_20261027.md')


def factors(mode):
    require(mode in MODES, 'fixed_P140_mode_required')
    return ('threshold', 'recursive') if mode == MODES[0] else ('exposure', 'delta')


def run_order():
    return [(n, MODES[(n-1+k) % 3]) for n in range(1,5) for k in range(3)]


def cell_id(number, mode):
    require(type(number) is int and number in range(1,5) and mode in MODES,
            'outside_fixed_P140_comparison')
    return f'BOC_P140_{number:02d}_{mode.upper()}'


def worker_config(original, plan, task_id, arm, run_id, checkpoint_representation_mode):
    tasks = [t['task_id'] for t in plan['known_tasks']]
    require(tuple(tasks) == TASKS and task_id in tasks, 'fixed_four_known_tasks_required')
    mode = checkpoint_representation_mode
    require(run_id == cell_id(tasks.index(task_id)+1, mode), 'fixed_P140_cell_required')
    config = original_worker_config(original, plan, task_id, arm, run_id, 'auto')
    require(config['max_api_requests'] == [160,80,80,80][tasks.index(task_id)]
            and config['draft_temperature'] == 0.7, 'unchanged_task_and_sampling_limits')
    timing, representation = factors(mode)
    config.update(checkpoint_policy='rolling_separate', read_views_enabled=False,
        inline_checkpoint_requirement='not_applicable', rolling_checkpoint_max_opportunities=2,
        rolling_min_fresh_turns=3, checkpoint_representation_mode=mode,
        checkpoint_timing=timing, checkpoint_representation=representation)
    return config


def config_for(original, plan, task_id, mode):
    return worker_config(original, plan, task_id, ERROR_POLICY,
                         cell_id(TASKS.index(task_id)+1, mode), mode)


def make_notification(messages, state, mode, *, wall_limit):
    require(mode in MODES, 'fixed_P140_mode_required')
    return notification(messages, state, 'not_exposed')


def fixed_fields():
    value = deepcopy(previous_fixed_fields())
    for key in ('factorial_comparisons', 'representation_prefix_match_required_for_attribution'):
        value.pop(key, None)
    value.update(experiment='P140', batch_id='P140_batch_v01',
        checkpoint_representation_modes=list(MODES), rolling_checkpoint_max_opportunities=2,
        repetitions=1, max_cells=12, max_model_calls=960, max_reserved_tokens=5400000,
        max_reserved_environment_api_requests=1200, max_evaluator_calls=12,
        max_summary_calls_in_batch=24, server_max_lifetime_seconds=30000,
        batch_timeout_seconds=28200, pipeline_timeout_seconds=30600,
        latest_launch_jst='2026-10-27T23:30:00+09:00', deadline_jst='2026-10-28T08:00:00+09:00',
        primary_comparison=list(COMPARISONS[0][:2]), additional_controls=['exposure_delta'],
        fixed_comparisons=[list(c) for c in COMPARISONS],
        primary_question='explicit_single_delta_object_prompt_under_unchanged_parser_and_budget',
        second_opportunity_only_object_prompt_change=True,
        legacy_delta_control_preserved=True, parser_and_fragment_limits_unchanged=True,
        posthoc_development_reason_disclosed=True, previous_results_modified=False,
        transport_ID_canonical_prefix_required_for_attribution=True,
        strict_prefix_reported_separately=True,
        native_preflight_initial_requests=12, native_preflight_focus_requests=4,
        native_preflight_post_checkpoint_actor_requests=2)
    return value


def validate_plan(plan):
    require(all(type(plan.get(k)) is type(v) and plan[k] == v for k,v in fixed_fields().items()),
            'fixed_P140_scope_changed')
    tasks = plan.get('known_tasks')
    require(type(tasks) is list and len(tasks)==4 and tuple(t.get('task_id') for t in tasks)==TASKS
        and [t.get('source_run') for t in tasks]==[f'P29_{n:02d}_CODE' for n in range(1,5)],
        'fixed_four_known_tasks_required')
    for name in REQUIRED_SOURCES:
        value=plan.get('source_sha256',{}).get(name)
        require(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value),
                'bound_P140_sources_required')


def canonical_prefix_match(a,b):
    from checkpoint_prefix_identity_p140 import representation_prefix_comparison
    return representation_prefix_comparison(a,b)['canonical_match']


def positive(value):
    return type(value) is int and value>0


def summarize(rows, errors):
    require(type(errors) is list, 'audit_errors_list_required')
    require(len(rows)==12 and len({(r['task_id'],r['checkpoint_representation_mode']) for r in rows})==12
        and {(r['task_id'],r['checkpoint_representation_mode']) for r in rows}=={(t,m) for t in TASKS for m in MODES},
        'all_twelve_P140_slots_required')
    cells={(r['task_id'],r['checkpoint_representation_mode']):r for r in rows}
    def known(r):
        return (r['record_status']=='evaluated' and type(r['success']) is bool
            and type(r.get('unknown_usage_calls')) is int and r['unknown_usage_calls']==0
            and type(r.get('known_total_tokens')) is int and r['known_total_tokens']>=0)
    comparisons=[]
    for baseline,candidate,name in COMPARISONS:
        attributable=baseline=='exposure_delta';pairs=[]
        for task in TASKS:
            a,b=cells[task,baseline],cells[task,candidate]
            evaluated=all(r['record_status']=='evaluated' and type(r['success']) is bool for r in (a,b))
            complete=known(a) and known(b)
            strict=strict_prefix_match(a,b) if attributable else None
            canonical=canonical_prefix_match(a,b) if attributable else None
            prompt=b.get('object_prompt_known_focus_calls');delta=b.get('actual_delta_known_actor_calls')
            actual=positive(prompt) and positive(delta) and (not attributable or canonical is True)
            pairs.append(dict(task_id=task,baseline=baseline,candidate=candidate,
                baseline_success=a['success'],candidate_success=b['success'],both_evaluated=evaluated,
                both_usage_known=complete,success_lost=a['success'] and not b['success'] if evaluated else None,
                both_successful=a['success'] and b['success'] if evaluated else None,
                candidate_minus_baseline_tokens=b['known_total_tokens']-a['known_total_tokens'] if complete else None,
                candidate_object_prompt_known_focus_calls=prompt,candidate_delta_known_actor_calls=delta,
                representation_prefix_match=strict,canonical_representation_prefix_match=canonical,
                actual_intervention=actual))
        complete=all(p['both_usage_known'] for p in pairs);common=[p for p in pairs if p['both_successful'] is True]
        total=sum(p['candidate_minus_baseline_tokens'] for p in pairs) if complete else None
        common_total=sum(p['candidate_minus_baseline_tokens'] for p in common) if complete and common else None
        active=any(p['actual_intervention'] for p in common)
        intact=all(cells[t,m].get(kind+'_contract_failed') is False and cells[t,m].get(kind+'_accounting_complete') is True
            for t in TASKS for m in (baseline,candidate) for kind in ('prefix_exposure','checkpoint_representation','delta_envelope'))
        matched=all(p['canonical_representation_prefix_match'] is True for p in pairs
                    if positive(p['candidate_object_prompt_known_focus_calls'])) if attributable else None
        gate=bool(complete and not errors and intact and common and active and not any(p['success_lost'] for p in pairs)
                  and total<0 and common_total<0 and (not attributable or matched is True))
        comparisons.append(dict(name=name,baseline=baseline,candidate=candidate,pairs=pairs,
            attribution_prefix_required=attributable,all_four_pairs_complete_with_known_usage=complete,
            all_task_token_difference=total,common_success_tasks=[p['task_id'] for p in common],
            common_success_token_difference=common_total,changed_intervention_on_common_success=active,
            all_activated_canonical_prefixes_match=matched,comparison_gate_met=gate))
    all_known=all(known(r) for r in rows)
    totals={m:sum(r['known_total_tokens'] for r in rows if r['checkpoint_representation_mode']==m
                 and type(r.get('known_total_tokens')) is int) for m in MODES}
    adopted=all(c['comparison_gate_met'] for c in comparisons)
    return dict(planned_rows=12,independent_tasks=4,repetitions=1,model_seed=57,
        all_twelve_complete_with_known_usage=all_known,
        success_counts={m:sum(r['success'] is True for r in rows if r['checkpoint_representation_mode']==m) for m in MODES},
        known_token_subtotals_by_mode=totals,total_tokens_by_mode=totals if all_known else {m:None for m in MODES},
        usage_count_missing_conditions=sum(type(r.get('unknown_usage_calls')) is not int for r in rows),
        recorded_unknown_usage_calls=sum(r['unknown_usage_calls'] for r in rows if type(r.get('unknown_usage_calls')) is int),
        comparisons=comparisons,primary_utility_gate_met=comparisons[0]['comparison_gate_met'],
        unchanged_delta_control_gate_met=comparisons[1]['comparison_gate_met'],both_control_development_gate_met=adopted,
        development_gate_met=adopted,prior_results_pooled=False,unknown_usage_imputed=False,
        exposure_is_guaranteed_savings=False,competitive_ratio_claim=False,novel_method_claim=False,
        general_quality_preservation_claim=False,independent_replication_claim=False,
        interpretation='Posthoc known four-task seed57 development comparison. Only the second delta focus prompt changes; '
        'parser and size caps remain fixed. All failures, missing cells and prefix mismatches remain. '
        'Canonical transport-ID equality is limited evidence, not semantic or hidden-state equivalence.')
