"""Describe a completely audited handoff cohort without exposing private values.

Matching requests are not automatically redundant: state may have changed, and
the request may be a write. These counters do not identify a causal remedy.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from diagnose_code_programs import classify
from handoff_factors import ARMS

ROOT=Path(__file__).resolve().parents[1]
def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'))


def require_complete(report,status,phase):
    if phase not in ('P31','P32','P33'):raise ValueError('unknown completed cohort')
    arms=ARMS
    if phase=='P33':
        from handoff_output_views import ARMS as arms
    count=4*len(arms)
    rows=report.get('rows',[]);tasks={r['task_id'] for r in rows}
    flag='all_twelve_reviewed' if phase=='P33' else 'all_sixteen_reviewed'
    if (report.get('phase')!=phase or not report.get(flag)
        or report.get('audit_errors') or len(tasks)!=4 or len(rows)!=count
        or {(r['task_id'],r['arm']) for r in rows}!={(t,a) for t in tasks for a in arms}
        or status.get('status')!='complete'
        or len(status.get('completed',[]))!=count
        or set(status.get('completed',[]))!={r['run_id'] for r in rows}):
        raise ValueError('require the complete audited cohort')


def matching_prefix_requests(prefix_events,prefix_spans,events,spans):
    def key(span):
        action=span['action']
        return action['name'],canonical(json.loads(action['arguments']))
    previous={}
    for event in prefix_events:
        if event['api_request_sent']:
            span=prefix_spans[event['span_id']]
            previous[key(span)]=canonical(span['observation'])
    names=Counter();same=0;different=0
    for event in events:
        if not event['api_request_sent']:continue
        span=spans[event['span_id']];k=key(span)
        if k not in previous:continue
        names[k[0]]+=1
        if canonical(span['observation'])==previous[k]:same+=1
        else:different+=1
    return {'requests_matching_prefix':sum(names.values()),
            'matching_request_api_names':dict(names),
            'same_public_observation_as_last_prefix_request':same,
            'different_public_observation_from_last_prefix_request':different,
            'unnecessary_request_claim':False}


def analyze(storage,root,phase):
    report_path=root/f'reports/{phase}_comparison.json'
    suffix='output_views' if phase=='P33' else 'handoff_factors'
    report=read(report_path);plan=read(root/f'configs/{phase}_{suffix}_v01.json')
    status=read(storage/'records/context_pilot'/plan['batch_id']/'status.json')
    require_complete(report,status,phase)
    rows=[]
    for cell in report['rows']:
        trial=storage/'records/context_pilot'/cell['run_id']
        for name in ('events.json','spans.json','usage.json','source_identity.json'):
            if sha(trial/name)!=cell['source_hashes'][name]:raise ValueError('audited source changed: '+name)
        events,spans,usage=[read(trial/n) for n in ('events.json','spans.json','usage.json')]
        prefix_events,prefix_spans=[read(trial/n) for n in ('prefix_events.json','prefix_spans.json')]
        programs={};results=sorted((trial/'programs').glob('*/result_private.json'))
        for path in results:programs.setdefault(path.parent.name.rsplit('_',1)[0],[]).append(read(path))
        row=classify(usage,events,spans,programs)
        row.update(matching_prefix_requests(prefix_events,prefix_spans,events,spans))
        row.update(run_id=cell['run_id'],task_id=cell['task_id'],arm=cell['arm'])
        known=[c for c in usage if c['status']=='ok']
        row['known_input_tokens']=sum(c['input_tokens'] for c in known)
        row['known_output_tokens']=sum(c['output_tokens'] for c in known)
        row['first_continuation_input_tokens']=usage[0]['input_tokens'] if usage and usage[0]['status']=='ok' else None
        if row['known_input_tokens']+row['known_output_tokens']!=cell['known_total_tokens']:
            raise ValueError('token totals differ from completed audit')
        row['program_result_sha256']={str(p.relative_to(trial)):sha(p) for p in results}
        row['source_sha256']={n:sha(trial/n) for n in ('events.json','spans.json','usage.json','prefix_events.json','prefix_spans.json')}
        rows.append(row)
    flag='all_twelve_reviewed' if phase=='P33' else 'all_sixteen_reviewed'
    return {'phase':phase,flag:True,'kind':'posthoc_closed_cohort_diagnostics',
            'rows':rows,'model_calls_added':0,'api_requests_added':0,'evaluator_contents_read':False,
            'novel_method_claim':False,'causal_remedy_identified':False,
            'request_match_scope':'Exact API name and parsed JSON arguments; aliases are not normalized. Includes writes. Compares to the last equal request in the prefix; changed observations can be legitimate.',
            'comparison_sha256':sha(report_path),'script_sha256':sha(Path(__file__)),
            'classifier_sha256':sha(root/'scripts/diagnose_code_programs.py')}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--repo-root',type=Path,default=ROOT);p.add_argument('--phase',choices=('P31','P32','P33'),required=True);a=p.parse_args()
    target=a.repo_root/f'reports/{a.phase}_program_diagnostics.json'
    if target.exists():raise FileExistsError('preserve completed diagnostics')
    result=analyze(a.storage_root,a.repo_root,a.phase)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([{'run_id':r['run_id'],'first_input':r['first_continuation_input_tokens'],
                      'prefix_request_matches':r['requests_matching_prefix'],'errors':r['program_error_types']} for r in result['rows']]))
