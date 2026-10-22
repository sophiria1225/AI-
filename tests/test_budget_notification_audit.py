import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from analyze_budget_notification import validate_request
from budget_signal import add_notification, digest


class BudgetRequestAuditTests(unittest.TestCase):
    def fixture(self, arm='budget_keep'):
        base = [{'role': 'user', 'content': 'fixture task'}]
        state = {'remaining': {'api_calls': 20, 'model_calls': 4, 'logical_input_plus_output_tokens': 1000},
                 'used': {'continuation_logical_tokens': 2000}}
        messages = add_notification(base, state, arm)
        signal = {'notification_supplied': arm == 'budget_keep', 'state': state, 'cache_prompt': False,
                  'base_messages_sha256': digest(base), 'model_messages_sha256': digest(messages)}
        expected = {'remaining_api_before': 20, 'remaining_calls_before': 4, 'remaining_tokens_before': 1000, 'known_tokens_before': 2000}
        return {'messages': messages, 'cache_prompt': False}, signal, expected

    def test_model_must_receive_exactly_the_logged_signal(self):
        request, signal, expected = self.fixture()
        self.assertGreater(validate_request(request, signal, 'budget_keep', expected, True)['notification_characters'], 0)
        modified = copy.deepcopy(request); modified['messages'][-1]['content'] += ' extra'
        with self.assertRaises(ValueError):
            validate_request(modified, signal, 'budget_keep', expected, True)

    def test_remaining_counter_and_cache_policy_are_independently_checked(self):
        request, signal, expected = self.fixture()
        with self.assertRaises(ValueError):
            validate_request(request, signal, 'budget_keep', {**expected, 'remaining_api_before': 19}, True)
        with self.assertRaises(ValueError):
            validate_request({**request, 'cache_prompt': True}, signal, 'budget_keep', expected, True)

    def test_used_token_display_must_match_accounting(self):
        request, signal, expected = self.fixture()
        with self.assertRaises(ValueError):
            validate_request(request, signal, 'budget_keep', {**expected, 'known_tokens_before': 1999}, True)

    def test_control_receives_no_extra_notification(self):
        request, signal, expected = self.fixture('plain_keep')
        result = validate_request(request, signal, 'plain_keep', expected, True)
        self.assertEqual(result['notification_characters'], 0)


if __name__ == '__main__':
    unittest.main()
