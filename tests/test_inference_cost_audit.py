from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_inference_costs import cohort_for, timing_row


class InferenceCostAuditTests(unittest.TestCase):
    def fixture(self):
        usage = {'id': 'call_001', 'role': 'ledger', 'status': 'ok',
                 'input_tokens': 100, 'output_tokens': 10, 'wall_seconds': 7}
        response = {**usage, 'cached_input_tokens': 40, 'message': 'PRIVATE',
                    'timings': {'cache_n': 40, 'prompt_n': 60, 'predicted_n': 10,
                                'prompt_ms': 2000, 'predicted_ms': 3000}}
        return usage, response

    def test_partition_and_separate_timings_without_text(self):
        usage, response = self.fixture()
        row = timing_row(usage, response)
        self.assertEqual(row['processed_input_tokens'], 60)
        self.assertEqual(row['prefill_seconds']+row['decode_seconds'], 5)
        self.assertNotIn('PRIVATE', str(row))

    def test_inconsistent_cache_counts_rejected(self):
        usage, response = self.fixture()
        response['timings']['prompt_n'] = 90
        with self.assertRaisesRegex(ValueError, 'partition'):
            timing_row(usage, response)

    def test_timeout_not_converted_to_zero_cost_or_zero_elapsed(self):
        usage, response = self.fixture()
        for obj in (usage, response):
            obj.update(status='error', input_tokens=None, output_tokens=None, wall_seconds=600)
        row = timing_row(usage, response)
        self.assertIsNone(row['prefill_seconds'])
        self.assertEqual(row['call_wall_seconds'], 600)

    def test_interrupted_run_is_not_silently_substituted_for_completed_cohort(self):
        plan = {'phase': 'P13', 'run_order': [['a', 'focus', 'original']]}
        with self.assertRaisesRegex(ValueError, 'explicit recovery'):
            cohort_for(plan)
        self.assertEqual(cohort_for(plan, {'cohort': [['a', 'focus', 'recovery']]})[0][2], 'recovery')
        with self.assertRaisesRegex(ValueError, 'changed task'):
            cohort_for(plan, {'cohort': [['b', 'focus', 'recovery']]})


if __name__ == '__main__':
    unittest.main()
