"""P131: ordinary checkpoint-bound inventory utility on one known CSV task, original first seed only after P130 startup failure."""
import hashlib
from budget_observation import notification
from budget_visibility_comparison import ERROR_POLICY
from protocol_stable_history import StableReferenceConversation
from receipt_reasoning_history import require
from whole_task_output_grounding import (fixed_fields as base_fixed_fields,
    config_for as base_config_for, initial_conversation as base_conversation)

MODES = ('off', 'checkpoint_inventory')
SEEDS = (57,)
API_BUDGETS = (120,)
PLAN = 'configs/P131_whole_task_checkpoint_inventory_recovery_v01.json'
PREFLIGHT = 'reports/P131_initial_checks.json'
ACTIVATION = 'reports/P131_activation_v01.json'
PREDECESSOR_REPORT = 'reports/P127_comparison.json'
INVENTORY_GUIDE = '''
The persistent Python namespace survives a history checkpoint. An optional
checkpoint_runtime_inventory notice lists current top-level variable names,
exact built-in types, and container lengths; it contains no values and does
not certify task success. You can refer to those existing variables in later
run_python code. Absence from this bounded list does not prove that a binding
does not exist. Ordinary Python inspection and archived records remain usable.
'''


def run_order():
    return [(rep, 1, mode) for rep in (1,)
            for mode in (MODES if rep == 1 else MODES[::-1])]


def cell_id(replication, number, mode):
    require(type(replication) is int and replication in (1,)
        and type(number) is int and number == 1 and mode in MODES, 'outside_fixed_P131_comparison')
    return f'BOC_P131_R{replication:02d}_{number:02d}_{mode.upper()}'


def initial_conversation(original, public_task):
    previous=base_conversation(original, public_task)
    return StableReferenceConversation(previous.messages()[0]['content']+INVENTORY_GUIDE,public_task)


def config_for(original, plan, task_id, mode, replication):
    rid=cell_id(replication,1,mode)
    config=base_config_for(original,plan,task_id,'feedback',replication)
    config.update(run_id=rid, inventory_mode=mode, checkpoint_inventory_policy=mode,
        grounding_mode='feedback', output_grounding_policy='feedback')
    return config


def make_notification(messages,state,mode,*,wall_limit):
    require(mode in MODES,'fixed_P131_inventory_mode_required')
    return notification(messages,state,'not_exposed')


def fixed_fields():
    value=base_fixed_fields()
    for name in ('grounding_modes','auxiliary_comparison','minimum_successful_repairs_on_common_success',
                 'require_P128_owned_session_closed_before_launch'):
        value.pop(name)
    value.update(experiment='P131',batch_id='P131_batch_v01',inventory_modes=list(MODES),
        grounding_mode='feedback',max_cells=2,max_model_calls=160,max_reserved_tokens=900000,
        max_reserved_environment_api_requests=240,max_evaluator_calls=2,
        max_summary_calls_in_batch=6,server_max_lifetime_seconds=6000,model_seeds=[57],repetitions=1,
        require_P129_owned_session_closed_before_launch=True,P129_results_used_for_selection=False,
        primary_comparison=list(MODES),minimum_inventory_exposures_on_common_success=1,
        same_inventory_capture_in_both_modes=True,inventory_only_after_accepted_checkpoint=True,
        inventory_next_actor_only=True,inventory_raw_values_disclosed=False,
        inventory_guide_sha256=hashlib.sha256(INVENTORY_GUIDE.encode()).hexdigest(),
        primary_question='ordinary_runtime_binding_inventory_utility_after_accepted_checkpoint',
        timing_superiority_claim=False,
        recovery_of='P130_startup_failure_before_model_spawn',
        original_first_seed_only_due_remaining_time=True,
        P129_outcomes_seen_before_recovery=True,
        seed_selection_rule='original_first_planned_seed_57_no_best_seed_selection',
        require_P130_original_failure_preserved=True)
    return value


def validate_plan(plan):
    fixed=fixed_fields()
    require(all(type(plan.get(k)) is type(v) and plan[k]==v for k,v in fixed.items()),
            'fixed_P131_scope_changed')
    tasks=plan.get('known_tasks')
    require(type(tasks) is list and len(tasks)==1 and tasks[0].get('source_run')=='P29_04_CODE'
        and type(tasks[0].get('task_id')) is str,'only_known_CSV_task_required')
    for name in ('scripts/checkpoint_runtime_inventory.py','scripts/checkpoint_inventory_runtime.py',
                 'scripts/checkpoint_inventory_inference.py','scripts/run_whole_task_checkpoint_inventory_recovery_cell.py',
                 'scripts/audit_whole_task_checkpoint_inventory_recovery.py',
                 'docs/experiments/P131_whole_task_checkpoint_inventory_recovery.md',
                 'reports/P130_closed_source_diagnosis_20261026.json',
                 'reports/P130_startup_failure_20261027.json',
                 'scripts/serve_research_model_recovery.py',
                 PREDECESSOR_REPORT,'reports/P127_server_session.json'):
        value=plan.get('source_sha256',{}).get(name)
        require(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value),
                'bound_P131_sources_required')


def summarize(rows,errors):
    require(len(rows)==2 and len({r['task_id'] for r in rows})==1
        and {(r['replication'],r['inventory_mode']) for r in rows}=={(rep,mode) for rep in (1,) for mode in MODES},
        'all_two_P131_slots_required')
    require(all(type(r['replication']) is int and type(r['model_seed']) is int
        and r['model_seed']==SEEDS[r['replication']-1] and r['grounding_mode']=='feedback' for r in rows),
        'fixed_P131_seeds_and_shared_feedback_required')
    pairs=[]
    for rep,seed in enumerate(SEEDS,1):
        cells={r['inventory_mode']:r for r in rows if r['replication']==rep};a,b=[cells[m] for m in MODES]
        evaluated=all(r['record_status']=='evaluated' and type(r['success']) is bool for r in (a,b))
        known=evaluated and all(type(r['unknown_usage_calls']) is int and r['unknown_usage_calls']==0
            and type(r['known_total_tokens']) is int and r['known_total_tokens']>=0 for r in (a,b))
        pairs.append(dict(replication=rep,model_seed=seed,task_id=a['task_id'],both_evaluated=evaluated,
            both_usage_known=known,off_success=a['success'],checkpoint_inventory_success=b['success'],
            success_lost=a['success'] and not b['success'] if evaluated else None,
            success_gained=b['success'] and not a['success'] if evaluated else None,
            both_successful=a['success'] and b['success'] if evaluated else None,
            checkpoint_inventory_minus_off_tokens=b['known_total_tokens']-a['known_total_tokens'] if known else None))
    complete=all(p['both_usage_known'] for p in pairs);evaluated=all(p['both_evaluated'] for p in pairs)
    common={p['replication'] for p in pairs if p['both_successful']}
    counts=[r.get('inventory_notice_actor_calls') for r in rows
            if r['inventory_mode']=='checkpoint_inventory' and r['replication'] in common]
    exposures=sum(counts) if counts and all(type(v) is int and v>=0 for v in counts) else None
    intact=all(r.get(k) is False for r in rows for k in
        ('inventory_contract_failed','grounding_contract_failed','projection_contract_failed'))
    intact &= all(r.get(k) is True for r in rows for k in ('inventory_accounting_complete','grounding_accounting_complete'))
    delta=sum(p['checkpoint_inventory_minus_off_tokens'] for p in pairs) if complete else None
    common_delta=sum(p['checkpoint_inventory_minus_off_tokens'] for p in pairs if p['both_successful']) if complete else None
    losses=sum(p['success_lost'] for p in pairs) if evaluated else None
    return dict(all_two_complete_with_known_usage=complete,paired_results=pairs,paired_success_losses=losses,
        paired_success_gains=sum(p['success_gained'] for p in pairs) if evaluated else None,
        paired_successful_task_seed_pairs=len(common) if evaluated else None,
        checkpoint_inventory_minus_off_whole_task_tokens=delta,paired_successful_token_difference=common_delta,
        both_failed_token_difference=sum(p['checkpoint_inventory_minus_off_tokens'] for p in pairs
            if p['both_evaluated'] and not p['off_success'] and not p['checkpoint_inventory_success']) if complete else None,
        inventory_exposures_on_common_success=exposures,mechanism_contracts_intact=bool(intact),
        development_gate_met=bool(complete and not errors and losses==0 and common and delta<0
            and common_delta<0 and exposures is not None and exposures>0 and intact),
        planned_rows=2,independent_tasks=1,repetitions=1,model_seeds=list(SEEDS),
        prior_results_pooled=False,general_quality_preservation_claim=False,novel_method_claim=False,
        timing_superiority_claim=False,
        interpretation='Ordinary inventory utility on one known CSV task, original first seed only after P130 startup failure, with shared feedback verification. '
            'All two known evaluated usages, no lost baseline success, lower aggregate and common-success '
            'whole-job tokens and actual inventory exposure on a common success are required. '
            'No comparison of presentation timings, generalization, or new mechanism is established.')
