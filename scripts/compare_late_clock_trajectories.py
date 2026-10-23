"""All P82 repetition and within-repetition pairs; metadata-only diagnosis."""
import argparse
import copy
from itertools import combinations
from pathlib import Path

from budget_observation import notification
from budget_signal import digest
from clock_notice_replay import output_fingerprints
from compare_budget_visibility_repetitions import compare_traces
from late_clock_comparison import cell_id,run_order
from stable_clock_observation import effective_visibility
from run_context_comparison import write_json
from run_handoff_factors import ROOT,read,sha


def request_fingerprints(request,notice,policy,wall_limit):
    state=notice['measured_state'];effective=effective_visibility(policy,state,wall_limit)
    if notice['effective_time_visibility']!=effective:
        raise ValueError('effective_policy_changed')
    expected=notification([],state,effective)[0][0]
    if request['messages'][-1]!=expected:raise ValueError('actual_notice_changed')
    no_wall=copy.deepcopy(request);zero=copy.deepcopy(state)
    zero['remaining']['wall_seconds_at_snapshot']=0
    # Keep the ACTUAL policy while removing its clock value. Re-evaluating the
    # half-time rule on zero would incorrectly activate previously hidden time.
    no_wall['messages'][-1]=notification([],zero,effective)[0][0]
    no_treatment=copy.deepcopy(request)
    no_treatment['messages'][-1]=notification([],state,'not_exposed')[0][0]
    return {'request_sha256':digest(request),'without_current_wall_sha256':digest(no_wall),
        'without_current_time_treatment_sha256':digest(no_treatment),
        'effective_time_visibility':effective,
        'wall_seconds_at_snapshot':state['remaining']['wall_seconds_at_snapshot']}


def trace(storage,row,wall_limit):
    folder=storage/'records/context_pilot'/row['run_id']
    if row['record_status'] not in ('evaluated','unevaluated'):
        return {'run_id':row['run_id'],'calls':[],'known_complete':False}
    notices={s['next_call_id']:s for s in read(folder/'budget_observations.json') if s['model_attempted']}
    calls=[]
    for check in row['request_checks']:
        cid=check['call_id'];values={}
        for kind in ('request','response'):
            p=folder/cid/(kind+'.json');expected=check[kind+'_sha256']
            if (sha(p) if p.exists() else None)!=expected:raise ValueError('audited_record_changed')
            values[kind]=read(p) if p.exists() else None
        item={'call_id':cid,'usage_status':check['status'],'request_sha256':None,
            'without_current_wall_sha256':None,'without_current_time_treatment_sha256':None,
            **output_fingerprints(values['response'] or {})}
        if values['request'] is not None:
            item.update(request_fingerprints(values['request'],notices[cid],row['time_visibility'],wall_limit))
        calls.append(item)
    if len(calls)!=row['model_calls'] or len(notices)!=len(calls):raise ValueError('all_attempts_required')
    return {'run_id':row['run_id'],'calls':calls,
        'known_complete':row['record_status']=='evaluated' and row['unknown_usage_calls']==0
            and all(c['request_sha256'] is not None and c['public_output_sha256'] is not None for c in calls),
        'first_measured_notice_call':next((i for i,c in enumerate(calls,1)
            if c.get('effective_time_visibility')=='measured'),None),
        'notices_sha256':sha(folder/'budget_observations.json')}


def pair(left,right):
    result=compare_traces(left,right);index=result['first_request_difference']
    result['first_difference_is_current_time_treatment_only']=None
    if index is not None:
        a,b=left['calls'][index-1],right['calls'][index-1]
        result['first_difference_is_current_time_treatment_only']=bool(
            a['without_current_time_treatment_sha256'] is not None
            and a['without_current_time_treatment_sha256']==b['without_current_time_treatment_sha256'])
    result['first_measured_notice_call_by_run']=[left.get('first_measured_notice_call'),right.get('first_measured_notice_call')]
    return result


def run(storage,root):
    source=root/'reports/P82_comparison.json';target=root/'reports/P82_trajectory_stability.json'
    if target.exists():raise FileExistsError('preserve_first_P82_trajectory_analysis')
    report=read(source);plan_path=root/'configs/P82_late_clock_comparison_v01.json';plan=read(plan_path)
    if (report['batch_status'] not in ('complete','stopped') or report['audit_errors']
            or len(report['rows'])!=24 or report['plan_sha256']!=sha(plan_path)
            or {r['run_id'] for r in report['rows']}!={cell_id(*v) for v in run_order()}):
        raise ValueError('all_fixed_new_conditions_required')
    rows=report['rows'];traces={r['run_id']:trace(storage,r,plan['max_wall_seconds']) for r in rows}
    pairs=[]
    for item in plan['known_tasks']:
        selected=[r for r in rows if r['task_id']==item['task_id']]
        for a,b in combinations(selected,2):
            same_policy=a['time_visibility']==b['time_visibility']
            same_rep=a['repetition']==b['repetition']
            if not (same_policy or same_rep):continue
            pairs.append({'task_id':item['task_id'],'relation':'same_policy_repetition' if same_policy else 'within_repetition',
                'policies':[a['time_visibility'],b['time_visibility']],
                'repetitions':[a['repetition'],b['repetition']],**pair(traces[a['run_id']],traces[b['run_id']])})
    if len(pairs)!=36 or sum(p['relation']=='same_policy_repetition' for p in pairs)!=12:
        raise ValueError('all_twelve_repeat_and_twenty_four_condition_pairs_required')
    result={'phase':'P82_stability','pairs':pairs,'traces':traces,'comparison_sha256':sha(source),
        'inspector_sha256':sha(Path(__file__)),'independent_tasks':4,'dependent_pairs':36,
        'private_reasoning_inspected_semantically':False,'additional_generations':0,
        'additional_api_requests':0,'additional_evaluations':0,'tokenizations':0,
        'interpretation':'Compare all same-policy repetitions and all within-repetition condition pairs. Time-treatment removal affects only the current notice. It does not erase earlier differences, impute missing outputs, establish model-token identity or identify a whole-task causal effect.'}
    write_json(target,result);print({'pairs':len(pairs),'runs':len(traces)})
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--repo-root',type=Path,default=ROOT);a=p.parse_args();run(a.storage_root,a.repo_root)
