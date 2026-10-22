"""Replay private P51 receipts offline; no network, generation or tool execution."""
import argparse
import hashlib
import json
from pathlib import Path

from local_llama import payload_for,parse_response
from local_llama_stream import stream_payload,save
from streaming_usage_receipt import SSEDecoder,CompletionReceipt

ROOT=Path(__file__).resolve().parents[1]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())

def audit(storage):
    folder=storage/'records/context_pilot/P51_stream_receipts_v02'
    state=read(folder/'status.json');plan=read(folder/'plan.json')
    errors=[];files={};checks=[]
    def verify(value,label):
        checks.append(label)
        if not value:errors.append(label)
    verify(state['status']=='complete' and len(state['rows'])==3,'three scheduled cases completed')
    verify(state['planned']==plan['schedule'] and state['not_attempted']==[],'schedule preserved')
    for relative,expected in state['source_sha256'].items():
        path=folder/'plan.json' if relative.startswith('configs/') else folder/'source'/Path(relative).name
        if relative.startswith('configs/'):
            # The runner saves parsed JSON with normalized indentation, not original bytes.
            verify(read(path)==read(ROOT/relative),'frozen plan contents '+relative)
        else:
            verify(sha(path)==expected,'frozen source '+relative)
        verify(sha(ROOT/relative)==expected,'published source '+relative)
    parsed=[]
    for index,row in enumerate(state['rows']):
        call=folder/row['call_id'];response=read(call/'response.json')
        verify(sha(call/'response.json')==row['response_sha256'],'response hash '+row['call_id'])
        expected=(payload_for if index==0 else stream_payload)(plan['model'],plan['messages'],[])
        verify(read(call/'request.json')==expected,'fixed request '+row['call_id'])
        for key in ('input_tokens','output_tokens','status','error_kind','stream_receipt'):
            verify(response.get(key)==row.get(key),'summary '+row['call_id']+' '+key)
        if index==0:
            raw=read(call/'raw_response.json');exact=parse_response(raw)
        else:
            decoder,receipt=SSEDecoder(),CompletionReceipt()
            stop=False
            with (call/'wire_private.sse').open('rb') as wire:
                while not stop and (data:=wire.read(137)):
                    for event in decoder.feed(data):
                        receipt.consume(event)
                        if receipt.done or (index==2 and receipt.output_lower_bound>=4):
                            stop=True;break
            verify(receipt.summary()==response['stream_receipt'],'offline stream receipt '+row['call_id'])
            if index==1:
                raw=receipt.final_response();exact=parse_response(raw)
                verify(raw==read(call/'raw_response.json'),'assembled full response')
            else:
                verify(not receipt.done and not receipt.summary()['message_ready']
                       and response['message']=={'role':'assistant','content':''},'incomplete message quarantined')
                verify(response['error_kind']=='intentional_probe_disconnect'
                       and response['input_tokens'] is None and response['output_tokens'] is None,
                       'partial count not terminal usage')
                verify(response['partial_message_executed'] is False and response['automatic_retries']==0,
                       'no partial execution or retry')
        if index<2:
            parsed.append(exact)
            verify(exact['input_tokens']==201 and exact['output_tokens']==76
                   and exact['cached_input_tokens']==0,'terminal counts '+row['call_id'])
            message_hash=hashlib.sha256(json.dumps(exact['message'],ensure_ascii=False,
                sort_keys=True,separators=(',',':')).encode()).hexdigest()
            verify(message_hash==row['private_message_sha256'],'message hash '+row['call_id'])
        for path in sorted(call.iterdir()):
            if path.is_file():files[str(path.relative_to(folder))]=sha(path)
    verify(parsed[0]['message']==parsed[1]['message'],'observed complete messages equal')
    verify(state['known_total_tokens']==554 and state['unknown_usage_calls']==1,'known plus unknown totals')
    verify(state['input_count_requests']==3 and state['model_calls_attempted']==3
           and state['reserved_logical_tokens']==987 and state['wall_seconds']<=300,'fixed budget')
    verify(all(state[k]==0 for k in ('environment_api_requests','generated_tools_executed',
        'evaluator_calls','reserved_scenarios_read')),'no task or evaluation access')
    server_dir=storage/state['server_record_directory'];server=read(server_dir/'summary.json')
    verify(server['status']=='stopped' and server['exit_code']==0
           and server['stop_reason']=='requested_stop'
           and server['supervisor_pid']==state['server_supervisor_pid'],'owned server stopped normally')
    closure={k:server[k] for k in ('started_at','status','wall_seconds','load_wall_seconds',
        'sampled_peak_rss_bytes','peak_system_swap_bytes','exit_code','stop_reason','memory_note')}
    closure['record_directory']=state['server_record_directory']
    closure['source_sha256']={name:sha(server_dir/name) for name in
        ('summary.json','memory.jsonl','server.log','serve_research_model.py','model_provenance.py')}
    report={'phase':'P51','batch_id':state['batch_id'],'audit_errors':errors,'checks':checks,
        'status_sha256':sha(folder/'status.json'),'files_sha256':files,'server_closure':closure,
        'private_plan_sha256':sha(folder/'plan.json'),
        'plan_check':'Runner normalized JSON serialization; compare parsed private plan with the published source whose original-byte SHA256 is fixed in status. The first audit incorrectly required identical whitespace; its failed check is preserved privately.',
        'input_output_raw_published':False,'model_calls_during_audit':0,'environment_calls_during_audit':0}
    target=ROOT/'reports/P51_stream_receipts_v02_audit.json'
    save(target,report)
    if errors:raise ValueError('P51 audit failed: '+repr(errors))
    public={**state,'server_shutdown_record_pending':False,
            'original_status_sha256':sha(folder/'status.json'),'server_closure':closure,
            'audit_report':'reports/P51_stream_receipts_v02_audit.json'}
    save(ROOT/'reports/P51_stream_receipts_v02.json',public)
    print(json.dumps({'audit_errors':errors,'checks':len(checks),'known_tokens':554,
        'unknown_calls':1,'server_wall_seconds':server['wall_seconds']}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--storage-root',required=True,type=Path)
    audit(parser.parse_args().storage_root.resolve())
