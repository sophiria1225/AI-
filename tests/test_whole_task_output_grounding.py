"""The six-cell decision cannot convert missing usage or cheap failure to a win."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from whole_task_output_grounding import MODES, SEEDS, cell_id, run_order, summarize


def rows():
    return [dict(task_id='synthetic_CSV', replication=rep, model_seed=SEEDS[rep-1],
        grounding_mode=mode, run_id=cell_id(rep, number, mode), record_status='evaluated',
        success=True, known_total_tokens={'off':120, 'feedback':100, 'repair':80}[mode],
        unknown_usage_calls=0, grounding_repairs=int(mode == 'repair'),
        grounding_contract_failed=False, projection_contract_failed=False,
        grounding_accounting_complete=True) for rep, number, mode in run_order()]


class OutputGroundingGateTests(unittest.TestCase):
    def test_fixed_six_conditions_primary_feedback_baseline(self):
        self.assertEqual(run_order(), [(1,1,'off'),(1,1,'feedback'),(1,1,'repair'),
                                      (2,1,'repair'),(2,1,'feedback'),(2,1,'off')])
        result=summarize(rows(), [])
        self.assertTrue(result['development_gate_met'])
        self.assertEqual(result['repair_minus_feedback_whole_task_tokens'], -40)
        self.assertEqual(result['successful_repairs_on_primary_common_success'], 2)
        self.assertEqual((result['independent_tasks'],result['repetitions']), (1,2))

    def test_no_missing_unknown_or_audit_failure_is_hidden(self):
        for change in ({'success':False}, {'unknown_usage_calls':1},
            {'record_status':'unevaluated','success':None},
            {'record_status':'not_run','success':None,'known_total_tokens':None,'unknown_usage_calls':None}):
            sample=rows();sample[2].update(change)
            self.assertFalse(summarize(sample,[])['development_gate_met'])
        self.assertFalse(summarize(rows(),['synthetic'])['development_gate_met'])

    def test_quality_gain_is_separate_from_preserved_quality_token_saving(self):
        sample=rows()
        for row in sample:
            if row['grounding_mode']=='feedback': row.update(success=False,known_total_tokens=1)
        result=summarize(sample,[])
        self.assertEqual(result['comparisons']['feedback']['paired_success_gains'],2)
        self.assertFalse(result['development_gate_met'])

    def test_cheap_failure_cannot_pay_for_more_expensive_common_success(self):
        sample=rows()
        for row in sample:
            if row['replication']==1: row.update(success=False,known_total_tokens=1 if row['grounding_mode']=='repair' else 1000)
            elif row['grounding_mode']=='repair':row['known_total_tokens']=110
        result=summarize(sample,[])
        self.assertLess(result['repair_minus_feedback_whole_task_tokens'],0)
        self.assertGreater(result['paired_successful_token_difference'],0)
        self.assertFalse(result['development_gate_met'])

    def test_improvement_over_off_cannot_replace_the_stronger_feedback_baseline(self):
        sample=rows()
        for row in sample:
            if row['grounding_mode']=='repair':row['known_total_tokens']=110
        result=summarize(sample,[])
        self.assertLess(result['comparisons']['off']['repair_minus_baseline_whole_task_tokens'],0)
        self.assertFalse(result['development_gate_met'])

    def test_off_success_loss_also_blocks_adoption(self):
        sample=rows()
        for row in sample:
            if row['replication']==2 and row['grounding_mode']!='off':row['success']=False
        result=summarize(sample,[])
        self.assertEqual(result['comparisons']['feedback']['paired_success_losses'],0)
        self.assertEqual(result['comparisons']['off']['paired_success_losses'],1)
        self.assertFalse(result['development_gate_met'])

    def test_unmeasured_contracts_or_accounting_cannot_pass(self):
        for key,value in (('grounding_contract_failed',True),('projection_contract_failed',None),
                          ('grounding_accounting_complete',False),('grounding_accounting_complete',None)):
            sample=rows();sample[0][key]=value
            self.assertFalse(summarize(sample,[])['development_gate_met'])
        sample=rows()
        for row in sample:row['grounding_repairs']=0;row['grounding_sent_repairs']=1
        self.assertFalse(summarize(sample,[])['development_gate_met'])

    def test_seed_identity_and_all_planned_slots_are_required(self):
        sample=rows()
        for value in (57.0,157,257):
            changed=deepcopy(sample);changed[0]['model_seed']=value
            with self.assertRaises(ValueError):summarize(changed,[])
        with self.assertRaises(ValueError):summarize(sample[:-1],[])
        sample[-1]=deepcopy(sample[0])
        with self.assertRaises(ValueError):summarize(sample,[])


if __name__=='__main__':unittest.main()
