"""P53: sixteen frozen input counts, zero model generations or task execution."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.request

from code_agent_interface import CODE_TOOLS
from contract_retention_controls import detail_only_control
from documentation_print_origin import build_origin_view
from inference_cache_control import require_idle
from later_handoff_sources import prepare_later_sources
from local_llama import count_input
from local_llama_stream import save
from model_provenance import check_live_model

ROOT=Path(__file__).resolve().parents[1]
PLAN='configs/P53_contract_retention_counts_v01.json'
MODES=('full_keep','all_documented_details','used_since_document','all_parameters_observed')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def get(config,path):
    with urllib.request.urlopen(config['base_url']+path,timeout=5) as response:return json.load(response)

def prepare(storage,plan):
    for path,digest in plan['source_reports_sha256'].items():
        if sha(ROOT/path)!=digest:raise ValueError('source report changed')
    prior=read(ROOT/'reports/P52_contract_use_retention.json')
    for path,digest in prior['source_sha256'].items():
        if sha(ROOT/path)!=digest:raise ValueError('P52 implementation changed')
    _,original,_,_,items=prepare_later_sources(storage,ROOT)
    if [i['source_run'] for i in items]!=plan['source_runs']:raise ValueError('source order changed')
    outputs=[]
    for item,old in zip(items,prior['rows'],strict=True):
        if item['boundary_manifest_sha256']!=old['boundary_manifest_sha256']:
            raise ValueError('boundary changed')
        full,_=build_origin_view(item);detail,control=detail_only_control(item)
        messages={}
        for name,view in [('full_keep',full['full_keep']),('all_documented_details',detail)]:
            message,fmt=view.for_model(original['observation_page_characters'])
            if fmt!={'text_fallback_turns':0,'paged_spans':0}:raise ValueError('format changed')
            messages[name]=message
        for name in MODES[2:]:
            path=storage/'records/context_pilot/P52_contract_use_retention_v01'/(
                item['source_run']+'_'+name+'_private.json')
            if sha(path)!=old['views'][name]['private_input_sha256']:raise ValueError('P52 input changed')
            messages[name]=read(path)
        outputs.append({'source_run':item['source_run'],'boundary_manifest_sha256':item['boundary_manifest_sha256'],
            'control':control,'messages':messages})
    return original,outputs

def run(storage,expected_commit):
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if actual!=expected_commit or subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
        raise ValueError('clean fixed commit required')
    plan=read(ROOT/PLAN)
    if (plan['phase']!='P53' or plan['modes']!=list(MODES) or plan['max_count_requests']!=16
            or plan['max_wall_seconds']!=180 or plan['gate_minimum_tokens']!=1000
            or plan['gate_minimum_tasks']!=2 or any(plan[k]!=0 for k in
                ('model_generations','environment_api_requests','program_reexecutions','evaluator_calls','reserved_scenarios_read'))):
        raise ValueError('outside fixed P53 scope')
    out=storage/'records/context_pilot'/plan['batch_id'];out.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();save(out/'plan.json',plan)
    state={'phase':'P53','status':'initializing','git_commit':actual,
        'started_at':datetime.now(timezone.utc).isoformat(),'source_sha256':{p:sha(ROOT/p) for p in plan['implementation_sources']+[PLAN]},
        'count_requests_attempted':0,'count_requests_completed':0,'rows':[],
        'planned_inputs':[[run,name] for run in plan['source_runs'] for name in MODES],
        'attempted_inputs':[],
        **{k:0 for k in ('model_generations','environment_api_requests','program_reexecutions','evaluator_calls','reserved_scenarios_read')},
        'quality_preservation_claim':False,'end_to_end_savings_claim':False,'server_shutdown_record_pending':True}
    try:
        original,inputs=prepare(storage,plan)
        cfg={**original['model'],'temperature':original['agent_temperature'],
             'seed':original['seed']+8,'num_predict':original['max_output_tokens'],'cache_prompt':False}
        runtime_path=storage/'.runtime/model_server.json';runtime=read(runtime_path)
        check_live_model(original['model_selection'],runtime,get(cfg,'/props'),root=storage,
                         expected_ctx=65536,expected_cache=('q8_0','q8_0'))
        require_idle(get(cfg,'/slots'))
        state.update(status='running',server_record_directory=runtime['record_directory'],
            server_supervisor_pid=runtime['supervisor_pid'],server_pid=runtime['pid'])
        save(out/'server_runtime.json',runtime)
        expected=read(ROOT/'reports/P44_documentation_origin.json')
        for item,old in zip(inputs,expected['rows'],strict=True):
            row={k:item[k] for k in ('source_run','boundary_manifest_sha256','control')};row['views']={}
            state['rows'].append(row)
            for name in MODES:
                if (storage/'.runtime/STOP_P53_COUNTS').exists():raise InterruptedError('user stop marker')
                remaining=180-(time.monotonic()-started)
                if remaining<=0 or state['count_requests_attempted']>=16:raise TimeoutError('P53 fixed cap')
                live=read(runtime_path)
                if any(live[k]!=runtime[k] for k in ('pid','supervisor_pid','record_directory','status')):
                    raise ValueError('server session changed')
                require_idle(get(cfg,'/slots'))
                path=out/(item['source_run']+'_'+name+'_private.json');save(path,item['messages'][name])
                state['count_requests_attempted']+=1
                state['attempted_inputs'].append([item['source_run'],name]);save(out/'status.json',state)
                counted=count_input(cfg,item['messages'][name],CODE_TOOLS,timeout=min(30,remaining))
                row['views'][name]={**counted,'input_sha256':sha(path)}
                state['count_requests_completed']+=1;save(out/'status.json',state)
            full=row['views']['full_keep']['input_tokens']
            if full!=old['views']['full_keep']['input_tokens']:raise ValueError('P44 full count changed')
            row['tokens_removed']={name:full-row['views'][name]['input_tokens'] for name in MODES[1:]}
        state['allocation_gate']={name:{'tasks_at_least_1000':sum(r['tokens_removed'][name]>=1000 for r in state['rows']),
            'passed':sum(r['tokens_removed'][name]>=1000 for r in state['rows'])>=2} for name in MODES[1:]}
        state['status']='complete'
    except BaseException as error:
        state.update(status='stopped',failure_type=type(error).__name__);raise
    finally:
        state['wall_seconds']=time.monotonic()-started
        state['not_attempted_inputs']=[x for x in state['planned_inputs'] if x not in state['attempted_inputs']]
        save(out/'status.json',state);save(ROOT/'reports/P53_contract_retention_counts.json',state)
    print(json.dumps({'status':state['status'],'count_requests':state['count_requests_completed'],
        'allocation_gate':state['allocation_gate'],'rows':[{k:r[k] for k in ('source_run','tokens_removed')} for r in state['rows']]}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--storage-root',required=True,type=Path)
    parser.add_argument('--expected-commit',required=True)
    args=parser.parse_args();run(args.storage_root.resolve(),args.expected_commit)
