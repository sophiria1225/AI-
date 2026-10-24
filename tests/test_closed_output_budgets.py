import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_closed_output_budgets import count_response, text_size


class OutputBudgetCounts(unittest.TestCase):
    def setUp(self):
        self.r = dict(status='ok', output_tokens=8, done_reason='length',
            message={'reasoning_content':'abc', 'content':None,
                     'tool_calls':[{'function':{'arguments':'{"code":"x"}'}}]},
            usage_details={'completion_tokens':8})

    def test_unknown_is_not_zero_or_empty_output(self):
        v = count_response({'status':'error', 'message':{'content':''}}, 8)
        self.assertFalse(v['terminal_observed'])
        for k in ('output_tokens','at_requested_token_cap','reasoning_characters',
                  'content_characters','tool_calls','argument_characters'):
            self.assertIsNone(v[k])

    def test_total_cap_does_not_supply_reasoning_token_split(self):
        v = count_response(self.r, 8)
        self.assertTrue(v['at_requested_token_cap'])
        self.assertEqual(v['reasoning_characters'],3)
        self.assertEqual(v['argument_characters'],12)
        self.assertIsNone(v['terminal_reasoning_token_count'])

    def test_optional_count_receipt_is_checked(self):
        self.r['usage_details']['completion_tokens_details']={'reasoning_tokens':4}
        self.assertEqual(count_response(self.r,8)['terminal_reasoning_token_count'],4)
        self.r['usage_details']['completion_tokens_details']['reasoning_tokens']=9
        with self.assertRaises(ValueError): count_response(self.r,8)

    def test_cap_and_nontext_scope(self):
        with self.assertRaises(ValueError): count_response(self.r,7)
        with self.assertRaises(ValueError): text_size({'text':'secret'})
        self.assertEqual(text_size('日本語'),3)
        self.assertEqual(text_size(None),0)

    def test_does_not_mutate_message_or_export_text(self):
        before = copy.deepcopy(self.r)
        v = count_response(self.r,16)
        self.assertEqual(self.r,before)
        self.assertFalse(v['at_requested_token_cap'])
        self.assertNotIn('abc',v.values())


if __name__ == '__main__': unittest.main()
