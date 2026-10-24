from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_whole_task_receipt_history as runner
from whole_task_receipt_history import POLICIES, cell_id, run_order, summarize, validate_plan

ROOT=Path(__file__).resolve().parents[1]


def fixture_plan():
    plan=json.loads((ROOT/'configs/P99_whole_task_tool_choice_v01.json').read_text())
    plan.update(experiment='P111',batch_id='P111_batch_v01',reasoning_display_policies=list(POLICIES),
        tool_choice='auto',max_cells=12,max_model_calls=960,max_reserved_tokens=5400000,
        max_reserved_environment_api_requests=1200,server_max_lifetime_seconds=32400,
        primary_question='receipt_conditioned_reasoning_whole_task_quality_and_cost',
        required_closed_diagnostic='reports/P110_receipt_history_inputs.json',required_predecessor_phase='P107',
        read_views_enabled=False,immutable_P110_display_rules=True)
    for rel in ('scripts/receipt_reasoning_history.py','reports/P110_receipt_history_inputs.json',
                'configs/P110_receipt_history_inputs_v01.json','reports/P107_comparison.json',
                'reports/P107_server_session.json','docs/experiments/P111_whole_task_receipt_history.md'):
        plan['source_sha256'][rel]='0'*64
    return plan


def rows():
    return [dict(task_id=str(n),reasoning_display_policy=p,record_status='evaluated',success=True,
        unknown_usage_calls=0,known_total_tokens={'full':100,'recent':95,'execution_gated':80}[p])
        for n,p in run_order()]


class ReceiptHistoryPlanTests(unittest.TestCase):
    def test_exact_all_four_by_three_scope_and_fixed_order(self):
        validate_plan(fixture_plan())
        self.assertEqual(len({cell_id(n,p) for n,p in run_order()}),12)
        self.assertEqual(run_order()[:3],[(1,'full'),(1,'recent'),(1,'execution_gated')])
        for key,value in [('max_calls',81),('server_max_lifetime_seconds',32401),('tool_choice','required'),
                          ('read_views_enabled',True),('immutable_P110_display_rules',False)]:
            plan=fixture_plan();plan[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_plan(plan)

    def test_gate_requires_both_ordinary_controls(self):
        data=rows();self.assertTrue(summarize(data,[])['development_gate_met'])
        for row in data:
            if row['reasoning_display_policy']=='recent':row['known_total_tokens']=70
        self.assertFalse(summarize(data,[])['development_gate_met'])

    def test_quality_loss_unknown_usage_audit_errors_and_missing_slots_prevent_gate(self):
        for key,value in [('success',False),('unknown_usage_calls',1),('record_status','not_run')]:
            data=rows();next(r for r in data if r['reasoning_display_policy']=='execution_gated')[key]=value
            self.assertFalse(summarize(data,[])['development_gate_met'])
        self.assertFalse(summarize(rows(),[{'reason':'synthetic'}])['development_gate_met'])
        with self.assertRaisesRegex(ValueError,'all_twelve'):summarize(rows()[:-1],[])

    def test_cheap_failure_cannot_substitute_for_successful_task_saving(self):
        data=rows()
        for row in data:
            if row['task_id']=='4':
                row['success']=False
                row['known_total_tokens']=1 if row['reasoning_display_policy']=='execution_gated' else 10000
            else:row['known_total_tokens']=100
        result=summarize(data,[])
        self.assertFalse(result['development_gate_met'])
        self.assertTrue(all(c['paired_successful_token_difference']==0 for c in result['comparisons']))
        for row in data:row['success']=False
        self.assertFalse(summarize(data,[])['development_gate_met'])

    def preflight(self,mismatch=False):
        plan=fixture_plan();original=json.loads((ROOT/plan['source_plan']).read_text())
        prepared=[dict(item,public_task={'instruction':'synthetic task','ground_truth_loaded':False}) for item in plan['known_tasks']]
        captured=[]
        def count(config,messages,tools,timeout):
            captured.append(deepcopy(config))
            return {'input_tokens':101 if mismatch and len(captured)==2 else 100,'wall_seconds':0,'method':'synthetic'}
        with tempfile.TemporaryDirectory() as temp:
            storage,root=Path(temp)/'storage',Path(temp)/'repo';(root/'reports').mkdir(parents=True)
            with patch.object(runner,'sources',return_value=(plan,original,[],prepared)), \
                 patch.object(runner,'frozen_hashes',return_value={'synthetic':'bound'}), \
                 patch.object(runner,'frozen_sources',return_value='synthetic-head'), \
                 patch.object(runner,'live_identity',return_value=({'synthetic':True},'lease-end')), \
                 patch.object(runner,'check_resume',return_value={'synthetic':True}), \
                 patch.object(runner,'count_input',side_effect=count):
                if mismatch:
                    with self.assertRaisesRegex(ValueError,'all_three_initial_inputs_must_match'):runner.preflight(storage,root)
                else:runner.preflight(storage,root)
            result=json.loads((root/runner.PREFLIGHT).read_text())
            requests=[json.loads(p.read_text()) for p in (storage/'records/context_pilot/P111_preflight_v01').glob('*_request_private.json')]
        return result,captured,requests

    def test_all_twelve_preflight_requests_are_identical_within_task(self):
        result,captured,requests=self.preflight()
        self.assertEqual(result['status'],'complete');self.assertTrue(result['all_twelve_inputs_checked'])
        self.assertEqual(result['input_count_requests'],12);self.assertEqual(len(requests),12)
        self.assertTrue(all(c['tool_choice']=='auto' and c['reasoning_budget_tokens']==-1 for c in captured))
        for row in result['rows']:
            self.assertEqual(len({e['count_request_sha256'] for e in row['conditions'].values()}),1)
        self.assertEqual(result['model_generations'],0)

    def test_preflight_count_disagreement_stops_and_keeps_all_attempted_inputs(self):
        result,captured,requests=self.preflight(mismatch=True)
        self.assertEqual(result['status'],'failed');self.assertFalse(result['all_twelve_inputs_checked'])
        self.assertEqual(len(captured),3);self.assertEqual(len(requests),3)
        self.assertEqual(result['model_generations'],0)


if __name__=='__main__':unittest.main()
