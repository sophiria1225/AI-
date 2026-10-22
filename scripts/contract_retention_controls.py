"""Ordinary control: keep listings but omit attributable API details."""
import copy
import json

from context_preservation import compact
from documentation_print_origin import build_origin_view
from handoff_factors import split_turns
from input_exposure_accounting import digest
from native_conversation import NativeConversation,recover_turn

def detail_only_control(item):
    # Reuse the frozen full-output recognition; never search text for a schema.
    views,meta=build_origin_view(item)
    prefix=item['prefix'];eligible=set()
    for event in prefix['events']:
        if event['stage']!='python_api':continue
        action=prefix['spans'][event['span_id']]['action']
        if action['name']!='api_docs__show_api_doc':continue
        args=json.loads(action['arguments'])
        if args.get('app_name') in ('api_docs','supervisor'):continue
        eligible.add(event['span_id'])
    checks={row['span_id']:row for row in meta['checks']}
    full=views['full_keep'];output=NativeConversation(full.messages()[0]['content'],prefix['public_task'])
    records=[]
    for turn in split_turns(full.messages()):
        spans=recover_turn(turn)
        for span in spans:
            check=checks.get(span['id'],{})
            if not check.get('recognized'):continue
            old=span['observation'];parts=[];omitted=set()
            for segment in check['segments']:
                text=old['stdout'][segment['start']:segment['end']]
                if digest(text)!=segment['text_sha256']:raise ValueError('recognized segment changed')
                sid=segment['receipt_id']
                if sid in eligible:
                    parts.append(f'[API documentation omitted; read archived span {sid}.]');omitted.add(sid)
                else:parts.append(text)
            if not omitted:continue
            replacement=copy.deepcopy(old);replacement['stdout']=''.join(parts)
            replacement['stdout_view']={'omitted':True,'source_span_id':span['id'],
                'documentation_receipt_ids':sorted(omitted),'literal_output_preserved':True,
                'retention_candidate':'all_documented_details','future_irrelevance_proven':False}
            if len(compact(replacement))>=len(compact(old)):continue
            span['observation']=replacement
            records.append({'span_id':span['id'],'documentation_receipt_ids':sorted(omitted)})
        output.append(turn[0],spans)
    return output,{'mode':'all_documented_details','changed_outputs':len(records),'changes':records,
        'app_and_api_listings_retained':True,'uses_execution_outcomes_to_choose_details':False,
        'latest_turn_retained':True,'future_irrelevance_proven':False}
