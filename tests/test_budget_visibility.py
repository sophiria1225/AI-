import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_budget_visibility import budget_before_calls


class VisibilityAuditTests(unittest.TestCase):
    limits = {'max_api_requests': 10, 'max_calls': 3, 'max_total_tokens': 100}

    def test_prefix_and_only_sent_requests_reduce_remaining_budget(self):
        usage = [{'id': 'a', 'status': 'ok', 'input_tokens': 20, 'output_tokens': 5},
                 {'id': 'b', 'status': 'ok', 'input_tokens': 30, 'output_tokens': 7}]
        events = [{'call': 'a', 'api_request_sent': True},
                  {'call': 'a', 'api_request_sent': False}]
        rows, totals = budget_before_calls(usage, events, 4, self.limits)
        self.assertEqual([r['remaining_api_before'] for r in rows], [6, 5])
        self.assertEqual([r['remaining_tokens_before'] for r in rows], [100, 75])
        self.assertEqual(totals['known_total_tokens'], 62)

    def test_unknown_last_call_is_retained_without_zero_cost_claim(self):
        rows, totals = budget_before_calls([{'id': 'a', 'status': 'error'}], [], 0, self.limits)
        self.assertFalse(rows[0]['terminal_usage_known'])
        self.assertEqual(totals['unknown_usage_calls'], 1)

    def test_calls_or_actions_after_unknown_usage_fail_closed(self):
        unknown = {'id': 'a', 'status': 'error'}
        with self.assertRaises(ValueError):
            budget_before_calls([unknown, {**unknown, 'id': 'b'}], [], 0, self.limits)
        with self.assertRaises(ValueError):
            budget_before_calls([unknown], [{'call': 'a', 'api_request_sent': True}], 0, self.limits)


if __name__ == '__main__':
    unittest.main()
