import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_repetition_usage_intervals import interval_calls, summarize
from inspect_budget_visibility_usage_bounds import parse_numeric_log
from test_budget_visibility_usage_bounds import calls, KNOWN, CANCELLED


def fixture():
    values = calls()
    for i, c in enumerate(values):
        c.update(repetition=1, task_id='task', success=False,
                 time_visibility=('measured', 'not_exposed')[i])
    requests = [{'stream': False, 'max_tokens': 8} for _ in values]
    return values, parse_numeric_log(KNOWN + CANCELLED), requests


class RepetitionIntervalTests(unittest.TestCase):
    def test_keeps_unknown_and_bounds_accepted_output_not_release_cache(self):
        values, tasks, requests = fixture()
        before = copy.deepcopy((values, tasks, requests))
        rows, checked = interval_calls(values, tasks, requests)
        self.assertEqual(checked, 1)
        self.assertEqual([(r['logical_tokens_lower_bound'], r['logical_tokens_upper_bound'])
                          for r in rows], [(5, 5), (11, 15)])
        self.assertFalse(rows[1]['complete_usage'])
        self.assertFalse(rows[1]['terminal_usage_imputed'])
        self.assertEqual((values, tasks, requests), before)

    def test_refuses_missing_shadowed_or_mismatched_request_caps(self):
        for change in ({'max_tokens': 7}, {'max_tokens': True}, {'n_predict': 100},
                       {'max_completion_tokens': 100}, {'n': 2}, {'n_cmpl': 1}, {'stream': True}):
            values, tasks, requests = fixture()
            requests[1].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                interval_calls(values, tasks, requests)
        values, tasks, requests = fixture()
        with self.assertRaises(ValueError):
            interval_calls(values, tasks, requests[:1])

    def test_refuses_receipt_imputation_and_known_cap_violation(self):
        values, tasks, requests = fixture()
        values[1]['output_tokens'] = 0
        with self.assertRaises(ValueError):
            interval_calls(values, tasks, requests)
        values, tasks, requests = fixture()
        values[0]['output_cap'] = requests[0]['max_tokens'] = 1
        with self.assertRaises(ValueError):
            interval_calls(values, tasks, requests)

    def test_failure_cost_is_retained_and_signed_interval_is_propagated(self):
        rows, _ = interval_calls(*fixture())
        successes = copy.deepcopy(rows)
        for row in successes:
            row.update(task_id='success', success=True)
        result = summarize(rows + successes)
        self.assertEqual(result['total']['H_minus_M'], [12, 20])
        self.assertEqual(result['both_failure']['H_minus_M'], [6, 10])
        self.assertEqual(result['both_success']['H_minus_M'], [6, 10])
        self.assertEqual(result['total']['original_unknown_usage_calls'], 2)
        self.assertEqual(result['both_failure']['task_pairs'], 1)
        self.assertEqual(result['discordant']['task_pairs'], 0)

    def test_discordant_or_missing_quality_is_not_a_success_pair(self):
        rows, _ = interval_calls(*fixture())
        rows[0]['success'] = True
        result = summarize(rows)
        self.assertEqual(result['discordant']['task_pairs'], 1)
        self.assertEqual(result['both_success']['task_pairs'], 0)
        with self.assertRaises(ValueError):
            summarize(rows[:1])
        rows[0]['success'] = None
        with self.assertRaises(ValueError):
            summarize(rows)


if __name__ == '__main__':
    unittest.main()
