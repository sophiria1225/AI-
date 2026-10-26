"""Synthetic-only ordinary receipt disclosure; no dispatch or live integration.

The host supplies closed records, never a model-supplied eligibility claim.
Only one unpaged, confirmed run_python turn is eligible. All other display
fields and the full archive remain literal. This is not a success certificate.
"""
from collections import Counter
from copy import copy, deepcopy
from dataclasses import dataclass
import hashlib
import json

from compact_api_receipts import decode_receipts
from context_preservation import compact
from native_conversation import recover_turn
from protocol_stable_history import StableReferenceConversation
from receipt_reasoning_history import digest, execution_evidence, require


MODES = ('full', 'disclose')
FORMAT = 'archived_receipt_index_v1'
SHARED_GUIDE = '''
run_python's api_receipts is either the complete table
{"columns":["span_id","api","api_request_sent"],"rows":[[span_id,api,true],...]}
or {"format":"archived_receipt_index_v1","span_id":outer_span_id,"receipt_rows":N}.
The latter references the unchanged outer archive record. Use the existing
read_span with that span_id and its original character offsets to obtain the
table; its inner span IDs retrieve the original API records. An archive read
is an additional tool action, with its usual model input, output and time costs.
The reference certifies neither API semantic success nor task completion.
stdout, errors, API counts and budget notices keep their existing meanings.
'''
_OBS_FIELDS = {'status', 'stdout', 'stdout_truncated', 'api_requests',
               'declared_complete', 'unknown_effects', 'api_receipts', 'error'}


@dataclass(frozen=True)
class _RecordedTurn:
    start: int
    stop: int
    messages_sha256: str
    source_json: str
    source_sha256: str


def _text_sha256(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _decision(source, messages, page_limit):
    """Derive eligibility from closed host records; never accept an eligibility bit."""
    reasons = set()
    events, archive = source['events'], source['archive']
    spans = source['outer_spans']
    meta = {'eligible': False, 'reasons': [], 'receipt_rows': 0,
            'table_bytes': 0, 'reference_bytes': 0,
            'semantic_success_certified': False, 'task_quality_established': False}
    if events is None:
        meta['reasons'] = ['trusted_turn_evidence_missing']
        return meta, None
    require(type(events) is list and len(events) <= 4000, 'bounded_host_events_required')
    require(type(archive) is dict, 'host_archive_mapping_required')
    ids = []
    for event in events:
        require(type(event) is dict and type(event.get('span_id')) is str
                and bool(event['span_id']), 'host_event_identity_required')
        require(type(event.get('call')) is str and bool(event['call'])
                and event.get('stage') in ('model_tool', 'python_api')
                and type(event.get('api_request_sent')) is bool,
                'host_event_types_required')
        require(type(event.get('effects_unknown', False)) is bool,
                'host_effect_flag_required')
        ids.append(event['span_id'])
    require(len(ids) == len(set(ids)) and set(ids) == set(archive),
            'complete_turn_record_mapping')
    require(len({event['call'] for event in events}) <= 1, 'one_model_turn_required')
    require(all(type(row) is dict and row.get('id') == sid
                for sid, row in archive.items()), 'archive_ID_binding_changed')
    outers = [event for event in events if event['stage'] == 'model_tool']
    require([event['span_id'] for event in outers] == [span['id'] for span in spans],
            'ordered_outer_binding_changed')
    require(all(archive[span['id']] == span for span in spans), 'outer_archive_binding_changed')
    calls = messages[0].get('tool_calls') or []
    if len(calls) != 1 or len(spans) != 1:
        reasons.add('single_native_python_turn_required')
    elif calls[0]['function']['name'] != 'run_python':
        reasons.add('single_native_python_turn_required')
    else:
        try:
            args = json.loads(calls[0]['function']['arguments'])
        except (ValueError, TypeError):
            args = None
        if (type(args) is not dict or set(args) != {'code', 'span_ids'}
                or type(args['code']) is not str or not 0 < len(args['code']) <= 20000
                or type(args['span_ids']) is not list or len(args['span_ids']) > 160
                or any(type(sid) is not str for sid in args['span_ids'])
                or len(args['span_ids']) != len(set(args['span_ids']))):
            reasons.add('ordinary_python_arguments_required')
    if reasons:
        meta['reasons'] = sorted(reasons)
        return meta, None
    outer = spans[0]
    obs = outer['observation']
    if type(obs) is not dict or set(obs) != _OBS_FIELDS:
        meta['reasons'] = ['supported_outer_observation_required']
        return meta, None
    try:
        receipts = decode_receipts(obs.get('api_receipts'))
    except ValueError:
        meta['reasons'] = ['supported_compact_receipt_table_required']
        return meta, None
    decoded = deepcopy(archive)
    decoded[outer['id']]['observation']['api_receipts'] = receipts
    require([row['span_id'] for row in receipts] ==
            [event['span_id'] for event in events if event['stage'] == 'python_api'],
            'ordered_inner_receipt_binding_changed')
    evidence = execution_evidence(events, decoded, pending_reads=source['pending_reads'])
    reasons.update(evidence['reasons'])
    # The older validator covers transport outcomes and links. This narrower
    # control also requires explicit flags and rejects unknown outer shapes.
    if (obs.get('status') != 'ok' or type(obs.get('stdout')) is not str
            or obs.get('stdout_truncated') is not False
            or obs.get('unknown_effects') is not False
            or type(obs.get('declared_complete')) is not bool
            or type(obs.get('api_requests')) is not int
            or obs.get('error') is not None):
        reasons.add('explicit_normal_outer_result_required')
    if len(compact(outer)) > page_limit or len(compact(recover_turn(messages)[0])) > page_limit:
        reasons.add('raw_outer_requires_paging')
    reference = {'format': FORMAT, 'span_id': outer['id'], 'receipt_rows': len(receipts)}
    for span in (deepcopy(outer), recover_turn(messages)[0]):
        span['observation']['api_receipts'] = deepcopy(reference)
        if len(compact(span)) > page_limit:
            reasons.add('reference_outer_requires_paging')
    meta.update(receipt_rows=len(receipts), table_bytes=len(compact(obs['api_receipts']).encode()),
                reference_bytes=len(compact(reference).encode()))
    if meta['reference_bytes'] >= meta['table_bytes']:
        reasons.add('reference_not_strictly_shorter_in_UTF8_bytes')
    meta.update(eligible=not reasons, reasons=sorted(reasons))
    return meta, reference if not reasons else None


class ReceiptDisclosureConversation(StableReferenceConversation):
    """Append-only raw history plus a deterministic, fixed-from-first-display view.

    `append_recorded` is a trusted host boundary, not a model tool. Its archive
    argument contains exactly this closed turn's records. It cannot authenticate
    a malicious host. Missing evidence uses the unchanged full display. A source
    contradiction raises before appending; callers must retain their raw records.
    """
    def __init__(self, system_prompt, task, *, execution_scope, mode='disclose', page_limit=24000):
        require(mode in MODES, 'fixed_receipt_mode_required')
        require(type(page_limit) is int and page_limit > 0, 'fixed_positive_page_limit_required')
        require(type(execution_scope) is str and bool(execution_scope), 'host_execution_scope_required')
        super().__init__(system_prompt + SHARED_GUIDE, task)
        self._mode, self._page_limit = mode, page_limit
        self._execution_scope = execution_scope
        self._configuration = (mode, page_limit, execution_scope)
        self._initial_sha256 = digest(self._messages)
        self._turns = ()
        self._archive = {}

    def append(self, response, spans):
        """Without closed host evidence, retain the full ordinary representation."""
        self.append_recorded(response, spans)

    def append_recorded(self, response, spans, *, events=None, archive_spans=None,
                        pending_reads=0):
        require(type(pending_reads) is int and pending_reads >= 0,
                'explicit_pending_read_count_required')
        require((events is None) == (archive_spans is None), 'paired_host_records_required')
        # Validate and build the complete turn on an isolated ordinary instance.
        # This keeps failed bindings from partially appending live history.
        trial = copy(self)
        trial._messages = deepcopy(self._messages)
        trial._call_ids, trial._span_ids = set(self._call_ids), set(self._span_ids)
        StableReferenceConversation.append(trial, response, spans)
        start, stop = len(self._messages), len(trial._messages)
        segment = trial._messages[start:stop]
        archive = deepcopy(archive_spans if archive_spans is not None
                           else {span['id']: span for span in spans})
        require(not set(archive) & set(self._archive), 'archival_span_ID_reuse')
        source = deepcopy({'events': events, 'archive': archive,
                           'outer_spans': spans, 'pending_reads': pending_reads,
                           'execution_scope': self._execution_scope,
                           'initial_messages_sha256': self._initial_sha256,
                           'raw_span_text_sha256': {
                               sid: _text_sha256(compact(row)) for sid, row in archive.items()}})
        _decision(source, segment, self._page_limit)
        # Raw page_span coordinates depend on insertion order, not canonical
        # dict equality. Preserve that order in the owned source as well.
        source_json = json.dumps(source, separators=(',', ':'),
                                 ensure_ascii=False, allow_nan=False)
        entry = _RecordedTurn(start, stop, digest(segment), source_json, _text_sha256(source_json))
        self._messages, self._call_ids, self._span_ids = trial._messages, trial._call_ids, trial._span_ids
        self._archive.update(archive)
        self._turns += (entry,)

    def archive(self):
        """A copy of original records, suitable for the existing page_span helper."""
        self._view()  # Refuse a changed raw coordinate system before returning it.
        return deepcopy(self._archive)

    def _view(self):
        require((self._mode, self._page_limit, self._execution_scope) == self._configuration,
                'receipt_configuration_changed')
        require(digest(self._messages[:2]) == self._initial_sha256, 'initial_messages_changed')
        visible = deepcopy(self._messages)
        sidecar = []
        expected_start, archival_ids = 2, set()
        for turn, entry in enumerate(self._turns, 1):
            require(entry.start == expected_start and entry.start < entry.stop <= len(self._messages),
                    'recorded_turn_coverage_changed')
            expected_start = entry.stop
            source = json.loads(entry.source_json)
            require(_text_sha256(entry.source_json) == entry.source_sha256, 'trusted_sidecar_source_changed')
            require(source['execution_scope'] == self._execution_scope
                    and source['initial_messages_sha256'] == self._initial_sha256,
                    'trusted_sidecar_scope_changed')
            segment = self._messages[entry.start:entry.stop]
            require(digest(segment) == entry.messages_sha256, 'recorded_turn_messages_changed')
            require(all(self._archive.get(sid) == row for sid, row in source['archive'].items()),
                    'archival_record_changed')
            require(set(source['raw_span_text_sha256']) == set(source['archive']) and all(
                _text_sha256(compact(row)) == source['raw_span_text_sha256'][sid]
                == _text_sha256(compact(self._archive[sid]))
                for sid, row in source['archive'].items()), 'raw_archival_text_changed')
            require(not archival_ids & set(source['archive']), 'archival_source_overlap')
            archival_ids.update(source['archive'])
            meta, reference = _decision(source, segment, self._page_limit)
            disclosed = self._mode == 'disclose' and meta['eligible']
            if disclosed:
                payload = json.loads(visible[entry.start + 1]['content'])
                payload['observation']['api_receipts'] = reference
                visible[entry.start + 1]['content'] = compact(payload)
            sidecar.append(dict(meta, turn=turn, disclosed=disclosed,
                source_sha256=entry.source_sha256, messages_sha256=entry.messages_sha256))
        require(expected_start == len(self._messages), 'recorded_turn_coverage_changed')
        require(archival_ids == set(self._archive), 'archival_source_coverage_changed')
        return visible, sidecar

    def sidecar(self):
        """Derived hashes/counts/reasons only; no task values or generated text."""
        return deepcopy(self._view()[1])

    def for_model(self, page_limit=None):
        require(page_limit is None or type(page_limit) is int and page_limit == self._page_limit,
                'receipt_page_limit_cannot_change')
        visible, sidecar = self._view()
        view = copy(self)
        view._messages = visible
        rendered, stats = StableReferenceConversation.for_model(view, self._page_limit)
        reasons = Counter(reason for row in sidecar for reason in row['reasons'])
        stats['receipt_disclosure'] = {
            'mode': self._mode, 'closed_turns': len(sidecar),
            'disclosed_turns': sum(row['disclosed'] for row in sidecar),
            'fallback_reasons': dict(sorted(reasons.items())),
            'removed_receipt_UTF8_bytes': sum(row['table_bytes'] - row['reference_bytes']
                for row in sidecar if row['disclosed']),
            'byte_scope': 'one rendering of receipt indexes only; not tokens or cumulative usage',
            'full_archive_sha256': digest(self._archive), 'sidecar_sha256': digest(sidecar),
            'task_quality_established': False, 'live_integration': False,
        }
        return rendered, stats
