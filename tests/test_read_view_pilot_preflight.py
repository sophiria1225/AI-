"""Synthetic initial-input and paired-outcome controls for the two-cell pilot."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_whole_task_read_views as runner
from tool_choice_local_llama import payload_for
from whole_task_read_views import fixed_parameters,POLICIES,TASK_ID,summarize

ROOT=Path(__file__).resolve().parents[1]


class ReadViewPreflightTests(unittest.TestCase):
    def exercise(self,change=None):
        plan=fixed_parameters()
        original=json.loads((ROOT/plan['source_plan']).read_text())
        prepared=[dict(task_id=TASK_ID,source_run='synthetic',public_task=dict(
            instruction='Synthetic fixture only',ground_truth_loaded=False))]
        captured=[]
        def count(cfg,messages,tools,timeout):
            captured.append(dict(cfg));return dict(input_tokens=100+int(change=='count' and len(captured)==2),wall_seconds=0)
        def request(cfg,messages,tools):
            value=payload_for(cfg,messages,tools)
            if change=='request' and len(captured)==1:value['temperature']=.5
            return value
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp)/'storage';root=Path(tmp)/'repo';(root/'reports').mkdir(parents=True)
            with patch.object(runner,'sources',return_value=(plan,original,[],prepared)), \
                 patch.object(runner,'frozen_hashes',return_value={'synthetic':'bound'}), \
                 patch.object(runner,'frozen_sources',return_value='synthetic-head'), \
                 patch.object(runner,'live_identity',return_value=({'synthetic':True},'lease-end')), \
                 patch.object(runner,'check_resume',return_value={'synthetic':True}), \
                 patch.object(runner,'count_input',side_effect=count), \
                 patch.object(runner,'payload_for',side_effect=request):
                if change:
                    with self.assertRaisesRegex(ValueError,'identical_initial_P107'):
                        runner.preflight(storage,root)
                else:runner.preflight(storage,root)
            result=json.loads((root/runner.PREFLIGHT).read_text())
        return result,captured

    def test_both_initial_requests_and_token_counts_match(self):
        result,captured=self.exercise()
        self.assertTrue(result['all_two_inputs_checked'])
        self.assertEqual(result['input_count_requests'],2)
        self.assertEqual(captured[0],captured[1])
        self.assertEqual([x['tool_choice'] for x in captured],['auto','auto'])

    def test_request_or_input_count_drift_preserves_failed_preflight(self):
        for change in ('request','count'):
            result,_=self.exercise(change)
            self.assertEqual(result['status'],'failed')
            self.assertEqual(result['input_count_requests'],2)
            self.assertFalse(result['all_two_inputs_checked'])

    def test_failed_or_unknown_runs_cannot_pass_the_successful_cost_gate(self):
        rows=[dict(read_view_policy=p,record_status='evaluated',unknown_usage_calls=0,
                   known_total_tokens=100-i*10,api_requests=10-i,success=False)
              for i,p in enumerate(POLICIES)]
        self.assertFalse(summarize(rows,[])['development_gate_met'])
        for row in rows:row['success']=True
        self.assertTrue(summarize(rows,[])['development_gate_met'])
        rows[1]['unknown_usage_calls']=1
        unknown=summarize(rows,[])
        self.assertFalse(unknown['development_gate_met'])
        self.assertIsNone(unknown['coalesced_minus_eager_tokens'])


if __name__=='__main__':unittest.main()
