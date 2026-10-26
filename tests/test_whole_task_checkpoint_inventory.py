"""Quality-preserving whole-job savings require complete paired evidence."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from whole_task_checkpoint_inventory import MODES,SEEDS,cell_id,run_order,summarize


def rows():
    return [dict(task_id='synthetic_CSV',replication=rep,model_seed=SEEDS[rep-1],
        inventory_mode=mode,grounding_mode='feedback',run_id=cell_id(rep,number,mode),
        record_status='evaluated',success=True,known_total_tokens=100 if mode=='off' else 80,
        unknown_usage_calls=0,inventory_notice_actor_calls=int(mode!='off'),
        inventory_contract_failed=False,grounding_contract_failed=False,
        projection_contract_failed=False,inventory_accounting_complete=True,
        grounding_accounting_complete=True) for rep,number,mode in run_order()]


class InventoryGateTests(unittest.TestCase):
    def test_common_success_and_whole_job_reduction_are_both_required(self):
        self.assertEqual(run_order(),[(1,1,'off'),(1,1,'checkpoint_inventory'),
                                     (2,1,'checkpoint_inventory'),(2,1,'off')])
        result=summarize(rows(),[])
        self.assertTrue(result['development_gate_met'])
        self.assertEqual(result['checkpoint_inventory_minus_off_whole_task_tokens'],-40)
        self.assertEqual(result['inventory_exposures_on_common_success'],2)
        self.assertEqual((result['independent_tasks'],result['repetitions']),(1,2))
        self.assertFalse(result['timing_superiority_claim'])
        self.assertFalse(result['novel_method_claim'])

    def test_unknown_missing_or_lost_success_is_not_a_saving(self):
        for changes in ({'unknown_usage_calls':1},{'success':False},
            {'record_status':'unevaluated','success':None},
            {'record_status':'not_run','success':None,'known_total_tokens':None,'unknown_usage_calls':None}):
            sample=rows();sample[1].update(changes)
            self.assertFalse(summarize(sample,[])['development_gate_met'])
        self.assertFalse(summarize(rows(),['synthetic error'])['development_gate_met'])

    def test_cheap_failed_tasks_cannot_pay_for_more_expensive_common_success(self):
        sample=rows()
        for row in sample:
            if row['replication']==1:
                row.update(success=False,known_total_tokens=1000 if row['inventory_mode']=='off' else 1)
            elif row['inventory_mode']!='off':row['known_total_tokens']=101
        result=summarize(sample,[])
        self.assertLess(result['checkpoint_inventory_minus_off_whole_task_tokens'],0)
        self.assertGreater(result['paired_successful_token_difference'],0)
        self.assertFalse(result['development_gate_met'])

    def test_quality_gains_without_common_success_do_not_establish_preserved_quality_savings(self):
        sample=rows()
        for row in sample:
            if row['inventory_mode']=='off':row['success']=False
        result=summarize(sample,[])
        self.assertEqual(result['paired_success_gains'],2)
        self.assertFalse(result['development_gate_met'])

    def test_only_actual_common_success_exposure_counts(self):
        for count in (0,None,True,-1):
            sample=rows()
            for row in sample:row['inventory_notice_actor_calls']=count
            self.assertFalse(summarize(sample,[])['development_gate_met'])

    def test_every_contract_and_accounting_flag_is_required(self):
        for key,value in (('inventory_contract_failed',True),('inventory_contract_failed',None),
            ('grounding_contract_failed',True),('projection_contract_failed',None),
            ('inventory_accounting_complete',False),('inventory_accounting_complete',None),
            ('grounding_accounting_complete',False)):
            sample=rows();sample[0][key]=value
            self.assertFalse(summarize(sample,[])['development_gate_met'])

    def test_fixed_repetitions_and_feedback_control(self):
        for key,value in (('model_seed',57.0),('model_seed',257),('replication',True),('grounding_mode','repair')):
            sample=rows();sample[0][key]=value
            with self.assertRaises(ValueError):summarize(sample,[])
        sample=rows();sample[-1]=deepcopy(sample[0])
        with self.assertRaises(ValueError):summarize(sample,[])
        with self.assertRaises(ValueError):summarize(rows()[:-1],[])

    def test_seed_costs_remain_visible_but_no_unplanned_each_seed_gate(self):
        sample=rows();sample[1]['known_total_tokens']=110;sample[2]['known_total_tokens']=70
        result=summarize(sample,[])
        self.assertTrue(result['development_gate_met'])
        self.assertEqual([p['checkpoint_inventory_minus_off_tokens'] for p in result['paired_results']],[10,-30])


if __name__=='__main__':unittest.main()
