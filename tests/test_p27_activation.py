import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run_native_batch as batch
from analyze_p26_budget_contrast import common_prefix, public_message


class P27Activation(unittest.TestCase):
    def test_preserve_known_tasks_and_per_task_budgets(self):
        p=json.loads((ROOT/'configs/P27_code_comparison_v01.json').read_text())
        batch.validate_schedule(p);batch.check_p27_activation(p)
        for key,value in [('seed',43),('max_calls',100),('max_api_requests',160),
                          ('task_ids',['aa8502b_1']),('ordinary_compute',{}),
                          ('api_budget_by_task',{k:160 for k in p['task_ids']}),
                          ('general_guidance_version','changed'),
                          ('code_interface_version','changed')]:
            bad=copy.deepcopy(p);bad[key]=value
            with self.assertRaises(ValueError):batch.check_p27_activation(bad)

    def test_public_progress_states_both_caps(self):
        result=batch.public_body([dict(task_number=1,status='running',instruction='PRIVATE')],
                                  dict(status='running',phase='P27'))
        self.assertIn('写真整理は160 API',result)
        self.assertIn('他３件は80 API',result)
        self.assertNotIn('PRIVATE',result)

    def test_prefix_stops_at_first_mismatch_and_excludes_reasoning(self):
        self.assertEqual(common_prefix([1,2,3],[1,4,3]),1)
        message=public_message({'message':{'role':'assistant','content':'x','tool_calls':[],
                                           'reasoning_content':'private'}})
        self.assertNotIn('reasoning_content',message)


if __name__=='__main__':unittest.main()
