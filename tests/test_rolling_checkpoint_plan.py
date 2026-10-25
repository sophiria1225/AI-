from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_rolling_checkpoint_summary import aggregate
from rolling_checkpoint_preflight import synthetic_transport_cases
from whole_task_rolling_checkpoint import POLICIES, cell_id, run_order, summarize, validate_plan


def synthetic_plan():
    root = Path(__file__).resolve().parents[1]
    plan = json.loads((root/'configs/P120_whole_task_required_inline_checkpoint_v01.json').read_text())
    plan.update(experiment='P123', batch_id='P123_batch_v01', checkpoint_policies=list(POLICIES),
        max_cells=12, max_model_calls=960, max_reserved_tokens=5400000,
        max_reserved_environment_api_requests=1200, server_max_lifetime_seconds=32400,
        primary_question='rolling_inline_whole_task_cost_against_single_and_rolling_separate',
        required_closed_diagnostic='reports/P122_comparison.json', required_predecessor_phase='P122',
        rolling_checkpoint_max_opportunities=3, rolling_min_fresh_turns=3,
        single_checkpoint_max_opportunities=1, max_summary_calls_in_batch=16,
        max_inline_opportunities_in_batch=12,
        invalid_summary_policy='keep_current_view_charge_known_cost_require_three_fresh_turns',
        minimum_repeated_installations_per_rolling_policy=2,
        predecessor_closure={k:'a'*64 for k in ('audit_sha256','pipeline_status_sha256','server_final_sha256')})
    for name in ('scripts/rolling_checkpoint_history.py', 'scripts/rolling_checkpoint_inference.py',
        'scripts/run_whole_task_rolling_checkpoint_cell.py', 'scripts/audit_rolling_checkpoint_trace.py',
        'reports/P122_comparison.json', 'reports/P122_server_session.json', 'docs/P122_findings.md',
        'reports/P120_pair_controls.json', 'reports/rolling_checkpoint_core_preparation_20261025.json',
        'docs/experiments/P123_whole_task_rolling_checkpoint.md'):
        plan['source_sha256'][name] = 'a'*64
    return plan


def rows():
    return [{'run_id':cell_id(n,p), 'task_id':f'synthetic-{n}', 'checkpoint_policy':p,
             'record_status':'evaluated', 'success':True, 'unknown_usage_calls':0,
             'checkpoint_installations':1 if p=='single_checkpoint' else 3,
             'known_total_tokens':{'single_checkpoint':100,'rolling_separate':90,'rolling_inline':80}[p]}
            for n,p in run_order()]


class RollingPlanTests(unittest.TestCase):
    def test_schedule_covers_all_twelve_slots_once(self):
        order = run_order()
        self.assertEqual(len(order), 12)
        self.assertEqual(set(order), {(n,p) for n in range(1,5) for p in POLICIES})
        self.assertEqual(order[:3], [(1,p) for p in POLICIES])
        self.assertEqual(order[3:6], [(2,p) for p in POLICIES[1:]+POLICIES[:1]])
        self.assertEqual(len({cell_id(n,p) for n,p in order}), 12)

    def test_plan_rejects_extended_budget_adaptive_scope_and_missing_closed_predecessor(self):
        plan = synthetic_plan(); validate_plan(plan)
        for key, value in (('max_total_tokens',500000), ('max_model_calls',961),
            ('rolling_checkpoint_max_opportunities',4), ('rolling_min_fresh_turns',0),
            ('single_checkpoint_max_opportunities',3), ('max_summary_calls_in_batch',17),
            ('max_inline_opportunities_in_batch',13), ('reserved_scenarios_read',1),
            ('same_call_results_summarized',True), ('separate_semantic_judge',True),
            ('novel_method_claim',True), ('predecessor_closure',None),
            ('minimum_repeated_installations_per_rolling_policy',1),
            ('source_sha256',{}), ('model_seed',157)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_plan({**plan,key:value})

    def test_both_baselines_and_repeated_activation_are_required(self):
        data = rows(); self.assertTrue(summarize(data,[])['development_gate_met'])
        for baseline in POLICIES[:2]:
            changed = deepcopy(data)
            for row in changed:
                if row['checkpoint_policy']==baseline: row['known_total_tokens']=70
            self.assertFalse(summarize(changed,[])['development_gate_met'])
        for policy in POLICIES[1:]:
            changed = deepcopy(data)
            for row in changed:
                if row['checkpoint_policy']==policy: row['checkpoint_installations']=1
            self.assertFalse(summarize(changed,[])['development_gate_met'])

    def test_success_loss_cannot_be_offset_by_success_gained_elsewhere(self):
        data = rows()
        for row in data:
            if row['task_id']=='synthetic-1' and row['checkpoint_policy']=='rolling_inline':
                row['success']=False; row['known_total_tokens']=1
            if row['task_id']=='synthetic-2' and row['checkpoint_policy']!='rolling_inline':
                row['success']=False
        result=summarize(data,[])
        self.assertEqual(len(set(result['success_counts'].values())),1)
        self.assertFalse(result['development_gate_met'])

    def test_cheap_failed_cases_cannot_hide_costlier_common_successes(self):
        data=rows()
        for row in data:
            if row['task_id']=='synthetic-1':
                row['success']=False
                row['known_total_tokens']=1000 if row['checkpoint_policy']!='rolling_inline' else 1
            else:
                row['known_total_tokens']=100 if row['checkpoint_policy']!='rolling_inline' else 101
        result=summarize(data,[])
        self.assertTrue(all(c['lower_all_four_tokens'] for c in result['comparisons']))
        self.assertFalse(result['development_gate_met'])

    def test_unknown_unrun_audit_errors_or_no_common_success_prevent_gate(self):
        for update in ({'unknown_usage_calls':1}, {'record_status':'not_run','known_total_tokens':None,'success':None}):
            data=rows();data[0].update(update)
            result=summarize(data,[])
            self.assertFalse(result['development_gate_met'])
            self.assertTrue(all(v is None for v in result['total_tokens_by_policy'].values()))
            self.assertIsNone(aggregate(data)['exact_all_condition_tokens'])
        self.assertFalse(summarize(rows(),[{'error':'synthetic'}])['development_gate_met'])
        data=rows()
        for row in data:row['success']=False
        self.assertFalse(summarize(data,[])['development_gate_met'])
        with self.assertRaises(ValueError):summarize(data[:-1],[])

    def test_twelve_templates_include_first_and_recurrent_inputs_without_current_result_prediction(self):
        cases=synthetic_transport_cases()
        self.assertEqual(len(cases),12)
        self.assertEqual(len({c['name'] for c in cases}),12)
        self.assertEqual(sum(c['role']=='focus' for c in cases),3)
        for rev in range(1,4):
            offer=next(c for c in cases if c['name']==f'inline_{rev}_offer')
            ordinary=next(c for c in cases if c['name']==f'inline_{rev}_ordinary')
            compacted=next(c for c in cases if c['name']==f'inline_{rev}_compacted')
            self.assertIn('checkpoint',offer['tools'][0]['function']['parameters']['required'])
            self.assertEqual(ordinary['messages'][-2:],compacted['messages'][-2:])
            for case in (ordinary,compacted):
                self.assertNotIn('checkpoint',case['tools'][0]['function']['parameters']['properties'])
                for message in case['messages']:
                    for call in message.get('tool_calls') or []:
                        self.assertNotIn('checkpoint',json.loads(call['function']['arguments']))


if __name__=='__main__':
    unittest.main()
