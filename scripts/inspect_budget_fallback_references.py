"""Read-only post-hoc diagnosis of renderer-bound fallback reference exposure."""
import argparse
import copy
from itertools import combinations
from pathlib import Path

from api_error_comparison import initial_conversation
from budget_observation import notification
from budget_signal import digest
from budget_visibility_comparison import canonical_messages
from compare_budget_visibility_repetitions import compare_traces, trace
from protocol_stable_history import fallback_inspection_view
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def request_views(storage, row, original):
    folder=storage/'records/context_pilot'/row['run_id']
    for name in ('summary','usage','evaluation'):
        if sha(folder/(name+'.json')) != row[name+'_sha256']:
            raise ValueError('audited_cell_record_changed')
    summary=read(folder/'summary.json')
    if summary['run_id']!=row['run_id'] or summary['task_id']!=row['task_id']:
        raise ValueError('audited_cell_identity_changed')
    config=read(folder/'plan.json')
    events,spans=read(folder/'events.json'),read(folder/'spans.json')
    notices={v['next_call_id']:v for v in read(folder/'budget_observations.json') if v['model_attempted']}
    conversation=initial_conversation(original,read(folder/'public_task.json'))
    views=[]
    for check in row['request_checks']:
        cid=check['call_id']; paths={kind:folder/cid/(kind+'.json') for kind in ('request','response')}
        for kind,path in paths.items():
            if (sha(path) if path.exists() else None)!=check[kind+'_sha256']:
                raise ValueError('audited_request_or_response_changed')
        if not paths['request'].exists():
            views.append({'call_id':cid,'available':False}); continue
        request=read(paths['request'])
        base,_=conversation.for_model(config['observation_page_characters'])
        notice=notices[cid]
        supplied,_=notification(canonical_messages(base),notice['measured_state'],row['time_visibility'])
        if request['messages']!=supplied:
            raise ValueError('request_not_bound_to_reconstructed_history')
        normalized,refs=fallback_inspection_view(conversation,config['observation_page_characters'])
        fallback=copy.deepcopy(request); fallback['messages'][:-1]=normalized
        both=copy.deepcopy(fallback); zero=copy.deepcopy(notice['measured_state'])
        zero['remaining']['wall_seconds_at_snapshot']=0
        both['messages'][-1]=notification([],zero,row['time_visibility'])[0][0]
        views.append({'call_id':cid,'available':True,'request_sha256':digest(request),
            'fallback_ids_normalized_sha256':digest(fallback),
            'fallback_ids_and_current_wall_normalized_sha256':digest(both),
            'bound_reference_paths':refs})
        if paths['response'].exists():
            response=read(paths['response'])
            outer=[spans[e['span_id']] for e in events if e['call']==cid and e['stage']=='model_tool']
            if response['status']=='ok' and outer:
                conversation.append(response['message'],outer)
    return views


def classify_first_difference(comparison,left,right):
    number=comparison['first_request_difference']
    if number is None:
        return {'first_request_difference_kind':'none_observed'}
    a,b=left[number-1],right[number-1]
    if not a['available'] or not b['available']:
        raise ValueError('first_difference_requires_two_saved_requests')
    if a['request_sha256']==b['request_sha256']:
        raise ValueError('first_difference_not_different')
    fallback_only=a['fallback_ids_normalized_sha256']==b['fallback_ids_normalized_sha256']
    combined=a['fallback_ids_and_current_wall_normalized_sha256']==b['fallback_ids_and_current_wall_normalized_sha256']
    wall_only=comparison['first_request_difference_is_current_wall_only']
    kind=('current_wall_only' if wall_only else 'renderer_bound_fallback_ids_only' if fallback_only
          else 'current_wall_and_renderer_bound_fallback_ids' if combined else 'other_request_fields')
    return {'first_request_difference_kind':kind,
        'equal_after_bound_fallback_ids_only':fallback_only,
        'equal_after_bound_fallback_ids_and_current_wall':combined,
        'bound_reference_paths_at_first_difference':[a['bound_reference_paths'],b['bound_reference_paths']],
        'causal_effect_identified':False}


def run(storage,root,checkpoint=None):
    anchor_path=root/'reports/P80_comparison.json'; anchor=read(anchor_path)
    if anchor['audit_errors'] or anchor['batch_status']!='complete' or len(anchor['rows'])!=8:
        raise ValueError('closed_all_eight_P80_cells_required')
    source=checkpoint or root/'reports/P81_repetitions.json'
    cohort=read(source)
    if checkpoint:
        if cohort.get('completed')!=8 or not cohort.get('partial_only') or not cohort.get('no_cohort_decision'):
            raise ValueError('exact_closed_second_repetition_checkpoint_required')
        new=cohort['audited_rows']
        expected={f'BOC_P81_R2_{n:02d}_{p}' for n in range(1,5) for p in ('MEASURED','NOT_EXPOSED')}
        if len(new)!=8 or {r['run_id'] for r in new}!=expected:
            raise ValueError('all_eight_second_repetition_cells_required')
        target=root/'reports/P81_second_repetition_diagnostic_20261024.json'
        rows=anchor['rows']+new
    else:
        if cohort['batch_status']!='complete' or cohort['audit_errors'] or len(cohort['rows'])!=16:
            raise ValueError('closed_full_P81_cohort_required')
        if cohort['anchor_sha256']!=sha(anchor_path) or cohort['anchor_rows']!=anchor['rows']:
            raise ValueError('closed_anchor_changed')
        target=root/'reports/P81_fallback_reference_diagnostic.json'
        rows=cohort['anchor_rows']+cohort['rows']
    if target.exists():raise FileExistsError('preserve_first_fallback_diagnostic')
    if any(r['record_status']!='evaluated' for r in rows):
        raise ValueError('all_selected_cells_must_be_audited_and_evaluated')
    plan=read(root/'configs/P81_budget_visibility_repetition_v01.json')
    original=read(root/plan['source_plan'])
    views={r['run_id']:request_views(storage,r,original) for r in rows}
    traces={r['run_id']:trace(storage,r) for r in rows}
    pairs=[]
    for task in [v['task_id'] for v in plan['known_tasks']]:
        for policy in ('measured','not_exposed'):
            selected=[r for r in rows if r['task_id']==task and r['time_visibility']==policy]
            if len(selected)!=(2 if checkpoint else 3):raise ValueError('all_planned_groups_required')
            for a,b in combinations(selected,2):
                x,y=a['run_id'],b['run_id']; comparison=compare_traces(traces[x],traces[y])
                pairs.append({'task_id':task,'time_visibility':policy,**comparison,
                    **classify_first_difference(comparison,views[x],views[y])})
    summaries=[]
    for row in rows:
        v=views[row['run_id']]
        summaries.append({k:row[k] for k in ('run_id','task_id','time_visibility','success',
            'known_total_tokens','unknown_usage_calls','model_calls')})
        summaries[-1].update(first_request_with_fallback_references=next(
            (i for i,r in enumerate(v,1) if r.get('bound_reference_paths')),None),
            requests_with_fallback_references=sum(bool(r.get('bound_reference_paths')) for r in v),
            reconstructed_request_count=sum(r['available'] for r in v))
    result={'phase':'P81_fallback_reference_diagnostic','posthoc':True,'partial_only':bool(checkpoint),
        'closed_cells':len(rows),'planned_total_cells':24,'pairs':pairs,'rows':summaries,
        'source_cohort_sha256':sha(source),'source_anchor_sha256':sha(anchor_path),
        'source_is_private_partial_checkpoint':bool(checkpoint),
        'source_sha256':{name:sha(root/name) for name in ('scripts/inspect_budget_fallback_references.py',
            'scripts/protocol_stable_history.py','scripts/native_conversation.py','scripts/reasoning_history.py',
            'scripts/budget_visibility_comparison.py','scripts/compare_budget_visibility_repetitions.py')},
        'additional_generations':0,'additional_api_requests':0,'additional_evaluations':0,
        'tokenizations':0,'private_reasoning_inspected_semantically':False,
        'causal_effect_identified':False,'novel_method_claim':False,
        'interpretation':'Preserve original inputs, costs, failures and unknown usage. Compare only renderer-bound fallback protocol IDs in a diagnostic view. No model-token equality, regenerated trajectory, quality improvement or savings is established.'}
    write_json(target,result)
    print({'closed_cells':len(rows),'pairs':len(pairs),'kinds':[p['first_request_difference_kind'] for p in pairs]})
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--repo-root',type=Path,default=ROOT); p.add_argument('--checkpoint',type=Path)
    a=p.parse_args(); run(a.storage_root,a.repo_root,a.checkpoint)
