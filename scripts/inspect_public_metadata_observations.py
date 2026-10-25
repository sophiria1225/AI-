"""P117: classify all P116 archived observations against fixed public schemas."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path
import signal
import time

from appworld_native_tools import NativeCatalog
from inspect_appworld_api_schemas import load_public_tools
from inspect_input_exposure import check_resume
from inspect_recorded_action_agreement import sha,read_bound,verify_ci
from public_action_structure import digest
from public_metadata_observation import describe_tool_observation,exposure_summary
from receipt_reasoning_history import require

PLAN='configs/P117_public_metadata_observations_v01.json'
TARGET='reports/P117_public_metadata_observations.json'
ZERO=('model_generations','environment_API_requests','saved_code_executions','evaluations',
      'task_databases_read','reserved_scenarios_read','tokenizer_calls')


def fixed_parameters():
    return dict(phase='P117',source_profile='reports/P116_observation_growth.json',
        source_plan='configs/P116_observation_growth_v01.json',conditions=16,known_tasks=4,
        original_model_attempts=283,original_API_requests=820,original_known_logical_tokens=3026706,
        original_unknown_usage_calls=2,observation_occurrences=263,private_files=315,
        public_schema_data_root='.runtime/appworld/r18_probe_01/data',
        max_wall_seconds=180,max_file_bytes=16777216,max_total_private_input_bytes=536870912,
        max_messages_per_request=1024,max_stdout_characters=65536,automatic_retries=0,
        selection='all_P116_observation_occurrences_and_all_original_requests',
        matching='whole_literal_equals_complete_pinned_public_function_schema_values',
        prior_results_known=True,private_reasoning_inspected_semantically=False,
        dataflow_provenance_claim=False,semantic_irrelevance_claim=False,novel_method_claim=False,
        **{k:0 for k in ZERO})


def read(p):return json.loads(p.read_text())
def write_new(p,v):
    with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


def inspect(storage,root):
    began=time.monotonic();plan=read(root/PLAN)
    require(all(type(plan.get(k)) is type(v) and plan[k]==v for k,v in fixed_parameters().items()),'fixed_P117_scope_changed')
    stop=storage/'.runtime/P117.stop';require(not stop.exists(),'explicit_P117_stop')
    resume=check_resume(storage)
    for rel,h in plan['source_sha256'].items():require(sha(root/rel)==h,'source_changed:'+rel)
    head,ci=verify_ci(root)
    prior=read(root/plan['source_profile'])
    require(prior['status']=='complete' and not prior['errors'] and prior['completed_conditions']==16,
            'complete_all_P116_conditions_required')
    require([r['run_id'] for r in prior['runs']]==plan['run_ids'],'original_run_order_required')
    tools,schema_hashes,_=load_public_tools(storage/plan['public_schema_data_root'])
    require(schema_hashes==plan['public_schema_sha256'],'public_schema_identity_changed')
    catalog=NativeCatalog(tools);functions={n:t['function'] for n,t in catalog.catalog.items()}
    require(sum((storage/rel).stat().st_size for rel in plan['private_source_sha256'])<=plan['max_total_private_input_bytes'],
            'total_private_input_bound')
    require(len(plan['private_source_sha256'])==315 and not plan['absent_private_sources'],'fixed_all_present_inventory_required')
    fields=('source_audit','run_id','task_id','reasoning_display_policy','success','stop_reason','model_calls',
            'api_requests','known_total_tokens','unknown_usage_calls')
    result=dict(**fixed_parameters(),source_commit=head,ci=ci,research_resume=resume,
        plan_sha256=sha(root/PLAN),source_sha256=plan['source_sha256'],
        private_source_sha256=plan['private_source_sha256'],public_schema_sha256=schema_hashes,
        started_at=datetime.now(timezone.utc).isoformat(),status='incomplete',errors=[],
        runs=[dict(**{k:r[k] for k in fields},status='not_inspected',
            observations=[dict(**e,status='not_inspected') for e in r['tool_exposure']['messages']],
            calls=[dict(call_id=c['call_id'],status='not_inspected',usage_status=c['usage_status']) for c in r['calls']]) for r in prior['runs']],
        source_schema_identity_is_not_semantic_irrelevance=True,measured_savings=None)
    seen=set()
    def get(rel):
        require(not stop.exists(),'explicit_P117_stop')
        require(time.monotonic()-began<plan['max_wall_seconds'],'finite_P117_deadline')
        require(rel in plan['private_source_sha256'],'unbound_private_source')
        p=storage/rel;p.resolve().relative_to((storage/'records/context_pilot').resolve())
        require(p.is_file() and not p.is_symlink(),'regular_private_source_required')
        seen.add(rel);return read_bound(p,plan['private_source_sha256'][rel])
    try:
        for i,original in enumerate(prior['runs']):
            prefix='records/context_pilot/'+original['run_id']+'/'
            events=get(prefix+'events.json');spans=get(prefix+'spans.json')
            require(len(events)==len(spans)<=4000 and {e['span_id'] for e in events}==set(spans),'complete_original_events_required')
            visible=set(catalog.visible);visible_by_span={}
            for e in events:
                new=e.get('new_tools',[])
                require(type(new) is list and all(n in functions for n in new),'only_public_discovered_names_required')
                visible.update(new)
                if e['stage']=='model_tool':visible_by_span[e['span_id']]=set(visible)
            expected={(e['message_sha256'],e['occurrence']):e for e in original['tool_exposure']['messages']}
            inspected={};counts=Counter();calls=[]
            for ordinal,call in enumerate(original['calls'],1):
                request=get(prefix+call['call_id']+'/request.json')
                require(type(request.get('messages')) is list and len(request['messages'])<=1024,'bounded_original_input_required')
                local=Counter();new_count=0;tool_count=0
                for message in request['messages']:
                    if message.get('role')!='tool':continue
                    fingerprint=digest(message);local[fingerprint]+=1;tool_count+=1
                    key=(fingerprint,local[fingerprint]);require(key in expected,'unrecognized_P116_observation')
                    counts[key]+=1
                    if key not in inspected:
                        saved=expected[key]
                        require(saved['first_input_ordinal']==ordinal and saved['characters']==len(message['content']),
                                'P116_first_exposure_changed')
                        described=describe_tool_observation(message,spans,functions,visible_by_span)
                        inspected[key]={**saved,**described,'status':'checked'};new_count+=1
                calls.append(dict(call_id=call['call_id'],ordinal=ordinal,status='checked',
                    usage_status=call['usage_status'],known_total_tokens=call['known_total_tokens'],
                    tool_messages=tool_count,new_observation_occurrences=new_count))
            require(set(inspected)==set(expected) and all(counts[k]==e['exposures'] for k,e in expected.items()),
                    'every_original_observation_exposure_required')
            rows=[inspected[(e['message_sha256'],e['occurrence'])] for e in original['tool_exposure']['messages']]
            result['runs'][i].update(status='complete',calls=calls,observations=rows,summary=exposure_summary(rows))
        require(seen==set(plan['private_source_sha256']),'all_private_sources_required')
        require(sum(len(r['calls']) for r in result['runs'])==283
                and sum(len(r['observations']) for r in result['runs'])==263,'all_request_and_observation_slots_required')
        for rel,h in plan['private_source_sha256'].items():require(sha(storage/rel)==h,'private_source_changed_during_profile')
        result.update(status='complete',summary=exposure_summary([e for r in result['runs'] for e in r['observations']]))
    except BaseException as error:
        result['errors'].append(dict(type=type(error).__name__,reason=str(error)
            if type(error) in (ValueError,TimeoutError,InterruptedError) else 'inspect_private_log'))
        raise
    finally:
        result.update(ended_at=datetime.now(timezone.utc).isoformat(),wall_seconds=time.monotonic()-began,
            inspected_private_sources=len(seen),completed_conditions=sum(r['status']=='complete' for r in result['runs']))
        write_new(root/TARGET,result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root',type=Path,required=True)
    parser.add_argument('--repo-root',type=Path,default=Path(__file__).resolve().parents[1]);args=parser.parse_args()
    root=args.repo_root.resolve();failure=root/'reports/P117_public_metadata_observations_failure.json'
    require(not (root/TARGET).exists() and not failure.exists(),'preserve_every_P117_attempt')
    began=time.monotonic()
    def expired(*_):raise TimeoutError('finite_P117_deadline')
    old=signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,180)
    try:data=inspect(args.storage_root.resolve(),root)
    except BaseException as error:
        write_new(failure,dict(status='failed',error_type=type(error).__name__,detail=str(error)
            if type(error) in (ValueError,TimeoutError,InterruptedError) else 'inspect_private_log',
            wall_seconds=time.monotonic()-began,**{k:0 for k in ZERO}));raise
    finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
    print(json.dumps({k:data[k] for k in ('status','completed_conditions','inspected_private_sources','summary','wall_seconds')}))


if __name__=='__main__':main()
