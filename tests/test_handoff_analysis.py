import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_handoff_factors import analyze, sha, trial_row


def put(root,name,value):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value))


class HandoffAnalysisTests(unittest.TestCase):
    def test_no_partial_cohort_can_become_comparison(self):
        for phase in ('P31','P32'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as d:
                root=Path(d)
                put(root,f'configs/{phase}_handoff_factors_v01.json',{'batch_id':'batch'})
                put(root,'records/context_pilot/batch/status.json',{'status':'running','completed':list(range(15))})
                with self.assertRaisesRegex(ValueError,'all 16'):analyze(root,root,phase)

    def fixture(self,root):
        span={'id':'s1','action':None,'observation':{'format_error':'no call'}}
        summary={'run_id':'probe','task_id':'test','arm':'full_keep','model_calls':1,
            'known_total_tokens':30,'unknown_usage_calls':0,'api_requests':0,'prefix_api_requests':1,
            'total_task_api_requests':1,'python_session':{'container_removed':True},
            'stop_reason':'call_limit','wall_seconds':2,'full_wall_seconds':3,'unknown_effect_requests':0}
        docs={'summary.json':summary,'events.json':[{'span_id':'s1','stage':'model_tool','call':'call_001','api_request_sent':False}],
             'spans.json':{'s1':span},'usage.json':[{'id':'call_001','status':'ok','input_tokens':20,'output_tokens':10}],
             'prefix_events.json':[{'api_request_sent':True}],'prefix_spans.json':{},
             'setup.json':{'status':'matched_observable_prefix','wall_seconds':1,'environment_replay':{'api_requests':1}},
             'source_identity.json':{'source_run':'source','boundary_manifest_sha256':'synthetic'},
             'plan.json':{},'factor_plan.json':{'max_total_tokens':30,'max_calls':1},
             'call_001/response.json':{'message':{'role':'assistant','content':'no call'}}}
        for name,value in docs.items():put(root,name,value)
        put(root,'evaluation.json',{'execution_summary_sha256':sha(root/'summary.json'),
                                    'evaluation_returned_to_model':False,'official_success':False})

    def test_prefix_cost_remains_separate_and_is_charged_to_original_cap(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            row=trial_row(root,{'api_budget_by_task':{'test':1}},'source')
            self.assertEqual(row['prefix_api_requests'],1);self.assertEqual(row['api_requests'],0)
            self.assertEqual(row['setup_api_requests'],1)
            with self.assertRaisesRegex(ValueError,'budget'):
                trial_row(root,{'api_budget_by_task':{'test':0}},'source')

    def test_changed_summary_or_cost_is_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            value=json.loads((root/'usage.json').read_text());value[0]['output_tokens']=11
            put(root,'usage.json',value)
            with self.assertRaisesRegex(ValueError,'accounting'):
                trial_row(root,{'api_budget_by_task':{'test':1}},'source')
            self.fixture(root)
            value=json.loads((root/'summary.json').read_text());value['known_total_tokens']=31
            put(root,'summary.json',value)
            with self.assertRaisesRegex(ValueError,'evaluation'):
                trial_row(root,{'api_budget_by_task':{'test':1}},'source')
