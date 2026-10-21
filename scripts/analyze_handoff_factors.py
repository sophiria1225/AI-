"""Whole-cohort aggregate audit for the fixed P31 continuation comparison."""
import argparse
import collections
import hashlib
import json
from pathlib import Path

from handoff_factors import ARMS

ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def trial_row(trial, source_plan, source_id):
    summary=read(trial/'summary.json');evaluation=read(trial/'evaluation.json')
    events=read(trial/'events.json');spans=read(trial/'spans.json');usage=read(trial/'usage.json')
    prefix=read(trial/'prefix_events.json');setup=read(trial/'setup.json');identity=read(trial/'source_identity.json')
    config=read(trial/'plan.json');plan=read(trial/'factor_plan.json')
    if identity['source_run']!=source_id or setup['status']!='matched_observable_prefix':
        raise ValueError('unmatched source prefix')
    if evaluation['execution_summary_sha256']!=sha(trial/'summary.json') or evaluation['evaluation_returned_to_model']:
        raise ValueError('independent evaluation linkage differs')
    known=[c for c in usage if c['status']=='ok'];unknown=len(usage)-len(known)
    tokens=sum(c['input_tokens']+c['output_tokens'] for c in known)
    sent=sum(e['api_request_sent'] for e in events);prefix_sent=sum(e['api_request_sent'] for e in prefix)
    if (len(usage)!=summary['model_calls'] or tokens!=summary['known_total_tokens']
            or unknown!=summary['unknown_usage_calls'] or sent!=summary['api_requests']
            or prefix_sent!=summary['prefix_api_requests']
            or sent+prefix_sent!=summary['total_task_api_requests']):
        raise ValueError('usage accounting mismatch')
    if (tokens>plan['max_total_tokens'] or len(usage)>plan['max_calls']
            or sent+prefix_sent>source_plan['api_budget_by_task'][summary['task_id']]):
        raise ValueError('budget exceeded')
    if not summary['python_session']['container_removed']:
        raise ValueError('interpreter cleanup not established')
    original=read(trial/'prefix_spans.json')
    if any(spans[k]!=v for k,v in original.items()) or set(spans)-set(original)!={e['span_id'] for e in events}:
        raise ValueError('prefix or suffix receipt identity differs')
    by_call=collections.Counter(e['call'] for e in events if e['stage']=='model_tool')
    for call in known:
        response=read(trial/call['id']/'response.json')['message']
        if by_call[call['id']] != len(response.get('tool_calls') or [None]):
            raise ValueError('model call and recorded outer results differ')
    query_counts=collections.Counter();exceptions=collections.Counter();archive=0;selected=0
    for event in events:
        span=spans[event['span_id']];action=span['action'];obs=span['observation']
        if event['stage']=='python_api' and event['api_request_sent']:
            args=json.loads(action['arguments'])
            query_counts[(action['name'],json.dumps(args,sort_keys=True,separators=(',',':')))]+=1
        if event['stage']=='model_tool':
            if action and action['name']=='read_span':archive+=1
            if action and action['name']=='run_python':
                try:selected+=len(json.loads(action['arguments']).get('span_ids',[]))
                except (ValueError,TypeError):pass
            error=str(obs.get('error') or '')
            for name in ('NameError','KeyError','TypeError','ValueError','AttributeError'):
                if name in error:exceptions[name]+=1;break
    return {'run_id':summary['run_id'],'task_id':summary['task_id'],'arm':summary['arm'],
        'success':evaluation['official_success'],'stop_reason':summary['stop_reason'],
        'model_calls':len(usage),'known_total_tokens':tokens,'unknown_usage_calls':unknown,
        'api_requests':sent,'prefix_api_requests':prefix_sent,
        'setup_api_requests':setup['environment_replay']['api_requests'],
        'setup_wall_seconds':setup['wall_seconds'],'continuation_wall_seconds':summary['wall_seconds'],
        'full_wall_seconds':summary['full_wall_seconds'],'unknown_effect_requests':summary['unknown_effect_requests'],
        'name_or_value_exceptions':dict(exceptions),'archive_read_calls':archive,'selected_prior_receipts':selected,
        'repeat_identical_request_excess':sum(v-1 for v in query_counts.values()),
        'repeat_count_scope':'All identical dispatched API name+argument pairs, including writes; not all are waste.',
        'source_boundary_sha256':identity['boundary_manifest_sha256'],
        'audit_errors':[], 'source_hashes':{n:sha(trial/n) for n in
         ('summary.json','evaluation.json','events.json','spans.json','usage.json','setup.json','source_identity.json','plan.json','factor_plan.json')}}


def analyze(storage,root):
    plan=read(root/'configs/P31_handoff_factors_v01.json')
    status=read(storage/'records/context_pilot'/plan['batch_id']/'status.json')
    if status['status']!='complete' or len(status['completed'])!=16:
        raise ValueError('wait for all 16 continuations and independent evaluations')
    source_plan=read(root/plan['source_plan'])
    rows=[]
    for number,source in enumerate(plan['source_runs'],1):
        task_rows=[]
        for arm in ARMS:
            rid=f'P31_{number:02d}_{arm.upper()}'
            row=trial_row(storage/'records/context_pilot'/rid,source_plan,source)
            if row['task_id']!=source_plan['task_ids'][number-1] or row['arm']!=arm:
                raise ValueError('cell identity differs')
            task_rows.append(row)
        if len({r['source_boundary_sha256'] for r in task_rows})!=1:
            raise ValueError('conditions do not share the same source state')
        rows+=task_rows
    totals={}
    for arm in ARMS:
        selected=[r for r in rows if r['arm']==arm]
        totals[arm]={'trials':len(selected),'successes':sum(r['success'] for r in selected)}
        for key in ('known_total_tokens','unknown_usage_calls','model_calls','api_requests','setup_api_requests',
                    'setup_wall_seconds','continuation_wall_seconds','full_wall_seconds','archive_read_calls','selected_prior_receipts'):
            totals[arm][key]=sum(r[key] for r in selected)
    differences=[]
    for task in source_plan['task_ids']:
        cells={r['arm']:r for r in rows if r['task_id']==task}
        delta=(int(cells['recent_keep']['success'])-int(cells['full_keep']['success'])
              -int(cells['recent_reset']['success'])+int(cells['full_reset']['success']))
        differences.append({'task_id':task,'success_interaction':delta})
    return {'phase':'P31','all_sixteen_reviewed':True,'audit_errors':[], 'rows':rows,'totals':totals,
        'per_task_interactions':differences,'mean_success_interaction':sum(r['success_interaction'] for r in differences)/4,
        'novel_method_claim':False,'full_process_equivalence_claim':False,
        'limitations':['Four known development tasks, one seed, fixed early boundary; descriptive results only.',
          'A one-time restart includes an accurate runtime-availability notice.',
          'Reconstruction is separate experimental setup; no deployment efficiency or arbitrary heap equivalence claim.',
          'All cells can retrieve archived public receipts; recent history is not irreversible evidence deletion.',
          'This comparison is not evidence that changing task ownership or multi-agent reorganization improves outcomes.'],
        'source_hashes':{n:sha(root/n) for n in ('configs/P31_handoff_factors_v01.json','reports/P31_activation_v01.json',
                                              'reports/P31_prefix_checks.json','reports/P29_comparison.json','reports/P30_recorded_replay.json')}}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--storage-root',type=Path,required=True)
    parser.add_argument('--repo-root',type=Path,default=ROOT);args=parser.parse_args()
    target=args.repo_root/'reports/P31_comparison.json'
    if target.exists():raise FileExistsError('preserve previous whole-cohort report')
    result=analyze(args.storage_root,args.repo_root)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result['totals']))
