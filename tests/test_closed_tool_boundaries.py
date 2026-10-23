import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_closed_tool_boundaries import classify_response


class ClosedToolBoundaryTests(unittest.TestCase):
    def response(self, arguments, reason='length'):
        return dict(status='ok', done_reason=reason, output_tokens=12,
                    message=dict(tool_calls=[dict(function=dict(arguments=a)) for a in arguments]))

    def test_partial_member_does_not_become_valid(self):
        result = classify_response(self.response(['{"code":"unfinished', '{"code":"pass"}']))
        self.assertEqual(result['invalid_json_arguments'], 1)
        self.assertEqual(result['tool_calls'], 2)
        self.assertTrue(result['fallback_eligible'])

    def test_valid_nonobject_still_requires_original_fallback(self):
        result = classify_response(self.response(['[]', 'null']))
        self.assertEqual(result['invalid_json_arguments'], 0)
        self.assertEqual(result['nonobject_arguments'], 2)
        self.assertTrue(result['fallback_eligible'])

    def test_length_does_not_itself_imply_invalid_arguments(self):
        result = classify_response(self.response(['{"code":"pass"}']))
        self.assertFalse(result['fallback_eligible'])
        self.assertEqual(result['finish_reason'], 'length')

    def test_error_is_unobserved_not_empty_valid_completion(self):
        result = classify_response(dict(status='error', message=dict(tool_calls=[])))
        self.assertIsNone(result['fallback_eligible'])
        self.assertIsNone(result['output_tokens'])
        self.assertIsNone(result['tool_calls'])
        self.assertFalse(result['terminal_observed'])


if __name__ == '__main__':
    unittest.main()
