"""Pure observed entity/field obligations and bounded checkpoint disclosures.

The two disclosure policies share all evidence and explicit query capabilities.
Only automatic presentation differs. This does not issue APIs, create content,
execute generated Python, infer hidden entities, or certify official success.
"""
from copy import deepcopy
import hashlib
import json
import re

from partitioned_export_monitor import (
    CONTRACT_ID, PartitionedExportMonitor, verify_partitioned_export_sources,
)
from public_output_grounding import require

VERSION = 'observed_public_field_obligations_v1'
MODES = ('raw_anchor', 'counts_only', 'entity_fields')
FIELDS = ('title', 'artists')
MAX_ENTITIES = 512
MAX_DISPLAY_ROWS = 16
MAX_QUERY_ROWS = 32
NOTICE_BYTE_LIMIT = 2048
RESPONSE_BYTE_LIMIT = 8192
NOTICE_PREFIX = '\nObserved progress at accepted checkpoint:\n'
_HEX64 = re.compile(r'[0-9a-f]{64}')


class ObligationQueryError(ValueError):
    """Caller-controlled query shape/range error; no source contract failure."""


def query_require(condition, reason):
    if not condition:
        raise ObligationQueryError(reason)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def capture(monitor):
    require(type(monitor) is PartitionedExportMonitor, 'trusted_exact_monitor_required')
    evidence, wanted, metadata = monitor.source_state()
    taints = sorted(monitor.taints)
    enumeration = ('unknown' if taints else
                   'closed' if all(evidence['source_complete'].values()) else 'open')
    rows = []
    if enumeration == 'closed':
        require(len(wanted) <= MAX_ENTITIES, 'entity_bound')
        for sid in sorted(wanted):
            missing = []
            if sid not in monitor.songs and sid not in monitor.song_parts:
                missing.append('title')
            if sid not in metadata:
                missing.append('artists')
            if missing:
                references = monitor.song_parts.get(sid, (None, ()))[1]
                rows.append({'song_id': sid, 'missing_fields': missing,
                             'observed_artist_ids_without_names': sorted(set(
                                 aid for aid in references if aid not in monitor.artists))})
    counts = None if enumeration != 'closed' else {
        'target_entities': len(wanted), 'complete_entities': len(wanted & metadata.keys()),
        'pending_entities': len(rows),
        'missing_title': sum('title' in row['missing_fields'] for row in rows),
        'missing_artists': sum('artists' in row['missing_fields'] for row in rows),
        'missing_artist_name_entities': len({aid for row in rows for aid in row['observed_artist_ids_without_names']}),
        'retired_field_obligations': 2*len(wanted)-sum(len(row['missing_fields']) for row in rows),
    }
    payload = {
        'version': VERSION, 'public_source_contract_id': CONTRACT_ID,
        'execution_scope_sha256': monitor.execution_scope_sha256,
        'requirement_sha256': monitor.requirement_sha256,
        'evidence_sha256': evidence['source_evidence_sha256'],
        'enumeration': enumeration, 'taint_reasons': taints,
        'source_complete': dict(evidence['source_complete']),
        'counts': counts, 'pending': rows,
        'all_required_fields_observed': enumeration == 'closed' and not rows,
        'official_task_success_claimed': False,
    }
    return {'payload': payload, 'sha256': digest(payload)}


def validate_snapshot(snapshot):
    require(type(snapshot) is dict and set(snapshot) == {'payload', 'sha256'}, 'snapshot_shape')
    payload = snapshot['payload']
    require(type(payload) is dict and payload.get('version') == VERSION
            and payload.get('public_source_contract_id') == CONTRACT_ID, 'snapshot_contract')
    require(type(snapshot['sha256']) is str and _HEX64.fullmatch(snapshot['sha256'])
            and snapshot['sha256'] == digest(payload), 'snapshot_hash')
    return payload


def snapshot_descriptor(snapshot):
    payload = validate_snapshot(snapshot)
    return {'handle': snapshot['sha256'], 'enumeration': payload['enumeration'],
            'counts': deepcopy(payload['counts']), 'source_complete': deepcopy(payload['source_complete']),
            'required_fields': list(FIELDS), 'official_task_success_claimed': False}


def notice(snapshot, mode, *, byte_limit=NOTICE_BYTE_LIMIT):
    require(mode in MODES, 'mode')
    require(type(byte_limit) is int and 768 <= byte_limit <= NOTICE_BYTE_LIMIT, 'notice_byte_limit')
    payload = validate_snapshot(snapshot)
    if mode == 'raw_anchor':
        return None
    counts = payload['counts']
    result = {'kind': 'observed_source_progress', **snapshot_descriptor(snapshot),
              'entity_fields': [], 'displayed_entities': 0,
              'omitted_entities': None if counts is None else counts['pending_entities']}
    require(len(encoded(result)) <= byte_limit, 'base_notice_budget')
    if mode == 'entity_fields' and counts is not None:
        for row in payload['pending'][:MAX_DISPLAY_ROWS]:
            proposed = deepcopy(result)
            proposed['entity_fields'].append({'song_id': row['song_id'], 'missing_fields': row['missing_fields']})
            proposed['displayed_entities'] += 1
            proposed['omitted_entities'] -= 1
            if len(encoded(proposed)) > byte_limit:
                break
            result = proposed
    return result


class ObservedFieldObligations:
    """One execution's trusted evidence; fresh query does not dispatch any API."""
    def __init__(self, public_task, *, execution_scope, public_source_directory):
        self.contract_id = verify_partitioned_export_sources(public_source_directory)
        require(self.contract_id == CONTRACT_ID, 'partition_contract_identity')
        self.monitor = PartitionedExportMonitor(public_task, execution_scope=execution_scope)
        self.query_counts = {'snapshot': 0, 'page': 0, 'stale': 0}

    def observe(self, event, span):
        self.monitor.observe(event, span)

    def capture(self):
        return capture(self.monitor)

    def query(self, *, op, handle, cursor, limit):
        query_require(type(op) is str and op in ('snapshot', 'page'), 'query_op')
        query_require(type(cursor) is int and cursor >= 0, 'query_cursor')
        query_require(type(limit) is int and 1 <= limit <= MAX_QUERY_ROWS, 'query_limit')
        query_require((op == 'snapshot' and handle is None and cursor == 0)
                or (op == 'page' and type(handle) is str and _HEX64.fullmatch(handle)), 'query_handle')
        current = self.capture()
        payload = current['payload']
        descriptor = snapshot_descriptor(current)
        self.query_counts[op] += 1
        if op == 'snapshot':
            result = {'status': 'snapshot', 'snapshot': descriptor, 'rows': [],
                      'total': None if payload['counts'] is None else payload['counts']['pending_entities'],
                      'next_cursor': None, 'complete_page': False}
        elif handle != current['sha256']:
            self.query_counts['stale'] += 1
            result = {'status': 'stale_snapshot', 'snapshot': descriptor, 'rows': [],
                      'total': None, 'next_cursor': None, 'complete_page': False}
        elif payload['enumeration'] != 'closed':
            result = {'status': payload['enumeration'], 'snapshot': descriptor, 'rows': [],
                      'total': None, 'next_cursor': None, 'complete_page': False}
        else:
            rows = payload['pending']
            query_require(cursor <= len(rows), 'query_cursor_outside_snapshot')
            result = {'status': 'known', 'snapshot': descriptor, 'rows': [],
                      'total': len(rows), 'next_cursor': cursor if cursor < len(rows) else None,
                      'complete_page': cursor == len(rows)}
            for row in rows[cursor:cursor+limit]:
                candidate = deepcopy(result)
                candidate['rows'].append(deepcopy(row))
                next_cursor = cursor+len(candidate['rows'])
                candidate['next_cursor'] = next_cursor if next_cursor < len(rows) else None
                candidate['complete_page'] = next_cursor == len(rows)
                if len(encoded(candidate)) > RESPONSE_BYTE_LIMIT:
                    break
                result = candidate
            require(bool(result['rows']) or cursor == len(rows), 'query_row_exceeds_response_budget')
        require(len(encoded(result)) <= RESPONSE_BYTE_LIMIT, 'query_response_budget')
        return result

    def summary(self):
        snapshot = self.capture()
        return {'version': VERSION, 'public_source_contract_id': self.contract_id,
                'snapshot': snapshot_descriptor(snapshot), 'query_counts': deepcopy(self.query_counts),
                'taint_reasons': list(snapshot['payload']['taint_reasons']),
                'official_task_success_claimed': False}


ObligationStore = ObservedFieldObligations


class CheckpointDisclosure:
    """Capture once after acceptance; transient next actor, never archive/focus."""
    def __init__(self, mode, *, byte_limit=NOTICE_BYTE_LIMIT):
        require(mode in MODES, 'mode')
        require(type(byte_limit) is int and 768 <= byte_limit <= NOTICE_BYTE_LIMIT, 'notice_byte_limit')
        self.mode, self.byte_limit = mode, byte_limit
        self.last_revision, self.pending, self.captures, self.submitted = 0, None, 0, 0
        self.store = None
        self.scope_identity = None

    def prepare(self, store, revision, *, accepted):
        require(type(store) is ObservedFieldObligations, 'trusted_store_required')
        require(type(accepted) is bool, 'accepted_bool')
        require(type(revision) is int and revision > 0, 'revision')
        if not accepted:
            return self.prepare_packet(None, revision, accepted=False)
        require(revision > self.last_revision and self.pending is None, 'revision_or_pending')
        result = self.prepare_packet(store.capture(), revision, accepted=True)
        self.store = store
        return result

    def prepare_packet(self, packet, revision, *, accepted):
        """Install one trusted runtime capture, without another source capture.

        The caller must bind this packet to its recorded source boundary and
        verify that boundary before count/send. This method validates identity
        and packet integrity; it does not reauthenticate source observations.
        """
        require(type(accepted) is bool, 'accepted_bool')
        require(type(revision) is int and revision > 0, 'revision')
        if not accepted:
            return None
        require(revision > self.last_revision and self.pending is None, 'revision_or_pending')
        payload = validate_snapshot(packet)
        identity = (payload['execution_scope_sha256'], payload['requirement_sha256'],
                    payload['public_source_contract_id'])
        require(self.scope_identity is None or identity == self.scope_identity,
                'checkpoint_disclosure_scope_changed')
        self.scope_identity = identity
        self.pending = deepcopy(packet)
        self.last_revision, self.store = revision, None
        self.captures += 1
        return deepcopy(self.pending)

    def actor_view(self, messages):
        require(type(messages) is list and messages and type(messages[0]) is dict
                and messages[0].get('role') == 'system' and type(messages[0].get('content')) is str,
                'ordinary_system_message_required')
        result = deepcopy(messages)
        if self.pending is not None:
            if self.store is not None:
                require(self.store.capture()['sha256'] == self.pending['sha256'],
                        'capture_boundary_changed_before_actor')
            body = notice(self.pending, self.mode, byte_limit=self.byte_limit)
            if body is not None:
                result[0]['content'] += NOTICE_PREFIX + encoded(body).decode('utf-8')
        return result

    def model_submitted(self, *, attempted):
        require(type(attempted) is bool, 'attempted_bool')
        if attempted and self.pending is not None:
            if self.mode != 'raw_anchor':
                self.submitted += 1
            self.pending = None
