import copy
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from handoff_output_views import ARMS
from output_view_decision import assess


class OutputGateTests(unittest.TestCase):
    def fixture(self):
        rows=[{'run_id':f'{t}_{a}','task_id':t,'arm':a,'success':True,
               'known_total_tokens':100 if a=='full_keep' else 75,'unknown_usage_calls':0}
               for t in ('a','b','c','d') for a in ARMS]
        return {'phase':'P33','all_twelve_reviewed':True,'audit_errors':[],'rows':rows},\
               {'status':'complete','completed':[r['run_id'] for r in rows]}

    def test_equal_counts_cannot_hide_a_lost_success(self):
        report,status=self.fixture()
        for r in report['rows']:
            if r['task_id']=='a' and r['arm']=='full_keep':r['success']=False
            if r['task_id']=='b' and r['arm']=='stdout_mask_keep':r['success']=False
        result=assess(report,status)['decisions']['stdout_mask_keep']
        self.assertEqual(result['baseline_successes_lost'],['b'])
        self.assertEqual(result['new_successes'],['a'])
        self.assertFalse(result['prespecified_descriptive_gate_passed'])

    def test_unknown_usage_prevents_exact_savings(self):
        report,status=self.fixture();report['rows'][1]['unknown_usage_calls']=1
        result=assess(report,status)['decisions']['stdout_mask_keep']
        self.assertFalse(result['prespecified_descriptive_gate_passed'])
        self.assertIsNone(result['total_token_change'])
        self.assertIsNone(result['token_change_fraction'])

    def test_cost_equal_is_not_saving_and_pass_is_not_quality_proof(self):
        report,status=self.fixture()
        result=assess(report,status)['decisions']['stdout_mask_keep']
        self.assertTrue(result['prespecified_descriptive_gate_passed'])
        self.assertFalse(result['quality_preservation_established'])
        self.assertFalse(result['novelty_established'])
        for r in report['rows']:r['known_total_tokens']=100
        self.assertFalse(assess(report,status)['decisions']['stdout_mask_keep']['prespecified_descriptive_gate_passed'])

    def test_partial_duplicate_or_malformed_cohort_fails(self):
        report,status=self.fixture()
        variants=[]
        r,s=copy.deepcopy(report),copy.deepcopy(status);r['rows'].pop();variants.append((r,s))
        r,s=copy.deepcopy(report),copy.deepcopy(status);s['completed'].append(s['completed'][0]);variants.append((r,s))
        r,s=copy.deepcopy(report),copy.deepcopy(status);r['rows'][0]['success']=1;variants.append((r,s))
        r,s=copy.deepcopy(report),copy.deepcopy(status);r['rows'][0]['known_total_tokens']=None;variants.append((r,s))
        for r,s in variants:
            with self.assertRaises(ValueError):assess(r,s)


if __name__=='__main__':unittest.main()
