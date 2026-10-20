"""Accounting controls; these tests do not measure model ability."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from local_llama import parse_response, payload_for


class UsageControls(unittest.TestCase):
    def setUp(self):
        self.raw = {'usage': {'prompt_tokens': 100, 'completion_tokens': 15, 'total_tokens': 115,
                             'prompt_tokens_details': {'cached_tokens': 90}},
                    'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant',
                                'content': '42', 'reasoning_content': 'fixture reasoning'}}]}

    def test_cached_tokens_are_not_subtracted(self):
        result = parse_response(self.raw)
        self.assertEqual(result['input_tokens'] + result['output_tokens'], 115)
        self.assertEqual(result['cached_input_tokens'], 90)

    def test_reasoning_is_preserved_without_recounting_text(self):
        result = parse_response(self.raw)
        self.assertEqual(result['output_tokens'], 15)
        self.assertIn('reasoning_content', result['message'])

    def test_missing_usage_is_not_zero(self):
        del self.raw['usage']['completion_tokens']
        with self.assertRaises(ValueError):
            parse_response(self.raw)

    def test_inconsistent_total_is_rejected(self):
        self.raw['usage']['total_tokens'] = 25
        with self.assertRaises(ValueError):
            parse_response(self.raw)

    def test_boolean_counter_is_not_an_integer_measurement(self):
        self.raw['usage']['prompt_tokens'] = True
        with self.assertRaises(ValueError):
            parse_response(self.raw)

    def test_unfinished_tool_call_keeps_length_stop(self):
        self.raw['choices'][0]['finish_reason'] = 'length'
        self.raw['choices'][0]['message']['tool_calls'] = [{'function': {'arguments': '{'}}]
        self.assertEqual(parse_response(self.raw)['done_reason'], 'length')

    def test_template_receives_tools_and_thinking_mode(self):
        config = dict(model='fixture', temperature=1, seed=7, num_predict=64, thinking_mode='enabled')
        message = {'role': 'assistant', 'content': '', 'reasoning_content': 'reason', 'extra': {'private': 'metadata'}}
        tools = [{'type': 'function', 'function': {'name': 'bash'}}]
        result = payload_for(config, [message], tools)
        self.assertEqual(result['tools'], tools)
        self.assertEqual(result['messages'][0]['reasoning_content'], 'reason')
        self.assertNotIn('extra', result['messages'][0])
        self.assertEqual(result['chat_template_kwargs']['thinking_mode'], 'enabled')


if __name__ == '__main__':
    unittest.main()
