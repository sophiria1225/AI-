import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from recorded_usage_intervals import analyze_cell, difference, summarize


def fixture(unknown=True):
    usage = [dict(id='call_001', status='ok', predicted_input_tokens=10,
                  output_cap=20, input_tokens=10, output_tokens=5)]
    if unknown:
        usage.append(dict(id='call_002', status='error', predicted_input_tokens=30,
                          output_cap=20, input_tokens=None, output_tokens=None))
    checks = [dict(call_id=c['id'], status=c['status'], request_sha256='fixture-request',
                   response_sha256='fixture-response', terminal_usage_recorded=True) for c in usage]
    original = dict(run_id='fixture', task_id='task', notice_policy='none', success=False,
        record_status='evaluated', stop_reason='wall_limit', model_calls=len(usage),
        api_requests=3, known_total_tokens=15, unknown_usage_calls=int(unknown),
        usage_sha256='fixture-usage', request_checks=checks)
    return (original, usage, {c['id']: c['output_cap'] for c in usage},
            dict(context_tokens=64, output_tokens=20, cell_tokens=100, max_calls=4))


class RecordedUsageIntervalsTests(unittest.TestCase):
    def test_error_receipt_is_not_known_usage_and_lower_zero_is_not_imputation(self):
        original, usage, caps, limits = fixture()
        before = copy.deepcopy((original, usage))
        row = analyze_cell(original, usage, caps, limits)
        self.assertEqual(row['conditional_request_interval'], [15, 65])
        self.assertEqual(row['conditional_context_interval'], [15, 79])
        self.assertIsNone(row['calls'][-1]['observed_logical_tokens'])
        self.assertTrue(row['calls'][-1]['terminal_record_present'])
        self.assertEqual((original, usage), before)

    def test_known_terminal_bound_failure_is_not_discarded(self):
        for key, value in [('input_tokens', 11), ('output_tokens', 21)]:
            original, usage, caps, limits = fixture()
            usage[0][key] = value
            with self.assertRaisesRegex(ValueError, 'violates_proposed_bound'):
                analyze_cell(original, usage, caps, limits)

    def test_missing_count_or_request_cap_cannot_get_default_upper_bound(self):
        for key in ('predicted_input_tokens', 'output_cap'):
            original, usage, caps, limits = fixture()
            usage[-1].pop(key)
            with self.assertRaises(ValueError):
                analyze_cell(original, usage, caps, limits)
        original, usage, caps, limits = fixture()
        caps['call_002'] = 21
        with self.assertRaisesRegex(ValueError, 'reservation_mismatch'):
            analyze_cell(original, usage, caps, limits)

    def test_context_limit_and_residual_budget_are_both_enforced(self):
        original, usage, caps, limits = fixture()
        limits['context_tokens'] = 49
        with self.assertRaisesRegex(ValueError, 'reservation_mismatch'):
            analyze_cell(original, usage, caps, limits)
        limits['context_tokens'] = 64
        limits['cell_tokens'] = 52
        with self.assertRaisesRegex(ValueError, 'reservation_mismatch'):
            analyze_cell(original, usage, caps, limits)
        usage[-1]['output_cap'] = caps['call_002'] = 7
        self.assertEqual(analyze_cell(original, usage, caps, limits)['conditional_request_interval'], [15, 52])

    def test_failed_attempt_cannot_be_imputed_or_retried(self):
        original, usage, caps, limits = fixture()
        usage[-1]['input_tokens'] = 0
        with self.assertRaisesRegex(ValueError, 'remain_unknown'):
            analyze_cell(original, usage, caps, limits)
        original, usage, caps, limits = fixture()
        usage[0].update(status='error', input_tokens=None, output_tokens=None)
        original['request_checks'][0]['status'] = 'error'
        with self.assertRaisesRegex(ValueError, 'remain_unknown'):
            analyze_cell(original, usage, caps, limits)

    def test_missing_reordered_and_duplicate_slots_rejected(self):
        for change in ('missing', 'reordered', 'duplicate'):
            original, usage, caps, limits = fixture()
            if change == 'missing': usage.pop()
            elif change == 'reordered': usage.reverse()
            else: usage[-1]['id'] = 'call_001'
            with self.assertRaises(ValueError):
                analyze_cell(original, usage, caps, limits)

    def test_original_cost_or_unknown_count_cannot_change(self):
        for key in ('known_total_tokens', 'unknown_usage_calls'):
            original, usage, caps, limits = fixture()
            original[key] += 1
            with self.assertRaisesRegex(ValueError, 'accounting_totals_changed'):
                analyze_cell(original, usage, caps, limits)

    def test_difference_extremes_are_attainable_without_independence(self):
        for left, right in [([3, 7], [1, 2]), ([1, 2], [3, 7]),
                            ([1, 4], [2, 6]), ([2, 2], [2, 2])]:
            attainable = [a - b for a in range(left[0], left[1] + 1)
                          for b in range(right[0], right[1] + 1)]
            self.assertEqual(difference(left, right)['bounds'], [min(attainable), max(attainable)])
        self.assertEqual(difference([3, 3], [1, 3])['sign_under_assumptions'], 'not_identified')
        self.assertEqual(difference([4, 7], [1, 3])['sign_under_assumptions'], 'positive')

    def test_all_tasks_policies_and_outcomes_preserved(self):
        rows = []
        for task in ('success', 'failure'):
            for policy in ('none', 'generic', 'factual'):
                args = fixture(unknown=task == 'failure' and policy != 'factual')
                args[0].update(task_id=task, notice_policy=policy, success=task == 'success')
                rows.append(analyze_cell(*args))
        result = summarize(rows, ['success', 'failure'], ['none', 'generic', 'factual'])
        self.assertEqual(len(result['all_task_differences']), 6)
        self.assertEqual(len(result['whole_cohort_differences']), 3)
        self.assertEqual([x['successes'] for x in result['totals']], [1, 1, 1])
        self.assertEqual(result['all_conditions']['unknown_usage_attempts'], 2)
        for subset in (rows[:-1], rows[:-1] + [rows[0]]):
            with self.assertRaisesRegex(ValueError, 'cartesian_product'):
                summarize(subset, ['success', 'failure'], ['none', 'generic', 'factual'])


if __name__ == '__main__':
    unittest.main()
