"""Fixed full-cohort gate: preserve task identity, usage and mechanism evidence."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from whole_task_receipt_disclosure import MODES, SEEDS, cell_id, run_order, summarize


def rows():
    return [dict(task_id=f'task_{n}', receipt_mode=policy, replication=rep, model_seed=SEEDS[rep-1],
                 record_status='evaluated', success=True, unknown_usage_calls=0,
                 receipt_disclosure_contract_failed=False, projection_contract_failed=False,
                 known_total_tokens=100 if policy == MODES[0] else 90,
                 receipt_disclosures=int(n == 4 and policy == MODES[1]))
            for rep, n, policy in run_order()]


class DisclosurePlanTests(unittest.TestCase):
    def test_fixed_order_and_valid_successful_activation_gate(self):
        self.assertEqual(run_order()[:4], [(1, 1, MODES[0]), (1, 1, MODES[1]),
                                          (1, 2, MODES[1]), (1, 2, MODES[0])])
        self.assertEqual(len({cell_id(rep, n, p) for rep, n, p in run_order()}), 16)
        result = summarize(rows(), [])
        self.assertTrue(result['development_gate_met'])
        self.assertEqual(result['paired_successful_token_difference'], -80)
        self.assertEqual(result['receipt_disclosures_on_common_success'], 2)

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
        self.assertEqual(result['receipt_disclosures_on_common_success'], 0)
        self.assertFalse(result['development_gate_met'])
        sample = rows()
        for row in sample:
            row['receipt_disclosures'] = 0
        self.assertFalse(summarize(sample, [])['development_gate_met'])

    def test_common_success_tokens_must_also_decrease(self):
        sample = rows()
        for row in sample:
            if row['task_id'] == 'task_1':
                row['success'] = False
                row['known_total_tokens'] = 1000 if row['receipt_mode'] == MODES[0] else 1
            elif row['receipt_mode'] == MODES[1]:
                row['known_total_tokens'] = 110
        result = summarize(sample, [])
        self.assertLess(result['disclose_minus_full_whole_task_tokens'], 0)
        self.assertGreater(result['paired_successful_token_difference'], 0)
        self.assertFalse(result['development_gate_met'])

    def test_missing_or_duplicate_planned_cells_are_rejected(self):
        sample = rows()
        with self.assertRaises(ValueError): summarize(sample[:-1], [])
        sample[-1] = deepcopy(sample[0])
        with self.assertRaises(ValueError): summarize(sample, [])

    def test_contract_failure_keeps_official_success_but_blocks_adoption(self):
        sample = rows(); sample[1]['receipt_disclosure_contract_failed'] = True
        result = summarize(sample, [])
        self.assertEqual(result['paired_successful_tasks'], 8)
        self.assertEqual(result['receipt_disclosure_contract_failure_cells'], 1)
        self.assertFalse(result['development_gate_met'])
        sample = rows(); del sample[0]['receipt_disclosure_contract_failed']
        result = summarize(sample, [])
        self.assertIsNone(result['receipt_disclosure_contract_failure_cells'])
        self.assertFalse(result['mechanism_contracts_intact'])
        self.assertFalse(result['development_gate_met'])
        sample = rows(); sample[1]['receipt_disclosures'] = None
        result = summarize(sample, [])
        self.assertIsNone(result['receipt_disclosures_on_common_success'])
        self.assertFalse(result['development_gate_met'])

    def test_seed_specific_regression_cannot_hide_behind_aggregate_gain(self):
        sample = rows()
        for row in sample:
            if row['receipt_mode'] == 'disclose':
                row['known_total_tokens'] = 1 if row['replication'] == 1 else 101
        result = summarize(sample, [])
        self.assertLess(result['disclose_minus_full_whole_task_tokens'], 0)
        self.assertFalse(result['development_gate_met'])

    def test_replications_do_not_masquerade_as_independent_tasks(self):
        result = summarize(rows(), [])
        self.assertEqual((result['independent_tasks'], result['repetitions']), (4, 2))
        self.assertEqual([r['model_seed'] for r in result['per_seed']], [57, 157])
        sample = rows(); sample[0]['model_seed'] = 257
        with self.assertRaises(ValueError): summarize(sample, [])

    def test_shared_runtime_contract_failure_blocks_the_gate(self):
        for value in (True, None):
            sample = rows(); sample[0]['projection_contract_failed'] = value
            result = summarize(sample, [])
            self.assertFalse(result['mechanism_contracts_intact'])
            self.assertFalse(result['development_gate_met'])


if __name__ == '__main__':
    unittest.main()
