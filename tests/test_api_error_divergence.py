import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from api_error_comparison import add_notification
from inspect_api_error_divergence import describe_pair, without_wall_snapshot


def record(seconds=100, argument='{}', ident='a'):
    state = {'remaining': {'wall_seconds_at_snapshot': seconds, 'api_calls': 8}}
    return {'request': {'seed': 51, 'messages': add_notification([{'role': 'user', 'content': 'fixture'}], state)},
            'state': state, 'response': {'status': 'ok', 'done_reason': 'tool_calls',
                'message': {'content': '', 'tool_calls': [{'id': ident,
                    'function': {'name': 'fixture', 'arguments': argument}}]}}}


class ApiErrorDivergenceTests(unittest.TestCase):
    def test_normalizes_only_current_measured_wall_snapshot(self):
        a, b = record(100), record(99)
        result = describe_pair([a], [b], [None, None])
        self.assertFalse(result['actual_request_structures_equal'])
        self.assertTrue(result['requests_equal_after_only_wall_snapshot_normalization'])
        self.assertTrue(result['divergence_before_any_API_exception'])
        b['request']['seed'] = 52
        self.assertFalse(describe_pair([a], [b], [None, None])[
            'requests_equal_after_only_wall_snapshot_normalization'])
        self.assertEqual(a['state']['remaining']['wall_seconds_at_snapshot'], 100)

    def test_transport_ids_do_not_hide_real_public_output_difference(self):
        a, b = record(ident='a'), record(ident='b')
        self.assertIsNone(describe_pair([a], [b], [None, None])['first_unmatched_call'])
        b['response']['message']['tool_calls'][0]['function']['arguments'] = '{"x": 1}'
        result = describe_pair([a, a], [a, b], [1, None])
        self.assertEqual(result['first_unmatched_call'], 2)
        self.assertFalse(result['divergence_before_any_API_exception'])

    def test_mismatched_notice_and_unknown_response_are_not_equality(self):
        a, b = record(), record()
        changed = copy.deepcopy(a['state']); changed['remaining']['api_calls'] = 9
        with self.assertRaises(ValueError): without_wall_snapshot(a['request'], changed)
        b['response']['status'] = 'error'
        self.assertEqual(describe_pair([a], [b], [None, None])['reason'], 'unknown_response')


if __name__ == '__main__':
    unittest.main()
