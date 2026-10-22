"""Describe P66 strict-prefix mismatches without changing the frozen criterion."""
import argparse
from collections import Counter
from pathlib import Path
import re
import time

from run_handoff_factors import ROOT, read, sha
from run_context_comparison import write_json

IDENTIFIER = re.compile(r'^\$(?:\.messages\[\d+\])?\.tool_calls\[\d+\]\.id$|^\$\.messages\[\d+\]\.tool_call_id$')


def difference_paths(a,b,path='$'):
    if type(a) is not type(b):return [path+':type']
    if isinstance(a,dict):
        return [p for k in sorted(set(a)|set(b)) for p in
            ([path+'.'+k+':missing'] if k not in a or k not in b else difference_paths(a[k],b[k],path+'.'+k))]
    if isinstance(a,list):
        if len(a)!=len(b):return [path+':length']
        return [p for i,(x,y) in enumerate(zip(a,b)) for p in difference_paths(x,y,f'{path}[{i}]')]
    return [] if a==b else [path]


def inspect(storage):
    began=time.monotonic();a=read(ROOT/'reports/P66_completion_audit.json');b=read(ROOT/'reports/P64_public_name_audit.json')
    if a['audit_errors'] or not a['server_stopped'] or a['owned_server_processes_present']:
        raise ValueError('closed reconciled P66 required')
    result=[]
    for row in a['rows']:
        if row['status']=='not_run':
            result.append({'run_id':row['run_id'],'status':'not_run'});continue
        base=next(x for x in b['rows'] if x['run_id']==row['baseline_comparison']['reference_run'])
        rows=[];totals=Counter()
        for n,call in enumerate(row['calls']):
            if n>=len(base['calls']):
                rows.append({'call_id':call['call_id'],'reference_present':False});continue
            old=base['calls'][n]
            if call['call_id']!=old['call_id']:raise ValueError('call order differs')
            c={'call_id':call['call_id'],'reference_present':True,'source_sha256':{}}
            for kind in ('request','response'):
                values=[]
                for side,rid,ref in [('new',row['run_id'],call),('reference',base['run_id'],old)]:
                    p=storage/'records/context_pilot'/rid/call['call_id']/(kind+'.json')
                    h=sha(p)
                    if h!=ref[kind+'_sha256']:raise ValueError('closed model record changed')
                    v=read(p);values.append(v if kind=='request' else v.get('message'))
                    c['source_sha256'][side+'_'+kind]=h
                diff=difference_paths(*values)
                ids=[p for p in diff if IDENTIFIER.fullmatch(p)]
                other=[p for p in diff if not IDENTIFIER.fullmatch(p)]
                c[kind]={'strict_equal':not diff,'identifier_difference_paths':ids,'other_difference_paths':other}
                totals[kind+'_identifier_differences']+=len(ids);totals[kind+'_other_differences']+=len(other)
            rows.append(c)
        result.append({'run_id':row['run_id'],'reference_run':base['run_id'],'status':row['status'],
            'strict_prefix_match_retained':row['baseline_comparison']['same_entire_executed_model_prefix'],
            'calls':rows,**dict(totals)})
    return {'phase':'P66_identity_difference_diagnosis','rows':result,
        'source_sha256':{p:sha(ROOT/p) for p in ('reports/P66_completion_audit.json','reports/P64_public_name_audit.json')},
        'inspector_sha256':sha(Path(__file__)),'criterion_changed':False,
        'new_model_calls':0,'environment_api_requests':0,'evaluator_calls':0,'reserved_scenarios_read':0,
        'wall_seconds':time.monotonic()-began,
        'scope':'Posthoc field-path diagnosis only. Original strict request/message prefix comparison remains unchanged; no causal or general-quality guarantee is added.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True);a=p.parse_args()
    out=ROOT/'reports/P66_identity_differences.json'
    if out.exists():raise FileExistsError('preserve original diagnosis')
    result=inspect(a.storage_root);write_json(out,result)
    print([{k:v for k,v in r.items() if k!='calls'} for r in result['rows']])
