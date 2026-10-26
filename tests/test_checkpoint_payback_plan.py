"""Two-cell time-limited recovery keeps shared controls and unknown costs."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from whole_task_checkpoint_payback import fixed_fields,validate_plan,summarize,cell_id,run_order
import run_whole_task_checkpoint_payback as driver

def fixture():
    previous=json.loads((ROOT/'configs/P123_whole_task_rolling_checkpoint_v01.json').read_text())
    previous['known_tasks']=[t for t in previous['known_tasks'] if t['source_run']=='P29_04_CODE']
    plan={**previous,**fixed_fields()}
    for name in ('configs/P123_whole_task_rolling_checkpoint_v01.json',
        'scripts/empirical_checkpoint_payback.py','scripts/empirical_payback_inference.py',
        'scripts/run_whole_task_checkpoint_payback_cell.py','scripts/audit_whole_task_checkpoint_payback.py',
        'scripts/payback_server_identity.py','scripts/serve_research_model_recovery.py',
        'reports/P123_comparison.json','reports/P132_comparison.json',
        'docs/experiments/P133_whole_task_checkpoint_payback.md'):
        plan['source_sha256'][name]='a'*64
    return plan

def rows():
    return [dict(task_id='synthetic',run_id=cell_id(rep,1,mode),replication=rep,model_seed=seed,
        payback_mode=mode,record_status='evaluated',success=True,
        known_total_tokens=100 if mode=='rolling_separate' else 80,unknown_usage_calls=0,
        payback_rejections=int(mode=='empirical_payback'),payback_contract_failed=False,payback_accounting_complete=True)
        for rep,seed in ((1,57),(2,157)) for mode in ('rolling_separate','empirical_payback')]

class RecoveryTests(unittest.TestCase):
    def test_fixed_order_original_first_seed_and_finite_lease(self):
        plan=fixture();validate_plan(plan)
        self.assertEqual(run_order(),[(1,1,'rolling_separate'),(1,1,'empirical_payback'),(2,1,'empirical_payback'),(2,1,'rolling_separate')])
        self.assertEqual((plan['max_cells'],plan['server_max_lifetime_seconds']),(4,14400))
        for key,value in [('model_seeds',[157]),('max_cells',2),('server_max_lifetime_seconds',14401)]:
            with self.assertRaises(ValueError):validate_plan({**plan,key:value})
        with self.assertRaises(ValueError):cell_id(3,1,'rolling_separate')

    def test_unknown_failure_no_exposure_and_bad_contract_cannot_pass(self):
        self.assertTrue(summarize(rows(),[])['development_gate_met'])
        for key,value in [('success',False),('unknown_usage_calls',1),('known_total_tokens',101),
            ('payback_rejections',0),('payback_contract_failed',True),('payback_accounting_complete',None)]:
            sample=rows();sample[1][key]=value
            if key=='payback_rejections':sample[3][key]=value
            if key=='known_total_tokens':sample[3][key]=value
            self.assertFalse(summarize(sample,[])['development_gate_met'])
        sample=rows();sample[1].update(record_status='not_run',success=None,known_total_tokens=None,unknown_usage_calls=None)
        self.assertFalse(summarize(sample,[])['development_gate_met'])
        self.assertFalse(summarize(rows(),['synthetic'])['development_gate_met'])

    def test_six_count_requests_common_input_then_frozen_activation(self):
        plan=fixture();original=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
        prepared=[{**t,'public_task':{'instruction':'Synthetic only'}} for t in plan['known_tasks']]
        captured=[]
        def count(cfg,messages,tools,timeout):
            captured.append((deepcopy(cfg),deepcopy(messages),deepcopy(tools)))
            return dict(input_tokens=5000,wall_seconds=0)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'root';root.mkdir();(root/'reports').mkdir();storage=Path(temp)/'store';storage.mkdir()
            with patch.object(driver,'sources',return_value=(plan,original,[],prepared)), \
                 patch.object(driver,'launch_predecessor_closed',return_value={}), \
                 patch.object(driver,'frozen_hashes',return_value={'fixture':'a'*64}), \
                 patch.object(driver,'frozen_sources',return_value='b'*40), \
                 patch.object(driver,'live_identity',return_value=({'fixture':True},999999)), \
                 patch.object(driver,'check_resume',return_value={}), \
                 patch.object(driver,'count_input',side_effect=count), \
                 patch.object(driver,'count_summary_input',side_effect=count):
                pre=driver.preflight(storage,root)
                self.assertEqual((pre['input_count_requests'],pre['summary_input_count_requests']),(4,2))
                self.assertEqual(len(captured),6);self.assertEqual(captured[0],captured[1]);self.assertEqual(captured[2],captured[3])
                driver.activate(storage,root)
                self.assertTrue(json.loads((root/driver.ACTIVATION).read_text())['all_four_conditions_frozen_before_generation'])
                with self.assertRaises(FileExistsError):driver.preflight(storage,root)

if __name__=='__main__':unittest.main()
