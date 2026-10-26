"""Reconstruct receipt views from original closed records before rolling audit.

Only trusted formatting/controller code runs. Saved model Python is never
executed. Sidecars are comparison targets, never inputs to disclosure decisions.
"""
from copy import deepcopy
import json
from pathlib import Path

from audit_rolling_checkpoint_trace import audit_trace as audit_rolling
from audit_whole_task_region_projection import equal, require
from context_preservation import compact, page_span
from public_name_catalog import PublicNameCatalog
from receipt_disclosure_live import ReceiptDisclosureLiveConversation
from receipt_reasoning_history import digest
from run_handoff_factors import read, sha


class RecordedReceiptConversation:
    """Audit-only append adapter for the unchanged rolling controller checker."""
    def __init__(self, folder, conversation):
        require(type(conversation) is ReceiptDisclosureLiveConversation,
                'fresh_exact_live_conversation_required')
        self.folder, self.live = Path(folder), conversation
        self.events, self.spans = read(self.folder / 'events.json'), read(self.folder / 'spans.json')
        require(type(self.events) is list and type(self.spans) is dict
                and [e['span_id'] for e in self.events] == list(self.spans),
                'complete_ordered_receipt_source_required')
        self.cursor, self.last_formatting = 0, None
        self.snapshots = [(0, self.live.disclosure_snapshot())]
        self.disclosed_sources = {}

    def messages(self):
        return self.live.messages()

    def for_model(self, page_limit):
        rendered, formatting = self.live.for_model(page_limit)
        self.last_formatting = deepcopy(formatting)
        return rendered, formatting

    def append(self, response, outer_spans):
        require(self.cursor < len(self.events), 'receipt_turn_without_host_records')
        call_id = self.events[self.cursor]['call']
        require(type(call_id) is str and call_id.startswith('call_')
                and call_id[5:].isdigit(), 'sequential_receipt_call_ID_required')
        ordinal = int(call_id[5:])
        require(call_id == f'call_{ordinal:03d}' and ordinal > self.snapshots[-1][0],
                'receipt_turn_order_changed')
        saved = read(self.folder / call_id / 'response.json')
        equal(response, saved['message'], 'receipt_response_source_changed')
        require(saved['status'] == 'ok', 'unknown_response_cannot_close_receipt_turn')
        stop = self.cursor
        while stop < len(self.events) and self.events[stop]['call'] == call_id:
            stop += 1
        prefix = self.events[:stop]
        archive = {e['span_id']: self.spans[e['span_id']] for e in prefix}
        self.live.append_closed_turn(response, outer_spans, call_id=call_id,
            events=prefix, spans=archive, pending_reads=0)
        self.cursor = stop
        snapshot = self.live.disclosure_snapshot()
        self.snapshots.append((ordinal, snapshot))
        if snapshot['decisions'][-1]['disclosed']:
            # A disclosed turn has exactly one normal outer Python result.
            rendered, _ = self.live.for_model()
            require(len(outer_spans) == 1 and rendered[-1]['role'] == 'tool',
                    'disclosed_outer_shape_changed')
            self.disclosed_sources[outer_spans[0]['id']] = dict(source_call=ordinal,
                content=rendered[-1]['content'], receipt_rows=snapshot['decisions'][-1]['receipt_rows'])

    def snapshot_before(self, call_id):
        require(type(call_id) is str and call_id.startswith('call_')
                and call_id[5:].isdigit(), 'invalid_receipt_inference_call_ID')
        ordinal = int(call_id[5:])
        require(call_id == f'call_{ordinal:03d}' and ordinal > 0,
                'invalid_receipt_inference_call_ID')
        return next(snapshot for index, snapshot in reversed(self.snapshots) if index < ordinal)

    def finish(self):
        require(self.cursor == len(self.events), 'unclosed_receipt_source_tail')
        # Ordered compact text, not canonical dict equality: character page
        # coordinates depend on insertion order in every archived row.
        require(compact(self.live.archive()) == compact(self.spans),
                'raw_receipt_archive_text_changed')
        self.live.validate_disclosure_snapshot(read(self.folder / 'receipt_disclosure_sidecar_private.json'))


def audit_archive_reads(events, spans, page_limit):
    """Bind every successful read_span page to the earlier raw archive text."""
    catalog, prefix, reads = PublicNameCatalog([]), {}, []
    for event in events:
        span = spans[event['span_id']]
        action = span.get('action')
        if type(action) is dict and action.get('name') == 'read_span':
            require(event['stage'] == 'model_tool' and event['api_request_sent'] is False
                    and not event.get('new_tools') and 'api_execution' not in event,
                    'archive_read_must_not_send_environment_API')
            observation = span['observation']
            if 'not_executed' in observation:
                equal(observation, {'not_executed': 'completion, unknown effects or run budget'},
                      'archive_read_skipped_result_changed')
            else:
                try:
                    decoded = catalog.decode(action)
                    expected = page_span(prefix, decoded['span_id'], decoded.get('offset', 0), page_limit)
                except (ValueError, KeyError, TypeError) as error:
                    expected = {'format_error': str(error)}
                equal(observation, expected, 'raw_archive_character_page_changed')
            reads.append({'call_id': event['call'], 'span_id': event['span_id'],
                'page_sha256': digest(observation),
                'returned_characters': len(observation['text']) if type(observation.get('text')) is str else 0})
        prefix[event['span_id']] = span
    return reads


def dispatched_disclosure_exposures(folder, request_checks, disclosed_sources):
    """Count actual paid input exposure, excluding final/unrequested decisions.

The rolling auditor already binds these request bytes to reconstructed agent
or focus inputs and dispatch admissions. Inspect only the structured message
locations used by that controller, not arbitrary substrings or model claims.
"""
    exposed, result = set(), []
    for check in request_checks:
        path = folder / check['call_id'] / 'request.json'
        if not path.exists():
            require(check['request_sha256'] is None, 'dispatched_request_hash_missing')
            continue
        request = read(path)
        messages = request['messages']
        if check['role'] == 'focus':
            require(len(messages) == 2 and messages[1]['role'] == 'user',
                    'focus_receipt_locations_changed')
            packet = json.loads(messages[1]['content'])
            messages = packet['older_history'] + packet['recent_context']
        content = {message['content'] for message in messages if message.get('role') == 'tool'
                   and type(message.get('content')) is str}
        ordinal = int(check['call_id'][5:])
        matched = {sid for sid, source in disclosed_sources.items()
                   if source['source_call'] < ordinal and source['content'] in content}
        exposed.update(matched)
        result.append(dict(call_id=check['call_id'], role=check['role'],
            disclosed_outer_count=len(matched), disclosed_outer_ids_sha256=digest(sorted(matched)),
            receipt_rows=sum(disclosed_sources[sid]['receipt_rows'] for sid in matched)))
    return len(exposed), result


def audit_trace(folder, config, conversation):
    folder = Path(folder)
    require(config['checkpoint_policy'] == 'rolling_separate'
            and config['projection_policy'] == 'explicit_joined_fields'
            and config['receipt_disclosure_policy'] == conversation.receipt_policy,
            'fixed_P128_history_and_runtime_required')
    wrapped = RecordedReceiptConversation(folder, conversation)
    checked = audit_rolling(folder, config, wrapped)
    wrapped.finish()
    summary = read(folder / 'summary.json')
    equal(summary['receipt_disclosure'], conversation.disclosure_summary(),
          'receipt_summary_not_reconstructed_from_raw_source')
    require(summary['receipt_disclosure_contract_intact'] is True
            and summary['receipt_disclosure_error_type'] is None
            and summary['sidecar_save_error_type'] is None,
            'receipt_contract_failure_cannot_pass_complete_history_audit')
    if wrapped.last_formatting is not None:
        equal(summary['history_formatting'], wrapped.last_formatting,
              'last_actor_history_formatting_changed')
    signals = read(folder / 'budget_observations.json')
    path = folder / 'receipt_disclosure_inference_views.json'
    views = read(path) if path.exists() else []
    expected = []
    for signal in signals:
        cid = signal['next_call_id']
        snapshot = wrapped.snapshot_before(cid)
        expected.append(dict(next_agent_call_id=cid, receipt_snapshot_sha256=digest(snapshot),
            normalized_history_sha256=snapshot['normalized_history_sha256'],
            raw_messages_sha256=snapshot['raw_messages_sha256'],
            closed_turns=snapshot['closed_turns'], disclosed_turns=snapshot['disclosed_turns']))
    equal(views, expected, 'receipt_inference_view_not_bound_to_prior_closed_source')
    reads = audit_archive_reads(wrapped.events, wrapped.spans, config['observation_page_characters'])
    final = conversation.disclosure_snapshot()
    exposed_count, exposures = dispatched_disclosure_exposures(
        folder, checked['request_checks'], wrapped.disclosed_sources)
    require(final['receipt_read_span_actions'] == len(reads)
            and final['receipt_read_span_returned_characters'] == sum(r['returned_characters'] for r in reads),
            'receipt_archive_read_accounting_changed')
    files = ['receipt_disclosure_sidecar_private.json', 'conversation_private.json', 'events.json', 'spans.json']
    if path.exists():
        files.append(path.name)
    return {**checked, 'receipt_disclosure': conversation.disclosure_summary(),
        'receipt_disclosure_contract_intact': True, 'receipt_disclosure_audit_complete': True,
        'receipt_disclosures': exposed_count, 'receipt_disclosure_contract_failed': False,
        'receipt_disclosure_paid_input_exposures': exposures,
        'receipt_disclosure_gate_scope': 'unique disclosed outer results appearing in dispatched agent/focus inputs',
        'receipt_eligible_turns': final['eligible_turns'], 'receipt_disclosed_turns': final['disclosed_turns'],
        'receipt_read_span_actions': len(reads), 'receipt_read_span_checks': reads,
        'receipt_disclosure_audit_hashes': {name: sha(folder / name) for name in files},
        'disclosure_decisions_reconstructed_from_original_records': True,
        'receipt_byte_counts_are_tokens': False}
