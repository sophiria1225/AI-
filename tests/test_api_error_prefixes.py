import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from compare_api_error_prefixes import compare, signature


def row(status, value, arm='error_value', complete=False):
    observation = {'api_error': value} if status == 'raised' and arm == 'error_exception' else {
        'observation': json.dumps(value)}
    event = {'api_execution': {'status': status, 'declared_complete': complete}}
    span = {'action': {'name': 'fixture__call', 'arguments': '{"x": 1}'}, 'observation': observation}
    return {'api': 'fixture__call', 'call_id': 'call_001', 'status': status,
            'signature': signature(event, span, arm)}


class ApiErrorPrefixTests(unittest.TestCase):
    def test_normalize_only_confirmed_exception_not_similar_string_value(self):
        value = row('raised', 'ValueError: fixture')
        raised = row('raised', 'ValueError: fixture', 'error_exception')
        normal = row('returned', 'ValueError: fixture')
        self.assertEqual(value['signature'], raised['signature'])
        self.assertNotEqual(value['signature'], normal['signature'])
        paired = compare([value], [raised])
        self.assertEqual(paired['first_matched_invocation_exception_api_index'], 1)
        self.assertFalse(paired['model_inputs_or_python_state_proven_equal'])

    def test_stop_at_first_difference_without_realignment(self):
        same = row('returned', {'success': False})
        a, b = row('returned', 2), row('returned', 3)
        paired = compare([same, a, same], [same, b, same])
        self.assertEqual(paired['matched_initial_api_requests_and_results'], 1)
        self.assertFalse(paired['whole_public_api_sequences_equal'])

    def test_unknown_result_or_different_completion_is_not_matched(self):
        unknown = row('unknown', 'unknown')
        self.assertEqual(compare([unknown], [unknown])['matched_initial_api_requests_and_results'], 0)
        self.assertEqual(compare([row('returned', None)], [row('returned', None, complete=True)])[
            'matched_initial_api_requests_and_results'], 0)


if __name__ == '__main__':
    unittest.main()
