"""Pure observed entity/field obligations and bounded checkpoint disclosures.

All modes share the original raw interface and passive evidence capture.
Only one bounded automatic post-checkpoint notice differs; no query is exposed. This does not issue APIs, create content,
execute generated Python, infer hidden entities, or certify official success.
"""
from copy import deepcopy
import hashlib
import json
import re

from late_obligation_monitor_p136 import (
    CONTRACT_ID, LateObligationMonitor, verify_late_obligation_sources,
)
from public_output_grounding import require

VERSION = 'late_obligation_disclosure_p136_v1'
MODES = ('raw_anchor', 'ids_only', 'entity_fields')
FIELDS = ('title', 'artists')
MAX_ENTITIES = 512
MAX_DISPLAY_ROWS = 16
MAX_QUERY_ROWS = 32
NOTICE_BYTE_LIMIT = 2048
RESPONSE_BYTE_LIMIT = 8192
NOTICE_PREFIX = '\nObserved progress at accepted checkpoint:\n'
_HEX64 = re.compile(r'[0-9a-f]{64}')


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def capture(monitor):
    require(type(monitor) is LateObligationMonitor, 'trusted_exact_monitor_required')
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


COUNT_MAX = dict(target_entities=512, complete_entities=512, pending_entities=512,
    missing_title=512, missing_artists=512, missing_artist_name_entities=512*512,
    retired_field_obligations=1024)
SELECTION_RULE = 'fixed_max_descriptor_and_mask_same_closed_pending_ID_prefix'


def snapshot_descriptor(snapshot):
    payload = validate_snapshot(snapshot)
    return {'enumeration': payload['enumeration'], 'counts': deepcopy(payload['counts']),
            'source_complete': deepcopy(payload['source_complete']),
            'required_fields': list(FIELDS), 'official_task_success_claimed': False}


def selected_prefix_length(ids, *, byte_limit=NOTICE_BYTE_LIMIT):
    """Selection depends only on this ordered ID list and the fixed budget.

    Reserve a maximal descriptor and maximal two-field row regardless of actual
    field state. Spare bytes never admit additional IDs in either arm.
    """
    require(type(byte_limit) is int and 768 <= byte_limit <= NOTICE_BYTE_LIMIT, 'notice_byte_limit')
    require(type(ids) is list and len(ids) <= MAX_ENTITIES
            and all(type(i) is int and i > 0 for i in ids)
            and ids == sorted(set(ids)), 'ordered_unique_pending_ids')
    budget = dict(kind='observed_source_progress', enumeration='closed', counts=COUNT_MAX,
        source_complete={'song':False, 'album':False, 'playlist':False},
        required_fields=list(FIELDS), official_task_success_claimed=False,
        entity_fields=[], displayed_entities=MAX_DISPLAY_ROWS, omitted_entities=MAX_ENTITIES)
    require(len(encoded(budget)) <= byte_limit, 'reserved_descriptor_budget')
    n = 0
    for sid in ids[:MAX_DISPLAY_ROWS]:
        candidate = deepcopy(budget)
        candidate['entity_fields'].append({'song_id':sid, 'missing_fields':list(FIELDS)})
        if len(encoded(candidate)) > byte_limit:
            break
        budget, n = candidate, n+1
    return n


def notice(snapshot, mode, *, byte_limit=NOTICE_BYTE_LIMIT):
    require(mode in MODES, 'mode')
    require(type(byte_limit) is int and 768 <= byte_limit <= NOTICE_BYTE_LIMIT, 'notice_byte_limit')
    payload = validate_snapshot(snapshot)
    if mode == 'raw_anchor':
        return None
    counts, rows = payload['counts'], payload['pending']
    result = {'kind':'observed_source_progress', **snapshot_descriptor(snapshot),
              'entity_fields':[], 'displayed_entities':0,
              'omitted_entities':None if counts is None else counts['pending_entities']}
    if counts is not None:
        require(payload['enumeration'] == 'closed' and type(counts) is dict
                and set(counts) == set(COUNT_MAX)
                and all(type(counts[k]) is int and 0 <= counts[k] <= bound
                        for k, bound in COUNT_MAX.items()), 'bounded_closed_counts')
        require(type(rows) is list and counts['pending_entities'] == len(rows), 'pending_count')
        require(all(type(r) is dict and type(r.get('missing_fields')) is list
                    and r['missing_fields'] in (['title'], ['artists'], list(FIELDS)) for r in rows),
                'required_missing_fields')
        n = selected_prefix_length([r['song_id'] for r in rows], byte_limit=byte_limit)
        result['entity_fields'] = [{'song_id':r['song_id'], **(
            {'missing_fields':deepcopy(r['missing_fields'])} if mode == 'entity_fields' else {})}
            for r in rows[:n]]
        result.update(displayed_entities=n, omitted_entities=len(rows)-n)
    else:
        require(payload['enumeration'] in ('open', 'unknown') and rows == [], 'unknown_open_rows_empty')
    require(set(result['source_complete']) == {'song','album','playlist'}
            and all(type(v) is bool for v in result['source_complete'].values()), 'source_complete_flags')
    require('handle' not in result and len(encoded(result)) <= byte_limit, 'bounded_handle_free_notice')
    return result


class LateFieldObligations:
    """Trusted passive evidence only: no query API and no environment calls."""
    def __init__(self, public_task, *, execution_scope, public_source_directory):
        self.contract_id = verify_late_obligation_sources(public_source_directory)
        require(self.contract_id == CONTRACT_ID, 'late_monitor_contract_identity')
        self.monitor = LateObligationMonitor(public_task, execution_scope=execution_scope)

    def observe(self, event, span):
        self.monitor.observe(event, span)

    def capture(self):
        return capture(self.monitor)

    def summary(self):
        packet = self.capture()
        return dict(version=VERSION, public_source_contract_id=self.contract_id,
            snapshot=snapshot_descriptor(packet), query_interface_exposed=False,
            taint_reasons=list(packet['payload']['taint_reasons']), official_task_success_claimed=False)


ObligationStore = LateFieldObligations


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
        require(type(store) is LateFieldObligations, 'trusted_store_required')
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
