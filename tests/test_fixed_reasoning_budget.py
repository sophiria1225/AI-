import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from fixed_reasoning_budget_replay import (BUDGETS,CASES,CONTEXTS,COUNTS,FIXED,SEEDS,
    code_completion,equality_summary,request_for,reserve_tokens,schedule,validate_plan)


def response(code='x = 1\n',span_ids=None,finish='tool_calls'):
    return {'status':'ok','done_reason':finish,'message':{'role':'assistant',
        'tool_calls':[{'function':{'name':'run_python','arguments':json.dumps(
            {'code':code,'span_ids':[] if span_ids is None else span_ids})}}]}}


class FixedReasoningBudget(unittest.TestCase):
    def test_committed_plan_and_dependencies_are_fixed(self):
        root=Path(__file__).resolve().parents[1]
        plan=json.loads((root/'configs/P87_fixed_reasoning_budget_v01.json').read_text())
        validate_plan(plan)
        for name,expected in plan['source_sha256'].items():
            with self.subTest(path=name):
                self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),expected)

    def test_only_budget_and_common_cache_flag_change(self):
        source={'seed':69,'max_tokens':4096,'cache_prompt':True,'stream':False,
            'temperature':1.0,'model':'minimax-m3-iq4xs',
            'chat_template_kwargs':{'thinking_mode':'enabled'},
            'messages':[{'role':'assistant','reasoning_content':'opaque fixture',
                         'tool_calls':[{'id':'retain-source-id'}]}]}
        saved=copy.deepcopy(source)
        a=request_for(source,CASES[0]);b=request_for(source,CASES[1])
        self.assertEqual(source,saved)
        self.assertFalse(a['cache_prompt']);self.assertFalse(b['cache_prompt'])
        self.assertEqual(a.pop('reasoning_budget_tokens'),-1)
        self.assertEqual(b.pop('reasoning_budget_tokens'),2048)
        self.assertEqual(a,b);self.assertEqual(a['messages'],source['messages'])
        source['thinking_budget_tokens']=99
        with self.assertRaises(ValueError):request_for(source,CASES[0])

    def test_wrong_seed_or_context_is_not_replaced(self):
        source={'seed':69,'max_tokens':4096,'cache_prompt':True,'stream':False,
            'temperature':1.0,'model':'minimax-m3-iq4xs',
            'chat_template_kwargs':{'thinking_mode':'enabled'}}
        with self.assertRaises(ValueError):request_for(source,CASES[2])
        with self.assertRaises(ValueError):request_for(source,'new_context')

    def test_fixed_reservation_and_balanced_schedule(self):
        self.assertEqual(reserve_tokens(COUNTS),228396)
        self.assertEqual(len(schedule()),8)
        for case in CASES:self.assertEqual(sum(r['case']==case for r in schedule()),2)
        with self.assertRaises(ValueError):reserve_tokens([1]*4)
        plan={**FIXED,'cases':[dict(id=c,expected_input_tokens=n,context=x,
            reasoning_budget_tokens=b,seed=s) for c,n,x,b,s in zip(CASES,COUNTS,CONTEXTS,BUDGETS,SEEDS)],
            'schedule':schedule(),'reserved_total_tokens':228396}
        validate_plan(plan)
        plan['max_calls']=9
        with self.assertRaises(ValueError):validate_plan(plan)

    def test_incomplete_json_required_argument_and_python_are_distinct(self):
        r=response();r['message']['tool_calls'][0]['function']['arguments']='{"code":"x'
        self.assertEqual(code_completion(r)['malformed_json_calls'],1)
        r['message']['tool_calls'][0]['function']['arguments']='{"code":"x=1"}'
        self.assertEqual(code_completion(r)['shape_invalid_calls'],1)
        self.assertEqual(code_completion(response('for x in range(3):\n'))['syntax_invalid_calls'],1)
        self.assertEqual(code_completion(response('# comment only\n'))['syntax_invalid_calls'],1)

    def test_public_argument_constraints_are_preserved(self):
        for ids in (['s1','s1'],[1],['s1']*161,'s1'):
            with self.subTest(ids_type=type(ids).__name__):
                self.assertEqual(code_completion(response(span_ids=ids))['shape_invalid_calls'],1)
        self.assertEqual(code_completion(response('x'*20001))['shape_invalid_calls'],1)

    def test_structural_completion_does_not_execute_or_validate_effects(self):
        value=code_completion(response("raise RuntimeError('never executed')\n",['unverified-span']))
        self.assertTrue(value['complete_code_submission'])
        self.assertFalse(value['task_quality_established'])
        self.assertFalse(code_completion(response(finish='length'))['complete_code_submission'])

    def test_empty_and_other_tool_output_remain_separate(self):
        self.assertFalse(code_completion({'status':'ok','done_reason':'stop','message':{'content':'done'}})['complete_code_submission'])
        r=response();r['message']['tool_calls'][0]['function']['name']='read_span'
        result=code_completion(r)
        self.assertEqual(result['other_tool_calls'],1)
        self.assertFalse(result['complete_code_submission'])

    def test_unknown_output_is_not_structural_failure(self):
        result=code_completion({'status':'error'})
        self.assertIsNone(result['tool_calls'])
        self.assertIsNone(result['complete_code_submission'])

    def test_summary_requires_both_contexts_and_preserves_unknown(self):
        rows=[]
        for item in schedule():
            i=CASES.index(item['case']);half=BUDGETS[i]==2048
            rows.append({**item,'status':'ok','input_tokens':COUNTS[i],
                'output_tokens':2000 if half else 4096,'done_reason':'tool_calls' if half else 'length',
                'public_output_sha256':'same within case '+item['case'],
                'complete_code_submission':half})
        summary=equality_summary(rows)
        self.assertTrue(summary['both_contexts_local_completion_improved'])
        self.assertFalse(summary['task_quality_measured'])
        self.assertEqual(summary['independent_tasks'],1)
        rows[-1]['status']='error'
        self.assertIsNone(equality_summary(rows)['both_contexts_local_completion_improved'])
        self.assertIsNone(equality_summary(rows)['comparisons'][1]['half_minus_unlimited_output_tokens'])
        with self.assertRaises(ValueError):equality_summary(rows+[rows[0]])


if __name__=='__main__':unittest.main()
