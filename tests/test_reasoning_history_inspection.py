import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_reasoning_history import inspect_attempt


class ReasoningInspectionTests(unittest.TestCase):
    def test_metadata_counts_omitted_reasoning_without_exposing_it(self):
        previous = [{'role': 'assistant', 'content': 'public', 'reasoning_content': 'SECRET'}]
        request = {'messages': [{'role': 'assistant', 'content': 'public'}]}
        response = {'status': 'ok', 'message': previous[0]}
        row = inspect_attempt(request, response, previous, 'ok')
        self.assertEqual(row['preceding_reasoning_characters'], 6)
        self.assertEqual(row['restored_reasoning_characters'], 6)
        self.assertEqual(row['input_reasoning_characters'], 0)
        self.assertFalse(row['reasoning_fields_exactly_match_preceding'])
        self.assertNotIn('SECRET', str(row))

    def test_existing_reasoning_is_observed_not_overwritten(self):
        previous = [{'role': 'assistant', 'content': '', 'reasoning_content': 'SECRET'}]
        request = {'messages': copy.deepcopy(previous)}
        row = inspect_attempt(request, {'status': 'ok', 'message': previous[0]}, previous, 'ok')
        self.assertTrue(row['reasoning_fields_exactly_match_preceding'])
        self.assertFalse(row['restorable_without_overwrite'])
        self.assertIsNone(row['restored_reasoning_characters'])

    def test_unknown_terminal_usage_is_not_a_zero_length_generated_response(self):
        row = inspect_attempt({'messages': []}, {'status': 'error'}, [], 'error')
        self.assertIsNone(row['known_output_reasoning'])
        self.assertEqual(row['recorded_status'], 'error')

    def test_later_response_or_public_value_mismatch_is_rejected(self):
        response = {'status': 'ok', 'message': {'role': 'assistant', 'content': 'future'}}
        with self.assertRaises(ValueError):
            inspect_attempt({'messages': []}, response, [response['message']], 'ok')
        with self.assertRaises(ValueError):
            inspect_attempt({'messages': [{'role': 'assistant', 'content': 'different'}]},
                            response, [response['message']], 'ok')
        with self.assertRaises(ValueError):
            inspect_attempt({'messages': []}, response, [], 'error')


if __name__ == '__main__':
    unittest.main()
