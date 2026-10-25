from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_rolling_checkpoint_plan import synthetic_plan
import run_whole_task_rolling_checkpoint as driver

ROOT = Path(__file__).resolve().parents[1]


class RollingPreflightTests(unittest.TestCase):
    def test_all_initial_inputs_and_twelve_recurrent_templates_counted_before_activation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'root'; root.mkdir()
            (root/'reports').mkdir()
            storage = Path(folder)/'storage'; storage.mkdir()
            plan = synthetic_plan()
            original = json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
            original['api_budget_by_task'] = {t['task_id']:160 if i==0 else 80
                                             for i,t in enumerate(plan['known_tasks'])}
            prepared = [{**t,'public_task':{'instruction':'Synthetic task only.'}} for t in plan['known_tasks']]
            captured=[]

            def count(cfg,messages,tools,timeout):
                captured.append((deepcopy(cfg),deepcopy(messages),deepcopy(tools)))
                return {'input_tokens':5000,'wall_seconds':0}

            with patch.object(driver,'sources',return_value=(plan,original,[],prepared)), \
                 patch.object(driver,'frozen_hashes',return_value={'synthetic':'a'*64}), \
                 patch.object(driver,'frozen_sources',return_value='b'*40), \
                 patch.object(driver,'live_identity',return_value=({'synthetic':True},999999)), \
                 patch.object(driver,'check_resume',return_value={'synthetic':True}), \
                 patch.object(driver,'count_input',side_effect=count), \
                 patch.object(driver,'count_summary_input',side_effect=count):
                result=driver.preflight(storage,root)
                self.assertEqual(result['status'],'complete')
                self.assertEqual(len(captured),24)
                self.assertEqual(result['input_count_requests'],12)
                self.assertEqual(result['summary_input_count_requests'],3)
                self.assertEqual(result['inline_input_count_requests'],9)
                self.assertEqual(result['model_generations'],0)
                self.assertEqual(result['environment_api_requests'],0)
                self.assertEqual(result['evaluator_calls'],0)
                for start in range(0,12,3):
                    self.assertEqual(captured[start],captured[start+1])
                    self.assertEqual(captured[start],captured[start+2])
                driver.activate(storage,root)
                activation=json.loads((root/driver.ACTIVATION).read_text())
                self.assertTrue(activation['all_twelve_conditions_frozen_before_generation'])
                with self.assertRaises(FileExistsError):driver.preflight(storage,root)

    def test_missing_or_incomplete_predecessor_is_rejected_before_live_runtime_lookup(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.object(driver,'read',side_effect=[
                {'status':'batch','server_stopped':False}, {}, {}, {}]), \
                 patch.object(driver,'live_identity') as live:
                with self.assertRaises(ValueError):driver.predecessor_closed(root,root)
                live.assert_not_called()

    def test_incomplete_native_template_checks_cannot_activate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            pre={'status':'complete','all_twelve_inputs_checked':True,'input_count_requests':12,
                 'summary_input_count_requests':3,'inline_input_count_requests':8,
                 'rolling_transport':[{}]*11,'failed_input_count_requests':0,'source_hashes':{}}
            with patch.object(driver,'read',return_value=pre), patch.object(driver,'write_json') as write:
                with self.assertRaises(ValueError):driver.activate(root,root)
                write.assert_not_called()


if __name__=='__main__':
    unittest.main()
