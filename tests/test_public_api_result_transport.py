import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from appworld_native_tools import NativeCatalog
from appworld_typed_bridge import execute_public_api
from container_api_python import ApiChannel
from public_api_envelope import PROTOCOL, InvalidExecutionEnvelope
from public_api_result_transport import PublicResultProgram, PublicResultTransport, TypedBridgeProcess


class FixtureWorld:
    def __init__(self):
        self.effects = []
        self.complete = False
        self.task = SimpleNamespace(api_docs={'fixture': {
            name: {'parameters': [{'name': 'value'}]} for name in ('echo', 'fail', 'finish', 'finish_fail')}})

    def execute(self, source):
        def action(name, value=None):
            self.effects.append((name, value))
            if name.startswith('finish'):
                self.complete = True
            if name.endswith('fail'):
                raise ValueError('synthetic failure after effect')
            return value
        api = SimpleNamespace(**{name: (lambda value=None, name=name: action(name, value))
                                 for name in self.task.api_docs['fixture']})
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            exec(compile(source, '<trusted fixture invocation>', 'exec'),
                 {'apis': SimpleNamespace(fixture=api)})
        return capture.getvalue()

    def task_completed(self):
        return self.complete


class FixtureTransport:
    def __init__(self, transform=lambda r: r):
        self.world = FixtureWorld()
        self.commands = []
        self.transform = transform

    def request(self, command):
        self.commands.append(command)
        if command['op'] == 'init':
            return self.transform({'ok': True, 'result': {'api_result_protocol': PROTOCOL}})
        if command['op'] == 'close':
            return {'ok': True, 'result': {'closed': True}}
        assert command['op'] == 'call_typed'
        return self.transform({'ok': True, 'result': execute_public_api(
            self.world, command['call'], command['nonce'])})


def catalog():
    names = ('echo', 'fail', 'finish', 'finish_fail')
    result = NativeCatalog([{'type': 'function', 'function': {'name': 'fixture__' + name,
        'parameters': {'type': 'object', 'properties': {'value': {}}}}} for name in names])
    result.visible.update(result.catalog)
    return result


def channel(transport, remaining=8, may_continue=lambda: True):
    base = ApiChannel(catalog(), transport, remaining, may_continue)
    return PublicResultProgram(lambda source, observations, wrapped: wrapped)('', [], base)


def exchange(ch, api='echo', value=None):
    return ch.exchange({'kind': 'api', 'id': ch.last_id + 1,
                        'app': 'fixture', 'api': api, 'arguments': {'value': value}})


class PublicApiResultTransportTests(unittest.TestCase):
    def test_channel_preserves_json_looking_strings_and_business_failure_values(self):
        raw = FixtureTransport(); transport = PublicResultTransport(raw); ch = channel(transport)
        for value in ['1', 'null', '{"status":"raised"}', 'Traceback: ordinary text',
                      {'success': False}, None, [True, 12, '日本語']]:
            reply = exchange(ch, value=value)
            self.assertTrue(reply['ok'])
            self.assertEqual(reply['value'], value)
            self.assertIs(type(reply['value']), type(value))
            self.assertEqual(ch.rows[-1]['api_execution']['status'], 'returned')
        self.assertEqual(len(raw.commands), 7)
        self.assertEqual(len({r['nonce'] for r in transport.receipts}), 7)
        self.assertEqual(ch.remaining, 1)

    def test_invocation_exception_is_error_without_retry_or_rollback(self):
        raw = FixtureTransport(); transport = PublicResultTransport(raw); ch = channel(transport)
        reply = exchange(ch, api='fail', value=7)
        self.assertFalse(reply['ok'])
        self.assertIn('ValueError: synthetic failure', reply['error'])
        self.assertEqual(raw.world.effects, [('fail', 7)])
        self.assertEqual(len(raw.commands), 1)
        self.assertFalse(ch.fatal)
        self.assertEqual(ch.remaining, 7)
        self.assertEqual(ch.rows[0]['api_execution']['status'], 'raised')
        self.assertFalse(ch.rows[0]['api_execution']['rollback_guaranteed'])

    def test_unknown_reply_stops_dispatch_across_fresh_program_channels(self):
        for bad in [{'ok': True, 'result': {'observation': 'legacy text', 'declared_complete': False}},
                    {'ok': False, 'error': 'bridge error'},
                    {'ok': 1, 'result': {}}, {'ok': True, 'result': None}]:
            with self.subTest(bad=bad):
                raw = FixtureTransport(lambda _: bad); transport = PublicResultTransport(raw)
                first = channel(transport); self.assertFalse(exchange(first)['ok'])
                self.assertTrue(first.fatal)
                self.assertEqual(first.rows[0]['api_execution']['status'], 'unknown')
                second = channel(transport); self.assertFalse(exchange(second)['ok'])
                self.assertFalse(second.rows[0]['api_request_sent'])
                self.assertEqual(second.remaining, 8)
                self.assertEqual(len(raw.commands), 1)

    def test_invalid_envelope_cannot_be_downgraded_to_a_string(self):
        for corruption in ('noise', 'nonce', 'completion_type'):
            def corrupt(response):
                result = response['result']
                if corruption == 'noise': result['observation'] = 'extra stdout\n' + result['observation']
                elif corruption == 'nonce':
                    packet = json.loads(result['observation']); packet['nonce'] = '0' * 32
                    result['observation'] = json.dumps(packet)
                else: result['declared_complete'] = 'false'
                return response
            raw = FixtureTransport(corrupt); transport = PublicResultTransport(raw); ch = channel(transport)
            self.assertFalse(exchange(ch)['ok']); self.assertTrue(ch.fatal)
            self.assertEqual(len(raw.world.effects), 1)
            self.assertEqual(transport.receipts[0]['status'], 'unknown')

    def test_completion_latches_across_programs_for_values_and_exceptions(self):
        for api in ['finish', 'finish_fail']:
            raw = FixtureTransport(); transport = PublicResultTransport(raw); first = channel(transport)
            exchange(first, api=api)
            self.assertTrue(first.complete)
            second = channel(transport); self.assertFalse(exchange(second)['ok'])
            self.assertTrue(second.complete)
            self.assertFalse(second.rows[0]['api_request_sent'])
            self.assertEqual(len(raw.commands), 1)

    def test_catalog_rejection_and_budgets_never_reach_transport(self):
        for remaining, continuing, api in [(0, True, 'echo'), (8, False, 'echo'), (8, True, 'hidden')]:
            raw = FixtureTransport(); transport = PublicResultTransport(raw)
            ch = channel(transport, remaining, lambda: continuing)
            self.assertFalse(exchange(ch, api=api)['ok'])
            self.assertFalse(ch.rows[0]['api_request_sent'])
            self.assertNotIn('api_execution', ch.rows[0])
            self.assertEqual(raw.commands, []); self.assertEqual(transport.receipts, [])
            self.assertEqual(ch.remaining, remaining)

    def test_transport_exception_after_effect_remains_unknown(self):
        def broken(_): raise TimeoutError('synthetic transport interruption')
        raw = FixtureTransport(broken); transport = PublicResultTransport(raw); ch = channel(transport)
        self.assertFalse(exchange(ch)['ok']); self.assertTrue(ch.fatal)
        self.assertEqual(len(raw.world.effects), 1)
        self.assertEqual(ch.rows[0]['api_execution']['failure_type'], 'TimeoutError')
        self.assertFalse(exchange(channel(transport))['ok'])
        self.assertEqual(len(raw.commands), 1)

    def test_nonce_collision_is_rejected_before_send_and_not_counted_as_api(self):
        raw = FixtureTransport(); transport = PublicResultTransport(raw); ch = channel(transport)
        with patch('public_api_result_transport.uuid.uuid4', return_value=SimpleNamespace(hex='b' * 32)):
            self.assertTrue(exchange(ch)['ok'])
            self.assertFalse(exchange(ch)['ok'])
        self.assertEqual(len(raw.commands), 1)
        self.assertEqual(ch.remaining, 7)
        self.assertFalse(ch.rows[-1]['api_request_sent'])
        self.assertFalse(ch.rows[-1]['effects_unknown'])
        self.assertEqual(ch.rows[-1]['api_execution']['status'], 'not_dispatched')
        self.assertTrue(ch.fatal)

    def test_program_wrapper_rejects_an_untyped_transport_before_running_code(self):
        runtime = PublicResultProgram(lambda *args, **kwargs: self.fail('must not run'))
        with self.assertRaises(ValueError):
            runtime('irrelevant', [], ApiChannel(catalog(), FixtureTransport(), 2))

    def test_initialization_requires_protocol_handshake_and_cannot_reset_used_transport(self):
        raw = FixtureTransport(lambda _: {'ok': True, 'result': {}})
        transport = PublicResultTransport(raw)
        with self.assertRaises(InvalidExecutionEnvelope): transport.request({'op': 'init'})
        self.assertTrue(transport.fatal)
        with self.assertRaises(ValueError): transport.request({'op': 'init'})
        self.assertEqual(len(raw.commands), 1)
        self.assertTrue(transport.request({'op': 'close'})['result']['closed'])

    def test_typed_server_rejects_raw_code_and_closes_without_loading_any_task(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/appworld_typed_bridge.py'
        commands = [[], {'op': 'execute', 'code': 'raise RuntimeError("must not execute")'},
                    {'op': 'call', 'call': {}}, {'op': 'close'}]
        run = subprocess.run([sys.executable, str(script)], input=''.join(json.dumps(x) + '\n' for x in commands),
                             capture_output=True, text=True, timeout=10, check=True)
        replies = [json.loads(line) for line in run.stdout.splitlines()]
        self.assertEqual([r['ok'] for r in replies], [False, False, False, True])
        self.assertEqual(replies[-1]['result'], {'closed': True})

    def test_failed_initialization_cannot_be_retried_or_followed_by_api_dispatch(self):
        def broken(_): raise TimeoutError('synthetic initialization interruption')
        raw = FixtureTransport(broken); transport = PublicResultTransport(raw)
        with self.assertRaises(TimeoutError): transport.request({'op': 'init'})
        self.assertTrue(transport.fatal)
        with self.assertRaises(ValueError): transport.request({'op': 'init'})
        ch = channel(transport); self.assertFalse(exchange(ch)['ok'])
        self.assertEqual(len(raw.commands), 1)
        self.assertFalse(ch.rows[0]['api_request_sent'])

    def test_process_transport_closes_the_real_typed_server_without_loading_a_task(self):
        with tempfile.TemporaryDirectory() as folder:
            process = TypedBridgeProcess(sys.executable, folder, folder)
            state = process.close()
            self.assertTrue(state['process_stopped']); self.assertTrue(state['graceful'])
            self.assertEqual(process.close(), state)

    def test_partial_reply_times_out_and_cannot_be_reused(self):
        real_popen = subprocess.Popen
        program = 'import sys,time\nsys.stdin.buffer.readline()\nsys.stdout.buffer.write(b"{\\\"ok\\\":")\nsys.stdout.buffer.flush()\ntime.sleep(30)'
        def fixture_popen(args, **kwargs):
            return real_popen([sys.executable, '-c', program], **kwargs)
        with tempfile.TemporaryDirectory() as folder, patch(
                'public_api_result_transport.subprocess.Popen', side_effect=fixture_popen):
            process = TypedBridgeProcess(sys.executable, folder, folder, timeout_seconds=.1)
            started = time.monotonic()
            try:
                with self.assertRaises(TimeoutError): process.request({'op': 'close'})
                self.assertLess(time.monotonic() - started, 2)
                with self.assertRaises(RuntimeError): process.request({'op': 'close'})
            finally:
                state = process.close()
            self.assertTrue(state['process_stopped']); self.assertFalse(state['graceful'])

    def test_outer_reply_duplicate_keys_are_not_accepted(self):
        real_popen = subprocess.Popen
        program = 'import sys\nsys.stdin.buffer.readline()\nprint(\'{"ok": false,"ok": true,"result": {}}\',flush=True)'
        def fixture_popen(args, **kwargs):
            return real_popen([sys.executable, '-c', program], **kwargs)
        with tempfile.TemporaryDirectory() as folder, patch(
                'public_api_result_transport.subprocess.Popen', side_effect=fixture_popen):
            process = TypedBridgeProcess(sys.executable, folder, folder)
            try:
                with self.assertRaises(InvalidExecutionEnvelope): process.request({'op': 'close'})
                self.assertTrue(process.failed)
            finally:
                self.assertTrue(process.close()['process_stopped'])


if __name__ == '__main__':
    unittest.main()
