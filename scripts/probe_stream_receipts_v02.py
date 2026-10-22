"""Three frozen synthetic generations; no task or generated tool execution."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time
import urllib.request

from inference_cache_control import cache_measurement, require_idle
from local_llama import count_input, model_call
from local_llama_stream import model_call_stream, save
from model_provenance import check_live_model

ROOT=Path(__file__).resolve().parents[1]
PLAN='configs/P51_stream_receipts_v02.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get(config,path):
    with urllib.request.urlopen(config['base_url']+path,timeout=5) as response:
        return json.load(response)


def wait_idle(config,seconds):
    started=time.monotonic()
    while True:
        slots=get(config,'/slots')
        try:
            require_idle(slots)
            return time.monotonic()-started
        except ValueError:
            if time.monotonic()-started >= seconds:
                raise TimeoutError('slot did not become idle')
            time.sleep(0.25)


def run(storage,expected_commit):
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if actual != expected_commit or subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
        raise ValueError('require the clean fixed source commit')
    plan=json.loads((ROOT/PLAN).read_text());cfg=plan['model']
    schedule=['nonstream_complete','stream_complete','stream_disconnect']
    if (plan['phase']!='P51' or plan['schedule']!=schedule or plan['max_model_calls']!=3
            or cfg['num_predict']!=128 or cfg['cache_prompt'] is not False
            or cfg['seed']!=73 or cfg['num_ctx']!=65536 or cfg['call_timeout_seconds']!=120
            or plan['max_input_tokens_per_call']!=2048 or plan['max_reserved_logical_tokens']!=8192
            or plan['max_wall_seconds']!=300 or plan['max_quiescence_wait_seconds']!=30
            or plan['disconnect_after_observed_output_tokens']!=4 or plan['tools']
            or any(plan[k]!=0 for k in ('environment_api_requests','generated_tools_executed',
                                       'evaluator_calls','reserved_scenarios_read'))):
        raise ValueError('outside frozen stream probe')
    out=storage/'records/context_pilot'/plan['batch_id']
    out.mkdir(parents=True,exist_ok=False)
    runtime_path=storage/'.runtime/model_server.json'
    snapshot=out/'source';snapshot.mkdir()
    source_names=['probe_stream_receipts_v02.py','streaming_usage_receipt.py','local_llama_stream.py',
                  'local_llama.py','inference_cache_control.py','model_provenance.py']
    hashes={}
    for name in source_names:
        path=ROOT/'scripts'/name;hashes['scripts/'+name]=digest(path)
        (snapshot/name).write_bytes(path.read_bytes())
    hashes[PLAN]=digest(ROOT/PLAN);save(out/'plan.json',plan)
    started=time.monotonic()
    state={'phase':'P51','batch_id':plan['batch_id'],'status':'initializing','git_commit':actual,
        'started_at':datetime.now(timezone.utc).isoformat(),'source_sha256':hashes,
        'planned':schedule,'rows':[],'reserved_logical_tokens':0,
        'input_count_requests':0,
        'environment_api_requests':0,'generated_tools_executed':0,'evaluator_calls':0,
        'reserved_scenarios_read':0,'server_shutdown_record_pending':True}
    save(out/'status.json',state)
    def timeout(signum,frame):
        raise TimeoutError('nonstream request deadline')
    previous=signal.signal(signal.SIGALRM,timeout)
    try:
        runtime=json.loads(runtime_path.read_text())
        if runtime['status']!='ready':
            raise ValueError('server is not ready')
        props=get(cfg,'/props')
        selection,download,model=check_live_model(plan['model_selection'],runtime,props,root=storage,
                                  expected_ctx=65536,expected_cache=('q8_0','q8_0'))
        require_idle(get(cfg,'/slots'))
        save(out/'server_runtime.json',runtime);save(out/'server_props.json',props)
        state.update(status='running',model_identity={
            'revision':selection['revision'],'quantization':selection['quantization'],
            'runtime':selection['runtime'],'download_status':download['status'],
            'model_path':str(model.relative_to(storage))},
            server_record_directory=runtime['record_directory'],
            server_supervisor_pid=runtime['supervisor_pid'])
        save(out/'status.json',state)
        for index,label in enumerate(schedule):
            if (storage/'.runtime/STOP_P51_STREAM_CALIBRATION').exists():
                raise RuntimeError('stop file present')
            if time.monotonic()-started >= plan['max_wall_seconds']:
                raise TimeoutError('probe wall limit')
            current=json.loads(runtime_path.read_text())
            if (current['pid']!=runtime['pid'] or current['supervisor_pid']!=runtime['supervisor_pid']
                    or current['record_directory']!=runtime['record_directory'] or current['status']!='ready'):
                raise RuntimeError('server session changed')
            check_live_model(plan['model_selection'],current,get(cfg,'/props'),root=storage,
                             expected_ctx=65536,expected_cache=('q8_0','q8_0'))
            require_idle(get(cfg,'/slots'))
            state['input_count_requests']+=1
            counted=count_input(cfg,plan['messages'],[],timeout=min(30,300-(time.monotonic()-started)))
            predicted=counted['input_tokens']
            if predicted>2048 or state['reserved_logical_tokens']+predicted+128>8192:
                raise ValueError('fixed reservation cap')
            state['reserved_logical_tokens']+=predicted+128
            row={'label':label,'call_id':f'call_{index+1:03d}','status':'reserved','model_attempted':False,
                'predicted_input_tokens':predicted,'reserved_maximum_input_plus_output':predicted+128,
                'count_wall_seconds':counted['wall_seconds']}
            state['rows'].append(row);save(out/'status.json',state)
            folder=out/row['call_id'];folder.mkdir()
            remaining=300-(time.monotonic()-started)
            if remaining <= 0:
                raise TimeoutError('probe wall limit after counting')
            row.update(model_attempted=True,status='attempting');save(out/'status.json',state)
            if label=='nonstream_complete':
                response=model_call(cfg,plan['messages'],folder,remaining,[])
            else:
                response=model_call_stream(cfg,plan['messages'],folder,remaining,[],
                    stop_after_observed_tokens=4 if label=='stream_disconnect' else None)
            row.update({k:response.get(k) for k in ('status','input_tokens','output_tokens',
                'cached_input_tokens','wall_seconds','done_reason','error_kind','stream_receipt')})
            row['response_sha256']=digest(folder/'response.json')
            if label!='stream_disconnect':
                if response['status']!='ok' or response['output_tokens']>128:
                    raise ValueError('unexpected complete-case failure')
                measured=cache_measurement('cold_1',response,predicted)
                if not measured['state_confirmed']:
                    raise ValueError('first input was not cold')
                row['cache_measurement']=measured
                row['private_message_sha256']=hashlib.sha256(json.dumps(response['message'],
                    ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            else:
                receipt=response.get('stream_receipt',{})
                if (response['error_kind']!='intentional_probe_disconnect'
                        or response['input_tokens'] is not None or response['output_tokens'] is not None
                        or receipt.get('message_ready') or receipt.get('terminal_usage_received')
                        or receipt.get('observed_output_tokens_lower_bound',0)<4
                        or response['message']!={'role':'assistant','content':''}):
                    raise ValueError('intentional disconnect did not exercise incomplete receipt')
            save(out/'status.json',state)
        state['after_disconnect_idle_wait_seconds']=wait_idle(cfg,30)
        first,second=state['rows'][:2]
        state['complete_case_comparison']={
            'input_token_counts_equal':first['input_tokens']==second['input_tokens'],
            'output_token_counts_equal':first['output_tokens']==second['output_tokens'],
            'private_messages_equal':first['private_message_sha256']==second['private_message_sha256'],
            'equality_is_not_assumed_or_required_for_retry':True}
        state['status']='complete'
    except BaseException as exc:
        state.update(status='stopped',failure_type=type(exc).__name__)
        raise
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,previous)
        state['wall_seconds']=time.monotonic()-started
        state['known_total_tokens']=sum(r['input_tokens']+r['output_tokens'] for r in state['rows']
            if type(r.get('input_tokens')) is int and type(r.get('output_tokens')) is int)
        state['unknown_usage_calls']=sum(r['model_attempted'] and
            (r.get('input_tokens') is None or r.get('output_tokens') is None) for r in state['rows'])
        state['model_calls_attempted']=sum(r['model_attempted'] for r in state['rows'])
        state['not_attempted']=[label for label in schedule if not any(
            r['label']==label and r['model_attempted'] for r in state['rows'])]
        save(out/'status.json',state)
    target=ROOT/'reports/P51_stream_receipts_v02.json'
    if target.exists():raise FileExistsError('preserve earlier probe report')
    save(target,state)
    print(json.dumps({k:state[k] for k in ('status','known_total_tokens','unknown_usage_calls',
        'complete_case_comparison','after_disconnect_idle_wait_seconds','wall_seconds')}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--storage-root',required=True,type=Path)
    parser.add_argument('--expected-commit',required=True)
    args=parser.parse_args()
    run(args.storage_root.resolve(),args.expected_commit)
