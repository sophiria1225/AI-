import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_code_appworld as runner
import code_agent_interface as interface
import test_p18_plan as fixture
from test_code_agent_execution import program
from analyze_code_comparison import budget,require_complete


class CodeComparisonAnalysis(unittest.TestCase):
    def test_budget_uses_inner_requests_and_rejects_changed_counts(self):
        message={'role':'assistant','content':'','tool_calls':[{'id':'p','type':'function',
            'function':{'name':'run_python','arguments':json.dumps({'code':'fixture','span_ids':[]})}}]}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(fixture,'runner',runner),patch.object(runner,'execute_response',
                side_effect=lambda *a,**kw:interface.execute_response(*a,**kw,program=program)):
                fixture.P18Controls().run_fixture(root,'P27',config_updates={'arms':['code_guided'],
                    'general_guidance_version':'appworld_public_rules_v1','api_budget_by_task':{'dev':80}},
                    response_messages=[message])
            trial=root/'storage/records/context_pilot/P27_FIXTURE'
            # The older execution fixture omits timing; add an explicit synthetic
            # duration for this accounting test, without changing the analyzer.
            usage_path=trial/'usage.json';usage=json.loads(usage_path.read_text())
            for u in usage:u['wall_seconds']=1.0
            usage_path.write_text(json.dumps(usage))
            report=budget(trial)
            self.assertEqual(report['api_requests'],2)
            self.assertEqual(report['model_calls'],1)
            path=trial/'summary.json';forged=json.loads(path.read_text());forged['api_requests']=1
            path.write_text(json.dumps(forged))
            with self.assertRaises(ValueError):budget(trial)

    def test_no_partial_cohort_interpretation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'records/context_pilot/P27_batch_v01';p.mkdir(parents=True)
            (p/'status.json').write_text(json.dumps({'status':'running'}))
            with self.assertRaisesRegex(ValueError,'all four'):
                require_complete(root,{'batch_id':'P27_batch_v01'})


if __name__=='__main__':unittest.main()
