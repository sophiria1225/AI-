"""Trusted closed-turn adapter for ordinary full versus receipt-index disclosure.

Raw events/spans come from the host recorder, never an eligibility assertion.
The same binding checks run in both modes and in closed offline reconstruction.
This module performs no inference, API request, archive expansion or code execution.
"""
from copy import deepcopy
from functools import wraps
import hashlib
import json

from context_preservation import compact
from receipt_disclosure_history import ReceiptDisclosureConversation
from receipt_reasoning_history import digest, require

VERSION = 'receipt_disclosure_live_v1'


def _contract_checked(method):
    @wraps(method)
    def checked(self, *args, **kwargs):
        require(not self._contract_failed, 'receipt_disclosure_contract_already_failed')
        try:
            return method(self, *args, **kwargs)
        except Exception as error:
            self._contract_failed = True
            self._contract_error_type = type(error).__name__
            raise
    return checked


def _text_sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def select_closed_turn(*, call_id, events, spans, committed_events, committed_archive):
    """Select only the new, completely recorded actor turn from cumulative logs.

    Prior record text/order cannot change, a future/other call cannot enter this
    suffix, and every span must have exactly one ordered event. No value is
    fetched, inferred, injected, or copied from an unobserved future turn.
    """
    require(type(call_id) is str and bool(call_id), 'explicit_closed_call_ID_required')
    require(type(events) is list and type(spans) is dict, 'cumulative_host_records_required')
    require(type(committed_events) is list and type(committed_archive) is dict,
            'owned_committed_prefix_required')
    n = len(committed_events)
    require(len(events) > n and compact(events[:n]) == compact(committed_events),
            'committed_event_prefix_changed_or_missing')
    require(all(type(e) is dict and type(e.get('span_id')) is str and bool(e['span_id'])
                and type(e.get('call')) is str and bool(e['call']) for e in events),
            'host_record_identity_required')
    ids = [e['span_id'] for e in events]
    require(len(ids) == len(set(ids)) and list(spans) == ids,
            'complete_ordered_event_archive_required')
    require(all(type(row) is dict and row.get('id') == sid for sid, row in spans.items()),
            'host_span_identity_changed')
    require(list(committed_archive) == ids[:n] and all(
        sid in spans and compact(spans[sid]) == compact(row)
        for sid, row in committed_archive.items()), 'committed_raw_archive_prefix_changed')
    require(all(e['call'] != call_id for e in committed_events), 'closed_call_ID_reused')
    current = events[n:]
    require(all(e['call'] == call_id for e in current), 'one_new_closed_call_suffix_required')
    current_ids = ids[n:]
    return deepcopy(current), {sid: deepcopy(spans[sid]) for sid in current_ids}


class ReceiptDisclosureLiveConversation(ReceiptDisclosureConversation):
    """Exact live adapter; ordinary append is forbidden to prevent silent fallback."""
    def __init__(self, system_prompt, task, *, execution_scope, mode, page_limit=24000):
        super().__init__(system_prompt, task, execution_scope=execution_scope,
                         mode=mode, page_limit=page_limit)
        self._contract_failed = False
        self._contract_error_type = None
        self._last_snapshot = None
        self._committed_events = []
        self._committed_calls = []

    @property
    def contract_failed(self):
        return self._contract_failed

    @property
    def receipt_policy(self):
        return self._mode

    @property
    def page_limit(self):
        return self._page_limit

    @_contract_checked
    def append(self, response, spans):
        raise ValueError('live_receipt_requires_closed_host_records')

    @_contract_checked
    def append_recorded(self, response, spans, **kwargs):
        raise ValueError('live_receipt_requires_cumulative_closed_turn_API')

    @_contract_checked
    def append_closed_turn(self, response, outer_spans, *, call_id, events, spans,
                           pending_reads=0):
        # Recheck the owned history before validating a new source suffix.
        self._view()
        current, archive = select_closed_turn(call_id=call_id, events=events, spans=spans,
            committed_events=self._committed_events, committed_archive=self._archive)
        require(type(outer_spans) is list, 'outer_span_list_required')
        wanted = [archive[e['span_id']] for e in current if e.get('stage') == 'model_tool']
        require(compact(wanted) == compact(outer_spans), 'exact_ordered_outer_records_required')
        # The prototype atomically validates/copies the whole turn. Only after it
        # succeeds can our trusted recorder prefix advance. Raw failures remain
        # the worker's responsibility; no rollback/retry of task actions occurs.
        ReceiptDisclosureConversation.append_recorded(self, response, outer_spans,
            events=current, archive_spans=archive, pending_reads=pending_reads)
        self._committed_events = deepcopy(events)
        self._committed_calls.append(call_id)

    @_contract_checked
    def for_model(self, page_limit=None):
        rendered, stats = super().for_model(page_limit)
        stats['receipt_disclosure']['live_integration'] = True
        stats['receipt_disclosure']['trusted_closed_turn_adapter'] = VERSION
        return rendered, stats

    @_contract_checked
    def disclosure_snapshot(self):
        """Deterministic hash/count sidecar, rederived from owned original records.

        Persist beside raw conversation/events/spans; it is not an input proof.
        Reconstruct a fresh adapter from those records before comparing this value.
        """
        rendered, stats = self.for_model()
        decisions = self.sidecar()
        require(len(self._committed_calls) == len(decisions)
                and len(set(self._committed_calls)) == len(self._committed_calls),
                'committed_call_coverage_changed')
        ids = [e['span_id'] for e in self._committed_events]
        require(list(self._archive) == ids and len(set(ids)) == len(ids),
                'committed_event_coverage_changed')
        # Rebind each per-turn owned source to the cumulative recorder prefix.
        sources = [json.loads(entry.source_json) for entry in self._turns]
        require(compact([e for source in sources for e in source['events']])
                == compact(self._committed_events), 'committed_events_not_bound_to_turn_sources')
        require(all({e['call'] for e in source['events']} == {call_id}
                    for source, call_id in zip(sources, self._committed_calls, strict=True)),
                'committed_calls_not_bound_to_turn_sources')
        read_spans = [row for row in self._archive.values()
                      if type(row.get('action')) is dict and row['action'].get('name') == 'read_span']
        snapshot = dict(version=VERSION, mode=self._mode, page_limit=self._page_limit,
            execution_scope_sha256=_text_sha(self._execution_scope),
            initial_messages_sha256=self._initial_sha256,
            raw_messages_sha256=digest(self.messages()),
            raw_archive_sha256=digest(self._archive),
            raw_span_text_mapping_sha256=digest({sid: _text_sha(compact(row))
                                                for sid, row in self._archive.items()}),
            normalized_history_sha256=digest(rendered),
            committed_events_sha256=digest(self._committed_events),
            committed_calls_sha256=digest(self._committed_calls),
            committed_event_count=len(self._committed_events), closed_turns=len(decisions),
            eligible_turns=sum(row['eligible'] for row in decisions),
            disclosed_turns=sum(row['disclosed'] for row in decisions),
            receipt_read_span_actions=len(read_spans),
            receipt_read_span_returned_characters=sum(
                len(row['observation']['text']) for row in read_spans
                if type(row.get('observation')) is dict and type(row['observation'].get('text')) is str),
            decisions=decisions, formatting=stats['receipt_disclosure'],
            byte_counts_are_tokens=False, automatic_archive_expansions=0,
            additional_environment_API_requests=0,
            archive_deleted=False, task_quality_established=False, novel_method_claim=False)
        self._last_snapshot = deepcopy(snapshot)
        return snapshot

    def disclosure_summary(self):
        """Safe terminal metadata; after a contract stop retain only last verified state."""
        snapshot = self._last_snapshot if self._contract_failed else self.disclosure_snapshot()
        keys = ('closed_turns', 'eligible_turns', 'disclosed_turns',
                'receipt_read_span_actions', 'receipt_read_span_returned_characters')
        result = {k: snapshot[k] if snapshot is not None else None for k in keys}
        result.update(mode=self._mode, disclosure_contract_intact=not self._contract_failed,
            sidecar_complete=not self._contract_failed and snapshot is not None,
            last_verified_snapshot_available=snapshot is not None,
            snapshot_sha256=digest(snapshot) if snapshot is not None else None,
            contract_error_type=self._contract_error_type,
            removed_receipt_UTF8_bytes=(snapshot['formatting']['removed_receipt_UTF8_bytes']
                if snapshot is not None else None),
            byte_scope='one final display of closed receipt indexes; not tokens or cumulative usage',
            automatic_archive_expansions=0, task_quality_established=False, novel_method_claim=False)
        return result

    @_contract_checked
    def validate_disclosure_snapshot(self, snapshot):
        require(type(snapshot) is dict and compact(snapshot) == compact(self.disclosure_snapshot()),
                'saved_receipt_disclosure_snapshot_differs')
        return True


def rebuild_disclosure_conversation(system_prompt, task, *, execution_scope, mode,
                                    page_limit, turns, events, spans, expected_snapshot=None):
    """Offline reconstruction from original messages and host recorder records.

    Each handwritten/saved turn descriptor is {call_id, response, outer_spans,
    pending_reads}. No generated code, model request or evaluator is invoked.
    Unclosed tail events are rejected by this complete-reconstruction helper;
    an auditor handling a terminal incomplete turn must report that separately.
    """
    require(type(turns) is list, 'closed_turn_descriptors_required')
    conversation = ReceiptDisclosureLiveConversation(system_prompt, task,
        execution_scope=execution_scope, mode=mode, page_limit=page_limit)
    cursor = 0
    for turn in turns:
        require(type(turn) is dict and set(turn) == {'call_id', 'response', 'outer_spans', 'pending_reads'},
                'exact_closed_turn_descriptor_required')
        begin = cursor
        while cursor < len(events) and events[cursor].get('call') == turn['call_id']:
            cursor += 1
        require(cursor > begin, 'recorded_turn_events_missing')
        prefix = events[:cursor]
        archive = {e['span_id']: spans[e['span_id']] for e in prefix}
        conversation.append_closed_turn(turn['response'], turn['outer_spans'], call_id=turn['call_id'],
            events=prefix, spans=archive, pending_reads=turn['pending_reads'])
    require(cursor == len(events) and set(spans) == set(conversation._archive),
            'unclosed_or_unbound_reconstruction_tail')
    if expected_snapshot is not None:
        conversation.validate_disclosure_snapshot(expected_snapshot)
    return conversation
