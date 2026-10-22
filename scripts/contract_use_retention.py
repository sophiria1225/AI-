"""Prefix-only candidates for retaining documentation until observed use.

A successful-looking public response is evidence of use, never proof that a
contract is irrelevant to future calls. This module does not run an agent.
"""
import copy
import json

from context_preservation import compact
from documentation_print_origin import recognize
from handoff_factors import split_turns
from handoff_output_views import make_view
from input_exposure_accounting import digest,receipt_group
from native_conversation import NativeConversation,recover_turn

MODES=('used_since_document','all_parameters_observed')

def decode_response(event,span):
    if event.get('api_request_sent') is not True or event.get('effects_unknown'):
        return False,None
    observation=span.get('observation')
    if (type(observation) is not dict or 'observation' not in observation
            or set(observation)-{'observation','declared_complete'} or observation.get('declared_complete')):
        return False,None
    value=observation['observation']
    try:value=json.loads(value) if isinstance(value,str) else value
    except ValueError:return False,None
    if type(value) not in (dict,list) or (type(value) is dict and {'error','detail'} & value.keys()):
        return False,None
    return True,value

def use_evidence(prefix,schemas):
    """Only passed prefix events may influence decisions, never later outcomes."""
    evidence={};seen=set();previous_call=0
    for event in prefix['events']:
        sid=event['span_id']
        if sid in seen or sid not in prefix['spans']:
            raise ValueError('duplicate or missing prefix receipt')
        seen.add(sid)
        number=int(event['call'].removeprefix('call_'))
        if number<previous_call or number>prefix['manifest']['state']['model_calls']:
            raise ValueError('outside chronological fixed prefix')
        previous_call=number
        if event['stage']!='python_api':continue
        span=prefix['spans'][sid];action=span['action'];name=action['name']
        args=json.loads(action['arguments'])
        if type(args) is not dict:raise ValueError('API arguments object required')
        ok,value=decode_response(event,span)
        # Every actual attempt after each documentation receipt contributes.
        for item in evidence.values():
            if item['target_api']!=name:continue
            item['attempts_since_document']+=1
            item['last_attempt_observed_non_error_json']=ok
            if ok:
                item['non_error_json_responses_since_document']+=1
                item['observed_parameter_names']=sorted(set(item['observed_parameter_names'])|set(args))
            else:
                item['uncertain_or_failed_attempts_since_document']+=1
        if name=='api_docs__show_api_doc' and ok:
            target=str(args.get('app_name'))+'__'+str(args.get('api_name'))
            schema=schemas.get(target)
            if type(schema) is not dict:raise ValueError('documentation target absent from pinned schema')
            properties=schema.get('parameters',{}).get('properties')
            if type(properties) is not dict:raise ValueError('properties object required')
            evidence[sid]={'target_api':target,'document_call':event['call'],
                'document_value_sha256':digest(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))),
                'public_parameter_names':sorted(properties),'observed_parameter_names':[],
                'attempts_since_document':0,'non_error_json_responses_since_document':0,
                'uncertain_or_failed_attempts_since_document':0,'last_attempt_observed_non_error_json':None}
    for item in evidence.values():
        # Do not retire protocol/finish instructions or any contract with a
        # later rejected/uncertain attempt. Counts describe observed calls only.
        used=(item['non_error_json_responses_since_document']>0
            and item['uncertain_or_failed_attempts_since_document']==0
            and not item['target_api'].startswith(('api_docs__','supervisor__')))
        complete=set(item['public_parameter_names'])<=set(item['observed_parameter_names'])
        item.update(used_since_document=used,all_parameters_observed=used and complete,
            future_irrelevance_proven=False,semantic_success_verified=False)
    return evidence

def build_use_view(item,schemas,mode):
    if mode not in MODES:raise ValueError('unknown retention candidate')
    prefix=item['prefix'];evidence=use_evidence(prefix,schemas)
    full,_=make_view(prefix['conversation_private'],prefix['public_task'],'full_keep')
    _,masked=make_view(prefix['conversation_private'],prefix['public_task'],'stdout_mask_keep')
    candidates={row['span_id'] for row in masked['masked_spans']}
    events={row['span_id']:row for row in prefix['events']}
    outer=[row for row in prefix['events'] if row['stage']=='model_tool']
    if len(outer)!=len(item['programs']):raise ValueError('program correspondence')
    programs={};sources=[]
    for event,program in zip(outer,item['programs'],strict=True):
        if not program['name'].startswith(event['call']+'_'):raise ValueError('program order')
        sources.append(program['source']['code']);programs[event['span_id']]=(program,sources[:])
    selected=NativeConversation(full.messages()[0]['content'],prefix['public_task']);checks=[]
    for turn in split_turns(full.messages()):
        spans=recover_turn(turn)
        for span in spans:
            if span['id'] not in candidates:continue
            obs=span['observation'];group,_=receipt_group(obs,prefix['spans'],events)
            row={'span_id':span['id'],'changed':False,'receipt_group':group};checks.append(row)
            if group!='documentation_only':continue
            program,source_prefix=programs[span['id']]
            if (program['expected']['stdout']!=obs['stdout']
                    or json.loads(span['action']['arguments'])['code']!=program['source']['code']
                    or any(events[r['span_id']]['call']!=events[span['id']]['call'] for r in obs['api_receipts'])):
                raise ValueError('source output or receipt changed')
            meta,segments=recognize(program,[r['span_id'] for r in obs['api_receipts']],source_prefix)
            row['recognized']=meta['recognized']
            if not meta['recognized']:continue
            omitted={s['receipt_id'] for s in segments if s['receipt_id'] in evidence
                     and evidence[s['receipt_id']][mode]}
            row['eligible_document_receipts']=sorted(omitted)
            if not omitted:continue
            replacement=copy.deepcopy(obs)
            replacement['stdout']=''.join(
                f'[API documentation omitted after observed use; read archived span {s["receipt_id"]}.]'
                if s['receipt_id'] in omitted else s['text'] for s in segments)
            replacement['stdout_view']={'omitted':True,'source_span_id':span['id'],
                'documentation_receipt_ids':sorted(omitted),'literal_output_preserved':True,
                'retention_candidate':mode,'future_irrelevance_proven':False}
            if len(compact(replacement))>=len(compact(obs)):
                row['reason']='replacement_not_shorter';continue
            row.update(changed=True,removed_stdout_characters=len(obs['stdout'])-len(replacement['stdout']),
                       documentation_receipt_ids=sorted(omitted))
            span['observation']=replacement
        selected.append(turn[0],spans)
    return selected,{'mode':mode,'checks':checks,'receipt_use_evidence':evidence,
        'candidate_outputs':len(checks),'changed_outputs':sum(r['changed'] for r in checks),
        'removed_stdout_characters':sum(r.get('removed_stdout_characters',0) for r in checks),
        'app_and_api_listings_retained':True,'latest_turn_retained':True,'original_archive_modified':False,
        'future_irrelevance_proven':False,'quality_preservation_claim':False}
