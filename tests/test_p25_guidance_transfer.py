import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run_native_appworld as runner
import run_native_batch as batch
from audit_native_boundaries import audit as audit_boundaries
from audit_native_execution import audit as audit_execution
import test_p18_plan as fixture


class P25GuidanceTransfer(unittest.TestCase):
    def plan(self):
        return json.loads((ROOT/'configs/P25_guidance_transfer_v01.json').read_text())

    def test_keeps_all_four_p18_tasks_and_prior_guidance(self):
        plan=self.plan();batch.validate_schedule(plan);batch.check_p25_activation(plan)
        p24=json.loads((ROOT/'configs/P24_generic_guidance_v01.json').read_text())
        self.assertEqual(runner.system_prompt_for(plan),runner.system_prompt_for(p24))
        self.assertEqual(len(plan['run_order']),4)
        for key,value in [('max_api_requests',81),('seed',43),
                          ('general_guidance_version','changed'),('ordinary_compute',{})]:
            changed=copy.deepcopy(plan);changed[key]=value
            with self.assertRaises(ValueError):batch.check_p25_activation(changed)
        for tasks in (list(reversed(plan['task_ids'])),plan['task_ids'][:2],
                      ['aa8502b_1',*plan['task_ids'][1:]]):
            changed=copy.deepcopy(plan);changed['task_ids']=tasks
            with self.assertRaises(ValueError):batch.validate_schedule(changed)

    def test_runtime_requests_and_audits_match_p24_guidance(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);helper=fixture.P18Controls()
            updates=dict(arms=['native_guided'],general_guidance_version='appworld_public_rules_v1')
            old,old_sent,old_requests=helper.run_fixture(root/'old','P24',config_updates=updates)
            new,new_sent,new_requests=helper.run_fixture(root/'new','P25',config_updates=updates)
            self.assertEqual(old_sent,new_sent)
            self.assertEqual(old_requests,new_requests)
            for key in ('model_calls','api_requests','boundary_records','stop_reason'):
                self.assertEqual(old[key],new[key])
            trial=root/'new/storage/records/context_pilot/P25_FIXTURE'
            self.assertEqual(audit_boundaries(trial,root/'new/world')['audit_errors'],[])
            result=audit_execution(trial)
            for key in ('audit_errors','dispatch_audit_errors','history_audit_errors'):
                self.assertEqual(result[key],[])

    def test_progress_uses_dedicated_issue(self):
        self.assertEqual(batch.PHASES['P25']['issue'],120)
        body=batch.public_body([dict(task_number=1,status='running',instruction='PRIVATE')],
                               dict(status='running',phase='P25'))
        self.assertNotIn('PRIVATE',body)
        self.assertIn('P18',body)


if __name__=='__main__':
    unittest.main()
