"""P129: six fixed CSV export conditions, ordinary feedback versus repair."""
import hashlib

from budget_observation import notification
from budget_visibility_comparison import ERROR_POLICY
from compact_api_receipts import RECEIPT_GUIDE
from late_clock_comparison import initial_conversation as base_conversation
from output_grounding_runtime import GUIDE
from protocol_stable_history import StableReferenceConversation
from receipt_reasoning_history import require
from region_projection_runtime import EXPLICIT_FIELD_GUIDE
from whole_task_tool_choice import worker_config as base_worker_config
from whole_task_region_projection import fixed_fields as previous_fixed_fields

MODES = ('off', 'feedback', 'repair')
SEEDS = (57, 157)
API_BUDGETS = (120,)
PLAN = 'configs/P129_whole_task_output_grounding_v01.json'
PREFLIGHT = 'reports/P129_initial_checks.json'
ACTIVATION = 'reports/P129_activation_v01.json'
PREDECESSOR_REPORT = 'reports/P127_comparison.json'


def run_order():
    return [(rep, 1, mode) for rep, order in ((1, MODES), (2, MODES[::-1])) for mode in order]


def cell_id(replication, number, mode):
    require(type(replication) is int and replication in (1, 2)
        and type(number) is int and number == 1 and mode in MODES, 'outside_fixed_P129_comparison')
    return f'BOC_P129_R{replication:02d}_{number:02d}_{mode.upper()}'


def initial_conversation(original, public_task):
    previous = base_conversation(original, public_task)
    return StableReferenceConversation(previous.messages()[0]['content'] + RECEIPT_GUIDE
                                       + EXPLICIT_FIELD_GUIDE + GUIDE, public_task)


def config_for(original, plan, task_id, mode, replication):
    require(len(plan['known_tasks']) == 1 and plan['known_tasks'][0]['task_id'] == task_id,
            'only_known_CSV_task_required')
    rid = cell_id(replication, 1, mode)
    seed = SEEDS[replication - 1]
    config = base_worker_config(original, {**plan, 'model_seed': seed}, task_id, ERROR_POLICY, rid, 'auto')
    require(config['draft_temperature'] == 0.7 and config['seed'] == seed,
            'fixed_P129_seed_and_summary_temperature_required')
    require(plan.get('api_budget_by_task_slot') == [120], 'fixed_P129_API_cap_required')
    config.update(run_id=rid, replication=replication, replication_index=replication,
        model_seed=seed, grounding_mode=mode, output_grounding_policy=mode,
        projection_policy='explicit_joined_fields', checkpoint_policy='rolling_separate',
        read_views_enabled=False, receipt_format='lossless_columns_rows_v1', max_api_requests=120,
        rolling_checkpoint_max_opportunities=3, rolling_min_fresh_turns=3,
        inline_checkpoint_requirement='not_applicable', explicit_joined_fields_enabled=True)
    return config


def make_notification(messages, state, mode, *, wall_limit):
    require(mode in MODES, 'fixed_P129_grounding_mode_required')
    return notification(messages, state, 'not_exposed')


def fixed_fields():
    value = previous_fixed_fields()
    for name in ('projection_policies', 'model_seed', 'required_replay',
                 'minimum_projection_hits_on_common_success', 'require_no_projection_contract_failure'):
        value.pop(name)
    value.update(experiment='P129', batch_id='P129_batch_v01', grounding_modes=list(MODES),
        source_runs=['P29_04_CODE'], model_seeds=list(SEEDS), repetitions=2,
        max_cells=6, max_model_calls=480, max_reserved_tokens=2700000,
        max_reserved_environment_api_requests=720, api_budget_by_task_slot=[120],
        max_evaluator_calls=6, max_summary_calls_in_batch=18, server_max_lifetime_seconds=21600,
        required_closed_predecessor='P127', require_P128_owned_session_closed_before_launch=True,
        P128_results_used_for_selection=False,
        projection_policy='explicit_joined_fields', automatic_region_projection_enabled=False,
        receipt_display='full', same_grounding_guide=True,
        grounding_guide_sha256=hashlib.sha256(GUIDE.encode()).hexdigest(),
        primary_comparison=['feedback', 'repair'], auxiliary_comparison=['off', 'repair'],
        minimum_successful_repairs_on_common_success=1,
        require_no_grounding_contract_failure=True, delete_intervention=False,
        unknown_evidence_intervention=False, original_payload_preserved=True,
        primary_question='ordinary_source_checked_CSV_write_feedback_versus_deterministic_repair',
        deadline_jst='2026-10-27T06:00:00+09:00')
    return value


def validate_plan(plan):
    fixed = fixed_fields()
    require(all(type(plan.get(k)) is type(v) and plan[k] == v for k, v in fixed.items()),
            'fixed_P129_scope_changed')
    tasks = plan.get('known_tasks')
    require(type(tasks) is list and len(tasks) == 1 and tasks[0].get('source_run') == 'P29_04_CODE'
            and type(tasks[0].get('task_id')) is str, 'only_known_CSV_task_required')
    for name in ('scripts/public_output_grounding.py', 'scripts/output_grounding_runtime.py',
                 'scripts/run_whole_task_output_grounding_cell.py',
                 'scripts/audit_whole_task_output_grounding.py',
                 'docs/experiments/P129_whole_task_output_grounding.md',
                 'reports/P129_closed_source_diagnosis_20261026.json',
                 PREDECESSOR_REPORT, 'reports/P127_server_session.json'):
        value = plan.get('source_sha256', {}).get(name)
        require(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value),
                'bound_P129_sources_required')


def summarize(rows, errors):
    actual = [(r['replication'], r['grounding_mode']) for r in rows]
    require(len(rows) == 6 and len({r['task_id'] for r in rows}) == 1
        and set(actual) == {(rep, mode) for rep in (1, 2) for mode in MODES},
        'all_six_P129_slots_required')
    require(all(type(r['replication']) is int and type(r['model_seed']) is int
        and r['model_seed'] == SEEDS[r['replication'] - 1] for r in rows), 'fixed_P129_row_seeds_required')
    complete = all(r['record_status'] == 'evaluated' and type(r['success']) is bool
        and type(r['unknown_usage_calls']) is int and r['unknown_usage_calls'] == 0
        and type(r['known_total_tokens']) is int and r['known_total_tokens'] >= 0 for r in rows)
    comparisons = {}
    for baseline in ('feedback', 'off'):
        pairs = []
        for rep, seed in enumerate(SEEDS, 1):
            by_mode = {r['grounding_mode']: r for r in rows if r['replication'] == rep}
            a, b = by_mode[baseline], by_mode['repair']
            evaluated = all(r['record_status'] == 'evaluated' and type(r['success']) is bool for r in (a,b))
            known = evaluated and all(type(r['unknown_usage_calls']) is int and r['unknown_usage_calls'] == 0
                and type(r['known_total_tokens']) is int and r['known_total_tokens'] >= 0 for r in (a,b))
            pairs.append(dict(replication=rep, model_seed=seed, task_id=a['task_id'], baseline=baseline,
                both_evaluated=evaluated, both_usage_known=known, baseline_success=a['success'], repair_success=b['success'],
                success_lost=a['success'] and not b['success'] if evaluated else None,
                success_gained=b['success'] and not a['success'] if evaluated else None,
                both_successful=a['success'] and b['success'] if evaluated else None,
                repair_minus_baseline_tokens=b['known_total_tokens']-a['known_total_tokens'] if known else None))
        common = [p for p in pairs if p['both_successful']]
        evaluated = all(p['both_evaluated'] for p in pairs)
        known = all(p['both_usage_known'] for p in pairs)
        comparisons[baseline] = dict(paired_results=pairs,
            paired_success_losses=sum(p['success_lost'] for p in pairs) if evaluated else None,
            paired_success_gains=sum(p['success_gained'] for p in pairs) if evaluated else None,
            paired_successful_task_seed_pairs=len(common) if evaluated else None,
            repair_minus_baseline_whole_task_tokens=sum(p['repair_minus_baseline_tokens'] for p in pairs) if known else None,
            paired_successful_token_difference=sum(p['repair_minus_baseline_tokens'] for p in common) if known else None,
            both_failed_token_difference=sum(p['repair_minus_baseline_tokens'] for p in pairs
                if p['both_evaluated'] and not p['baseline_success'] and not p['repair_success']) if known else None,
            every_seed_tokens_lower=all(p['repair_minus_baseline_tokens'] < 0 for p in pairs) if known else None)
    primary = comparisons['feedback']
    common_reps = {p['replication'] for p in primary['paired_results'] if p['both_successful']}
    counts = [r.get('grounding_repairs') for r in rows
              if r['grounding_mode'] == 'repair' and r['replication'] in common_reps]
    repairs = sum(counts) if counts and all(type(v) is int and v >= 0 for v in counts) else None
    flags = [r.get(k) for r in rows for k in ('grounding_contract_failed','projection_contract_failed')]
    intact = (all(type(v) is bool and not v for v in flags)
              and all(r.get('grounding_accounting_complete') is True for r in rows))
    gate = bool(complete and not errors and intact and repairs is not None and repairs > 0
        and all(c['paired_success_losses'] == 0 for c in comparisons.values())
        and primary['paired_successful_task_seed_pairs'] > 0
        and primary['repair_minus_baseline_whole_task_tokens'] < 0
        and primary['paired_successful_token_difference'] < 0)
    return dict(all_six_complete_with_known_usage=complete, comparisons=comparisons,
        paired_results=primary['paired_results'], paired_success_losses=primary['paired_success_losses'],
        paired_successful_token_difference=primary['paired_successful_token_difference'],
        repair_minus_feedback_whole_task_tokens=primary['repair_minus_baseline_whole_task_tokens'],
        successful_repairs_on_primary_common_success=repairs, mechanism_contracts_intact=intact,
        development_gate_met=gate, planned_rows=6, independent_tasks=1, repetitions=2,
        model_seeds=list(SEEDS), prior_results_pooled=False,
        general_quality_preservation_claim=False, novel_method_claim=False,
        interpretation='Single known export-template calibration. Repair is compared primarily to ordinary '
            'feedback, with off as an auxiliary quality control. All six evaluations and known costs, '
            'no success lost to either baseline, lower aggregate and common-success whole-job tokens '
            'versus feedback, and an actual successful repair on primary common success are required. '
            'Report each seed; quality gains and cheap failures are distinct from the token goal.')
