"""Container-only synthetic lifecycle probe, with zero model/real AppWorld calls."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
from context_preservation import function
from appworld_native_tools import NativeCatalog
from container_api_python import ApiChannel
from persistent_api_python import PersistentApiPython

class Bridge:
    def __init__(self):self.calls=[]
    def request(self,request):
        self.calls.append(request)
        return {'ok':True,'result':{'observation':json.dumps(request['call']['args']['value']),
            'declared_complete':False}}


def probe(storage,out):
    out.mkdir(parents=True,exist_ok=False)
    tools=[function('api_docs__echo','synthetic fixture',{'value':{'type':'integer'}},['value'])]
    catalog=NativeCatalog(tools);bridge=Bridge();results=[];sessions=[]
    session=PersistentApiPython(storage,out/'session_one')
    snippets=['import math\nx=call_api("api_docs","echo",value=7)\ndef f():return x+1\nprint(x)',
        'print(f(),math.isqrt(81))', 'x=13\nraise ValueError("fixture")',
        'print(x,observations[0]["fixture"])', 'call_api("api_docs","echo",value=8)']
    try:
        for i,code in enumerate(snippets,1):
            channel=ApiChannel(catalog,bridge,0 if i==5 else 3)
            r=session.run(code,[{'fixture':i}],channel,storage_root=storage,
                record_dir=out/'programs'/str(i),timeout=30)
            results.append(r)
    finally:sessions.append(session.close())
    assert [r['status'] for r in results]==['ok','ok','execution_error','ok','execution_error']
    assert results[1]['stdout']=='8 9\n' and results[3]['stdout']=='13 4\n'
    assert len(bridge.calls)==1 and results[-1]['api_requests']==0
    separate=PersistentApiPython(storage,out/'session_two')
    try:
        r=separate.run('print(x)',[],ApiChannel(catalog,bridge,3),storage_root=storage,
            record_dir=out/'separate_program',timeout=30)
        assert r['status']=='execution_error' and 'NameError' in r['error']
        results.append(r)
        t=separate.run('while True:pass',[],ApiChannel(catalog,bridge,3),storage_root=storage,
            record_dir=out/'timeout_program',timeout=.5)
        assert t['status']=='timeout' and not t['session_usable'] and t['container_removed']
        results.append(t)
        try:
            separate.run('print(1)',[],ApiChannel(catalog,bridge,3),storage_root=storage,
                record_dir=out/'forbidden_resume',timeout=1)
        except RuntimeError:pass
        else:raise AssertionError('timeout must not resume/reset silently')
    finally:sessions.append(separate.close())
    class UncertainBridge:
        def __init__(self):self.attempts=0
        def request(self,request):
            self.attempts+=1
            raise TimeoutError('synthetic response unknown')
    uncertain=UncertainBridge();third=PersistentApiPython(storage,out/'session_three')
    try:
        r=third.run('call_api("api_docs","echo",value=9)',[],ApiChannel(catalog,uncertain,3),
            storage_root=storage,record_dir=out/'uncertain_program',timeout=30)
        assert r['unknown_effects'] and r['api_requests']==1 and r['container_removed']
        assert uncertain.attempts==1 and not r['session_usable']
        results.append(r)
    finally:sessions.append(third.close())
    fourth=PersistentApiPython(storage,out/'session_four')
    try:
        source='import sys, json\nsys.__stdout__.write(json.dumps({"kind":"api","id":1,"program_index":0,"app":"api_docs","api":"echo","arguments":{"value":10}})+"\\n")\nsys.__stdout__.flush()'
        r=fourth.run(source,[],ApiChannel(catalog,bridge,3),storage_root=storage,
            record_dir=out/'stale_program_packet',timeout=30)
        assert r['status']=='harness_error' and r['api_requests']==0 and r['container_removed']
        assert len(bridge.calls)==1
        results.append(r)
    finally:sessions.append(fourth.close())
    assert all(s['container_removed'] for s in sessions)
    assert all(len(r['controls'])==14 and all(r['controls'].values()) for r in results)
    return {'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'model_calls':0,'appworld_requests':0,'fixture_api_dispatch_attempts':len(bridge.calls)+uncertain.attempts,
        'programs':len(results),'sessions':len(sessions),'all_controls_passed':True,
        'all_task_containers_removed':True,'values_functions_imports_retained':True,
        'exception_partial_state_retained':True,'task_isolation_checked':True,
        'timeout_no_resume_checked':True,'api_budget_enforced':True,
        'unknown_effects_stop_without_retry':True,'stale_program_packet_rejected':True,
        'scope':'Synthetic fixtures only; no model task performance or exact process-state restoration claim.',
        'source_sha256':{n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest()
            for n in ('persistent_api_python.py','container_api_python.py','container_data_python.py','preflight_persistent_api.py')}}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--private-output',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();r=probe(a.storage_root,a.private_output);a.report.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
