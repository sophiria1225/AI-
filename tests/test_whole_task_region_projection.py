"""Fixed full-cohort gate: preserve task identity, usage and mechanism evidence."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from whole_task_region_projection import POLICIES, cell_id, run_order, summarize


def rows():
    return [dict(task_id=f'task_{n}', projection_policy=policy,
                 record_status='evaluated', success=True, unknown_usage_calls=0,
                 projection_contract_failed=False,
                 known_total_tokens=100 if policy == POLICIES[0] else 90,
                 projection_hits=int(n == 4 and policy == POLICIES[1]))
            for n, policy in run_order()]


class ProjectionPlanTests(unittest.TestCase):
    def test_fixed_order_and_valid_successful_activation_gate(self):
        self.assertEqual(run_order()[:4], [(1, POLICIES[0]), (1, POLICIES[1]),
                                          (2, POLICIES[1]), (2, POLICIES[0])])
        self.assertEqual(len({cell_id(n, p) for n, p in run_order()}), 8)
        result = summarize(rows(), [])
        self.assertTrue(result['development_gate_met'])
        self.assertEqual(result['paired_successful_token_difference'], -40)
        self.assertEqual(result['projection_hits_on_common_success'], 1)

    def test_no_quality_loss_unknown_usage_or_audit_failure_is_hidden(self):
        for change in ({'success': False}, {'unknown_usage_calls': 1},
                       {'record_status': 'unevaluated', 'success': None},
                       {'record_status': 'not_run', 'known_total_tokens': None, 'success': None}):
            sample = rows(); sample[1].update(change)
            self.assertFalse(summarize(sample, [])['development_gate_met'])
        self.assertFalse(summarize(rows(), [{'reason': 'synthetic audit failure'}])['development_gate_met'])

    def test_cheap_failures_or_unactivated_successes_cannot_pass(self):
        sample = rows()
        for row in sample:
            if row['task_id'] == 'task_4':
                row['success'] = False
        result = summarize(sample, [])
        self.assertEqual(result['projection_hits_on_common_success'], 0)
        self.assertFalse(result['development_gate_met'])
        sample = rows()
        for row in sample:
            row['projection_hits'] = 0
        self.assertFalse(summarize(sample, [])['development_gate_met'])

    def test_common_success_tokens_must_also_decrease(self):
        sample = rows()
        for row in sample:
            if row['task_id'] == 'task_1':
                row['success'] = False
                row['known_total_tokens'] = 1000 if row['projection_policy'] == POLICIES[0] else 1
            elif row['projection_policy'] == POLICIES[1]:
                row['known_total_tokens'] = 110
        result = summarize(sample, [])
        self.assertLess(result['automatic_region_joined_fields_minus_explicit_joined_fields_whole_task_tokens'], 0)
        self.assertGreater(result['paired_successful_token_difference'], 0)
        self.assertFalse(result['development_gate_met'])

    def test_missing_or_duplicate_planned_cells_are_rejected(self):
        sample = rows()
        with self.assertRaises(ValueError): summarize(sample[:-1], [])
        sample[-1] = deepcopy(sample[0])
        with self.assertRaises(ValueError): summarize(sample, [])

    def test_contract_failure_keeps_official_success_but_blocks_adoption(self):
        sample = rows(); sample[1]['projection_contract_failed'] = True
        result = summarize(sample, [])
        self.assertEqual(result['paired_successful_tasks'], 4)
        self.assertEqual(result['projection_contract_failure_cells'], 1)
        self.assertFalse(result['development_gate_met'])
        sample = rows(); del sample[0]['projection_contract_failed']
        result = summarize(sample, [])
        self.assertIsNone(result['projection_contract_failure_cells'])
        self.assertFalse(result['mechanism_contracts_intact'])
        self.assertFalse(result['development_gate_met'])
        sample = rows(); sample[1]['projection_hits'] = None
        result = summarize(sample, [])
        self.assertIsNone(result['projection_hits_on_common_success'])
        self.assertFalse(result['development_gate_met'])


if __name__ == '__main__':
    unittest.main()
