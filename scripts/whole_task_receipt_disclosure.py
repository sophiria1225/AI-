"""P128: fixed known-task receipt disclosure calibration, no generation on import."""
import hashlib

from audit_budget_visibility_comparison import development_gate
from budget_observation import notification
from budget_visibility_comparison import ERROR_POLICY
from compact_api_receipts import RECEIPT_GUIDE
from late_clock_comparison import initial_conversation as base_conversation
from receipt_disclosure_live import ReceiptDisclosureLiveConversation
from receipt_disclosure_history import SHARED_GUIDE
from receipt_reasoning_history import require
from region_projection_runtime import EXPLICIT_FIELD_GUIDE
from whole_task_tool_choice import worker_config as base_worker_config
from whole_task_region_projection import fixed_fields as previous_fixed_fields

MODES = ('full', 'disclose')
SEEDS = (57, 157)
API_BUDGETS = (160, 80, 80, 120)
PLAN = 'configs/P128_whole_task_receipt_disclosure_v01.json'
PREFLIGHT = 'reports/P128_initial_checks.json'
ACTIVATION = 'reports/P128_activation_v01.json'
PREDECESSOR_REPORT = 'reports/P127_comparison.json'


def run_order():
    return [(rep, number, mode) for rep in (1, 2) for number in range(1, 5)
            for mode in (MODES if (rep + number) % 2 == 0 else MODES[::-1])]


def cell_id(replication, number, mode):
    require(type(replication) is int and replication in (1, 2)
            and type(number) is int and number in range(1, 5) and mode in MODES,
            'outside_fixed_P128_comparison')
    return f'BOC_P128_R{replication:02d}_{number:02d}_{mode.upper()}'


def initial_conversation(original, public_task, mode, *, execution_scope='P128:preflight'):
    previous = base_conversation(original, public_task)
    return ReceiptDisclosureLiveConversation(previous.messages()[0]['content'] + RECEIPT_GUIDE
        + EXPLICIT_FIELD_GUIDE, public_task, execution_scope=execution_scope, mode=mode)


def config_for(original, plan, task_id, mode, replication):
    number = [item['task_id'] for item in plan['known_tasks']].index(task_id) + 1
    rid = cell_id(replication, number, mode)
    seed = SEEDS[replication - 1]
    config = base_worker_config(original, {**plan, 'model_seed': seed}, task_id,
                                ERROR_POLICY, rid, 'auto')
    require(config['draft_temperature'] == 0.7 and config['seed'] == seed,
            'fixed_P128_seed_and_summary_temperature_required')
    require(plan.get('api_budget_by_task_slot') == list(API_BUDGETS),
            'prespecified_common_P128_API_budgets_required')
    config.update(run_id=rid, replication=replication, replication_index=replication,
        model_seed=seed, receipt_mode=mode, receipt_disclosure_policy=mode,
        projection_policy='explicit_joined_fields', checkpoint_policy='rolling_separate',
        read_views_enabled=False, receipt_format='lossless_columns_rows_v1',
        max_api_requests=API_BUDGETS[number - 1],
        rolling_checkpoint_max_opportunities=3, rolling_min_fresh_turns=3,
        inline_checkpoint_requirement='not_applicable', explicit_joined_fields_enabled=True)
    return config


def make_notification(messages, state, mode, *, wall_limit):
    require(mode in MODES, 'fixed_P128_receipt_mode_required')
    return notification(messages, state, 'not_exposed')


def fixed_fields():
    value = previous_fixed_fields()
    for name in ('projection_policies', 'model_seed', 'required_replay',
                 'minimum_projection_hits_on_common_success', 'require_no_projection_contract_failure'):
        value.pop(name)
    value.update(experiment='P128', batch_id='P128_batch_v01', receipt_modes=list(MODES),
        model_seeds=list(SEEDS), repetitions=2, max_cells=16, max_model_calls=1280,
        max_reserved_tokens=7200000, max_reserved_environment_api_requests=1760,
        max_evaluator_calls=16, max_summary_calls_in_batch=48,
        server_max_lifetime_seconds=39600, required_closed_predecessor='P127',
        projection_policy='explicit_joined_fields', automatic_region_projection_enabled=False,
        same_disclosure_guide=True, disclosure_guide_sha256=hashlib.sha256(SHARED_GUIDE.encode()).hexdigest(),
        minimum_disclosures_on_common_success=1, require_no_disclosure_contract_failure=True,
        require_no_success_loss_in_each_seed=True, require_token_reduction_in_each_seed=True,
        primary_question='ordinary_receipt_disclosure_whole_job_cost_and_quality',
        deadline_jst='2026-10-27T06:00:00+09:00')
    return value


def validate_plan(plan):
    fixed = fixed_fields()
    require(all(type(plan.get(k)) is type(v) and plan[k] == v for k, v in fixed.items()),
            'fixed_P128_scope_changed')
    tasks = plan.get('known_tasks')
    require(type(tasks) is list and len(tasks) == 4
        and [t.get('source_run') for t in tasks] == fixed['source_runs']
        and len({t.get('task_id') for t in tasks}) == 4, 'all_four_known_tasks_required')
    for name in ('scripts/receipt_disclosure_live.py', 'scripts/receipt_disclosure_history.py',
                 'scripts/receipt_disclosure_rolling_inference.py',
                 'scripts/run_whole_task_receipt_disclosure_cell.py',
                 'scripts/audit_whole_task_receipt_disclosure.py',
                 'docs/experiments/P128_whole_task_receipt_disclosure.md',
                 PREDECESSOR_REPORT, 'reports/P127_server_session.json'):
        value = plan.get('source_sha256', {}).get(name)
        require(type(value) is str and len(value) == 64
            and all(c in '0123456789abcdef' for c in value), 'bound_P128_sources_required')


def summarize(rows, errors):
    tasks = list(dict.fromkeys(row['task_id'] for row in rows))
    actual = [(r['replication'], r['task_id'], r['receipt_mode']) for r in rows]
    require(len(tasks) == 4 and len(actual) == 16 and set(actual) ==
        {(rep, task, mode) for rep in (1, 2) for task in tasks for mode in MODES},
        'all_sixteen_P128_slots_required')
    require(all(type(r['replication']) is int and type(r['model_seed']) is int
                and r['model_seed'] == SEEDS[r['replication'] - 1]
                for r in rows), 'fixed_P128_row_seeds_required')
    per_seed, pairs = [], []
    aliases = dict(zip(MODES, ('measured', 'not_exposed')))
    def rename(value):
        if isinstance(value, dict):
            return {k.replace('not_exposed', 'disclose').replace('measured', 'full'):
                    rename(v) for k, v in value.items()}
        if isinstance(value, list):
            return [rename(v) for v in value]
        return value
    for rep, seed in enumerate(SEEDS, 1):
        subset = [r for r in rows if r['replication'] == rep]
        result = rename(development_gate([{**r, 'time_visibility': aliases[r['receipt_mode']]}
                                          for r in subset], errors))
        complete = result['all_eight_complete_with_known_usage']
        common = [p for p in result['paired_results'] if p['both_successful']]
        delta = sum(p['disclose_minus_full_tokens'] for p in common) if complete else None
        result.update(replication=rep, model_seed=seed, paired_successful_token_difference=delta,
            development_gate_met=bool(result['development_gate_met'] and common and delta < 0))
        per_seed.append(result)
        pairs.extend({**p, 'replication': rep, 'model_seed': seed} for p in result['paired_results'])
    complete = all(r['all_eight_complete_with_known_usage'] for r in per_seed)
    evaluated = all(p['both_evaluated'] for p in pairs)
    common_keys = {(p['replication'], p['task_id']) for p in pairs if p['both_successful']}
    values = [r.get('receipt_disclosures') for r in rows if r['receipt_mode'] == 'disclose'
              and (r['replication'], r['task_id']) in common_keys]
    disclosures = sum(values) if values and all(type(v) is int and v >= 0 for v in values) else None
    flags = [r.get('receipt_disclosure_contract_failed') for r in rows]
    contracts_known = all(type(v) is bool for v in flags)
    failures = sum(flags) if contracts_known else None
    runtime_flags = [r.get('projection_contract_failed') for r in rows]
    runtime_known = all(type(v) is bool for v in runtime_flags)
    runtime_failures = sum(runtime_flags) if runtime_known else None
    contracts_intact = contracts_known and failures == 0 and runtime_known and runtime_failures == 0
    delta = sum(p['disclose_minus_full_tokens'] for p in pairs) if complete else None
    common_delta = sum(p['disclose_minus_full_tokens'] for p in pairs if p['both_successful']) if complete else None
    return dict(all_sixteen_complete_with_known_usage=complete, paired_results=pairs,
        per_seed=per_seed, paired_success_losses=sum(p['success_lost'] for p in pairs) if evaluated else None,
        paired_success_gains=sum(p['success_gained'] for p in pairs) if evaluated else None,
        paired_successful_tasks=sum(p['both_successful'] for p in pairs) if evaluated else None,
        disclose_minus_full_whole_task_tokens=delta, paired_successful_token_difference=common_delta,
        both_failed_token_difference=sum(p['disclose_minus_full_tokens'] for p in pairs
            if p['both_evaluated'] and not p['full_success'] and not p['disclose_success']) if complete else None,
        receipt_disclosures_on_common_success=disclosures,
        receipt_disclosure_contract_failure_cells=failures, shared_runtime_contract_failure_cells=runtime_failures,
        mechanism_contracts_intact=contracts_intact,
        development_gate_met=bool(not errors and all(r['development_gate_met'] for r in per_seed)
            and disclosures is not None and disclosures >= 1 and contracts_intact),
        planned_rows=16, independent_tasks=4, repetitions=2, model_seeds=list(SEEDS),
        summary_failure_and_recovery_costs_included=True, prior_results_pooled=False,
        general_quality_preservation_claim=False, novel_method_claim=False,
        interpretation='Known-task development calibration. In EACH fixed seed, all-task and common-success '
            'whole-job tokens must decrease with no full-mode success lost. Actual disclosure on a common '
            'success and intact contracts are required. Repetitions are not independent tasks; bytes, '
            'API savings and cheap failures do not establish the token goal.')
