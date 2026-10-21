"""Synthetic-only container check for saved-reply Python replay."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from persistent_api_python import PersistentApiPython
from recorded_python_replay import RecordedChannel, replay_programs

ROOT=Path(__file__).resolve().parents[1]


def preflight(storage, output, report):
    if output.exists() or report.exists():
        raise FileExistsError('preserve earlier replay preflight')
    output.mkdir(parents=True)
    schemas={f'sample__{name}':{'name':f'sample__{name}','parameters':{'type':'object','properties':{key:{'type':'integer'}}}}
             for name,key in [('read','index'),('write','count')]}
    def entry(api,arguments,value):
        return {'request':{'kind':'api','id':1,'app':'sample','api':api,'arguments':arguments},
                'reply':{'id':1,'ok':True,'value':value,'new_schemas':{}},
                'originally_sent':True,'declared_complete':False,'effects_unknown':False}
    examples=[
        ('import math\nitem=call_api("sample","read",index=2)\ndef square(x): return x*x\nprint(item["count"])',
         '7\n',None,[entry('read',{'index':2},{'count':7})]),
        ('answer=square(item["count"])\nreceipt=call_api("sample","write",count=answer)\nprint(receipt["accepted"])',
         'True\n',None,[entry('write',{'count':49},{'accepted':True})]),
        ('partial=answer+1\nraise ValueError("synthetic boundary")','', 'ValueError: synthetic boundary',[]),
        ('print(partial,math.sqrt(answer))','50 7.0\n',None,[]),
    ]
    programs=[]
    for i,(code,stdout,error,entries) in enumerate(examples,1):
        programs.append({'name':f'synthetic_{i:02d}',
                         'source':{'code':code,'observations':[],'api_schemas':schemas,'program_index':i},
                         'expected':{'status':'execution_error' if error else 'ok','stdout':stdout,
                                     'stdout_truncated':False,'error':error,'declared_complete':False,
                                     'unknown_effects':False},
                         'entries':entries,'source_sha256':{}})
    started=time.monotonic()
    session=PersistentApiPython(storage,output/'matched_session')
    try:
        rows=replay_programs(programs,schemas,session,output/'programs',storage)
    finally:
        session.close()
    mismatch_session=PersistentApiPython(storage,output/'mismatch_session')
    channel=RecordedChannel(schemas,[entry('write',{'count':49},{'accepted':True})],schemas)
    try:
        mismatch=mismatch_session.run('call_api("sample","write",count=50)',[],channel,
                                     storage_root=storage,record_dir=output/'mismatch_program',timeout=10)
    finally:
        mismatch_session.close()
    checks={
        'four_programs_match':len(rows)==4 and all(r['observable_prefix_matches'] for r in rows),
        'no_live_api_dispatch':all(r['api_requests_sent']==0 for r in rows) and mismatch['api_requests']==0,
        'changed_write_rejected':mismatch['status']=='harness_error' and channel.mismatch=='recorded request differs',
        'all_containers_removed':session.state['container_removed'] and mismatch_session.state['container_removed'],
        'all_isolation_controls':len(session.controls)==14 and all(session.controls.values())
                                 and len(mismatch_session.controls)==14 and all(mismatch_session.controls.values()),
    }
    result={'scope':'Synthetic data only; no model calls, live AppWorld calls or evaluator use.',
            'programs':5,'sessions':2,'recorded_requests_matched':sum(r['matched_requests'] for r in rows),
            'model_calls':0,'api_requests_sent':0,'checks':checks,'wall_seconds':time.monotonic()-started,
            'source_sha256':{f:hashlib.sha256((ROOT/'scripts'/f).read_bytes()).hexdigest()
                             for f in ('recorded_python_replay.py','persistent_api_python.py','preflight_recorded_replay.py')},
            'full_process_equivalence_claim':False}
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    if not all(checks.values()):raise RuntimeError('replay preflight failed')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();preflight(a.storage_root,a.output,a.report)
