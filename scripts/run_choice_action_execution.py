"""P102: execute all available audited P101 outputs on matched fresh worlds.

All 36 source slots remain visible. No generation, text rescue, retry, evaluator,
or claim of reconstructing the original complete process state.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

from choice_action_execution import validate_plan, source_slots, execution_comparisons
from choice_context_replay import schedule
from inspect_appworld_api_schemas import load_public_tools
from inspect_input_exposure import check_resume
from matched_live_prefix import assemble_programs, public_next_message
from persistent_api_python import PersistentApiPython
from preflight_public_api_live import RecordedBridge, confirm_initial_world
from public_api_result_transport import PublicResultTransport, TypedBridgeProcess
from public_name_catalog import PublicNameCatalog
from run_saved_action_execution import sha, write, read_private, reconstruct, suffix
from run_whole_task_tool_choice_pipeline import checked_ci

PLAN='configs/P102_choice_action_execution_v01.json'
DESIGN='configs/P102_choice_action_execution_preparation_v01.json'
IMPLEMENTATION='configs/P102_choice_action_execution_runtime_v01.json'
PREFIX='records/context_pilot/BOC_P80_04_NOT_EXPOSED'
PREDECESSOR_HEAD='879f04696a8129252b47678f92ee4e1031a09ea7'


def read(path):
    if path.stat().st_size > 16777216:
        raise ValueError('bounded_record_required')
    return json.loads(path.read_text())


def previous_closed(storage, root, plan, source):
    folder=storage/plan['required_closed_pipeline']
    pipeline=read(folder/'status.json');server=read(folder/'server_final.json')
    if (pipeline['status'] not in ('complete','stopped') or not pipeline.get('server_stopped')
            or pipeline['git_commit']!=PREDECESSOR_HEAD or server['status']!='stopped'
            or pipeline['server_supervisor_pid']!=server['supervisor_pid']
            or source['pipeline_status_sha256']!=sha(folder/'status.json')):
        raise ValueError('closed_owned_P101_pipeline_and_audit_required')
    record=Path(server['record_directory'])
    if not record.is_absolute():record=storage/record
    if (read(record/'summary.json')!=server
            or source['server_summary_sha256']!=sha(record/'summary.json')):
        raise ValueError('P101_server_record_disagrees')
    for pid in (server['pid'],server['supervisor_pid']):
        result=subprocess.run(['ps','-p',str(pid),'-o','pid='],capture_output=True,text=True,timeout=10)
        if result.returncode!=1 or result.stdout.strip():
            raise ValueError('P101_owned_process_still_exists')
    pre=read(root/'reports/P101_initial_checks.json')
    if (pre['status']!='complete' or pre['git_commit']!=PREDECESSOR_HEAD
            or source['preflight_sha256']!=sha(root/'reports/P101_initial_checks.json')
            or source['source_sha256']!=pre['source_sha256']):
        raise ValueError('P101_original_preflight_required')
    for rel,h in pre['source_sha256'].items():
        if sha(root/rel)!=h:raise ValueError('P101_original_source_changed:'+rel)
    return dict(executed_head=PREDECESSOR_HEAD,pipeline_sha256=sha(folder/'status.json'),
        server_final_sha256=sha(folder/'server_final.json'),owned_processes_absent=True)


def prepare(storage, root, plan):
    validate_plan(plan)
    if plan.get('execution_ready') is not True or plan.get('implementation_ready') is not True:
        raise ValueError('final_P102_execution_plan_required')
    for rel,key in ((DESIGN,'design_plan_sha256'),(IMPLEMENTATION,'runtime_preparation_sha256')):
        original=read(root/rel)
        if sha(root/rel)!=plan.get(key) or any(plan['source_sha256'].get(n)!=h for n,h in original['source_sha256'].items()):
            raise ValueError('predeclared_design_and_runtime_bindings_required')
    for name,expected in plan['source_sha256'].items():
        if sha(root/name)!=expected:raise ValueError('fixed_source_changed:'+name)
    source=read(root/plan['required_closed_audit']);slots=source_slots(source)
    closure=previous_closed(storage,root,plan,source)
    if (plan.get('P101_final_plan_sha256')!=sha(root/'configs/P101_choice_context_v01.json')
            or plan.get('P101_audit_sha256')!=sha(root/plan['required_closed_audit'])):
        raise ValueError('final_P101_evidence_not_bound')
    p101=read(root/'configs/P101_choice_context_v01.json')
    if source['source_request_sha256']!={c['id']:c['source_request_sha256'] for c in p101['cases']}:
        raise ValueError('original_six_request_bindings_changed')
    old=read(root/'configs/P94_saved_action_execution_v01.json')
    prefix_bindings={n:h for n,h in old['private_file_sha256'].items() if n.startswith(PREFIX+'/')}
    expected_private=dict(prefix_bindings)
    for slot in slots:
        if slot['should_execute']:
            expected_private[plan['source_batch']+'/'+slot['id']+'/response.json']=slot['source_response_sha256']
    if plan.get('private_file_sha256')!=expected_private:
        raise ValueError('all_known_sources_and_exact_original_prefix_required')
    package=storage/'.runtime/appworld/venv/lib/python3.12/site-packages/appworld'
    for name,expected in old['runtime_source_sha256'].items():
        if sha(package/name)!=expected:raise ValueError('original_AppWorld_runtime_changed:'+name)
    world_root=storage/'.runtime/appworld/r18_probe_01'
    tools,schema_sources,_=load_public_tools(world_root/'data')
    if schema_sources!=old['public_schema_sha256']:
        raise ValueError('original_public_schemas_changed')
    schemas={t['function']['name']:t['function'] for t in tools}
    events=[e for e in read_private(storage,plan,PREFIX+'/events.json') if e['call']<'call_014']
    original_spans=read_private(storage,plan,PREFIX+'/spans.json')
    spans={e['span_id']:original_spans[e['span_id']] for e in events}
    program_files=[]
    for n in range(1,13):
        base=PREFIX+f'/programs/call_{n:03d}_01/'
        program_files.append(dict(input=read_private(storage,plan,base+'input_private.json'),
            result=read_private(storage,plan,base+'result_private.json'),
            wire=read_private(storage,plan,base+'wire_private.jsonl',lines=True)))
    programs=assemble_programs(events,spans,program_files,schemas)
    messages=[]
    for slot in slots:
        if slot['should_execute']:
            response=read_private(storage,plan,plan['source_batch']+'/'+slot['id']+'/response.json')
            messages.append(public_next_message(response,slot['source_public_output_sha256']))
        else:messages.append(None)
    public=read_private(storage,plan,PREFIX+'/public_task.json')
    return tools,programs,spans,public,messages,slots,closure


def run(storage,root):
    plan=read(root/PLAN);validate_plan(plan)
    if (plan.get('private_output')!='records/context_pilot/P102_choice_action_execution_v01'
            or plan.get('experiment_prefix')!='P102_ACTION_V01'
            or plan.get('stop_marker')!='.runtime/P102.stop'):
        raise ValueError('fixed_P102_output_scope')
    stopped=lambda:(storage/plan['stop_marker']).exists()
    if stopped():raise InterruptedError('explicit_stop_before_P102')
    resume=check_resume(storage)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True,timeout=10).strip()
    if subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True,timeout=10).strip():
        raise ValueError('clean_fixed_execution_tree_required')
    ci=checked_ci(root,head)
    output=storage/plan['private_output'];target=root/'reports/P102_choice_action_execution.json'
    if output.exists() or target.exists():raise FileExistsError('preserve_every_P102_attempt')
    output.mkdir(parents=True,exist_ok=False);started=time.monotonic();deadline=started+1800
    report=dict(phase='P102',status='running',started_at=datetime.now(timezone.utc).isoformat(),
        source_commit=head,ci=ci,research_resume=resume,plan_sha256=sha(root/PLAN),
        conditions=[dict(**item,status='not_attempted',prefix_programs=[],prefix_api_requests=0,
            public_prefix_matched=False) for item in schedule()],model_generations=0,evaluator_calls=0,
        reserved_scenarios_read=0,original_full_state_restored=False,task_quality_measured=False,
        new_method_claim=False,automatic_retries=0)
    try:
        tools,programs,spans,public,messages,slots,closure=prepare(storage,root,plan)
        report['P101_closure']=closure
        for condition,slot in zip(report['conditions'],slots,strict=True):condition.update(slot)
        report['source_audit_sha256']=sha(root/plan['required_closed_audit'])
        report['available_saved_outputs']=sum(s['should_execute'] for s in slots)
        world_root=storage/'.runtime/appworld/r18_probe_01'
        for condition in report['conditions']:
            if (world_root/'experiments/outputs'/(plan['experiment_prefix']+'_'+condition['id'])).exists():
                raise FileExistsError('preserve_existing_P102_world')
        for condition,message in zip(report['conditions'],messages,strict=True):
            if stopped() or time.monotonic()>=deadline:raise InterruptedError('P102_stop_before_slot')
            if message is None:
                condition['status']='source_unavailable';write(output/'status.json',report);continue
            cell_started=time.monotonic();cell_deadline=min(deadline,cell_started+180)
            folder=output/condition['id'];folder.mkdir()
            raw=recorded=transport=session=None;condition['status']='running'
            try:
                raw=TypedBridgeProcess(storage/'.runtime/appworld/venv/bin/python',world_root,folder,timeout_seconds=30)
                condition['owned_bridge_pid']=raw.process.pid
                recorded=RecordedBridge(raw,folder,cell_deadline,stop=stopped)
                transport=PublicResultTransport(recorded)
                confirm_initial_world(transport.request(dict(op='init',task_id=plan['task_id'],
                    experiment=plan['experiment_prefix']+'_'+condition['id'],seed=42)),public)
                session=PersistentApiPython(storage,folder/'python_session');catalog=PublicNameCatalog(tools)
                reconstruct(programs,session,catalog,transport,recorded,folder,storage,plan,cell_deadline,stopped,condition)
                suffix(message,spans,session,catalog,transport,recorded,folder,storage,plan,cell_deadline,stopped,condition)
                condition['status']='complete'
            except BaseException as error:
                condition.update(status='stopped',error_type=type(error).__name__)
                write(folder/'error_private.json',dict(type=type(error).__name__,message=str(error)))
                raise
            finally:
                condition['active_wall_seconds']=time.monotonic()-cell_started
                cleanup_started=time.monotonic();errors=[]
                if session is not None:
                    try:
                        clean=session.close()
                        condition['python_cleanup']={k:clean.get(k) for k in ('status','container_removed','cleanup_wall_seconds','oom_killed')}
                        condition['container_controls']=session.controls
                        condition['saved_program_executions']=len(session.programs)
                    except BaseException as error:errors.append('python:'+type(error).__name__)
                if raw is not None:
                    try:
                        condition['bridge_cleanup']=raw.close()
                        try:os.kill(raw.process.pid,0);condition['owned_bridge_absent']=False
                        except ProcessLookupError:condition['owned_bridge_absent']=True
                    except BaseException as error:errors.append('bridge:'+type(error).__name__)
                receipts=transport.receipts if transport else []
                condition.update(cleanup_errors=errors,cleanup_wall_seconds=time.monotonic()-cleanup_started,
                    full_wall_seconds=time.monotonic()-cell_started,transport_attempts=len(receipts),
                    typed_status_counts=dict(Counter(x['status'] for x in receipts)),
                    bridge_attempts=len(recorded.attempts) if recorded else 0,
                    typed_requests_started=sum(a['raw_request_started'] and a['command']['op']=='call_typed'
                        for a in recorded.attempts) if recorded else 0)
                write(folder/'progress.json',condition);write(output/'status.json',report)
            total=condition['prefix_api_requests']+condition['suffix_api_requests']
            if (condition['cleanup_errors'] or not condition['python_cleanup']['container_removed']
                    or not condition['bridge_cleanup']['graceful'] or not condition['owned_bridge_absent']
                    or not all(condition['container_controls'].values()) or len(condition['container_controls'])!=14
                    or not total==condition['transport_attempts']==condition['typed_requests_started'] or total>80
                    or sum(c.get('typed_requests_started',0) for c in report['conditions'])>2880):
                condition['status']='cleanup_or_accounting_failed';raise ValueError('P102_cleanup_or_accounting')
            print(json.dumps(dict(processed_slot=condition['id'],planned_slots=36)),flush=True)
        report['status']='complete'
    except BaseException as error:
        report.update(status='stopped',error_type=type(error).__name__)
        write(output/'error_private.json',dict(type=type(error).__name__,message=str(error)))
    finally:
        report.update(wall_seconds=time.monotonic()-started,
            environment_api_requests=sum(c.get('typed_requests_started',0) for c in report['conditions']),
            saved_program_executions=sum(c.get('saved_program_executions',0) for c in report['conditions']),
            completed_conditions=sum(c['status']=='complete' for c in report['conditions']),
            unavailable_source_slots=sum(c['status']=='source_unavailable' for c in report['conditions']),
            unattempted_execution_slots=sum(c['status']=='not_attempted' for c in report['conditions']),
            finished_at=datetime.now(timezone.utc).isoformat())
        report['execution_comparisons']=execution_comparisons(report['conditions'])
        write(output/'status.json',report);write(target,report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--storage-root',type=Path,required=True)
    args=parser.parse_args();result=run(args.storage_root.resolve(),Path(__file__).resolve().parents[1])
    print(json.dumps({k:result[k] for k in ('status','completed_conditions','unavailable_source_slots',
        'environment_api_requests','saved_program_executions','wall_seconds')}))
    raise SystemExit(0 if result['status']=='complete' else 1)
