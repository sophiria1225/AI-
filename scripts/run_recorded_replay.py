"""Post-cohort Python replay prerequisite for future handoff comparisons.

No inference, Bridge, AppWorld world construction, evaluation, or live API call
is performed here. Full process equivalence is deliberately not asserted.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import time

from analyze_code_comparison import require_complete
from audit_code_execution import audit
from inspect_appworld_api_schemas import load_public_tools
from persistent_api_python import PersistentApiPython
from recorded_python_replay import load_programs, replay_programs

ROOT=Path(__file__).resolve().parents[1]


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def put(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def check_ready(storage,root):
    plan=read(root/'configs/P29_stateful_code_v01.json')
    require_complete(storage,plan)
    result=read(root/'reports/P29_comparison.json')
    if (not result['all_four_reviewed'] or len(result['pairs'])!=4
            or [r['task_id'] for r in result['pairs']]!=plan['task_ids']):
        raise ValueError('wait for the complete P29 cohort review')
    for name,digest in result['source_hashes'].items():
        if sha(root/name)!=digest:raise ValueError('P29 review source changed')
    preflight=read(root/'reports/P30_replay_preflight.json')
    if not all(preflight['checks'].values()):raise ValueError('preflight incomplete')
    for name,digest in preflight['source_sha256'].items():
        if sha(root/'scripts'/name)!=digest:raise ValueError('replay implementation changed after preflight')
    return plan


def run(storage,root,output,report):
    plan=check_ready(storage,root)
    if output.exists() or report.exists():raise FileExistsError('preserve prior replay records')
    output.mkdir(parents=True)
    tools,schema_hashes,_=load_public_tools(storage/'.runtime/appworld/r18_probe_01/data')
    schemas={t['function']['name']:t['function'] for t in tools}
    rows=[];started=time.monotonic()
    put(output/'status.json',{'status':'running','model_calls':0,'api_requests_sent':0})
    for task,arm,rid in plan['run_order']:
        trial=storage/'records/context_pilot'/rid
        destination=output/rid;destination.mkdir()
        row={'run_id':rid,'status':'not_started','model_calls':0,'api_requests_sent':0}
        session=None;task_started=time.monotonic()
        try:
            checked=audit(trial)
            if checked['audit_errors'] or checked['code_audit_errors']:
                raise ValueError('recorded trial audit differs')
            if read(trial/'provenance.json')['public_schema_hashes']!=schema_hashes:
                raise ValueError('public API schema source differs')
            programs=load_programs(trial,schemas)
            if not programs:raise ValueError('no executed programs to replay')
            session=PersistentApiPython(storage,destination/'python_session')
            observed=replay_programs(programs,schemas,session,destination/'programs',storage)
            matches=len(observed)==len(programs) and all(x['observable_prefix_matches'] for x in observed)
            row.update(status='observable_prefix_match' if matches else 'observable_mismatch',
                       planned_programs=len(programs),replayed_programs=len(observed),programs=observed,
                       recorded_requests=sum(len(p['entries']) for p in programs),
                       matched_requests=sum(p['matched_requests'] for p in observed),
                       source_sha256={name:sha(trial/name) for name in
                                      ('events.json','spans.json','summary.json','plan.json','provenance.json')})
        except Exception as exc:
            row.update(status='replay_not_established',error_type=type(exc).__name__)
            (destination/'error_private.txt').write_text(str(exc))
        finally:
            if session is not None:
                try:
                    session.close()
                    row['container_removed']=session.state['container_removed']
                except Exception as exc:
                    row.update(status='cleanup_error',cleanup_error_type=type(exc).__name__)
            row['replay_wall_seconds']=time.monotonic()-task_started
            put(destination/'summary.json',row)
            rows.append(row)
            put(output/'status.json',{'status':'running','completed_trials':len(rows),
                                     'model_calls':0,'api_requests_sent':0})
    result={'phase':'P30','kind':'recorded_reply_replay_validation',
            'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'all_four_attempted':len(rows)==4,'trials':rows,
            'all_observable_prefixes_match':all(r['status']=='observable_prefix_match' for r in rows),
            'model_calls':0,'api_requests_sent':0,'wall_seconds':time.monotonic()-started,
            'original_outcomes_replaced':False,'full_process_equivalence_claim':False,
            'limitations':['Checks saved requests, printed output, exception text and completion flags only.',
                           'Does not prove equality of unprinted objects, heap aliases, threads, RNG or future behavior.',
                           'Python/OS time, randomness, object repr and background work can prevent replay.',
                           'No environment state is restored or changed; recorded write replies are inert.',
                           'Ordinary record/replay prerequisite, not a novel method or a new success score.'],
            'source_sha256':{'P29_comparison':sha(root/'reports/P29_comparison.json'),
                             'preflight':sha(root/'reports/P30_replay_preflight.json'),
                             'runner':sha(Path(__file__)),'replay':sha(root/'scripts/recorded_python_replay.py')}}
    put(report,result);put(output/'summary.json',result)
    put(output/'status.json',{'status':'complete','all_observable_prefixes_match':result['all_observable_prefixes_match'],
                             'completed_trials':len(rows),'model_calls':0,'api_requests_sent':0})
    print(json.dumps({'trials':[(r['run_id'],r['status'],r.get('replayed_programs')) for r in rows],
                      'model_calls':0,'api_requests_sent':0,'seconds':result['wall_seconds']}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--repo-root',type=Path,default=ROOT);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    run(a.storage_root,a.repo_root,a.output,a.report)
