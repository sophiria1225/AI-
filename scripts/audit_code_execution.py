"""Offline correspondence checks for the ordinary code-agent comparator."""
import argparse
import hashlib
import json
from pathlib import Path

from summarize_context_pilot import summarize_trial
from native_conversation import NativeConversation
from run_code_appworld import code_system_prompt
from code_agent_interface import CODE_TOOLS
from native_data_compute import selected_receipts

def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def audit(trial):
    summary=read(trial/'summary.json')
    if summary['arm']!='code_guided': raise ValueError('only code-guided trials')
    result=summarize_trial(trial);errors=[]
    for name,expected in summary['source_hashes'].items():
        if sha(trial/'source'/name)!=expected:
            errors.append('saved source differs: '+name)
    plan=read(trial/'plan.json')
    sources=['run_code_appworld.py','code_agent_interface.py','native_conversation.py']
    if plan['phase'] in ('P28','P29'): sources+=['run_code_control_appworld.py','code_runtime_prompts.py']
    if plan['phase']=='P29': sources+=['run_stateful_code_appworld.py','stateful_code_prompts.py','persistent_api_python.py']
    for name in sources:
        if sha(Path(__file__).parent/name)!=summary['source_hashes'][name]:
            raise ValueError('use the frozen code/history implementation')
    usage=read(trial/'usage.json');events=read(trial/'events.json');spans=read(trial/'spans.json')
    prompt=code_system_prompt()
    if plan['phase']=='P28':
        from code_runtime_prompts import control_system_prompt
        prompt=control_system_prompt(plan)
    session=None
    if plan['phase']=='P29':
        from stateful_code_prompts import stateful_system_prompt
        prompt=stateful_system_prompt(plan)
        session=read(trial/'python_session/session_private.json')
        if (session!=summary['python_session'] or session['status']!='closed'
            or not session['container_removed'] or session['process_memory_checkpointed']):
            errors.append('task-local interpreter lifecycle differs')
    history=NativeConversation(prompt,read(trial/'public_task.json'))
    prior={};programs=0;program_api=0
    for call in usage:
        request=read(trial/call['id']/'request.json')
        if request['messages']!=history.for_model(read(trial/'plan.json')['observation_page_characters'])[0]:
            errors.append(call['id']+': model-visible history differs')
        if request['tools']!=CODE_TOOLS: errors.append(call['id']+': code tools differ')
        if call['status']!='ok': continue
        message=read(trial/call['id']/'response.json')['message']
        this=[e for e in events if e['call']==call['id']]
        visible=[spans[e['span_id']] for e in this if e['stage']=='model_tool']
        try: history.append(message,visible)
        except ValueError: errors.append(call['id']+': public conversation cannot be reconstructed')
        inner=[];outer_count=0
        for e in this:
            row=spans[e['span_id']]
            if e['stage']=='python_api': inner.append((e,row));continue
            outer_count+=1
            folder=trial/'programs'/f"{call['id']}_{outer_count:02d}"
            if folder.exists():
                programs+=1
                arguments=json.loads(row['action']['arguments'])
                packet=read(folder/'input_private.json')
                if packet['code']!=arguments['code'] or packet['observations']!=selected_receipts(arguments['span_ids'],prior):
                    errors.append(call['id']+': program input differs from supplied code/prior receipts')
                wire_path=folder/'wire_private.jsonl'
                wire=[json.loads(line) for line in wire_path.read_text().splitlines()] if wire_path.exists() else []
                requests=[p for p in wire if p.get('kind')=='api']
                if len(requests)!=len(inner): errors.append(call['id']+': inner operation count differs')
                for rpc,(ev,span) in zip(requests,inner):
                    fn={'name':rpc['app']+'__'+rpc['api'], 'arguments':rpc['arguments']}
                    if fn['name']!=span['action']['name'] or fn['arguments']!=json.loads(span['action']['arguments']):
                        errors.append(call['id']+': code request/action mismatch')
                execution=read(folder/'result_private.json')
                sent=sum(int(x[0]['api_request_sent']) for x in inner);program_api+=sent
                if execution['api_requests']!=sent or row['observation'].get('api_requests')!=sent:
                    errors.append(call['id']+': code API accounting differs')
                if execution['status']!=row['observation'].get('status'):
                    errors.append(call['id']+': code result status differs')
                if session is not None:
                    if (execution.get('session_id')!=session['session_id']
                        or execution.get('program_index')!=programs
                        or packet.get('program_index')!=programs
                        or not execution.get('persistent_namespace')
                        or any(r.get('program_index')!=programs for r in requests)):
                        errors.append(call['id']+': persistent program/session identity differs')
                if ((session is None and not execution['container_removed']) or len(execution.get('controls',{}))!=14 or not all(execution.get('controls',{}).values())):
                    errors.append(call['id']+': isolation/cleanup was not verified')
                refs=row['observation'].get('api_receipts',[])
                if [x['span_id'] for x in refs]!=[x[0]['span_id'] for x in inner]:
                    errors.append(call['id']+': returned source references differ')
            elif inner: errors.append(call['id']+': inner effects without program artifact')
            inner=[]
        if inner: errors.append(call['id']+': unpaired program API operations')
        for e in this: prior[e['span_id']]=spans[e['span_id']]
    if session is not None and len(session['programs'])!=programs:
        errors.append('persistent session program count differs')
    if sum(int(e['api_request_sent']) for e in events)!=summary['api_requests'] or program_api!=summary['api_requests']:
        errors.append('total API accounting differs')
    if history.messages()!=read(trial/'conversation_private.json'):
        errors.append('final public conversation differs')
    result.update(code_audit_errors=errors,program_executions=programs,api_requests=program_api,
        source_hashes={**result['source_hashes'],**{p:sha(trial/p) for p in ('spans.json','events.json','plan.json')}},
        scope='Saved public input/history, code-to-API correspondence, budgets and container controls. No proof of semantic correctness.')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--trial',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=audit(a.trial);a.output.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:r[k] for k in ('run_id','audit_errors','code_audit_errors','program_executions','api_requests')}))
