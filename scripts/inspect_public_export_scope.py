"""Inspect all three fixed known export records without executing anything."""
import argparse
from pathlib import Path
import signal
import time

from inspect_new_move_scope import later_cost
from public_export_evidence import inspect_export
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

PLAN='configs/P67_public_export_scope_v01.json'
RUNS=['P18_04_ROLES','P25_04_GUIDED','P29_04_CODE']


def inspect(storage):
    began=time.monotonic();plan=read(ROOT/PLAN)
    required={'phase':'P67','task_id':'6104387_1','run_ids':RUNS,'max_wall_seconds':120,
        'max_events_per_record':4000,'max_model_boundaries':80,'max_source_ids':512,
        'max_content_characters':1048576,'model_generations':0,'environment_api_requests':0,
        'evaluator_calls':0,'task_databases_read':0,'reserved_scenarios_read':0,'novel_method_claim':False}
    if any(plan.get(k)!=v for k,v in required.items()):raise ValueError('fixed P67 scope changed')
    for path,digest in {**plan['audit_reports'],**plan['helper_sha256']}.items():
        if sha(ROOT/path)!=digest:raise ValueError('closed source/helper changed')
    for app,digest in plan['public_api_implementation_sha256'].items():
        path=storage/'.runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps'/app/'apis.py'
        if sha(path)!=digest:raise ValueError('public API semantics changed')
    rows=[]
    for rid in RUNS:
        trial=storage/'records/context_pilot'/rid;source=plan['source_files'][rid]
        for name,digest in source.items():
            if sha(trial/name)!=digest:raise ValueError('fixed public record changed: '+rid+'/'+name)
        audit=read(ROOT/('reports/'+rid+'_execution_audit.json'))
        if audit['audit_errors'] or audit['task_id']!=plan['task_id']:raise ValueError('closed audit required')
        for name in ('summary','usage','events','spans'):
            expected=audit['source_hashes'].get(name,audit['source_hashes'].get(name+'.json'))
            if source[name+'.json']!=expected:raise ValueError('record differs from prior execution audit')
        task,spans,events,usage=[read(trial/(n+'.json')) for n in ('public_task','spans','events','usage')]
        result=inspect_export(task,spans,events,usage)
        result.update(run_id=rid,original_official_success=audit['evaluation']['official_success'],
            source_sha256=source,observed_cost_after_first_supported_boundary=later_cost(result['boundaries'],usage))
        rows.append(result)
    return {'phase':'P67','selection':plan['selection'],'known_tasks':1,'records':3,'rows':rows,
        'plan_sha256':sha(ROOT/PLAN),'checker_sha256':sha(ROOT/'scripts/public_export_evidence.py'),
        'inspector_sha256':sha(Path(__file__)),'public_api_implementation_sha256':plan['public_api_implementation_sha256'],
        'helper_sha256':plan['helper_sha256'],'audit_reports':plan['audit_reports'],
        'wall_seconds':time.monotonic()-began,'model_generations':0,'environment_api_requests':0,
        'evaluator_calls':0,'task_databases_read':0,'reserved_scenarios_read':0,
        'online_controller_installed':False,'novel_method_claim':False,
        'limits':'Single known instruction template; bounded, trusted API semantics and same credential scopes. Source terminal pages and metadata precede backup, supported backup precedes deletion. Exact strings with unambiguous title/artists pairs. No independent task sample or observed savings.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True);a=p.parse_args()
    target=ROOT/'reports/P67_public_export_scope.json'
    if target.exists():raise FileExistsError('preserve original inspection')
    def timeout(*_):raise TimeoutError('fixed 120-second inspection budget')
    old=signal.getsignal(signal.SIGALRM);signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
    try:result=inspect(a.storage_root)
    finally:signal.alarm(0);signal.signal(signal.SIGALRM,old)
    write_json(target,result)
    print([{'run_id':r['run_id'],'trace_support':r['final']['trace_support'],
        'source_ids':r['final']['source_ids'],'later_cost':r['observed_cost_after_first_supported_boundary']} for r in result['rows']])
