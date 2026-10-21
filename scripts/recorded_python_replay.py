"""Replay Python against recorded public replies, without a live API bridge.

This checks observable prefix correspondence. It is not a process snapshot,
semantic equivalence proof, or a novel agent algorithm. Generated code runs only
through the existing isolated persistent interpreter.
"""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


class RecordedChannel:
    """The only responses available are those in a fixed, ordered transcript."""
    def __init__(self, initial_schemas, entries, all_schemas):
        self.catalog = SimpleNamespace(
            visible=set(initial_schemas),
            catalog={name: {'function': copy.deepcopy(value)}
                     for name, value in all_schemas.items()})
        for name, schema in initial_schemas.items():
            if canonical(schema) != canonical(all_schemas[name]):
                raise ValueError('initial public schema differs')
        self.entries = copy.deepcopy(entries)
        self.rows = []
        self.complete = self.fatal = False
        self.mismatch = None
        self.api_requests_sent = 0

    def reject(self, reason):
        self.mismatch = reason
        self.fatal = True
        raise ValueError(reason)

    def exchange(self, packet):
        index = len(self.rows)
        if index >= len(self.entries):
            self.reject('unexpected additional request')
        expected = self.entries[index]
        if canonical(packet) != canonical(expected['request']):
            self.reject('recorded request differs')
        # Neither a bridge object nor a live-dispatch function is accepted by
        # this class. A matching write request only receives its saved reply.
        reply = copy.deepcopy(expected['reply'])
        self.rows.append({'api_request_sent': False,
                          'recorded_api_request_sent': expected['originally_sent'],
                          'request_index': index + 1})
        self.complete |= expected['declared_complete']
        self.fatal |= expected['effects_unknown']
        self.catalog.visible.update(reply.get('new_schemas', {}))
        return reply

    def compare_result(self, actual, expected):
        checks = {
            'request_sequence': self.mismatch is None and len(self.rows) == len(self.entries),
            'status': actual['status'] == expected['status'],
            'stdout': actual.get('stdout') == expected.get('stdout'),
            'stdout_truncated': actual.get('stdout_truncated') == expected.get('stdout_truncated'),
            'error': actual.get('error') == expected.get('error'),
            'declared_complete': actual['declared_complete'] == expected['declared_complete'],
            'unknown_effects': actual['unknown_effects'] == expected['unknown_effects'],
            'no_live_api_dispatch': actual['api_requests'] == 0 and self.api_requests_sent == 0,
        }
        return {'checks': checks, 'observable_prefix_matches': all(checks.values()),
                'recorded_requests': len(self.entries), 'matched_requests': len(self.rows),
                'recorded_dispatched_requests': sum(e['originally_sent'] for e in self.entries),
                'api_requests_sent': 0, 'mismatch_kind': self.mismatch,
                'expected_stdout_sha256': hashlib.sha256(expected['stdout'].encode()).hexdigest(),
                'actual_stdout_sha256': hashlib.sha256(actual['stdout'].encode()).hexdigest()}


def reply_from_receipt(request, span, event, schemas):
    """Invert only the documented reply encoding, retaining error observations."""
    action = span['action']
    if (action['name'] != request['app']+'__'+request['api']
            or canonical(json.loads(action['arguments'])) != canonical(request['arguments'])):
        raise ValueError('saved request and receipt differ')
    obs = span['observation']
    reply = {'id': request['id'], 'ok': False}
    if event.get('effects_unknown'):
        raise ValueError('unknown API effect cannot establish a replay prefix')
    if 'not_executed' in obs:
        reply['error'] = obs['not_executed']
    elif 'format_error' in obs:
        reply['error'] = obs['format_error']
    elif 'api_error' in obs:
        reply['error'] = obs['api_error']
    else:
        if not event['api_request_sent'] or 'observation' not in obs:
            raise ValueError('unrecognized recorded reply shape')
        value = obs['observation']
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                pass
        reply.update(ok=True, value=value,
                     new_schemas={name: copy.deepcopy(schemas[name]) for name in event['new_tools']})
    return {'request': {k: v for k, v in request.items() if k != 'program_index'},
            'reply': reply, 'originally_sent': event['api_request_sent'],
            'declared_complete': bool(obs.get('declared_complete')),
            'effects_unknown': False}


def load_programs(trial, schemas):
    """Use outer receipt references to avoid confusing API and model turns."""
    def read(name):
        return json.loads((trial/name).read_text())
    events, spans = read('events.json'), read('spans.json')
    by_id = {e['span_id']: e for e in events}
    numbers = {}
    programs = []
    for event in events:
        if event['stage'] != 'model_tool':
            continue
        call = event['call']
        numbers[call] = numbers.get(call, 0) + 1
        folder = trial/'programs'/f'{call}_{numbers[call]:02d}'
        if not folder.exists():
            continue
        source = json.loads((folder/'input_private.json').read_text())
        result = json.loads((folder/'result_private.json').read_text())
        if result['status'] not in ('ok', 'execution_error') or not result.get('session_usable'):
            raise ValueError('recorded interpreter boundary is not replayable')
        expected_number = len(programs) + 1
        if source['program_index'] != expected_number or result['program_index'] != expected_number:
            raise ValueError('recorded program order differs')
        wire = [json.loads(line) for line in (folder/'wire_private.jsonl').read_text().splitlines()]
        requests = [row for row in wire if row.get('kind') == 'api']
        if (not wire or wire[-1].get('kind') != 'done' or len(wire) != len(requests)+1
                or wire[-1].get('program_index') != expected_number
                or any(wire[-1].get(k) != result.get(k) for k in ('stdout','stdout_truncated','error'))):
            raise ValueError('recorded program completion differs')
        receipts = spans[event['span_id']]['observation']['api_receipts']
        if len(requests) != len(receipts):
            raise ValueError('request/receipt count differs')
        entries = []
        for i, (request, receipt) in enumerate(zip(requests, receipts, strict=True), 1):
            if request['id'] != i or request['program_index'] != expected_number:
                raise ValueError('RPC identity differs')
            sid = receipt['span_id']
            if by_id[sid]['stage'] != 'python_api' or by_id[sid]['call'] != call:
                raise ValueError('receipt belongs to another program')
            entries.append(reply_from_receipt(request, spans[sid], by_id[sid], schemas))
        if sum(e['originally_sent'] for e in entries) != result['api_requests']:
            raise ValueError('recorded API accounting differs')
        programs.append({'name': folder.name, 'source': source, 'expected': result,
                         'entries': entries,
                         'source_sha256': {str(p.relative_to(trial)): hashlib.sha256(p.read_bytes()).hexdigest()
                                           for p in (folder/'input_private.json', folder/'result_private.json',
                                                     folder/'wire_private.jsonl')}})
    return programs


def replay_programs(programs, schemas, session, output, storage):
    """Stop at first observable discrepancy; never repair the replay transcript."""
    rows = []
    for program in programs:
        source, expected = program['source'], program['expected']
        channel = RecordedChannel(source['api_schemas'], program['entries'], schemas)
        actual = session.run(source['code'], source['observations'], channel,
                             storage_root=storage, record_dir=output/program['name'], timeout=90)
        row = channel.compare_result(actual, expected)
        row.update(program=program['name'], source_sha256=program['source_sha256'],
                   replay_wall_seconds=actual['wall_seconds'])
        rows.append(row)
        if not row['observable_prefix_matches']:
            break
    return rows
