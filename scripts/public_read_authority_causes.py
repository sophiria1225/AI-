"""Explain missing authority using prior observations, never grant stale reuse.

P89's frozen availability rows remain the authority classification. This module
adds a historical index solely to distinguish absent observations from erased
ones. Later responses can check agreement but cannot create an earlier grant.
"""
from collections import Counter, defaultdict
import hashlib
import json

from field_read_contract import (CONTRACT_ID, FIELDS, READ_ONLY_APIS, SOURCE,
                                 TARGET, canonical, target_identity, valid_field)
from public_contract_read_views import PublicReadAuthority
from public_read_opportunity import public_value


def analyze(events, spans, usage, expected_targets):
    if len(events) > 4000 or len(usage) > 80:
        raise ValueError('fixed_record_bound_exceeded')
    positions = {u['id']: i for i, u in enumerate(usage)}
    ids = [e['span_id'] for e in events]
    ranks = [positions.get(e['call'], -1) for e in events]
    if (len(positions) != len(usage) or -1 in ranks or ranks != sorted(ranks)
            or len(ids) != len(set(ids)) or set(ids) != set(spans)):
        raise ValueError('complete_chronological_records_required')
    expected = {t['event_ordinal']: t for t in expected_targets}
    if len(expected) != len(expected_targets):
        raise ValueError('duplicate_frozen_target')
    history = defaultdict(list)
    barriers = []
    targets = []
    counts = Counter()
    indexed = 0
    for ordinal, event in enumerate(events, 1):
        if not event['api_request_sent']:
            if event.get('effects_unknown'):
                barriers.append(dict(event_ordinal=ordinal, api=None,
                                     receipt_status='unsent_unknown_effect'))
            continue
        receipt = event.get('api_execution')
        if (event['stage'] != 'python_api' or not isinstance(receipt, dict)
                or receipt.get('bridge_request_sent') is not True
                or receipt.get('automatic_retries') != 0
                or receipt.get('status') not in {'returned', 'raised', 'unknown'}):
            raise ValueError('one_typed_receipt_per_sent_request_required')
        span = spans[event['span_id']]
        action = span['action']
        name, args = action.get('name'), action.get('arguments')
        if isinstance(args, str): args = json.loads(args)
        if not isinstance(name, str) or name.count('__') != 1 or not isinstance(args, dict):
            raise ValueError('documented_action_shape_required')
        app, api = name.split('__')
        call = dict(app=app, api=api, args=args)
        counts['sent_requests'] += 1
        counts['receipt_' + receipt['status']] += 1
        if name not in READ_ONLY_APIS:
            barriers.append(dict(event_ordinal=ordinal, api=name, receipt_status=receipt['status']))
            counts['conservative_invalidations'] += 1
        known = receipt['status'] == 'returned' and not event.get('effects_unknown')
        value = public_value(span) if known and name in (SOURCE, TARGET) else None
        identity = target_identity(name, args)
        if name == TARGET:
            original = expected.get(ordinal)
            request_hash = hashlib.sha256(canonical(call).encode()).hexdigest()
            if (original is None or original['request_sha256'] != request_hash
                    or original['call_id'] != event['call']
                    or original['receipt_status'] != receipt['status']):
                raise ValueError('frozen_P89_target_changed')
            prior = history.get(identity, []) if identity is not None else []
            eligible = [r for r in prior if r['individually_eligible']]
            latest = eligible[-1] if eligible else None
            between = ([b.copy() for b in barriers if b['event_ordinal'] > latest['ordinal']]
                       if latest else [])
            before = original['authority_before']
            if before != 'absent':
                reason = 'original_' + before
            elif identity is None:
                reason = 'unsupported_target_identity'
            elif latest and between:
                reason = 'previous_eligible_observation_invalidated'
            elif latest:
                reason = 'previous_eligible_observation_but_no_current_grant'
            elif prior:
                reason = 'previous_records_not_individually_eligible'
            else:
                reason = 'target_not_previously_observed_in_current_sources'
            equal = None
            if latest and known and type(value) is dict:
                equal = all(k in value and valid_field(k, value[k])
                            and canonical(v) == canonical(value[k])
                            for k, v in latest['fields'].items())
            targets.append(dict(**original, missing_authority_reason=reason,
                prior_source_records=sum(r['kind'] == 'library' for r in prior),
                prior_complete_records=sum(r['kind'] == 'detail' for r in prior),
                prior_individually_eligible_records=len(eligible),
                prior_valid_fields=sorted({k for r in prior for k in r['fields']}),
                latest_eligible_ordinal=latest['ordinal'] if latest else None,
                latest_eligible_kind=latest['kind'] if latest else None,
                invalidating_operations_since=between,
                latest_prior_fields_equal_later_response=equal,
                historical_values_are_authority=False,
                effect_exemption_established=False))
            counts['target_requests'] += 1
            counts['reason_' + reason] += 1
        if receipt['status'] == 'unknown' or event.get('effects_unknown'):
            if name in READ_ONLY_APIS:
                barriers.append(dict(event_ordinal=ordinal, api=name, receipt_status='unknown_effect'))
            counts['unknown_effect_events'] += 1
        if not known or name not in (SOURCE, TARGET):
            continue
        # A fresh provider checks whether this one response could support a read
        # in its own revision. It never supplies the actual authority decision.
        isolated = PublicReadAuthority('historical-record-only', verified_contract=CONTRACT_ID)
        isolated.observe(call, value, 0)
        records = value if name == SOURCE and type(value) is list else [value] if name == TARGET else []
        for record in records:
            if (type(record) is not dict or type(record.get('song_id')) is not int
                    or record['song_id'] <= 0):
                continue
            sid = record['song_id']
            target = dict(app='spotify', api='show_song', args={'song_id':sid})
            grant = isolated.lookup(target, 0)
            indexed += 1
            if indexed > 8192:
                raise ValueError('fixed_historical_record_bound_exceeded')
            history[sid].append(dict(ordinal=ordinal, kind='library' if name == SOURCE else 'detail',
                individually_eligible=grant is not None,
                fields={k:record[k] for k in FIELDS if k in record and valid_field(k, record[k])}))
    if {t['event_ordinal'] for t in targets} != set(expected):
        raise ValueError('frozen_P89_target_omitted')
    return dict(counts=dict(counts), targets=targets, historical_records=indexed,
        measured_savings=None, new_authorities_granted=0,
        future_field_demand_inferred=False, online_replacement_verified=False)
