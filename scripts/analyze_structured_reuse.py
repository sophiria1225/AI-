"""Closed-cohort posthoc probe; never substitutes a live tool response."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

from diagnose_handoff_programs import require_complete
from structured_reuse_probe import RecordIndex

ROOT=Path(__file__).resolve().parents[1]
def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def decode(observation):
    if any(k in observation for k in ('api_error','format_error','not_executed')):
        return False,None
    if 'observation' not in observation:return False,None
    value=observation['observation']
    if type(value) is str:
        try:value=json.loads(value)
        except ValueError:pass
    return True,value


def probe(events,spans,methods,index,*,measure):
    rows=[];counts=Counter()
    for event in events:
        if not event['api_request_sent']:continue
        span=spans[event['span_id']];action=span['action'];name=action['name']
        arguments=json.loads(action['arguments']);counts['sent_requests']+=1
        if methods.get(name)!='GET':
            index.invalidate();counts['nonget_or_unknown_invalidations']+=1
            continue
        counts['get_requests']+=1
        ok,value=decode(span['observation'])
        if not ok:
            counts['get_error_responses']+=1
            continue
        counts['get_success_responses']+=1
        if measure:
            row=index.assess(name,arguments,value)
            row['api']=name;row['event_index']=counts['sent_requests']
            rows.append(row)
        # Current reply becomes a source only after the candidate assessment.
        index.add(name,arguments,value)
    return dict(counts),rows


def run(storage,root):
    report=read(root/'reports/P33_comparison.json');plan=read(root/'configs/P33_output_views_v01.json')
    status=read(storage/'records/context_pilot'/plan['batch_id']/'status.json')
    require_complete(report,status,'P33')
    out=storage/'records/context_pilot/P36_structured_reuse_v01'
    target=root/'reports/P36_structured_reuse.json'
    if out.exists() or target.exists():raise FileExistsError('preserve existing probe')
    out.mkdir();started=time.monotonic();methods={};schema_hashes={}
    data=storage/'.runtime/appworld/r18_probe_01/data/api_docs/standard'
    for path in sorted(data.glob('*.json')):
        if path.stem=='admin':raise ValueError('public catalog only')
        schema_hashes[path.name]=sha(path)
        for api,item in read(path).items():methods[path.stem+'__'+api]=item['method'].upper()
    sources={p:sha(root/p) for p in ('scripts/structured_reuse_probe.py',
        'scripts/analyze_structured_reuse.py','docs/experiments/P36_structured_reuse.md',
        'reports/P33_comparison.json')}
    write(out/'source_sha256.json',sources);rows=[]
    for cell in report['rows']:
        trial=storage/'records/context_pilot'/cell['run_id']
        for name in ('events.json','spans.json','source_identity.json'):
            if sha(trial/name)!=cell['source_hashes'][name]:raise ValueError('closed source changed')
        identity=read(trial/'source_identity.json')
        original=storage/'records/context_pilot'/identity['source_run']
        known=read(original/'provenance.json')['public_schema_hashes']
        for name,digest in schema_hashes.items():
            if known['api_docs/standard/'+name]!=digest:raise ValueError('public schema changed')
        index=RecordIndex()
        prefix_counts,_=probe(read(trial/'prefix_events.json'),read(trial/'prefix_spans.json'),methods,index,measure=False)
        prefix_invalidations=index.invalidations
        counts,observations=probe(read(trial/'events.json'),read(trial/'spans.json'),methods,index,measure=True)
        row={k:cell[k] for k in ('run_id','task_id','arm')}
        totals={key:sum(item[key] for item in observations) for key in (
            'exact_previous_request','exact_reply_content_equal','eligible_identity_shape',
            'candidate_records','other_auth_candidate_records','candidate_fields','conflicting_prior_fields',
            'matching_current_fields','different_current_fields','missing_current_fields',
            'matching_fields_from_different_api','matching_nonidentity_fields_from_different_api',
            'full_current_object_covered','all_current_fields_from_different_api')
            if key!='exact_reply_content_equal'}
        totals['exact_reply_content_equal']=sum(item['exact_reply_content_equal'] is True for item in observations)
        totals['requests_with_cross_api_matching_data']=sum(item['matching_nonidentity_fields_from_different_api']>0 for item in observations)
        totals['requests_with_prior_conflicts']=sum(item['conflicting_prior_fields']>0 for item in observations)
        row.update(prefix_counts=prefix_counts,counts=counts,totals=totals,observations=observations,
                   prefix_invalidations=prefix_invalidations,all_invalidations=index.invalidations,
                   bounded_scans=index.bounded_scans,
                   source_sha256={n:sha(trial/n) for n in ('events.json','spans.json','prefix_events.json','prefix_spans.json')})
        rows.append(row)
        print(json.dumps({k:row[k] for k in ('run_id','counts','totals')}),flush=True)
    result={'phase':'P36_structured_reuse','all_twelve_reviewed':len(rows)==12,'rows':rows,
            'source_sha256':sources,'public_documentation_sha256':schema_hashes,
            'model_calls':0,'live_api_requests':0,'final_evaluator_invocations':0,'reserved_scenarios_read':0,
            'wall_seconds':time.monotonic()-started,
            'runtime_reuse_correctness_established':False,'actual_savings_measured':False,'novel_method_claim':False,
            'limits':['Structural identity can mistake a foreign key for a primary key; content comparisons are posthoc only.',
                'Authentication is partitioned by exact credential arguments; missing credentials do not imply the same principal.',
                'Non-GET or unknown dispatched actions invalidate every app; GET can still have stateful or external effects.',
                'No alias normalization or semantic field mapping. Equal prior values are not proof of freshness.',
                'Current reply fields are used for posthoc coverage, not an operational demand prediction.',
                'Partial field agreement does not replace full-object printing or prove fewer tokens/API calls.']}
    write(out/'summary.json',result);write(target,result)
    return 0


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--repo-root',type=Path,default=ROOT);a=p.parse_args()
    raise SystemExit(run(a.storage_root,a.repo_root))
