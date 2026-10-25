from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_checkpoint_replication import rows
from test_rolling_checkpoint_plan import synthetic_plan
from whole_task_checkpoint_replication import summarize
from build_required_inline_checkpoint_summary import aggregate
from prepare_rolling_checkpoint_followup import review, make_plan, findings


def data():
    result=rows()
    for r in result:
        r.update(model_calls=1,api_requests=1)
        r['request_checks']=[{'role':'agent','status':'ok','input_tokens':r['known_total_tokens']-10,
            'output_tokens':10,'inline_offered':r['checkpoint_policy']=='inline_checkpoint'}]
        r['usage_by_role']={'agent':{'calls':1,'unknown_usage':0,'input_tokens':r['known_total_tokens']-10,'output_tokens':10},
                           'focus':{'calls':0,'unknown_usage':0,'input_tokens':0,'output_tokens':0}}
    return result


def bundle(items):
    totals=summarize(items,[])
    return ({'phase':'P122','batch_status':'complete','owned_processes_absent':True,'audit_errors':[],
             'rows':items,**totals},
            {'phase':'P122','status':'stopped','owned_processes_absent':True},
            {**aggregate(items),**{k:totals[k] for k in ('replication_gate_met',
                'photo_reduction_repeated_with_success','task_summaries','repetition_summaries')}})


class FollowupTests(unittest.TestCase):
    def test_all_rows_and_recalculated_statistics_are_retained(self):
        report,session,overview=bundle(data())
        checked=review(report,session,overview)
        self.assertTrue(checked['next_predeclared_comparison_may_be_bound'])
        self.assertTrue(checked['replication_gate_met'])
        self.assertEqual(checked['all_slots_reviewed'],24)
        text=findings(report,checked)
        self.assertEqual(sum(line.startswith('| 57 |') or line.startswith('| 157 |')
                             or line.startswith('| 257 |') for line in text.splitlines()),24)
        self.assertIn('非劣性',text)

    def test_next_scope_does_not_require_favorable_scientific_results(self):
        items=data();items[1]['success']=False
        checked=review(*bundle(items))
        self.assertFalse(checked['replication_gate_met'])
        self.assertTrue(checked['next_predeclared_comparison_may_be_bound'])
        self.assertFalse(checked['general_quality_preservation_claim'])

    def test_unknown_usage_blocks_binding_without_imputation(self):
        items=data();r=items[0]
        r['request_checks'].append({'role':'agent','status':'error','input_tokens':None,'output_tokens':None})
        r.update(model_calls=2,unknown_usage_calls=1)
        r['usage_by_role']['agent'].update(calls=2,unknown_usage=1)
        checked=review(*bundle(items))
        self.assertFalse(checked['next_predeclared_comparison_may_be_bound'])
        self.assertIsNone(checked['by_policy']['single_checkpoint']['exact_all_condition_tokens'])

    def test_missing_slots_open_session_and_false_aggregates_are_rejected(self):
        report,session,overview=bundle(data())
        for key,value in (('rows',report['rows'][:-1]),('audit_errors',[{'error':'fixture'}]),
                          ('replication_gate_met',False)):
            with self.subTest(key=key),self.assertRaises(ValueError):
                review({**report,key:value},session,overview)
        with self.assertRaises(ValueError):review(report,{**session,'status':'ready'},overview)
        with self.assertRaises(ValueError):review(report,session,{**overview,'recorded_known_tokens':0})

    def test_hidden_role_cost_cannot_pass_recalculation(self):
        report,session,overview=bundle(data())
        report['rows'][0]['usage_by_role']['focus']['input_tokens']=10000
        with self.assertRaisesRegex(ValueError,'role_accounting_changed'):
            review(report,session,overview)

    def test_plan_binds_the_closed_predecessor_and_keeps_predeclared_scope(self):
        prior=json.loads((Path(__file__).resolve().parents[1]/'configs/P120_whole_task_required_inline_checkpoint_v01.json').read_text())
        synthetic=synthetic_plan()
        plan=make_plan(prior,synthetic['predecessor_closure'],synthetic['source_sha256'])
        self.assertEqual(plan['max_cells'],12)
        self.assertEqual(plan['max_reserved_tokens'],5400000)
        self.assertEqual(plan['model_seed'],57)
        self.assertFalse(plan['conditions_selected_from_P122_outcomes'])
        self.assertNotIn('latest_results_publication',plan)
        self.assertEqual(plan['predecessor_closure'],synthetic['predecessor_closure'])


if __name__=='__main__':unittest.main()
