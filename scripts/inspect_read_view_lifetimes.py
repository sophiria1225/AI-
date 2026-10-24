"""P108: once-only factual host replay after the entire P107 batch closes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import subprocess
import time

from inspect_appworld_api_schemas import load_public_tools
from inspect_recorded_action_agreement import verify_ci
from replay_read_view_controls import read, replay_cell, require, sha

PLAN='configs/P108_read_view_lifetimes_v01.json'
RUN_IDS=['BOC_P107_01_EAGER_CACHED','BOC_P107_01_COALESCED_CACHED']


def fixed_parameters():
    return dict(phase='P108',run_ids=RUN_IDS,max_wall_seconds=180,max_files_per_cell=2048,
        max_programs_per_cell=256,max_controls_per_cell=5000,max_bytes_per_cell=268435456,
        source_plan_sha256='7d30d81ea1100de182341043cf5bacab4caa057c552d723360cbd40e1893aff0',
        model_generations=0,environment_API_requests=0,saved_generated_program_executions=0,
        evaluations=0,reserved_scenarios_read=0,automatic_retries=0,
        alternate_policy_replay=False,novel_method_claim=False,
        source_outcomes_inspected_during_preparation=False)


def inventory(folder,plan):
    paths=[folder/name for name in ('summary.json','events.json','spans.json',
        'request_budget_events_private.json','view_control_events_private.json')]
    paths+=list(folder.glob('bridge_*_private.json'))
    for name in ('input_private.json','wire_private.jsonl','view_program_private.json','schema_forwarding_private.json'):
        paths+=list((folder/'programs').glob('*/'+name))
    paths=sorted(set(paths))
    require(len(paths)<=plan['max_files_per_cell'],'private_file_count_limit')
    require(all(p.is_file() and not p.is_symlink() and p.stat().st_size<=16777216 for p in paths),
            'bounded_regular_private_files_required')
    require(sum(p.stat().st_size for p in paths)<=plan['max_bytes_per_cell'],'private_byte_limit')
    programs=list((folder/'programs').glob('*/view_program_private.json'))
    require(len(programs)<=plan['max_programs_per_cell'],'program_count_limit')
    controls=sum(read(p)['control_requests'] for p in programs)
    require(controls<=plan['max_controls_per_cell'],'control_count_limit')
    return {str(p.relative_to(folder)):sha(p) for p in paths}


def write_new(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')


def inspect(storage,root):
    plan=read(root/PLAN)
    for key,value in fixed_parameters().items():
        require(type(plan.get(key)) is type(value) and plan[key]==value,'fixed_plan_differs:'+key)
    for rel,expected in plan['source_sha256'].items():
        require(sha(root/rel)==expected,'frozen_analysis_source_changed:'+rel)
    head,ci=verify_ci(root)
    source_plan=read(root/'configs/P107_whole_task_read_views_v01.json')
    require(sha(root/'configs/P107_whole_task_read_views_v01.json')==plan['source_plan_sha256'],
            'original_plan_changed')
    for rel,expected in source_plan['source_sha256'].items():
        require(sha(root/rel)==expected,'original_host_source_changed:'+rel)
    pipeline=storage/'records/context_pilot/P107_pipeline_v01'
    state=read(pipeline/'status.json');server=read(pipeline/'server_final.json')
    require(state['status'] in ('complete','stopped') and state['server_stopped'] and server['status']=='stopped',
            'entire_original_pipeline_must_be_closed')
    for key in ('pid','supervisor_pid'):
        process=subprocess.run(['ps','-p',str(server[key]),'-o','command='],capture_output=True,text=True,timeout=10)
        require(process.returncode==1 and not process.stdout.strip(),'original_owned_process_still_exists')
    audit=read(root/'reports/P107_comparison.json')
    require(not audit['audit_errors'] and [r['run_id'] for r in audit['rows']]==RUN_IDS
        and audit['plan_sha256']==plan['source_plan_sha256']
        and audit['pipeline_status_sha256']==sha(pipeline/'status.json')
        and audit['server_final_sha256']==sha(pipeline/'server_final.json'), 'closed_original_audit_required')
    tools,schemas,_=load_public_tools(storage/'.runtime/appworld/r18_probe_01/data')
    require(schemas==plan['public_schema_sha256'],'frozen_public_schema_changed')
    output=root/'reports/P108_read_view_lifetimes.json'
    directory=storage/'records/context_pilot/P108_control_replay_v01'
    require(not output.exists() and not directory.exists(),'preserve_every_analysis_attempt')
    directory.mkdir(parents=True)
    started=time.monotonic();stamp=datetime.now(timezone.utc).isoformat()
    manifests={};rows=[];errors=[]
    def deadline(*_):raise TimeoutError('P108_analysis_deadline')
    previous=signal.signal(signal.SIGALRM,deadline);signal.alarm(plan['max_wall_seconds'])
    try:
        for original in audit['rows']:
            rid=original['run_id'];folder=storage/'records/context_pilot'/rid
            if original['record_status'] in ('not_run','incomplete_worker'):
                rows.append(dict(run_id=rid,status=original['record_status']));continue
            try:
                manifests[rid]=inventory(folder,plan)
                require(manifests[rid]['summary.json']==original['summary_sha256'],'original_summary_changed')
                # Bind the complete fixed input inventory before replaying it.
                write_new(directory/(rid+'_input_manifest.json'),manifests[rid])
                result=replay_cell(folder,tools)
                require(inventory(folder,plan)==manifests[rid],'saved_records_changed_during_replay')
                require(result['replayed_API_receipts']==original['api_requests'],'original_API_total_differs')
                rows.append(dict(status='checked',**result))
            except Exception as error:
                errors.append(dict(run_id=rid,type=type(error).__name__,reason=str(error)))
                rows.append(dict(run_id=rid,status='analysis_error'))
                if isinstance(error,TimeoutError):break
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,previous)
        for rid in RUN_IDS:
            if not any(r['run_id']==rid for r in rows):rows.append(dict(run_id=rid,status='not_analyzed'))
        result=dict(phase='P108',started_at=stamp,ended_at=datetime.now(timezone.utc).isoformat(),
            wall_seconds=time.monotonic()-started,source_commit=head,ci=ci,rows=rows,errors=errors,
            status='complete' if not errors and all(r['status']=='checked' for r in rows) else 'incomplete',
            plan_sha256=sha(root/PLAN),source_audit_sha256=sha(root/'reports/P107_comparison.json'),
            private_record_sha256=manifests,model_generations=0,environment_API_requests=0,
            saved_generated_program_executions=0,evaluations=0,reserved_scenarios_read=0,
            automatic_retries=0,alternate_policy_replay=False,novel_method_claim=False,
            original_outcomes_selected=False,source_outcomes_inspected_during_preparation=False,
            limitation='Factual trusted-host replay against already-returned values. '
                'No generated Python or task is rerun. Local field accesses are not in the control wire. '
                'Cancellation counts are not causal API savings, token savings or task quality.')
        write_new(output,result);write_new(directory/'end.json',dict(status=result['status'],report_sha256=sha(output)))
    print(json.dumps({k:result[k] for k in ('status','wall_seconds','errors')}))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--storage-root',type=Path,required=True)
    parser.add_argument('--repo-root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args();inspect(args.storage_root.resolve(),args.repo_root.resolve())
