import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from matched_live_prefix import (MatchedLiveChannel, assemble_programs,
    public_next_message, result_comparison)


class Catalog:
    visible = {'demo__read'}
    catalog = {'demo__read': {'function': {'name': 'demo__read'}}}
    def decode(self, fn):
        if fn['name'] != 'demo__read':
            raise ValueError('undiscovered')
        return dict(app='demo', api='read', args=json.loads(fn['arguments']))
    def expose_requested_document(self, action):
        return []


class Bridge:
    def __init__(self, value=None, error=None):
        self.value = {'value': 7} if value is None else value
        self.error = error; self.calls = []
    def request(self, action):
        self.calls.append(copy.deepcopy(action))
        if self.error is not None:
            return dict(ok=False, error=self.error)
        return dict(ok=True, result=dict(observation=self.value, declared_complete=False))


def entry(number=1, *, value=None, error=None, sent=True):
    request = dict(kind='api', id=number, app='demo', api='read', arguments={'key': 1})
    reply = (dict(id=number, ok=False, error=error) if error is not None else
             dict(id=number, ok=True, value={'value': 7} if value is None else value, new_schemas={}))
    return dict(request=request, reply=reply, originally_sent=sent,
                declared_complete=False, effects_unknown=False)


class ChannelTest(unittest.TestCase):
    def test_live_value_not_substituted(self):
        bridge = Bridge(); e = entry()
        channel = MatchedLiveChannel(Catalog(), bridge, 2, [e])
        reply = channel.exchange(e['request'])
        self.assertEqual(len(bridge.calls), 1)
        self.assertEqual(reply['value'], {'value': 7})
        self.assertEqual(channel.matched_replies, 1)
        self.assertFalse(channel.fatal)

    def test_different_request_never_dispatched(self):
        bridge = Bridge(); e = entry(); changed = copy.deepcopy(e['request'])
        changed['arguments']['key'] = 2
        channel = MatchedLiveChannel(Catalog(), bridge, 2, [e])
        with self.assertRaisesRegex(ValueError, 'before_dispatch'):
            channel.exchange(changed)
        self.assertEqual(bridge.calls, [])
        self.assertTrue(channel.fatal)

    def test_live_reply_mismatch_is_not_repaired_and_latches(self):
        bridge = Bridge(value={'value': 8}); e = entry()
        channel = MatchedLiveChannel(Catalog(), bridge, 2, [e, entry(2)])
        with self.assertRaisesRegex(ValueError, 'live_reply_differs'):
            channel.exchange(e['request'])
        self.assertEqual(channel.rows[0]['observation']['observation'], {'value': 8})
        with self.assertRaisesRegex(ValueError, 'already_diverged'):
            channel.exchange(entry(2)['request'])
        self.assertEqual(len(bridge.calls), 1)

    def test_extra_request_prevented_before_dispatch(self):
        bridge = Bridge(); e = entry()
        channel = MatchedLiveChannel(Catalog(), bridge, 2, [e])
        channel.exchange(e['request'])
        with self.assertRaisesRegex(ValueError, 'unexpected_request'):
            channel.exchange(entry(2)['request'])
        self.assertEqual(len(bridge.calls), 1)

    def test_expected_exception_matches_without_assuming_rollback(self):
        bridge = Bridge(error='known failure'); e = entry(error='known failure')
        channel = MatchedLiveChannel(Catalog(), bridge, 2, [e])
        self.assertFalse(channel.exchange(e['request'])['ok'])
        self.assertFalse(channel.fatal)
        self.assertTrue(channel.rows[0]['api_request_sent'])

    def test_budget_rejection_differs_from_expected_send(self):
        bridge = Bridge(); e = entry()
        channel = MatchedLiveChannel(Catalog(), bridge, 0, [e])
        with self.assertRaisesRegex(ValueError, 'live_reply_differs'):
            channel.exchange(e['request'])
        self.assertEqual(bridge.calls, [])

    def test_missing_tail_and_changed_stdout_not_accepted(self):
        e = entry(); channel = MatchedLiveChannel(Catalog(), Bridge(), 2, [e, entry(2)])
        channel.exchange(e['request'])
        actual = dict(status='ok', stdout='8', api_requests=1, error=None)
        expected = dict(actual, stdout='7', api_requests=2)
        check = result_comparison(channel, actual, expected)
        self.assertFalse(check['public_prefix_matches'])
        self.assertFalse(check['checks']['all_requests_and_live_replies'])
        self.assertFalse(check['checks']['stdout'])


def synthetic_prefix():
    events = []; spans = {}; files = []
    counts = [3, 2, 2, 1, 2, 4, 4, 4, 0, 3, 0, 3]
    for n, count in enumerate(counts, 1):
        call = f'call_{n:03d}'; wire = []; receipts = []
        for i in range(1, count + 1):
            sid = 's' + str(len(spans) + 1); e = entry(i)
            events.append(dict(call=call, span_id=sid, stage='python_api', api_request_sent=True,
                               new_tools=[], effects_unknown=False, declared_complete=False))
            spans[sid] = dict(id=sid, action=dict(name='demo__read', arguments='{"key":1}'),
                observation=dict(observation={'value': 7}, declared_complete=False))
            wire.append(dict(e['request'], program_index=n)); receipts.append({'span_id': sid})
        result = dict(status='ok', program_index=n, session_usable=True, api_requests=count,
                      stdout='', stdout_truncated=False, error=None)
        wire.append(dict(kind='done', program_index=n, stdout='', stdout_truncated=False, error=None))
        sid = 's' + str(len(spans) + 1)
        events.append(dict(call=call, span_id=sid, stage='model_tool', api_request_sent=False,
                           effects_unknown=False, declared_complete=False))
        spans[sid] = dict(id=sid, observation={'api_receipts': receipts})
        files.append(dict(input=dict(program_index=n, code='pass', observations=[]), result=result, wire=wire))
    sid = 's' + str(len(spans) + 1)
    events.append(dict(call='call_013', span_id=sid, stage='model_tool', api_request_sent=False,
                       effects_unknown=False, declared_complete=False))
    spans[sid] = dict(id=sid, observation={'format_error': 'known malformed argument'})
    return events, spans, files


class PrefixInventoryTest(unittest.TestCase):
    def test_all_twelve_programs_and_nonexecuted_thirteenth_boundary(self):
        programs = assemble_programs(*synthetic_prefix(), {})
        self.assertEqual(len(programs), 12)
        self.assertEqual(sum(len(p['entries']) for p in programs), 28)

    def test_future_event_or_observation_injection_rejected(self):
        events, spans, files = synthetic_prefix(); events[-1]['call'] = 'call_014'
        with self.assertRaises(ValueError):
            assemble_programs(events, spans, files, {})
        events, spans, files = synthetic_prefix(); files[0]['input']['observations'] = [{'future': True}]
        with self.assertRaises(ValueError):
            assemble_programs(events, spans, files, {})

    def test_cross_program_receipt_rejected(self):
        events, spans, files = synthetic_prefix()
        files[0]['wire'][0]['program_index'] = 2
        with self.assertRaisesRegex(ValueError, 'receipt_identity'):
            assemble_programs(events, spans, files, {})

    def test_duplicate_model_boundary_and_missing_wire_rejected(self):
        events, spans, files = synthetic_prefix(); events[-1]['call'] = 'call_012'
        with self.assertRaisesRegex(ValueError, 'model_boundary'):
            assemble_programs(events, spans, files, {})
        events, spans, files = synthetic_prefix(); files[2]['wire'].pop()
        with self.assertRaisesRegex(ValueError, 'wire_boundary'):
            assemble_programs(events, spans, files, {})

    def test_unknown_effect_and_executed_thirteenth_rejected(self):
        events, spans, files = synthetic_prefix(); events[0]['effects_unknown'] = True
        with self.assertRaises(ValueError):
            assemble_programs(events, spans, files, {})
        events, spans, files = synthetic_prefix(); spans[events[-1]['span_id']]['observation'] = {'status': 'ok'}
        with self.assertRaisesRegex(ValueError, 'thirteenth'):
            assemble_programs(events, spans, files, {})


class PublicMessageTest(unittest.TestCase):
    def response(self, calls):
        response = dict(status='ok', done_reason='stop', message=dict(content='日本語',
            tool_calls=calls, reasoning_content='private reasoning must not be copied'))
        payload = dict(content='日本語', functions=[c['function'] for c in calls], done_reason='stop')
        h = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
            separators=(',', ':')).encode()).hexdigest()
        return response, h

    def test_text_only_remains_without_tool_calls(self):
        message = public_next_message(*self.response([]))
        self.assertEqual(message['tool_calls'], [])
        self.assertEqual(set(message), {'role', 'content', 'tool_calls'})

    def test_tool_payload_preserved_and_hash_change_rejected(self):
        calls = [dict(id='original-id', function=dict(name='run_python', arguments='{"code":"print(1)","span_ids":[]}'))]
        response, h = self.response(calls)
        self.assertEqual(public_next_message(response, h)['tool_calls'], calls)
        response['message']['content'] += 'x'
        with self.assertRaisesRegex(ValueError, 'output_changed'):
            public_next_message(response, h)


if __name__ == '__main__':
    unittest.main()
