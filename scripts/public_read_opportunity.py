"""Chronological availability under the existing contract, not a savings oracle.

Only previously returned responses enter the real candidate's provider. A later
response can confirm or contradict that prior value, never create a prior hit.
No saved Python or API is executed, and Python liveness is not inferred.
"""
from collections import Counter
import hashlib
import json

from field_read_contract import (CONTRACT_ID, FIELDS, READ_ONLY_APIS, SOURCE, TARGET,
                                 canonical, target_identity, valid_field)
from public_contract_read_views import PublicReadAuthority


def public_value(span):
    observation = span['observation']
    if 'observation' not in observation or 'api_error' in observation:
        raise ValueError('returned_API_value_missing')
    value = observation['observation']
    if isinstance(value, str):
        try: value = json.loads(value)
        except ValueError: pass
    return value


def analyze(events, spans, usage, *, execution_scope):
    if len(events) > 4000 or len(usage) > 80:
        raise ValueError('fixed_record_bound_exceeded')
    positions = {u['id']: i for i, u in enumerate(usage)}
    ids = [e['span_id'] for e in events]
    ranks = [positions.get(e['call'], -1) for e in events]
    if (len(positions) != len(usage) or -1 in ranks or ranks != sorted(ranks)
            or len(ids) != len(set(ids)) or set(ids) != set(spans)):
        raise ValueError('complete_chronological_records_required')
    provider = PublicReadAuthority(execution_scope, verified_contract=CONTRACT_ID)
    epoch = 0
    poisoned = False
    rows = []
    counts = Counter()
    api_names = Counter()
    for ordinal, event in enumerate(events, 1):
        if not event['api_request_sent']:
            if event.get('effects_unknown'):
                poisoned = True
                provider.cache.invalidate()
            continue
        if event['stage'] != 'python_api':
            raise ValueError('sent_API_outside_python_receipt')
        receipt = event.get('api_execution')
        if (not isinstance(receipt, dict) or receipt.get('bridge_request_sent') is not True
                or receipt.get('automatic_retries') != 0
                or receipt.get('status') not in {'returned', 'raised', 'unknown'}):
            raise ValueError('one_typed_receipt_per_sent_request_required')
        span = spans[event['span_id']]
        action = span['action']
        name = action.get('name')
        args = action.get('arguments')
        if isinstance(args, str): args = json.loads(args)
        if not isinstance(name, str) or name.count('__') != 1 or not isinstance(args, dict):
            raise ValueError('documented_action_shape_required')
        app, api = name.split('__')
        call = dict(app=app, api=api, args=args)
        counts['sent_requests'] += 1
        counts['receipt_' + receipt['status']] += 1
        api_names[name] += 1
        if name not in READ_ONLY_APIS:
            provider.cache.invalidate()
            epoch += 1
            counts['conservative_invalidations'] += 1
        found = provider.lookup(call, epoch) if name == TARGET and not poisoned else None
        before = 'unknown_state' if poisoned else found[0] if found else 'absent'
        confirmed = receipt['status'] == 'returned' and not event.get('effects_unknown')
        value = public_value(span) if confirmed and name in (SOURCE, TARGET) else None
        if name == TARGET:
            supported = (target_identity(name, args) is not None and confirmed and type(value) is dict
                         and type(value.get('song_id')) is int
                         and value['song_id'] == args.get('song_id')
                         and all(k in value and valid_field(k, value[k]) for k in FIELDS))
            match = None
            if found is not None:
                match = bool(supported and (canonical(value) == canonical(found[1])
                    if found[0] == 'complete' else all(
                        k in value and canonical(value[k]) == canonical(v) for k, v in found[1].items())))
            rows.append(dict(event_ordinal=ordinal, call_id=event['call'],
                request_sha256=hashlib.sha256(canonical(call).encode()).hexdigest(),
                authority_before=before, receipt_status=receipt['status'],
                response_supported=bool(supported), prior_value_matches_returned=match,
                field_demand_known=False, reference_lifetime_known=False,
                avoided_request_established=False))
            counts['target_requests'] += 1
            counts['before_' + before] += 1
            if found is not None:
                counts['prior_value_confirmed' if match else 'prior_value_not_confirmed'] += 1
        if receipt['status'] == 'unknown' or event.get('effects_unknown'):
            poisoned = True
            provider.cache.invalidate()
        if confirmed and not poisoned and name in (SOURCE, TARGET):
            provider.observe(call, value, epoch)
            counts['source_responses_observed' if name == SOURCE else 'target_responses_observed'] += 1
    return dict(counts=dict(counts), api_names=dict(sorted(api_names.items())), targets=rows,
        final_unknown_state=poisoned, cache_bounds_rejected=provider.cache.bounds_rejected,
        measured_savings=None, removable_model_generations=None,
        future_field_demand_inferred=False, online_replacement_verified=False)
