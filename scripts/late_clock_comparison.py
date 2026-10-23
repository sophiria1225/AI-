"""Finite P82 preparation: two repetitions of three ordinary clock controls.

No experiment can start without the final hash-bound plan and closed P81 proof.
"""
from budget_observation import notification
from api_error_comparison import initial_conversation as original_conversation
from budget_observation_worker import worker_config as base_worker_config
from budget_visibility_comparison import ERROR_POLICY, validate_plan as validate_base
from audit_budget_visibility_comparison import development_gate
from stable_clock_observation import POLICIES, effective_visibility
from protocol_stable_history import StableReferenceConversation

REPETITIONS = (1, 2)
REQUIRED_SOURCES = ('reports/P80_comparison.json', 'reports/P80_server_session.json',
    'configs/P80_budget_visibility_v01.json', 'reports/P81_repetitions.json',
    'reports/P81_server_session.json', 'reports/P81_trajectory_stability.json',
    'reports/late_clock_feasibility_20261024.json',
    'reports/P81_fallback_reference_diagnostic.json')


def run_order():
    first = (POLICIES, POLICIES[1:]+POLICIES[:1], POLICIES[2:]+POLICIES[:2], POLICIES[::-1])
    return [(rep,n,p) for rep in REPETITIONS for n in range(1,5)
            for p in (first[n-1] if rep==1 else first[n-1][::-1])]


def initial_conversation(original,public_task):
    previous=original_conversation(original,public_task)
    return StableReferenceConversation(previous.messages()[0]['content'],public_task)


def cell_id(rep,number,policy):
    if (type(rep) is not int or rep not in REPETITIONS or type(number) is not int
            or number not in range(1,5) or policy not in POLICIES):
        raise ValueError('outside_fixed_P82_comparison')
    return f'BOC_P82_R{rep}_{number:02d}_{policy.upper()}'


def worker_config(original,plan,task_id,arm,run_id,time_visibility):
    if time_visibility not in POLICIES:
        raise ValueError('explicit_P82_time_policy_required')
    config=base_worker_config(original,plan,task_id,arm,run_id,'measured')
    config['time_visibility']=time_visibility
    config['protocol_reference_policy']='source_protocol_fields_before_rendering'
    return config


def config_for(original,plan,task_id,policy):
    number=[t['task_id'] for t in plan['known_tasks']].index(task_id)+1
    return worker_config(original,plan,task_id,ERROR_POLICY,cell_id(1,number,policy),policy)


def make_notification(messages,state,policy,*,wall_limit):
    return notification(messages,state,effective_visibility(policy,state,wall_limit))


def validate_plan(plan):
    expected={'experiment':'P82','batch_id':'P82_batch_v01','time_policies':list(POLICIES),
        'repetitions':list(REPETITIONS),'remaining_time_fraction':[1,2],
        'max_cells':24,'max_model_calls':1920,'max_reserved_tokens':10800000,
        'server_max_lifetime_seconds':64800,'fresh_seed_search':False,
        'threshold_search':False,'new_task_requirements_read':0,
        'protocol_references':'source_protocol_fields_before_rendering',
        'primary_question':'late_time_observation_whole_task_cost_and_quality',
        'prior_cohort':'reports/P80_comparison.json','required_closed_cohort':'reports/P81_repetitions.json'}
    if any(type(plan.get(k)) is not type(v) or plan[k]!=v for k,v in expected.items()):
        raise ValueError('fixed_P82_scope_changed')
    for name in REQUIRED_SOURCES:
        value=plan.get('source_sha256',{}).get(name)
        if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('closed_dependency_must_be_hash_bound')
    validate_base({**plan,'experiment':'P80','batch_id':'P80_batch_v01',
        'time_policies':['measured','not_exposed'],'max_cells':8,'max_model_calls':640,
        'max_reserved_tokens':3600000,'server_max_lifetime_seconds':21600,
        'protocol_references':'canonical_in_both_before_counting'})


def summarize(rows,errors):
    tasks=list(dict.fromkeys(r['task_id'] for r in rows))
    expected={(rep,t,p) for rep in REPETITIONS for t in tasks for p in POLICIES}
    actual=[(r['repetition'],r['task_id'],r['time_visibility']) for r in rows]
    if len(tasks)!=4 or len(actual)!=24 or set(actual)!=expected:
        raise ValueError('all_twenty_four_new_conditions_required')
    def renamed(value,baseline):
        if isinstance(value,dict):
            return {k.replace('not_exposed','late_half').replace('measured',baseline):renamed(v,baseline)
                    for k,v in value.items()}
        if isinstance(value,list):return [renamed(v,baseline) for v in value]
        return value
    repeats=[]
    for rep in REPETITIONS:
        selected=[r for r in rows if r['repetition']==rep]
        comparisons=[]
        for baseline in ('measured','not_exposed'):
            pair_rows=[r for r in selected if r['time_visibility'] in (baseline,'late_half')]
            gate=renamed(development_gate([{**r,'time_visibility':
                'not_exposed' if r['time_visibility']=='late_half' else 'measured'} for r in pair_rows],errors),baseline)
            gate['development_gate_met']=bool(gate['development_gate_met']
                and gate['paired_successful_tasks'] and gate['paired_successful_tasks']>0)
            pairs=gate['paired_results']; delta='late_half_minus_'+baseline+'_tokens'
            gate['paired_successful_token_difference']=sum(p[delta]
                for p in pairs if p['both_successful']) if gate['all_eight_complete_with_known_usage'] else None
            gate['both_failed_token_difference']=sum(p[delta]
                for p in pairs if p['both_evaluated'] and not p[baseline+'_success']
                and not p['late_half_success']) if gate['all_eight_complete_with_known_usage'] else None
            comparisons.append({'baseline':baseline,**gate})
        repeats.append({'repetition':rep,'comparisons':comparisons,
            'beats_both_ordinary_controls':all(c['development_gate_met'] for c in comparisons)})
    complete=all(c['all_eight_complete_with_known_usage'] for r in repeats for c in r['comparisons'])
    return {'planned_rows':24,'repetitions':repeats,'all_twenty_four_complete_with_known_usage':complete,
        'all_repetition_gates_met':all(r['beats_both_ordinary_controls'] for r in repeats),
        'independent_tasks':4,'novel_method_claim':False,'general_quality_preservation_claim':False,
        'interpretation':'Two development repetitions of three ordinary controls on four known tasks. Late-half must beat each baseline separately in both repetitions. Unknown usage stays unknown; faster failed work is separate from successful-task savings. No seed or threshold search.'}
