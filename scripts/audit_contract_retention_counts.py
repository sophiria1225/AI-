"""Offline P53 source/input/accounting audit and owned-server closure."""
import argparse
import hashlib
import json
from pathlib import Path

from count_contract_retention import MODES,prepare,read,sha
from local_llama_stream import save

ROOT=Path(__file__).resolve().parents[1]

def audit(storage):
    folder=storage/'records/context_pilot/P53_contract_retention_counts_v01'
    state=read(folder/'status.json');plan=read(folder/'plan.json');errors=[];checks=[]
    def check(ok,label):
        checks.append(label)
        if not ok:errors.append(label)
    check(state['status']=='complete','completed source status')
    check(state['planned_inputs']==state['attempted_inputs'] and state['not_attempted_inputs']==[],
          'all sixteen planned inputs attempted once in order')
    check(state['count_requests_attempted']==state['count_requests_completed']==16,'sixteen completed counts')
    for path,digest in state['source_sha256'].items():check(sha(ROOT/path)==digest,'source '+path)
    check(plan==read(ROOT/'configs/P53_contract_retention_counts_v01.json'),'normalized plan contents')
    _,inputs=prepare(storage,plan)
    for item,row in zip(inputs,state['rows'],strict=True):
        check(item['source_run']==row['source_run'],'source '+row['source_run'])
        check(item['control']==row['control'],'control selection '+row['source_run'])
        for mode in MODES:
            path=folder/(row['source_run']+'_'+mode+'_private.json')
            check(sha(path)==row['views'][mode]['input_sha256'],'input hash '+row['source_run']+' '+mode)
            check(read(path)==item['messages'][mode],'input reconstruction '+row['source_run']+' '+mode)
            check(type(row['views'][mode]['input_tokens']) is int and row['views'][mode]['input_tokens']>0,
                  'recorded count '+row['source_run']+' '+mode)
        for mode in MODES[1:]:
            check(row['tokens_removed'][mode]==row['views']['full_keep']['input_tokens']-row['views'][mode]['input_tokens'],
                  'difference '+row['source_run']+' '+mode)
    for mode in MODES[1:]:
        number=sum(r['tokens_removed'][mode]>=1000 for r in state['rows'])
        check(state['allocation_gate'][mode]=={'tasks_at_least_1000':number,'passed':number>=2},'fixed gate '+mode)
    check(all(state[k]==0 for k in ('model_generations','environment_api_requests','program_reexecutions',
        'evaluator_calls','reserved_scenarios_read')),'zero generation and task execution')
    session=storage/state['server_record_directory'];server=read(session/'summary.json')
    check(server['status']=='stopped' and server['exit_code']==0 and server['stop_reason']=='requested_stop'
          and server['supervisor_pid']==state['server_supervisor_pid']
          and server['pid']==state['server_pid'],'owned server normal shutdown')
    closure={k:server[k] for k in ('started_at','status','wall_seconds','load_wall_seconds',
        'sampled_peak_rss_bytes','peak_system_swap_bytes','exit_code','stop_reason','memory_note')}
    closure['record_directory']=state['server_record_directory']
    closure['source_sha256']={name:sha(session/name) for name in ('summary.json','memory.jsonl','server.log')}
    report={'phase':'P53','audit_errors':errors,'checks':checks,'original_status_sha256':sha(folder/'status.json'),
        'count_requests_during_audit':0,'model_generations_during_audit':0,
        'server_closure':closure,'scope':'Reconstruct all fixed inputs and verify saved counts/accounting; no repeated tokenizer calls or task-quality evaluation.'}
    save(ROOT/'reports/P53_contract_retention_audit.json',report)
    if errors:raise ValueError('P53 audit failed '+repr(errors))
    save(ROOT/'reports/P53_contract_retention_counts.json',{**state,'server_shutdown_record_pending':False,
        'original_status_sha256':sha(folder/'status.json'),'server_closure':closure,
        'audit_report':'reports/P53_contract_retention_audit.json'})
    print(json.dumps({'checks':len(checks),'audit_errors':errors,'server_wall_seconds':server['wall_seconds'],
                     'counting_wall_seconds':state['wall_seconds']}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--storage-root',required=True,type=Path)
    audit(parser.parse_args().storage_root.resolve())
