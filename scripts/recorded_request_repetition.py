"""Describe repeated public requests without licensing cached execution.

Historical equality and an already observed value inside a conservative read
scope are separate measures. Later replies never create prior availability.
No authentication normalization, state equivalence or removable LM call is
inferred. All returned, raised and unknown requests remain in the accounting.
"""
from collections import Counter
import hashlib
import json

from field_read_contract import READ_ONLY_APIS, canonical


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def returned_payload(span):
    observation = span['observation']
    if not isinstance(observation, dict) or 'observation' not in observation or 'api_error' in observation:
        raise ValueError('returned_payload_required')
    raw = observation['observation']
    value = raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except ValueError:
            pass
    return digest(raw), digest(value), len(canonical(value).encode())


def analyze(events, spans, usage, *, max_cache_entries=512, max_value_bytes=65536):
    if (len(events) > 4000 or len(usage) > 80 or max_cache_entries < 1 or max_value_bytes < 1):
        raise ValueError('fixed_record_or_cache_bounds_exceeded')
    call_ids = [u['id'] for u in usage]
    positions = {c: i for i, c in enumerate(call_ids)}
    ids = [e['span_id'] for e in events]
    ranks = [positions.get(e.get('call'), -1) for e in events]
    if (len(positions) != len(usage) or call_ids != [f'call_{i:03d}' for i in range(1,len(usage)+1)]
            or -1 in ranks or ranks != sorted(ranks) or len(ids) != len(set(ids))
            or set(ids) != set(spans)):
        raise ValueError('complete_chronological_records_required')
    counts, names = Counter(), Counter()
    by_call = {cid: Counter() for cid in call_ids}
    history, cache, conflicting = {}, {}, set()
    epoch = barriers = 0
    poisoned = False
    rows = []
    for ordinal, event in enumerate(events,1):
        if type(event.get('api_request_sent')) is not bool:
            raise ValueError('explicit_send_status_required')
        if not event['api_request_sent']:
            if event.get('effects_unknown'):
                poisoned = True; cache.clear(); conflicting.clear()
                epoch += 1; barriers += 1; counts['nonsent_unknown_effect_barriers'] += 1
            continue
        receipt = event.get('api_execution')
        if (event.get('stage') != 'python_api' or not isinstance(receipt,dict)
                or receipt.get('bridge_request_sent') is not True
                or receipt.get('automatic_retries') != 0
                or receipt.get('status') not in {'returned','raised','unknown'}):
            raise ValueError('single_typed_API_receipt_required')
        span = spans[event['span_id']]
        action = span['action']; name = action.get('name'); args = action.get('arguments')
        if isinstance(args,str): args = json.loads(args)
        if type(name) is not str or name.count('__') != 1 or type(args) is not dict:
            raise ValueError('complete_structured_request_required')
        key = digest({'name':name,'arguments':args})
        status = receipt['status']; previous = history.get(key)
        between = barriers - previous['after_barrier'] if previous else None
        read_scope = name in READ_ONLY_APIS
        if not read_scope:
            epoch += 1; barriers += 1; cache.clear(); conflicting.clear()
            counts['nonread_scope_barriers'] += 1
        prior = cache.get(key) if read_scope and not poisoned and key not in conflicting else None
        # Availability is captured before consulting the current returned value.
        before = ('unknown_state' if poisoned else 'outside_read_scope' if not read_scope
                  else 'conflicting_or_failed_read' if key in conflicting
                  else 'prior_success' if prior else 'absent')
        confirmed = status == 'returned' and not event.get('effects_unknown')
        raw_hash, value_hash, value_bytes = returned_payload(span) if confirmed else (None,None,None)
        both_returned = bool(previous and previous['confirmed_return']) and confirmed
        counts['sent_requests'] += 1; names[name] += 1; counts['receipt_'+status] += 1
        by_call[event['call']]['sent_requests'] += 1
        if previous:
            counts['repeated_requests'] += 1; by_call[event['call']]['repeated_requests'] += 1
            counts['repeated_with_barriers' if between else 'repeated_without_intervening_barriers'] += 1
            if previous['call_id'] != event['call']: counts['repeated_across_model_boundaries'] += 1
        if both_returned:
            counts['repeated_returned_pairs'] += 1
            counts['repeated_payload_equal' if raw_hash==previous['payload_sha256'] else 'repeated_payload_different'] += 1
            counts['repeated_value_equal' if value_hash==previous['value_sha256'] else 'repeated_value_different'] += 1
        if prior:
            counts['prior_success_inside_read_scope'] += 1
            by_call[event['call']]['prior_success_inside_read_scope'] += 1
            counts['prior_success_confirmed' if confirmed and value_hash==prior['value_sha256'] else 'prior_success_not_confirmed'] += 1
        row = dict(request_ordinal=counts['sent_requests'],event_ordinal=ordinal,call_id=event['call'],
            api_name=name,request_sha256=key,receipt_status=status,effects_unknown=bool(event.get('effects_unknown')),
            previous_request_ordinal=previous['request_ordinal'] if previous else None,
            previous_call_id=previous['call_id'] if previous else None,
            previous_receipt_status=previous['receipt_status'] if previous else None,
            intervening_barriers=between,within_declared_read_scope=read_scope,scope_epoch=epoch,
            prior_status=before,prior_success_request_ordinal=prior['request_ordinal'] if prior else None,
            repeated_payload_equal=(raw_hash==previous['payload_sha256']) if both_returned else None,
            repeated_value_equal=(value_hash==previous['value_sha256']) if both_returned else None,
            current_matches_prior_read_value=(confirmed and value_hash==prior['value_sha256']) if prior else None,
            current_returned_value_bytes=value_bytes,online_cache_permission=False,avoided_API_established=False)
        rows.append(row)
        if status=='unknown' or event.get('effects_unknown'):
            poisoned=True;cache.clear();conflicting.clear()
            if read_scope: epoch+=1;barriers+=1
            counts['unknown_effect_requests']+=1
        elif read_scope and not poisoned:
            if status=='raised':
                cache.pop(key,None);conflicting.add(key)
            elif key not in conflicting:
                old=cache.get(key)
                if old and old['value_sha256']!=value_hash:
                    cache.pop(key,None);conflicting.add(key);counts['read_value_conflicts']+=1
                elif value_bytes>max_value_bytes or (not old and len(cache)>=max_cache_entries):
                    counts['cache_bounds_rejected']+=1
                elif not old:
                    cache[key]=dict(request_ordinal=counts['sent_requests'],value_sha256=value_hash)
        history[key]=dict(request_ordinal=counts['sent_requests'],call_id=event['call'],receipt_status=status,
            confirmed_return=confirmed,payload_sha256=raw_hash,value_sha256=value_hash,after_barrier=barriers)
    calls=[]
    for cid in call_ids:
        c=by_call[cid]; sent=c['sent_requests']
        calls.append(dict(call_id=cid,sent_requests=sent,repeated_requests=c['repeated_requests'],
            prior_success_inside_read_scope=c['prior_success_inside_read_scope'],
            all_sent_requests_historical_repeats=sent>0 and sent==c['repeated_requests'],
            removable_generation_established=False))
    return dict(counts=dict(counts),api_names=dict(sorted(names.items())),requests=rows,model_boundaries=calls,
        final_unknown_state=poisoned,read_scope_apis=sorted(READ_ONLY_APIS),
        measured_API_savings=None,measured_token_savings=None,removable_generations=None,
        online_replacement_verified=False,task_quality_measured=False,
        scope='Posthoc public request/reply equality and prior success inside six previously declared read handlers. No future response grants prior availability. No cache execution or intent equivalence is proved.')
