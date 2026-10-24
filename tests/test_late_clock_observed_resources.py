from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from summarize_late_clock_observed_resources import difference


class NonnegativeMissingUsageTests(unittest.TestCase):
    def arm(self, known, missing):
        return {'known_logical_tokens': known, 'unknown_usage_calls': missing}

    def test_complete_receipts_give_exact_difference(self):
        result = difference(self.arm(50, 0), self.arm(100, 0), 'logical_tokens')
        self.assertEqual((result['kind'], result['value']), ('exact', -50))

    def test_negative_lower_bound_does_not_establish_saving(self):
        result = difference(self.arm(50, 1), self.arm(100, 0), 'logical_tokens')
        self.assertEqual((result['kind'], result['value']), ('lower_bound', -50))
        self.assertFalse(result['missing_usage_imputed'])
        self.assertGreater(50 + 75 - 100, 0)  # A possible missing amount reverses the sign.

    def test_positive_lower_bound_establishes_more_cost(self):
        result = difference(self.arm(150, 1), self.arm(100, 0), 'logical_tokens')
        self.assertEqual((result['kind'], result['value']), ('lower_bound', 50))

    def test_missing_baseline_gives_upper_not_lower_bound(self):
        result = difference(self.arm(150, 0), self.arm(100, 2), 'logical_tokens')
        self.assertEqual((result['kind'], result['value']), ('upper_bound', 50))

    def test_missing_both_sides_keeps_difference_unidentified(self):
        result = difference(self.arm(50, 1), self.arm(100, 2), 'logical_tokens')
        self.assertEqual(result['kind'], 'unidentified')
        self.assertIsNone(result['value'])
        self.assertEqual(result['known_subtotal_difference'], -50)
        self.assertGreater(50 + 100 - (100 + 0), 0)
        self.assertLess(50 + 0 - (100 + 100), 0)

    def test_zero_unknown_is_different_from_zero_known(self):
        result = difference(self.arm(0, 1), self.arm(0, 0), 'logical_tokens')
        self.assertEqual((result['kind'], result['value']), ('lower_bound', 0))


if __name__ == '__main__':
    unittest.main()
