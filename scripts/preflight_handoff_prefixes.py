"""Validate all four fixed environment/runtime prefixes before P31 inference."""
import argparse
import datetime
from pathlib import Path
import time

from appworld_native_tools import NativeCatalog
from handoff_factors import replay_environment
from persistent_api_python import PersistentApiPython
from recorded_python_replay import replay_programs
from run_context_comparison import Bridge, write_json
from run_handoff_factors import prepare_sources, sha, ROOT


def run(storage, root, output, report, phase='P31'):
    if phase=='P31':plan, source_plan, tools, schemas, prepared = prepare_sources(storage, root)
    elif phase=='P32':
        from later_handoff_sources import prepare_later_sources
        plan, source_plan, tools, schemas, prepared = prepare_later_sources(storage, root)
    else:raise ValueError('unknown phase')
    if output.exists() or report.exists(): raise FileExistsError('preserve preflight records')
    output.mkdir(parents=True)
    rows=[];started=time.monotonic()
    appworld=storage/'.runtime/appworld/r18_probe_01'
    for number, item in enumerate(prepared,1):
        prefix=item['prefix'];task_id=item['task_id'];rid=f'{phase}_PREFIX_V01_{number:02d}'
        out=output/rid;out.mkdir()
        world=appworld/'experiments/outputs'/rid
        if world.exists():raise FileExistsError('preserve original world')
        bridge=session=None;at=time.monotonic()
        row={'source_run':item['source_run'],'task_id':task_id,'status':'not_started',
             'boundary_manifest_sha256':item['boundary_manifest_sha256'],
             'model_calls':0,'evaluator_invocations':0}
        row['environment']={}
        try:
            bridge=Bridge(storage/'.runtime/appworld/venv/bin/python',appworld,out)
            result=bridge.request({'op':'init','task_id':task_id,'experiment':rid,'seed':source_plan['seed']})
            if not result['ok'] or result['result']!=prefix['public_task'] or result['result']['ground_truth_loaded']:
                raise ValueError('initial task differs')
            catalog=NativeCatalog(tools)
            row['environment']=replay_environment(prefix,catalog,bridge,world/'tasks'/task_id/'dbs',
                deadline=at+plan['max_setup_seconds'],clock=time.monotonic,accounting=row['environment'])
            session=PersistentApiPython(storage,out/'python_session')
            replayed=replay_programs(item['programs'],schemas,session,out/'programs',storage)
            row['python']={'programs':len(replayed),'api_requests_sent':0,'checks':replayed}
            if len(replayed)!=len(item['programs']) or not all(r['observable_prefix_matches'] for r in replayed):
                raise ValueError('Python prefix mismatch')
            if time.monotonic()-at>plan['max_setup_seconds']:raise TimeoutError('setup deadline')
            row['status']='matched_observable_prefix'
        except Exception as exc:
            row.update(status='failed',error_type=type(exc).__name__)
            (out/'error_private.txt').write_text(str(exc))
        finally:
            for resource in (session,bridge):
                if resource is not None:
                    try:resource.close()
                    except Exception as exc:row.update(status='cleanup_error',error_type=type(exc).__name__)
            row['wall_seconds']=time.monotonic()-at
            row['container_removed']=session.state['container_removed'] if session else None
            write_json(out/'summary.json',row);rows.append(row)
    source_names=['scripts/handoff_factors.py','scripts/run_handoff_factors.py','scripts/preflight_handoff_prefixes.py',
                  f'configs/{phase}_handoff_factors_v01.json','reports/P30_recorded_replay.json']
    if phase=='P32':source_names.append('scripts/later_handoff_sources.py')
    result={'phase':phase+'_prefix_preflight','at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'all_four_attempted':len(rows)==4,
            'all_observable_prefixes_match':all(r['status']=='matched_observable_prefix' for r in rows),
            'rows':rows,'model_calls':0,'evaluator_invocations':0,
            'setup_api_requests':sum(r.get('environment',{}).get('api_requests',0) for r in rows),
            'wall_seconds':time.monotonic()-started,'full_process_equivalence_claim':False,
            'source_hashes':{name:sha(root/name) for name in source_names},
            'scope':'Original world never changed. Public API observations, discovered schemas, saved DB bytes and recorded Python request/output correspondence only.'}
    write_json(output/'summary.json',result);write_json(report,result)
    print({k:result[k] for k in ('all_four_attempted','all_observable_prefixes_match','setup_api_requests','wall_seconds')})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--storage-root',type=Path,required=True)
    parser.add_argument('--repo-root',type=Path,default=ROOT);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True);parser.add_argument('--phase',choices=('P31','P32'),default='P31');a=parser.parse_args()
    run(a.storage_root,a.repo_root,a.output,a.report,a.phase)
