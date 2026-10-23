import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from budget_visibility_comparison import (CanonicalBudgetInference, canonical_messages,
    cell_id, config_for, run_order, validate_plan)
from run_context_comparison import BudgetStop
import test_budget_observation as base_fixture

ROOT = Path(__file__).resolve().parents[1]


def history(ident='random-id'):
    return [{'role':'user', 'content':'instruction'},
        {'role':'assistant', 'content':'literal random-id is content',
         'reasoning_content':'opaque retained text random-id', 'tool_calls':[
             {'id':ident, 'type':'function', 'function':{
                 'name':'run_python', 'arguments':'{"code":"print(42)","span_ids":[]}'}}]},
        {'role':'tool', 'tool_call_id':ident, 'content':'42'}]


class VisibilityComparisonTests(unittest.TestCase):
    def test_ids_normalize_but_all_semantic_strings_and_original_history_survive(self):
        a=history(); before=copy.deepcopy(a); b=history('different-id')
        normalized=canonical_messages(a)
        self.assertEqual(normalized, canonical_messages(b))
        self.assertEqual(a, before)
        self.assertEqual(normalized[1]['content'], a[1]['content'])
        self.assertEqual(normalized[1]['reasoning_content'], a[1]['reasoning_content'])
        self.assertEqual(normalized[1]['tool_calls'][0]['function'], a[1]['tool_calls'][0]['function'])
        self.assertEqual(canonical_messages(normalized), normalized)

    def test_multiple_calls_keep_actual_result_association_and_order(self):
        a=history('second')
        first=copy.deepcopy(a[1]['tool_calls'][0]); first['id']='transport_reference_2'
        a[1]['tool_calls'].append(first)
        a.insert(2, {'role':'tool', 'tool_call_id':'transport_reference_2', 'content':'other'})
        n=canonical_messages(a)
        self.assertEqual(n[2]['tool_call_id'], 'transport_reference_2')
        self.assertEqual(n[3]['tool_call_id'], 'transport_reference_1')
        self.assertEqual([m['content'] for m in n[2:]], ['other','42'])

    def test_malformed_reference_graph_stops_before_inference(self):
        mutations=[lambda x:x.pop(), lambda x:x[2].update(tool_call_id='orphan'),
            lambda x:x.append(copy.deepcopy(x[2])),
            lambda x:x[1]['tool_calls'].append(copy.deepcopy(x[1]['tool_calls'][0])),
            lambda x:x[1]['tool_calls'][0].update(id=''),
            lambda x:x[2].update(tool_call_id=[])]
        for mutate in mutations:
            x=history(); mutate(x)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): canonical_messages(x)

    def test_fixed_order_contains_all_eight_and_only_authorized_tasks(self):
        order=run_order()
        self.assertEqual(len(set(order)),8)
        self.assertEqual(order[:4],[(1,'measured'),(1,'not_exposed'),(2,'not_exposed'),(2,'measured')])
        self.assertEqual(len({cell_id(*v) for v in order}),8)
        for bad in [(0,'measured'), (True,'measured'),(5,'not_exposed'),(1,'rounded')]:
            with self.assertRaises(ValueError): cell_id(*bad)

    def test_plan_rejects_budget_seed_task_and_policy_changes(self):
        plan=json.loads((ROOT/'configs/P80_budget_visibility_v01.json').read_text())
        validate_plan(plan)
        for key,value in [('model_seed',58),('max_cells',9),('max_calls',True),
            ('automatic_retries',1),('protocol_references','raw'),('novel_method_claim',True)]:
            with self.subTest(key=key), self.assertRaises(ValueError): validate_plan({**plan,key:value})
        changed=copy.deepcopy(plan); changed['known_tasks'][0]['task_id']='unseen'
        with self.assertRaises(ValueError): validate_plan(changed)
        original=json.loads((ROOT/plan['source_plan']).read_text())
        for number,policy in run_order():
            cfg=config_for(original,plan,plan['known_tasks'][number-1]['task_id'],policy)
            self.assertEqual(cfg['max_api_requests'],160 if number==1 else 80)
            self.assertEqual(cfg['seed'],57)
            self.assertEqual(cfg['error_presentation'],'error_exception')

    def test_exact_counted_and_sent_input_controls_ids_and_clock_together(self):
        fixture=base_fixture.BudgetObservationTests(); observed=[]; receipts=[]
        for elapsed,ident in [(10,'random-first'),(11,'random-second')]:
            with tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)
                with patch('budget_observation.time.monotonic',return_value=0):
                    runner=CanonicalBudgetInference(fixture.config(),out,time_visibility='not_exposed')
                counted=[]
                def count(cfg,msgs,tools,timeout):
                    counted.append(copy.deepcopy(msgs)); return {'input_tokens':75}
                with patch('budget_observation.time.monotonic',return_value=elapsed), \
                     patch('residual_output_budget.count_input',side_effect=count), \
                     patch('residual_output_budget.model_call',side_effect=fixture.sender(observed)):
                    runner.call('agent',history(ident),[])
                self.assertEqual(counted[0],observed[-1]['messages'])
                self.assertEqual(runner.tokens,100)
                receipts.append(json.loads((out/'protocol_reference_views.json').read_text())[0])
        self.assertEqual(observed[0]['messages'],observed[1]['messages'])
        self.assertEqual([r['wall'] for r in observed],[50,49])
        self.assertNotEqual(receipts[0]['original_messages_sha256'],receipts[1]['original_messages_sha256'])
        self.assertEqual(receipts[0]['canonical_messages_sha256'],receipts[1]['canonical_messages_sha256'])

    def test_measured_retains_clock_difference_after_protocol_normalization(self):
        fixture=base_fixture.BudgetObservationTests(); observed=[]
        for elapsed in (10,11):
            with tempfile.TemporaryDirectory() as tmp:
                with patch('budget_observation.time.monotonic',return_value=0):
                    runner=CanonicalBudgetInference(fixture.config(),Path(tmp),time_visibility='measured')
                with patch('budget_observation.time.monotonic',return_value=elapsed), \
                     patch('residual_output_budget.count_input',return_value={'input_tokens':75}), \
                     patch('residual_output_budget.model_call',side_effect=fixture.sender(observed)):
                    runner.call('agent',history(),[])
        self.assertEqual(observed[0]['messages'][:-1],observed[1]['messages'][:-1])
        self.assertNotEqual(observed[0]['messages'][-1],observed[1]['messages'][-1])

    def test_real_deadline_and_unknown_dispatch_are_not_hidden(self):
        fixture=base_fixture.BudgetObservationTests()
        for elapsed in (10,61):
            with tempfile.TemporaryDirectory() as tmp:
                with patch('budget_observation.time.monotonic',return_value=0):
                    runner=CanonicalBudgetInference(fixture.config(),Path(tmp),time_visibility='not_exposed')
                with patch('budget_observation.time.monotonic',return_value=elapsed), \
                     patch('residual_output_budget.count_input',return_value={'input_tokens':75}), \
                     patch('residual_output_budget.model_call',side_effect=OSError('lost')) as send:
                    with self.assertRaises((OSError,BudgetStop)): runner.call('agent',history(),[])
                self.assertEqual(send.call_count,1 if elapsed==10 else 0)
                self.assertEqual(runner.snapshots[0]['usage_unknown'],elapsed==10)
                self.assertEqual(runner.calls,[])


if __name__=='__main__': unittest.main()
