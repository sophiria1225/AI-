"""P110: fixed-history input counts, not a changed agent trajectory."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from inspect_recorded_action_agreement import verify_ci
from model_provenance import verified_model
from receipt_reasoning_history import POLICIES, digest, execution_evidence, project, require

PLAN='configs/P110_receipt_history_inputs_v01.json'


def fixed_parameters():
    return dict(phase='P110', source_audit='reports/P99_comparison.json',
        policies=list(POLICIES), known_tasks=4, source_cells=8, original_model_attempts=148,
        max_renderings=444, max_wall_seconds=600, max_renderer_seconds=90,
        max_renderer_rss_bytes=2147483648, max_file_bytes=16777216,
        max_total_private_input_bytes=536870912, max_events_per_cell=4000,
        max_saved_calls_per_cell=80, runtime_commit='620d2225cc436ab0b001e3200e590e3b286ef9ab',
        runtime_record='records/context_pilot/P99_pipeline_v01/server_runtime.json',
        private_output='records/context_pilot/P110_receipt_history_inputs_v01',
        stop_marker='.runtime/P110.stop', automatic_retries=0,
        model_generations=0, environment_API_requests=0, saved_generated_program_executions=0,
        evaluations=0, task_databases_read=0, reserved_scenarios_read=0,
        novel_method_claim=False, task_quality_measured=False, observed_new_LLM_usage=False,
        existing_P99_outcomes_known=True, actual_trajectory_preserved_for_diagnosis=True)


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write_new(p,value):
    with p.open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


def private_read(storage, plan, relative):
    path=storage/relative;path.resolve().relative_to(storage.resolve())
    require(path.is_file() and not path.is_symlink() and path.stat().st_size<=plan['max_file_bytes'],
            'bounded_regular_private_file_required')
    require(sha(path)==plan['private_source_sha256'][relative],'fixed_private_input_changed')
    return read(path)


def prepared_views(usage, events, spans, requests):
    require(len(usage)<=80 and len(events)<=4000,'bounded_saved_cell_required')
    ids=[u['id'] for u in usage];ranks={cid:i for i,cid in enumerate(ids)}
    require(len(ids)==len(set(ids)) and set(requests)==set(ids),'all_saved_requests_required')
    order=[ranks.get(e['call'],-1) for e in events]
    require(-1 not in order and order==sorted(order),'chronological_records_required')
    require(len({e['span_id'] for e in events})==len(events) and
            {e['span_id'] for e in events}==set(spans),'complete_saved_span_mapping')
    evidence=[];previous_masks={p:set() for p in POLICIES};rows=[]
    for u in usage:
        cid=u['id'];request=requests[cid]
        for policy in POLICIES:
            messages,meta=project(request['messages'],evidence,policy)
            removed=set(meta['removed_reasoning_turns'])
            meta['redisplayed_reasoning_turns']=sorted(previous_masks[policy]-removed)
            previous_masks[policy]=removed
            payload=deepcopy(request);payload['messages']=messages
            other=deepcopy(payload);other['messages']=request['messages']
            require(other==request,'non_history_request_parameters_changed')
            rows.append(dict(call_id=cid,policy=policy,original_usage_status=u['status'],
                original_measured_input_tokens=u.get('input_tokens') if u['status']=='ok' else None,
                original_measured_output_tokens=u.get('output_tokens') if u['status']=='ok' else None,
                original_measured_cached_input_tokens=u.get('cached_input_tokens') if u['status']=='ok' else None,
                projection=meta,payload=payload))
        selected=[e for e in events if e['call']==cid]
        if u['status']!='ok':
            require(cid==ids[-1] and not selected,'unknown_generation_cannot_have_later_execution')
        evidence.append(execution_evidence(selected,{e['span_id']:spans[e['span_id']] for e in selected},
            pending_reads=0))  # P99's ordinary eager API interface has no read-view reservations.
    return rows,evidence


def guard(storage,plan,deadline):
    if (storage/plan['stop_marker']).exists():raise InterruptedError('explicit_P110_stop')
    if time.monotonic()>=deadline:raise TimeoutError('P110_deadline')


def render(storage, plan, build, runtime, model, directory, cases, deadline, operation):
    manifest=directory/'manifest_private.json'
    write_new(manifest,dict(recorded_server_command=runtime['command'],model_path=str(model),
        output_dir=str(directory),cases=cases))
    process=None;started=time.monotonic()
    try:
        with (directory/'renderer_private.log').open('x') as log:
            process=subprocess.Popen([str(storage/build['renderer_relative']),str(manifest)],
                stdout=log,stderr=log,start_new_session=True)
        operation.update(pid=process.pid,status='running',sampled_peak_rss_bytes=0)
        while process.poll() is None:
            guard(storage,plan,min(deadline,started+plan['max_renderer_seconds']))
            sample=subprocess.run(['ps','-o','rss=','-p',str(process.pid)],capture_output=True,text=True,timeout=10)
            if sample.returncode==0 and sample.stdout.strip():
                operation['sampled_peak_rss_bytes']=max(operation['sampled_peak_rss_bytes'],int(sample.stdout.strip())*1024)
                require(operation['sampled_peak_rss_bytes']<=plan['max_renderer_rss_bytes'],'renderer_memory_bound')
            time.sleep(.05)
        require(process.returncode==0,'renderer_failed')
        require(read(directory/'renderer_complete.json')==dict(renderings=len(cases),decode_calls=0),
                'complete_planned_renderings_required')
        metadata=read(directory/'renderer_metadata_private.json')
        require(metadata['vocabulary_only'] is True and metadata['inference_contexts_created']==0
            and metadata['decode_calls']==0 and hashlib.sha256(metadata['default_template'].encode()).hexdigest()
            ==plan['effective_template_sha256'],'fixed_vocabulary_only_rendering_required')
        operation.update(status='complete',renderings=len(cases),decode_calls=0,
            metadata_sha256=sha(directory/'renderer_metadata_private.json'))
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=15)
        operation.update(owned_process_absent=process is None or process.poll() is not None,
            wall_seconds=time.monotonic()-started,exit_code=process.returncode if process else None)


def collect_renderings(directory,views):
    rows=[];previous={};full={}
    for view in views:
        name=view['case_id'];path=directory/(name+'_rendered_private.json')
        require(path.stat().st_size<=16777216,'bounded_rendered_record')
        value=read(path);tokens=value['tokens']
        require(value['id']==name and value['input_tokens']==len(tokens) and value['media_files']==0,
                'rendered_input_shape')
        old=previous.get(view['policy']);common=0
        if old is not None:
            for a,b in zip(old,tokens):
                if a!=b:break
                common+=1
        previous[view['policy']]=tokens
        if view['policy']=='full':
            full[view['call_id']]=value
            require(view['original_measured_input_tokens'] is None or
                    value['input_tokens']==view['original_measured_input_tokens'],'original_measured_input_count_differs')
        original=full[view['call_id']]
        require(value['session_controls']==original['session_controls'] and
                value['parsed_non_message_parameters']==original['parsed_non_message_parameters'],
                'only_history_may_change_decoder_controls')
        rows.append(dict(**view,status='counted',input_tokens=value['input_tokens'],
            delta_from_full=value['input_tokens']-original['input_tokens'],
            prompt_sha256=hashlib.sha256(value['prompt'].encode()).hexdigest(),
            token_sequence_sha256=digest(tokens),rendered_private_sha256=sha(path),
            adjacent_input_common_prefix_tokens=common if old is not None else None,
            common_prefix_is_not_measured_cache_usage=True,
            original_unknown_usage_not_imputed=view['original_usage_status']!='ok'))
    return rows


def inspect(storage,root):
    plan=read(root/PLAN)
    for key,value in fixed_parameters().items():
        require(type(plan.get(key)) is type(value) and plan[key]==value,'fixed_plan_changed:'+key)
    for rel,expected in plan['source_sha256'].items():require(sha(root/rel)==expected,'fixed_source_changed:'+rel)
    head,ci=verify_ci(root)
    require(sum((storage/rel).stat().st_size for rel in plan['private_source_sha256'])
            <=plan['max_total_private_input_bytes'],'total_private_input_bound')
    audit=read(root/plan['source_audit'])
    require(not audit['audit_errors'] and audit['owned_processes_absent'] and audit['batch_status']=='complete'
        and [r['run_id'] for r in audit['rows']]==plan['run_ids'] and len(audit['rows'])==8
        and len({r['task_id'] for r in audit['rows']})==4
        and sum(r['model_calls'] for r in audit['rows'])==148,'all_original_closed_cells_required')
    runtime=private_read(storage,plan,plan['runtime_record'])
    # Model selection lives in the original worker plan, not in task records.
    base=read(root/'configs/P29_stateful_code_v01.json')
    selection,_,model=verified_model(base['model_selection'],root=storage)
    require(runtime['runtime']['commit']==plan['runtime_commit'] and runtime['model_revision']==selection['revision']
        and Path(runtime['command'][runtime['command'].index('--model')+1])==model,'fixed_source_model_runtime_required')
    build=read(root/'reports/P110_renderer_build.json')
    require(build['exit_code']==0 and sha(storage/build['renderer_relative'])==build['renderer_sha256']
        and sha(root/'scripts/render_receipt_history.cpp')==build['source_cpp_sha256'],'fixed_renderer_binary_required')
    for rel,h in build['library_sha256'].items():require(sha(storage/rel)==h,'renderer_library_changed')
    for rel,h in build['header_sha256'].items():require(sha(storage/build['source_tree_relative']/rel)==h,'renderer_header_changed')
    target=root/'reports/P110_receipt_history_inputs.json';directory=storage/plan['private_output']
    require(not target.exists() and not directory.exists(),'preserve_every_P110_attempt')
    directory.mkdir(parents=True)
    result=dict(**fixed_parameters(),source_commit=head,ci=ci,plan_sha256=sha(root/PLAN),
        started_at=datetime.now(timezone.utc).isoformat(),status='incomplete',rows=[],cells=[],operations=[],errors=[],
        measured_whole_task_savings=None,source_audit_sha256=sha(root/plan['source_audit']),
        limitation='Hypothetical inputs on already realized histories. Subsequent model outputs would '
            'be endogenous under a new policy. Token deltas are not achievable whole-task savings; '
            'input common prefixes are not measured cache usage. Original missing usage remains missing.')
    result['rows']=[dict(run_id=r['run_id'],call_id=c['call_id'],policy=p,status='not_counted')
        for r in audit['rows'] for c in r['request_checks'] for p in POLICIES]
    positions={(r['run_id'],r['call_id'],r['policy']):i for i,r in enumerate(result['rows'])}
    require(len(positions)==len(result['rows'])==444,'all_unique_planned_slots_required')
    started=time.monotonic();deadline=started+plan['max_wall_seconds']
    try:
        for original in audit['rows']:
            guard(storage,plan,deadline);rid=original['run_id'];prefix='records/context_pilot/'+rid+'/'
            values={n:private_read(storage,plan,prefix+n+'.json') for n in ('usage','events','spans')}
            require(sha(storage/(prefix+'usage.json'))==original['usage_sha256'],'original_usage_changed')
            requests={c['call_id']:private_read(storage,plan,prefix+c['call_id']+'/request.json') for c in original['request_checks']}
            require(len(values['usage'])==original['model_calls'],'original_call_count_changed')
            views,evidence=prepared_views(values['usage'],values['events'],values['spans'],requests)
            folder=directory/rid;folder.mkdir();cases=[];metadata=[]
            for view in views:
                payload=view.pop('payload');key=view['call_id']+'_'+view['policy'];path=folder/(key+'_request_private.json')
                write_new(path,payload);cases.append(dict(id=key,request_path=str(path)))
                metadata.append(dict(**view,case_id=key,run_id=rid,task_id=original['task_id'],
                    original_tool_choice=original['tool_choice_policy'],request_private_sha256=sha(path)))
            operation=dict(run_id=rid,status='starting',renderings=0);result['operations'].append(operation)
            render(storage,plan,build,runtime,model,folder,cases,deadline,operation)
            rows=collect_renderings(folder,metadata)
            for row in rows:
                result['rows'][positions[(rid,row['call_id'],row['policy'])]]=row
            result['cells'].append(dict(run_id=rid,status='counted',original_success=original['success'],
                original_model_calls=original['model_calls'],original_known_total_tokens=original['known_total_tokens'],
                original_unknown_usage_calls=original['unknown_usage_calls'],prior_turn_evidence=evidence,
                hypothetical_input_tokens={p:sum(r['input_tokens'] for r in rows if r['policy']==p) for p in POLICIES},
                input_token_deltas_not_whole_task_savings=True))
        require(all(r['status']=='counted' for r in result['rows']),'all_fixed_renderings_required')
        for rel,h in plan['private_source_sha256'].items():require(sha(storage/rel)==h,'private_inputs_changed_during_counting')
        result['status']='complete'
    except BaseException as error:
        result['errors'].append(dict(type=type(error).__name__,
            reason=str(error) if type(error) in (ValueError,TimeoutError,InterruptedError) else 'inspect_private_diagnostic_log'))
        raise
    finally:
        completed={c['run_id'] for c in result['cells']}
        for rid in plan['run_ids']:
            if rid not in completed:result['cells'].append(dict(run_id=rid,status='not_completed'))
        result.update(ended_at=datetime.now(timezone.utc).isoformat(),wall_seconds=time.monotonic()-started,
            completed_renderings=sum(r['status']=='counted' for r in result['rows']))
        write_new(target,result);write_new(directory/'end.json',dict(status=result['status'],report_sha256=sha(target)))
    print(json.dumps({k:result[k] for k in ('status','completed_renderings','wall_seconds','errors')}))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--repo-root',type=Path,default=Path(__file__).resolve().parents[1])
    a=p.parse_args();inspect(a.storage_root.resolve(),a.repo_root.resolve())
