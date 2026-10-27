"""Prospective gate tests: reject cheap failures, unknowns and empty success sets."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import whole_task_prefix_exposure_p138 as p


def rows():
    return [dict(task_id=str(n),prefix_exposure_mode=m,record_status='evaluated',success=True,
        known_total_tokens=90 if m=='prefix_exposure' else 100, unknown_usage_calls=0,
        prefix_exposure_contract_failed=False,prefix_exposure_accounting_complete=True,
        actual_decision_differences_from_rolling_separate=1,
        actual_decision_differences_from_fixed_interval=1) for n,m in p.run_order()]


class GateTests(unittest.TestCase):
    def test_prespecified_twelve_unique_rotated_slots(self):
        order=p.run_order()
        self.assertEqual(len(order),12)
        self.assertEqual(len({p.cell_id(n,m) for n,m in order}),12)
        self.assertEqual([m for n,m in order if n==2],['fixed_interval','prefix_exposure','rolling_separate'])

    def test_successful_savings_need_both_controls(self):
        out=p.summarize(rows(),[])
        self.assertTrue(out['development_gate_met'])
        self.assertEqual([c['all_task_token_difference'] for c in out['comparisons']],[-40,-40])

    def test_cheap_failure_cannot_qualify(self):
        data=rows(); cell=next(r for r in data if r['prefix_exposure_mode']=='prefix_exposure')
        cell.update(success=False,known_total_tokens=1)
        self.assertFalse(p.summarize(data,[])['development_gate_met'])

    def test_same_success_count_with_different_tasks_fails(self):
        data=rows()
        next(r for r in data if r['task_id']=='1' and r['prefix_exposure_mode']=='rolling_separate')['success']=False
        next(r for r in data if r['task_id']=='2' and r['prefix_exposure_mode']=='prefix_exposure')['success']=False
        self.assertFalse(p.summarize(data,[])['primary_utility_gate_met'])

    def test_unknown_remains_unknown(self):
        data=rows(); next(r for r in data if r['prefix_exposure_mode']=='prefix_exposure')['unknown_usage_calls']=1
        out=p.summarize(data,[])
        self.assertFalse(out['development_gate_met'])
        self.assertIsNone(out['comparisons'][0]['all_task_token_difference'])
        self.assertTrue(all(v is None for v in out['total_tokens_by_mode'].values()))

    def test_empty_success_effect_is_undefined(self):
        data=rows()
        for r in data:r['success']=False
        out=p.summarize(data,[])
        self.assertFalse(out['development_gate_met'])
        self.assertTrue(all(c['common_success_token_difference'] is None for c in out['comparisons']))

    def test_timing_control_can_block_mechanism_without_hiding_primary(self):
        data=rows()
        for r in data:
            if r['prefix_exposure_mode']=='fixed_interval':r['known_total_tokens']=80
        out=p.summarize(data,[])
        self.assertTrue(out['primary_utility_gate_met'])
        self.assertFalse(out['both_control_development_gate_met'])

    def test_missing_cell_is_not_zero_or_valid_complete_result(self):
        data=rows(); data[0].update(record_status='not_run',success=None,known_total_tokens=None,unknown_usage_calls=None)
        out=p.summarize(data,[])
        self.assertFalse(out['development_gate_met'])
        self.assertEqual(out['usage_count_missing_conditions'],1)
        with self.assertRaises(ValueError):p.summarize(data[:-1],[])

    def test_no_intervention_and_audit_errors_both_fail(self):
        data=rows()
        for r in data:r['actual_decision_differences_from_rolling_separate']=0
        self.assertFalse(p.summarize(data,[])['primary_utility_gate_met'])
        self.assertFalse(p.summarize(rows(),[{'type':'audit_error'}])['development_gate_met'])

    def test_known_usage_but_unfinished_exposure_count_cannot_pass(self):
        data=rows(); data[0]['prefix_exposure_accounting_complete']=False
        self.assertFalse(p.summarize(data,[])['primary_utility_gate_met'])


if __name__=='__main__':unittest.main()
