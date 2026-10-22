import copy
import json
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from profile_handoff_costs import summarize_calls, visible_characters


class CostProfileTests(unittest.TestCase):
    def fixtures(self):
        calls = [{'id': 'call_001', 'status': 'ok', 'input_tokens': 100,
                  'output_tokens': 7, 'cached_input_tokens': 60, 'wall_seconds': 3},
                 {'id': 'call_002', 'status': 'error', 'input_tokens': None,
                  'output_tokens': None, 'wall_seconds': 4}]
        responses = {'call_001': {'status': 'ok', 'input_tokens': 100, 'output_tokens': 7,
            'timings': {'cache_n': 60, 'prompt_n': 40, 'predicted_n': 7, 'prompt_ms': 500, 'predicted_ms': 1000}},
            'call_002': {'status': 'error'}}
        payload = {'messages': [{'role': 'system', 'content': 'sys'},
            {'role': 'user', 'content': 'task'},
            {'role': 'assistant', 'content': '', 'tool_calls': [{'function': {
                'name': 'run_python', 'arguments': json.dumps({'code': 'print(1)', 'span_ids': []})}}]},
            {'role': 'tool', 'content': json.dumps({'span_id': 's1', 'observation': {'stdout': 'private-value'}})}]}
        return calls, responses, payload

    def test_unknown_usage_not_zero_and_cache_separated(self):
        calls, responses, payload = self.fixtures()
        row = summarize_calls(calls, responses.__getitem__, lambda _: payload)
        self.assertEqual(row['totals']['known_total_tokens'], 107)
        self.assertEqual(row['totals']['unknown_usage_calls'], 1)
        self.assertEqual(row['totals']['processed_input_tokens'], 40)
        self.assertEqual(row['totals']['cached_input_tokens'], 60)
        self.assertEqual(row['totals']['unknown_call_wall_seconds'], 4)
        self.assertIsNone(row['calls'][1]['input_tokens'])
        self.assertNotIn('private-value', json.dumps(row))

    def test_cache_and_output_mismatch_rejected(self):
        for key in ('cache_n', 'predicted_n'):
            calls, responses, payload = self.fixtures()
            responses['call_001']['timings'][key] += 1
            with self.assertRaisesRegex(ValueError, 'totals mismatch'):
                summarize_calls(calls, responses.__getitem__, lambda _: payload)

    def test_response_token_mismatch_rejected(self):
        calls, responses, payload = self.fixtures()
        responses['call_001']['input_tokens'] += 1
        with self.assertRaisesRegex(ValueError, 'token mismatch'):
            summarize_calls(calls, responses.__getitem__, lambda _: payload)

    def test_missing_timings_are_unmeasured(self):
        calls, responses, payload = self.fixtures()
        del responses['call_001']['timings']
        row = summarize_calls(calls, responses.__getitem__, lambda _: payload)
        self.assertEqual(row['totals']['timed_calls'], 0)
        self.assertEqual(row['totals']['untimed_known_calls'], 1)
        self.assertIsNone(row['calls'][0]['cached_input_tokens'])

    def test_nested_sizes_not_double_counted(self):
        _, _, payload = self.fixtures()
        original = copy.deepcopy(payload)
        row = visible_characters(payload)
        self.assertEqual(row['nested_field_characters']['python_stdout'], len('private-value'))
        self.assertEqual(row['nested_field_characters']['python_code'], len('print(1)'))
        self.assertEqual(row['total_exposed_field_characters'], sum(row['exposed_field_characters'].values()))
        self.assertEqual(original, payload)

    def test_invalid_tool_json_remains_profileable(self):
        _, _, payload = self.fixtures()
        payload['messages'][2]['tool_calls'][0]['function']['arguments'] = '{bad'
        payload['messages'][3]['content'] = 'plain error text'
        row = visible_characters(payload)
        self.assertEqual(row['exposed_field_characters']['function_arguments'], 4)
        self.assertEqual(row['nested_field_characters']['python_code'], 0)


if __name__ == '__main__':
    unittest.main()
