"""Replay a fixed public prefix live, refusing divergence before later work.

No saved reply is substituted for a live reply. Matching public observations
does not recreate the unrecorded original DB, RNG or full process state.
"""
from copy import deepcopy
import hashlib
import json

from container_api_python import ApiChannel
from recorded_python_replay import canonical, reply_from_receipt


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class MatchedLiveChannel(ApiChannel):
    def __init__(self, catalog, bridge, remaining, entries, may_continue=lambda: True):
        super().__init__(catalog, bridge, remaining, may_continue)
        self.entries = deepcopy(entries)
        self.mismatch = None
        self.matched_replies = 0

    def reject(self, reason):
        self.mismatch = reason
        self.fatal = True
        raise ValueError(reason)

    def exchange(self, packet):
        if self.mismatch is not None:
            raise ValueError('prefix_already_diverged')
        index = len(self.rows)
        if index >= len(self.entries):
            self.reject('prefix_unexpected_request')
        expected = self.entries[index]
        if canonical(packet) != canonical(expected['request']):
            self.reject('prefix_request_differs_before_dispatch')
        actual = super().exchange(packet)
        if (self.rows[-1]['api_request_sent'] != expected['originally_sent']
                or canonical(actual) != canonical(expected['reply'])
                or self.complete != expected['declared_complete']
                or self.fatal != expected['effects_unknown']):
            self.reject('prefix_live_reply_differs')
        self.matched_replies += 1
        return actual


def result_comparison(channel, actual, expected):
    keys = ('status', 'stdout', 'stdout_truncated', 'error', 'declared_complete',
            'unknown_effects', 'api_requests', 'session_usable', 'program_index')
    checks = {key: actual.get(key) == expected.get(key) for key in keys}
    checks['all_requests_and_live_replies'] = (
        channel.mismatch is None and channel.matched_replies == len(channel.entries))
    return dict(checks=checks, public_prefix_matches=all(checks.values()),
        matched_requests=channel.matched_replies, expected_requests=len(channel.entries),
        sent_requests=sum(bool(r['api_request_sent']) for r in channel.rows),
        mismatch_kind=channel.mismatch,
        expected_result_sha256=digest({k: expected.get(k) for k in keys}),
        actual_result_sha256=digest({k: actual.get(k) for k in keys}))


def assemble_programs(events, spans, program_files, schemas):
    """Accept only the selected first thirteen model boundaries / twelve codes."""
    if (any(e['call'] >= 'call_014' for e in events)
            or len(events) != 41 or sum(e['api_request_sent'] for e in events) != 28
            or any(e.get('effects_unknown') or e.get('declared_complete') for e in events)
            or set(spans) != {e['span_id'] for e in events}
            or len(program_files) != 12):
        raise ValueError('fixed_prefix_scope')
    by_id = {e['span_id']: e for e in events}
    model_events = [e for e in events if e['stage'] == 'model_tool']
    if [e['call'] for e in model_events] != [f'call_{n:03d}' for n in range(1, 14)]:
        raise ValueError('fixed_model_boundary_sequence')
    if (spans[model_events[-1]['span_id']]['observation'].get('format_error') is None
            or any(e['api_request_sent'] for e in events if e['call'] == 'call_013')):
        raise ValueError('thirteenth_boundary_must_be_unexecuted_format_error')
    programs = []
    for number, (event, files) in enumerate(zip(model_events[:12], program_files, strict=True), 1):
        source, result, wire = files['input'], files['result'], files['wire']
        if (source['program_index'] != number or result['program_index'] != number
                or source['observations'] != []
                or result['status'] not in ('ok', 'execution_error')
                or result.get('session_usable') is not True):
            raise ValueError('invalid_original_program_boundary')
        requests = [r for r in wire if r.get('kind') == 'api']
        if (not wire or wire[-1].get('kind') != 'done'
                or len(wire) != len(requests) + 1
                or wire[-1].get('program_index') != number
                or any(wire[-1].get(k) != result.get(k)
                       for k in ('stdout', 'stdout_truncated', 'error'))):
            raise ValueError('original_program_wire_boundary')
        receipts = spans[event['span_id']]['observation']['api_receipts']
        if len(requests) != len(receipts):
            raise ValueError('original_receipt_count')
        entries = []
        for index, (request, receipt) in enumerate(zip(requests, receipts, strict=True), 1):
            sid = receipt['span_id']
            if (request.get('id') != index or request.get('program_index') != number
                    or by_id[sid]['call'] != event['call'] or by_id[sid]['stage'] != 'python_api'):
                raise ValueError('original_receipt_identity')
            entries.append(reply_from_receipt(request, spans[sid], by_id[sid], schemas))
        if sum(e['originally_sent'] for e in entries) != result['api_requests']:
            raise ValueError('original_program_accounting')
        programs.append(dict(name=event['call'] + '_01', source=source,
                             expected=result, entries=entries))
    if sum(p['expected']['api_requests'] for p in programs) != 28:
        raise ValueError('original_prefix_accounting')
    return programs


def public_next_message(response, expected_public_sha):
    """Keep public content and tool calls only; never semantic-read reasoning."""
    if response.get('status') != 'ok' or type(response.get('message')) is not dict:
        raise ValueError('known_saved_response_required')
    message = response['message']
    calls = message.get('tool_calls') or []
    if type(calls) is not list or len(calls) > 16:
        raise ValueError('saved_call_bound')
    if any(type(c) is not dict or type(c.get('function')) is not dict for c in calls):
        raise ValueError('saved_call_shape')
    value = dict(content=message.get('content'), functions=[c['function'] for c in calls],
                 done_reason=response.get('done_reason'))
    # P84's public fingerprint uses ensure_ascii=False; preserve its definition.
    actual = hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    if actual != expected_public_sha:
        raise ValueError('saved_public_output_changed')
    return dict(role='assistant', content=deepcopy(message.get('content')),
                tool_calls=deepcopy(calls))
