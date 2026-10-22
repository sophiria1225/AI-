import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_inventory_comparison import development_gate
from inventory_display import ARMS


class InventoryGateTests(unittest.TestCase):
    def rows(self):
        return [{'task_id': str(task), 'arm': arm, 'record_status': 'evaluated',
            'success': True, 'known_total_tokens': cost, 'logical_task_known_total_tokens': cost + 100,
            'unknown_usage_calls': 0, 'logical_task_unknown_usage_calls': 0,
            'inventory_input_changed': task != 3}
            for task in range(1, 5) for arm, cost in zip(ARMS, (200, 100, 120), strict=True)]

    def test_lower_cost_same_success_does_not_alone_prove_inventory_advantage(self):
        report = development_gate(self.rows())
        self.assertTrue(report['development_gate_met'])
        self.assertFalse(report['inventory_advantage_supported'])
        self.assertEqual(report['contrasts'][ARMS[0]]['candidate_minus_control_work_tokens'], -400)

    def test_changed_inventory_success_gain_is_required(self):
        rows = self.rows()
        for row in rows:
            if row['task_id'] == '1' and row['arm'] == ARMS[2]: row['success'] = False
        self.assertTrue(development_gate(rows)['inventory_advantage_supported'])
        rows = self.rows()
        for row in rows:
            if row['task_id'] == '3' and row['arm'] == ARMS[2]: row['success'] = False
        self.assertTrue(development_gate(rows)['development_gate_met'])
        self.assertFalse(development_gate(rows)['inventory_advantage_supported'])

    def test_any_unknown_missing_or_quality_loss_blocks_adoption(self):
        for change in ({'unknown_usage_calls': 1, 'logical_task_unknown_usage_calls': 1},
                       {'record_status': 'not_run_after_stop', 'success': None},
                       {'success': False}):
            rows = self.rows(); rows[1].update(change)
            self.assertFalse(development_gate(rows)['development_gate_met'])

    def test_lower_cost_due_to_lost_success_and_unknown_prefix_are_not_savings(self):
        rows = self.rows(); rows[1].update(success=False, logical_task_known_total_tokens=1)
        self.assertFalse(development_gate(rows)['development_gate_met'])
        rows = self.rows(); rows[0]['logical_task_unknown_usage_calls'] = 1
        self.assertFalse(development_gate(rows)['development_gate_met'])

    def test_no_budget_reduction_against_full_or_more_cost_than_both_fails(self):
        for index, value in ((1, 500), (2, 1)):
            rows = self.rows(); rows[index]['logical_task_known_total_tokens'] = value
            self.assertFalse(development_gate(rows)['development_gate_met'])

    def test_missing_duplicate_and_nonboolean_results_are_rejected(self):
        for rows in (self.rows()[:-1], self.rows() + [copy.deepcopy(self.rows()[0])]):
            with self.assertRaises(ValueError): development_gate(rows)
        rows = self.rows(); rows[0]['success'] = 1
        with self.assertRaises(ValueError): development_gate(rows)


if __name__ == '__main__': unittest.main()
