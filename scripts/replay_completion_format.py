"""Four fixed completion-only interventions after strict public-prefix replay.

No model calls, hidden task state, answer search or original-world mutation.
Evaluation runs in the existing separate process after each new world is frozen.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time

from inspect_appworld_api_schemas import load_public_tools
from native_boundary_record import verify_boundary
from run_context_comparison import Bridge, write_json

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('P22_02_ROLES', 'P24_02_GUIDED')
ARMS = ('answer_present', 'answer_omitted')
SOURCE_FILES = ('provenance.json', 'plan.json', 'public_task.json', 'events.json',
                'spans.json', 'summary.json', 'evaluation.json')
CODE_FILES = ('replay_completion_format.py', 'appworld_native_tools.py',
              'appworld_bridge.py', 'context_preservation.py', 'run_context_comparison.py',
              'inspect_appworld_api_schemas.py', 'native_boundary_record.py',
              'evaluate_context_trial.py')
FROZEN_DISPATCH = dict(zip(SOURCES, ('p22-run', 'p24-run'), strict=True))


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def database_hashes(directory):
    files = list(directory.iterdir())
    if not files or any(not p.is_file() or p.is_symlink() for p in files):
        raise ValueError('unexpected saved database directory')
    return {'dbs/'+p.name: sha(p) for p in files}


def completion_structure(source):
    events, spans = read(source/'events.json'), read(source/'spans.json')
    calls = list(dict.fromkeys(e['call'] for e in events))
    terminal = [e for e in events if (spans[e['span_id']].get('action') or {}).get('name')
                == 'supervisor__complete_task']
    if (len(terminal) != 1 or terminal[0] != events[-1] or len(calls) < 2
            or len([e for e in events if e['call'] == calls[-1]]) != 1):
        raise ValueError('requires exactly one terminal-only final response')
    message = read(source/calls[-1]/'response.json')['message']
    if (len(message.get('tool_calls', [])) != 1
            or message['tool_calls'][0]['function'] != spans[terminal[0]['span_id']]['action']):
        raise ValueError('completion response and event differ')
    args = json.loads(message['tool_calls'][0]['function']['arguments'])
    if not set(args) <= {'answer', 'status'} or 'status' not in args:
        raise ValueError('unexpected completion arguments')
    return events, spans, calls, message


def change_completion(message, arm, recorded_answer):
    if arm not in ARMS or not isinstance(recorded_answer, str) or not recorded_answer:
        raise ValueError('fixed arm and recorded nonempty answer required')
    changed = copy.deepcopy(message)
    args = json.loads(message['tool_calls'][0]['function']['arguments'])
    if arm == 'answer_present': args['answer'] = recorded_answer
    else: args.pop('answer', None)
    changed['tool_calls'][0]['function']['arguments'] = json.dumps(args, ensure_ascii=False)
    return changed


def assert_rows_match(rows, expected, spans):
    if len(rows) != len(expected):
        raise ValueError('prefix event count differs')
    for row, event in zip(rows, expected, strict=True):
        original = spans[event['span_id']]
        if (row['action'] != original['action'] or row['observation'] != original['observation']
                or row['api_request_sent'] != event['api_request_sent']
                or row.get('effects_unknown', False) != event.get('effects_unknown', False)
                or row['new_tools'] != event['new_tools']):
            raise ValueError('prefix action, observation or dispatch differs')


def original_dispatcher(storage, rid, provenance):
    # P22 predates the optional Python tool. Load its own unchanged dispatcher,
    # rather than claiming the current implementation is byte-identical.
    path = storage/'.runtime/worktrees'/FROZEN_DISPATCH[rid]/'scripts/appworld_native_tools.py'
    if sha(path) != provenance['sources']['appworld_native_tools.py']:
        raise ValueError('original dispatcher is missing or changed')
    spec = importlib.util.spec_from_file_location('replay_dispatch_'+rid, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.NativeCatalog, module.dispatch_native_calls


def prepare(storage, path):
    if path.exists():
        raise FileExistsError('preserve fixed replay plan')
    sources = {}
    for rid in SOURCES:
        source = storage/'records/context_pilot'/rid
        _, _, calls, message = completion_structure(source)
        original_dispatcher(storage, rid, read(source/'provenance.json'))
        verify_boundary(source/'boundaries', calls[-2])
        sources[rid] = dict(hashes={name: sha(source/name) for name in SOURCE_FILES},
            prefix_boundary=calls[-2],
            boundary_sha256=sha(source/'boundaries/manifests'/(calls[-2]+'.json')),
            call_hashes={cid: {name: sha(source/cid/name) for name in ('request.json','response.json')}
                         for cid in calls},
            original_answer_present='answer' in json.loads(message['tool_calls'][0]['function']['arguments']))
    if [sources[r]['original_answer_present'] for r in SOURCES] != [True, False]:
        raise ValueError('the predeclared present/omitted source pair changed')
    rest=[]
    for rid in SOURCES:
        _,_,_,message=completion_structure(storage/'records/context_pilot'/rid)
        rest.append({k:v for k,v in json.loads(message['tool_calls'][0]['function']['arguments']).items()
                     if k!='answer'})
    if rest[0]!=rest[1]:
        raise ValueError('other completion arguments differ between sources')
    plan = dict(created_at=now(), sources=sources, arms=list(ARMS),
        run_prefix='P24_COMPLETION_V01', max_api_requests=80, max_wall_seconds=600,
        code_sha256={n: sha(ROOT/'scripts'/n) for n in CODE_FILES},
        specification_sha256=sha(ROOT/'docs/experiments/completion_replay_20261021.md'),
        cases=[dict(source=rid,arm=arm) for rid in SOURCES for arm in ARMS],
        model_calls=0, requires_p25_complete=True)
    write_json(path, plan)
    print(json.dumps({'plan':str(path),'cases':len(plan['cases']),'model_calls':0}))


def verify_plan(storage, plan):
    if (plan['cases'] != [dict(source=r,arm=a) for r in SOURCES for a in ARMS]
            or plan['arms'] != list(ARMS) or plan['max_api_requests'] != 80
            or plan['max_wall_seconds'] != 600 or plan['run_prefix'] != 'P24_COMPLETION_V01'
            or not plan['requires_p25_complete']):
        raise ValueError('fixed case set or budgets changed')
    for name, digest in plan['code_sha256'].items():
        if sha(ROOT/'scripts'/name) != digest:
            raise ValueError('replay source changed: '+name)
    if sha(ROOT/'docs/experiments/completion_replay_20261021.md') != plan['specification_sha256']:
        raise ValueError('replay specification changed')
    for rid, meta in plan['sources'].items():
        source = storage/'records/context_pilot'/rid
        for name, digest in meta['hashes'].items():
            if sha(source/name) != digest:
                raise ValueError('original source changed')
        for cid, entries in meta['call_hashes'].items():
            for name,digest in entries.items():
                if sha(source/cid/name) != digest:
                    raise ValueError('recorded model call changed')
        if sha(source/'boundaries/manifests'/(meta['prefix_boundary']+'.json')) != meta['boundary_sha256']:
            raise ValueError('original boundary changed')
        verify_boundary(source/'boundaries', meta['prefix_boundary'])


def replay_case(storage, plan, case, number, answer, output):
    rid, arm = case['source'], case['arm']
    source = storage/'records/context_pilot'/rid
    events, spans, calls, message = completion_structure(source)
    provenance, config = read(source/'provenance.json'), read(source/'plan.json')
    world = storage/'.runtime/appworld/r18_probe_01'
    python = storage/'.runtime/appworld/venv/bin/python'
    run_id = plan['run_prefix']+f'_{number:02d}'
    task_id = provenance['task_id']
    dbs = world/'experiments/outputs'/run_id/'tasks'/task_id/'dbs'
    if (world/'experiments/outputs'/run_id).exists():
        raise FileExistsError('never replace an existing replay world')
    output.mkdir()
    tools, schema_hashes, _ = load_public_tools(world/'data')
    if (schema_hashes != provenance['public_schema_hashes']
            or sha(world/'data/tasks'/task_id/'specs.json') != provenance['spec_sha256']):
        raise ValueError('public schema or original task specification changed')
    for name in ('appworld_bridge.py','context_preservation.py','inspect_appworld_api_schemas.py'):
        if sha(ROOT/'scripts'/name) != provenance['sources'][name]:
            raise ValueError('dispatch implementation differs from original')
    NativeCatalog, dispatch_native_calls = original_dispatcher(storage,rid,provenance)
    catalog = NativeCatalog(tools)
    bridge = Bridge(python,world,output)
    result = dict(source_run=rid, arm=arm, run_id=run_id,status='started',
        replayed_responses=0, observation_matches=0, api_requests=0,model_calls=0)
    started=time.monotonic()
    try:
        initial=bridge.request({'op':'init','task_id':task_id,'experiment':run_id,'seed':config['seed']})
        if not initial['ok'] or initial['result'] != read(source/'public_task.json'):
            raise ValueError('public task initialization differs')
        if initial['result']['ground_truth_loaded']:
            raise ValueError('unexpected task ground truth')
        private=[]
        for cid in calls[:-1]:
            if time.monotonic()-started>plan['max_wall_seconds']:
                raise TimeoutError('fixed replay time limit')
            request,response=read(source/cid/'request.json'),read(source/cid/'response.json')
            if response['status']!='ok' or request['tools']!=catalog.tools():
                raise ValueError('recorded response or tool visibility differs')
            def no_archive(*_):
                raise ValueError('archive outside the predeclared API replay')
            rows=dispatch_native_calls(response['message'],catalog,bridge,no_archive,
                remaining_api_calls=plan['max_api_requests']-result['api_requests'])
            private.append({'call':cid,'rows':rows});write_json(output/'replay_private.json',private)
            result['api_requests']+=sum(r['api_request_sent'] for r in rows)
            assert_rows_match(rows,[e for e in events if e['call']==cid],spans)
            result['replayed_responses']+=1;result['observation_matches']+=len(rows)
        boundary=read(source/'boundaries/manifests'/(calls[-2]+'.json'))
        expected={k:v['sha256'] for k,v in boundary['files'].items() if k.startswith('dbs/')}
        before=database_hashes(dbs)
        result['prefix_database_matches_original']=before==expected
        result['prefix_database_hashes']=before
        if not result['prefix_database_matches_original']:
            raise ValueError('pre-completion database bytes differ')
        if (read(source/calls[-1]/'request.json')['tools']!=catalog.tools()
                or time.monotonic()-started>plan['max_wall_seconds']
                or result['api_requests']>=plan['max_api_requests']):
            raise ValueError('completion tools or remaining replay budget differ')
        altered=change_completion(message,arm,answer)
        rows=dispatch_native_calls(altered,catalog,bridge,no_archive,
            remaining_api_calls=plan['max_api_requests']-result['api_requests'])
        write_json(output/'completion_private.json',rows)
        result['api_requests']+=sum(r['api_request_sent'] for r in rows)
        if len(rows)!=1 or not rows[0]['api_request_sent'] or not rows[0]['observation'].get('declared_complete'):
            raise ValueError('completion not recorded as a successful declaration')
        result['status']='execution_frozen'
    except Exception as error:
        result.update(status='replay_failed',error_type=type(error).__name__)
        write_json(output/'error_private.json',{'type':type(error).__name__,'message':str(error)})
    finally:
        try: bridge.close()
        except Exception as error: result.update(status='replay_failed',close_error_type=type(error).__name__)
        result['execution_wall_seconds']=time.monotonic()-started
        write_json(output/'result.json',result)
    if result['status']=='execution_frozen':
        write_json(output/'summary.json',dict(run_id=run_id,task_id=task_id,finished_at=now(),evaluation='not_run'))
        evaluation_started=time.monotonic()
        try:
            with (output/'evaluation.log').open('w') as log:
                completed=subprocess.run([str(python),str(ROOT/'scripts/evaluate_context_trial.py'),
                    '--appworld-root',str(world),'--trial',str(output)],stdout=log,stderr=subprocess.STDOUT,timeout=180)
            if completed.returncode:
                result['status']='evaluation_failed'
            else:
                evaluation=read(output/'evaluation.json')
                result.update(status='evaluated',official_success=evaluation['official_success'],
                    pass_count=evaluation['pass_count'],fail_count=evaluation['fail_count'],
                    evaluation_sha256=sha(output/'evaluation.json'))
        except Exception as error:
            result.update(status='evaluation_failed',evaluation_error_type=type(error).__name__)
        result['evaluation_wall_seconds']=time.monotonic()-evaluation_started
    write_json(output/'result.json',result)
    return result


def run(storage, plan_path, report_path):
    plan=read(plan_path);verify_plan(storage,plan)
    if read(storage/'records/context_pilot/P25_batch_v01/status.json')['status']!='complete':
        raise ValueError('wait for all P25 tasks before any replay')
    output=storage/'records/completion_replay'/plan['run_prefix']
    if output.exists() or report_path.exists():
        raise FileExistsError('preserve previous replay results')
    output.mkdir(parents=True)
    _,_,_,message=completion_structure(storage/'records/context_pilot'/SOURCES[0])
    answer=json.loads(message['tool_calls'][0]['function']['arguments'])['answer']
    report=dict(started_at=now(),plan_sha256=sha(plan_path),model_calls=0,results=[],
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        scope='Four fixed post-hoc completion interventions. No agent rerun or new-method success claim.')
    for i,case in enumerate(plan['cases'],1):
        result=replay_case(storage,plan,case,i,answer,output/f'case_{i:02d}')
        report['results'].append(result)
        write_json(report_path,report)
        print(json.dumps({k:v for k,v in result.items() if k!='prefix_database_hashes'}),flush=True)
    verify_plan(storage,plan)
    report['original_sources_unchanged']=True
    report['finished_at']=now()
    write_json(report_path,report);write_json(output/'report.json',report)
    return all(r['status']=='evaluated' for r in report['results'])


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--prepare',action='store_true')
    p.add_argument('--report',type=Path)
    a=p.parse_args()
    if a.prepare: prepare(a.storage_root,a.plan);return 0
    if not a.report: p.error('--report required for execution')
    return 0 if run(a.storage_root,a.plan,a.report) else 1


if __name__=='__main__':
    raise SystemExit(main())
