"""Bounded P39 calibration, never executes model-generated tools or task worlds."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time
import urllib.request

from diagnose_projected_misses import model_payload
from field_read_contract import canonical
from inference_cache_control import (SCHEDULE, cache_measurement, request_for,
                                     require_idle, validate_erasure)
from local_llama import parse_response, post
from model_provenance import check_live_model
from run_event_view_probe import lease_remaining

ROOT=Path(__file__).resolve().parents[1]
SOURCES=('scripts/probe_inference_cache.py','scripts/inference_cache_control.py',
         'scripts/local_llama.py','scripts/model_provenance.py',
         'scripts/diagnose_projected_misses.py','scripts/field_read_contract.py',
         'scripts/run_event_view_probe.py',
         'configs/P29_stateful_code_v01.json',
         'tests/test_inference_cache_control.py')


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)


def get(endpoint):
    with urllib.request.urlopen('http://127.0.0.1:8011'+endpoint,timeout=10) as response:
        return json.load(response)


def live_identity(storage,source_plan,required_seconds):
    runtime=read(storage/'.runtime/model_server.json')
    check_live_model(source_plan['model_selection'],runtime,get('/props'),root=storage,
                     expected_ctx=source_plan['model']['num_ctx'],expected_cache=('q8_0','q8_0'))
    require_idle(get('/slots'))
    command=subprocess.check_output(['ps','-p',str(runtime['supervisor_pid']),'-o','command='],text=True).strip()
    remaining,end=lease_remaining(runtime,command,dt.datetime.now(dt.timezone.utc))
    if remaining<required_seconds:raise ValueError('not enough server lease for bounded calibration')
    return {k:runtime[k] for k in ('model_revision','runtime','started_at','pid','supervisor_pid','ctx_size')},end


def source_paths(version):
    if version not in ('v01','v02'):raise ValueError('unknown fixed calibration version')
    return SOURCES+(f'configs/P39_inference_cache_{version}.json',
                    'docs/experiments/P39_inference_cache'+('_v02' if version=='v02' else '')+'.md')


def condition_payload(payload,label,version):
    import copy
    if label not in SCHEDULE or version not in ('v01','v02'):raise ValueError('unknown condition/version')
    result=copy.deepcopy(payload)
    if version=='v02':result['cache_prompt']=not label.startswith('cold_')
    return result


def sources(storage,root,version='v01'):
    source_paths(version)
    plan=read(root/f'configs/P39_inference_cache_{version}.json')
    if plan['source_run']!='P38_04_NONE_KEEP' or plan['batch_id']!='P39_inference_cache_'+version:
        raise ValueError('outside the fixed known development input')
    status=read(storage/'records/context_pilot/P38_batch_v01/status.json')
    if status['status']!='complete' or len(status['completed'])!=3:
        raise ValueError('P38 must be closed')
    trial=storage/'records/context_pilot'/plan['source_run'];usage=read(trial/'usage.json')
    path=trial/usage[0]['id']/'request.json'
    if sha(path)!=plan['source_request_sha256']:raise ValueError('fixed input changed')
    payload=request_for(read(path),plan)
    if (plan['max_total_tokens']<plan['max_calls']*(plan['source_input_tokens']+plan['max_output_tokens'])
            or payload['model']!='minimax-m3-iq4xs'):
        raise ValueError('invalid bounded generation budget/model')
    return plan,read(root/'configs/P29_stateful_code_v01.json'),payload


def prepare(storage,root,version='v01'):
    plan,source_plan,payload=sources(storage,root,version)
    identity,end=live_identity(storage,source_plan,plan['max_wall_seconds']+60)
    count=post({'base_url':'http://127.0.0.1:8011'},'/v1/chat/completions/input_tokens',payload,60)
    if count.get('input_tokens')!=plan['source_input_tokens']:raise ValueError('input count differs')
    target=root/f'reports/P39_activation_{version}.json'
    if target.exists():raise FileExistsError('preserve preparation')
    result={'phase':'P39','version':version,'source_sha256':{p:sha(root/p) for p in source_paths(version)},
            'request_sha256':hashlib.sha256(canonical(payload).encode()).hexdigest(),
            'condition_request_sha256':{label:hashlib.sha256(canonical(condition_payload(payload,label,version)).encode()).hexdigest() for label in SCHEDULE},
            'input_tokens':count['input_tokens'],'model_identity':identity,'server_lease_end':end,
            'prepared_at':dt.datetime.now(dt.timezone.utc).isoformat(),
            'model_calls':0,'input_count_requests':1,'environment_api_requests':0}
    write(target,result);print(json.dumps(result,ensure_ascii=False))


def erase():
    require_idle(get('/slots'));at=time.monotonic()
    response=post({'base_url':'http://127.0.0.1:8011'},'/slots/0?action=erase',{},30)
    count=validate_erasure(response);require_idle(get('/slots'))
    return {'erased_tokens':count,'wall_seconds':time.monotonic()-at}


def run(storage,root,version='v01'):
    plan,source_plan,payload=sources(storage,root,version);activation=read(root/f'reports/P39_activation_{version}.json')
    if activation['source_sha256']!={p:sha(root/p) for p in source_paths(version)}:
        raise ValueError('prepared sources changed')
    if activation['request_sha256']!=hashlib.sha256(canonical(payload).encode()).hexdigest():
        raise ValueError('prepared request changed')
    identity,end=live_identity(storage,source_plan,plan['max_wall_seconds']+60)
    if identity!=activation['model_identity']:raise ValueError('server identity changed')
    folder=storage/'records/context_pilot'/plan['batch_id']
    target=root/('reports/P39_inference_cache'+('_v02' if version=='v02' else '')+'.json')
    if folder.exists() or target.exists():raise FileExistsError('preserve calibration')
    folder.mkdir();write(folder/'plan.json',plan);write(folder/'activation.json',activation)
    start=time.monotonic();rows=[];total=0;unknown=0
    state={'phase':'P39','version':version,'status':'running','active':None,'rows':rows,
           'started_at':dt.datetime.now(dt.timezone.utc).isoformat(),'model_identity':identity,
           'server_lease_end':end,'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
           'source_sha256':activation['source_sha256']}
    def save():
        state.update(known_total_tokens=total,unknown_usage_calls=unknown,
                     updated_at=dt.datetime.now(dt.timezone.utc).isoformat())
        write(folder/'status.json',state)
    save()
    try:
        for label in SCHEDULE:
            if (storage/'.runtime/P39.stop').exists():raise InterruptedError('stop requested')
            remaining=plan['max_wall_seconds']-(time.monotonic()-start)
            if remaining<plan['call_timeout_seconds']+35:raise TimeoutError('insufficient remaining calibration wall budget')
            if total+plan['source_input_tokens']+plan['max_output_tokens']>plan['max_total_tokens']:
                raise ValueError('calibration token reservation limit')
            current,_=live_identity(storage,source_plan,plan['call_timeout_seconds']+35)
            if current!=identity:raise ValueError('server identity changed during calibration')
            trial=folder/label;trial.mkdir();state['active']=label;save()
            call_payload=condition_payload(payload,label,version)
            if hashlib.sha256(canonical(call_payload).encode()).hexdigest()!=activation['condition_request_sha256'][label]:
                raise ValueError('condition request differs from activation')
            preparation=erase() if version=='v01' and label.startswith('cold_') else {'erased_tokens':None,'wall_seconds':0}
            preparation['cache_prompt']=call_payload['cache_prompt']
            write(trial/'preparation.json',preparation);write(trial/'request.json',call_payload)
            begin=time.monotonic();record={'status':'error','input_tokens':None,'output_tokens':None}
            signal.alarm(plan['call_timeout_seconds'])
            try:
                raw=post({'base_url':'http://127.0.0.1:8011'},'/v1/chat/completions',call_payload,plan['call_timeout_seconds'])
                write(trial/'raw_response.json',raw);record.update(parse_response(raw))
            except Exception as error:
                record.update(error_type=type(error).__name__)
                (trial/'error_private.txt').write_text(str(error))
            finally:
                signal.alarm(0);record['wall_seconds']=time.monotonic()-begin;write(trial/'response.json',record)
            row={'label':label,'status':record['status'],'preparation':preparation,
                 'wall_seconds':record['wall_seconds'],'state_confirmed':False,
                 'input_tokens':record['input_tokens'],'output_tokens':record['output_tokens'],
                 'request_sha256':sha(trial/'request.json'),'response_sha256':sha(trial/'response.json')}
            rows.append(row)
            if record['status']!='ok':
                unknown+=1;save();raise ValueError('unknown terminal usage; no replacement trial')
            total+=record['input_tokens']+record['output_tokens']
            row.update(cache_measurement(label,record,plan['source_input_tokens']))
            row['done_reason']=record['done_reason']
            row['model_payload_sha256']=hashlib.sha256(canonical(model_payload(record['message'])).encode()).hexdigest()
            save();print(json.dumps(row,ensure_ascii=False),flush=True)
            if not row['state_confirmed']:raise ValueError('observed cache state did not meet the fixed condition')
        state['status']='complete'
    except Exception as error:
        state.update(status='stopped',error_type=type(error).__name__)
        (folder/'error_private.txt').write_text(str(error))
    finally:
        state['active']=None
        if version=='v01':
            try:
                current,_=live_identity(storage,source_plan,35)
                if current!=identity:raise ValueError('do not clear a different server')
                state['cleanup']={'status':'cleared',**erase()}
            except Exception as error:
                state['cleanup']={'status':'not_cleared','reason_type':type(error).__name__}
        else:
            state['cleanup']={'status':'cache_retained','next_call_requires_explicit_cache_policy':True}
        state['wall_seconds']=time.monotonic()-start;save()
    groups={kind:[r for r in rows if r['label'].startswith(kind+'_') and r.get('state_confirmed')]
            for kind in ('cold','warm')}
    comparison={}
    for kind,group in groups.items():
        pairs=[(a,b) for i,a in enumerate(group) for b in group[i+1:]]
        comparison[kind]={'confirmed_calls':len(group),'compared_pairs':len(pairs),
                          'equal_pairs':sum(a['model_payload_sha256']==b['model_payload_sha256'] for a,b in pairs)}
    cross=[(a,b) for a in groups['cold'] for b in groups['warm']]
    comparison['cross']={'compared_pairs':len(cross),
                         'equal_pairs':sum(a['model_payload_sha256']==b['model_payload_sha256'] for a,b in cross)}
    result={**state,'all_six_attempted':len(rows)==6,'output_comparison':comparison,
            'model_calls_attempted':len(rows),
            'environment_api_requests':0,'final_evaluator_calls':0,'reserved_scenarios_read':0,
            'limits':['One known input, capped generation, no task execution or task success metric.',
                      'Pairs share prompts and a single runtime; they are not independent samples.',
                      'Different batches/cache states may change computation; this probe does not locate a numerical cause.',
                      'Only transport tool-call IDs are excluded from message equality.']}
    write(target,result);return 0 if state['status']=='complete' else 1


def interrupt(*_):raise TimeoutError('bounded local calibration interrupted')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--repo-root',type=Path,default=ROOT);p.add_argument('--prepare',action='store_true')
    p.add_argument('--version',choices=('v01','v02'),default='v01');a=p.parse_args()
    signal.signal(signal.SIGALRM,interrupt);signal.signal(signal.SIGTERM,interrupt)
    if a.prepare:prepare(a.storage_root,a.repo_root,a.version)
    else:raise SystemExit(run(a.storage_root,a.repo_root,a.version))
