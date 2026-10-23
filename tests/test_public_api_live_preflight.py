import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from preflight_public_api_live import RecordedBridge, confirm_initial_world
from public_api_envelope import PROTOCOL


class Raw:
    def __init__(self, error=None):
        self.timeout_seconds = 30
        self.calls = []
        self.error = error

    def request(self, command):
        self.calls.append((command, self.timeout_seconds))
        if self.error:
            raise self.error
        return {'ok': True, 'result': 'normal text'}


class PublicApiLivePreflightTests(unittest.TestCase):
    def test_program_deadline_bounds_io_and_restores_base_timeout(self):
        with tempfile.TemporaryDirectory() as folder:
            raw = Raw()
            bridge = RecordedBridge(raw, folder, 10.5, clock=lambda: 10)
            result = bridge.request({'op': 'call_typed'})
            self.assertEqual(raw.calls, [({'op': 'call_typed'}, .5)])
            self.assertEqual(raw.timeout_seconds, 30)
            record = json.loads((Path(folder) / 'bridge_01_private.json').read_text())
            self.assertEqual(record['response'], result)

    def test_expired_or_stopped_work_never_enters_raw_transport(self):
        for stopped in (False, True):
            with self.subTest(stopped=stopped), tempfile.TemporaryDirectory() as folder:
                raw = Raw()
                bridge = RecordedBridge(raw, folder, 20 if stopped else 9,
                                        clock=lambda: 10, stop=lambda: stopped)
                with self.assertRaises(InterruptedError if stopped else TimeoutError):
                    bridge.request({'op': 'call_typed'})
                self.assertEqual(raw.calls, [])
                record = json.loads((Path(folder) / 'bridge_01_private.json').read_text())
                self.assertFalse(record['raw_request_started'])

    def test_failure_is_recorded_once_without_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            raw = Raw(TimeoutError('unknown response after submission'))
            bridge = RecordedBridge(raw, folder, 11, clock=lambda: 10)
            with self.assertRaises(TimeoutError):
                bridge.request({'op': 'call_typed'})
            self.assertEqual(len(raw.calls), 1)
            self.assertEqual(raw.timeout_seconds, 30)
            record = json.loads((Path(folder) / 'bridge_01_private.json').read_text())
            self.assertTrue(record['raw_request_started'])
            self.assertEqual(record['error']['type'], 'TimeoutError')

    def test_initial_world_allows_only_protocol_addition_to_known_public_state(self):
        expected = {'instruction': 'known fixture', 'ground_truth_loaded': False}
        response = {'ok': True, 'result': {**expected, 'api_result_protocol': PROTOCOL}}
        self.assertEqual(confirm_initial_world(response, expected), expected)
        self.assertIn('api_result_protocol', response['result'])
        for change in ({'instruction': 'different task'}, {'ground_truth_loaded': True},
                       {'unexpected': 'extra state'}, {'api_result_protocol': 'old'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                confirm_initial_world({'ok': True, 'result': {**response['result'], **change}}, expected)


if __name__ == '__main__':
    unittest.main()
