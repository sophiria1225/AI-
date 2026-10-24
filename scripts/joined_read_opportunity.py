"""Chronological joined-field availability and bounded syntax, not savings."""
from collections import Counter
import hashlib
import json

from field_read_contract import (FIELDS, READ_ONLY_APIS, SOURCE, TARGET, canonical,
                                 target_identity, valid_field)
from joined_public_read_views import JOINED_CONTRACT_ID, JoinedPublicReadAuthority
from public_read_opportunity import public_value
from return_use_scope import analyze as syntax_inventory

SOURCES = frozenset((SOURCE,TARGET,'spotify__show_album','spotify__show_playlist'))


def analyze(events, spans, usage, original_targets):
    if len(events)>4000 or len(usage)>80:raise ValueError('fixed_record_bound_exceeded')
    positions={u['id']:i for i,u in enumerate(usage)}
    ids=[e['span_id'] for e in events];ranks=[positions.get(e['call'],-1) for e in events]
    if (len(positions)!=len(usage) or -1 in ranks or ranks!=sorted(ranks)
            or len(ids)!=len(set(ids)) or set(ids)!=set(spans)):
        raise ValueError('complete_chronological_records_required')
    original={t['event_ordinal']:t for t in original_targets}
    if len(original)!=len(original_targets):raise ValueError('duplicate_fixed_target')
    p=JoinedPublicReadAuthority('closed-P91',verified_contract=JOINED_CONTRACT_ID)
    epoch=0;poisoned=False;counts=Counter();targets=[];target_spans={}
    for ordinal,e in enumerate(events,1):
        if not e['api_request_sent']:
            if e.get('effects_unknown'):poisoned=True;p.cache.invalidate()
            continue
        receipt=e.get('api_execution')
        if (e['stage']!='python_api' or type(receipt) is not dict
                or receipt.get('bridge_request_sent') is not True
                or receipt.get('automatic_retries')!=0
                or receipt.get('status') not in {'returned','raised','unknown'}):
            raise ValueError('typed_request_receipt_required')
        span=spans[e['span_id']];action=span['action'];name=action.get('name');args=action.get('arguments')
        if isinstance(args,str):args=json.loads(args)
        if type(name) is not str or name.count('__')!=1 or type(args) is not dict:
            raise ValueError('documented_action_shape_required')
        app,api=name.split('__');call=dict(app=app,api=api,args=args)
        counts['sent_requests']+=1;counts['receipt_'+receipt['status']]+=1
        if name not in READ_ONLY_APIS:
            p.cache.invalidate();epoch+=1;counts['conservative_invalidations']+=1
        found=p.lookup(call,epoch) if name==TARGET and not poisoned else None
        before='unknown_state' if poisoned else found[0] if found else 'absent'
        known=receipt['status']=='returned' and not e.get('effects_unknown')
        value=public_value(span) if known and name in SOURCES else None
        if name==TARGET:
            old=original.get(ordinal);request_hash=hashlib.sha256(canonical(call).encode()).hexdigest()
            if (old is None or old['request_sha256']!=request_hash or old['call_id']!=e['call']
                    or old['receipt_status']!=receipt['status']):
                raise ValueError('fixed_P89_target_changed')
            supported=(target_identity(name,args) is not None and known and type(value) is dict
                and type(value.get('song_id')) is int and value['song_id']==args['song_id']
                and all(k in value and valid_field(k,value[k]) for k in FIELDS))
            match=None if found is None else bool(supported and (canonical(value)==canonical(found[1])
                if found[0]=='complete' else all(k in value and canonical(v)==canonical(value[k])
                                                for k,v in found[1].items())))
            row=dict(event_ordinal=ordinal,call_id=e['call'],request_sha256=request_hash,
                original_authority_before=old['authority_before'],joined_authority_before=before,
                available_fields_before=sorted(found[1]) if found else [],
                receipt_status=receipt['status'],prior_fields_match_returned=match,
                response_supported=bool(supported),field_demand_known=False,
                avoided_request_established=False)
            targets.append(row);target_spans[e['span_id']]=row
            counts['target_requests']+=1;counts['before_'+before]+=1
        if receipt['status']=='unknown' or e.get('effects_unknown'):
            poisoned=True;p.cache.invalidate()
        if known and not poisoned and name in SOURCES:
            p.observe(call,value,epoch);counts['observed_'+name]+=1
    if {t['event_ordinal'] for t in targets}!=set(original):raise ValueError('fixed_target_omitted')
    # API receipts explicitly connect executed inner calls to their outer code
    # submission. AST sites are NOT mapped one-for-one to dynamic requests.
    programs=[];assigned=set()
    for e in events:
        if e['stage']!='model_tool':continue
        span=spans[e['span_id']];obs=span['observation']
        receipts=obs.get('api_receipts',[])
        members=[r['span_id'] for r in receipts if r.get('span_id') in target_spans]
        if not members:continue
        if any(r.get('api')!=TARGET or r.get('api_request_sent') is not True
               for r in receipts if r.get('span_id') in target_spans):
            raise ValueError('target_parent_receipt_not_an_executed_target')
        if len(members)!=len(set(members)) or assigned.intersection(members):
            raise ValueError('ambiguous_target_program_receipt')
        if any(target_spans[s]['call_id']!=e['call'] for s in members):
            raise ValueError('target_program_boundary_mismatch')
        fn=span['action']
        if fn.get('name')!='run_python':raise ValueError('actual_python_parent_required')
        args=fn['arguments'];args=json.loads(args) if type(args) is str else args
        if type(args) is not dict or type(args.get('code')) is not str:
            raise ValueError('recorded_source_required')
        inventory=syntax_inventory(args['code'])
        programs.append(dict(parent_span_id=e['span_id'],call_id=e['call'],
            actual_target_requests=len(members),source_sha256=inventory['source_sha256'],
            ast_nodes=inventory['ast_nodes'],current_program_hazards=inventory['current_program_hazards'],
            bridge_name_non_call_loads=inventory['bridge_name_non_call_loads'],
            target_syntax_sites=[s for s in inventory['sites'] if s['existing_helper_target']],
            syntax_does_not_prove_field_demand=True,persistent_namespace_inspected=False))
        assigned.update(members)
    if assigned!=set(target_spans):raise ValueError('executed_target_parent_missing')
    return dict(counts=dict(counts),targets=targets,target_programs=programs,
        final_unknown_state=poisoned,bounds_rejected=p.bounds_rejected,
        measured_savings=None,online_replacement_verified=False)
