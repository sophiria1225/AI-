import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from recorded_action_agreement import response_summary, compare_call
from submission_components import components, compare, summarize


def response(code='print(1)',spans=None):
    return dict(status='ok',done_reason='stop',message=dict(content=None,tool_calls=[dict(
        function=dict(name='run_python',arguments=json.dumps({'code':code,'span_ids':spans or []})))]))


def old_call(value,api=1):
    return dict(response=response_summary(value),API_requests_known=True,API_requests=api,
        API_request_sequence_sha256='same-request',API_result_sequence_sha256='same-result',
        public_tool_results_sha256='same-public-result',prior_API_prefix_sha256='same-prior',
        completed_submission=True)


def pair(left,right):
    original=compare_call(old_call(left),old_call(right))
    return compare(components(left),components(right),original)


class SubmissionComponentsTests(unittest.TestCase):
    def test_reference_only_change_is_not_a_Python_AST_change(self):
        left=response(spans=['s1']);right=response(spans=['s2'])
        old=compare_call(old_call(left),old_call(right))
        self.assertFalse(old['syntax_equal']);self.assertTrue(old['different_syntax_same_nonempty_API'])
        result=pair(left,right)
        self.assertTrue(result['Python_AST_equal']);self.assertFalse(result['noncode_arguments_equal'])
        self.assertEqual(result['target_component_class'],'Python_AST_same_other_components_differ')

    def test_code_literal_and_variable_changes_are_retained(self):
        for code in ('print(2)','x=1; print(x)'):
            result=pair(response(),response(code))
            self.assertFalse(result['Python_AST_equal']);self.assertTrue(result['noncode_arguments_equal'])
            self.assertEqual(result['target_component_class'],'Python_AST_differs')

    def test_whitespace_and_comments_do_not_change_AST_fingerprint(self):
        result=pair(response(),response('print( 1 ) # comment\n'))
        self.assertTrue(result['Python_AST_equal']);self.assertFalse(result['original_target'])

    def test_other_tool_placement_is_separate_from_Python_sequence(self):
        read=dict(function=dict(name='read_span',arguments=json.dumps({'span_id':'s1'})))
        left=response();left['message']['tool_calls'].append(read)
        right=copy.deepcopy(left);right['message']['tool_calls'].reverse()
        result=pair(left,right)
        self.assertTrue(result['Python_AST_equal']);self.assertFalse(result['tool_names_equal'])
        self.assertEqual(result['target_component_class'],'Python_AST_same_other_components_differ')

    def test_absent_python_does_not_become_equal_empty_code(self):
        value=response();value['message']['tool_calls']=[dict(function=dict(name='read_span',arguments='{"span_id":"s1"}'))]
        result=components(value)
        self.assertTrue(result['all_components_available']);self.assertEqual(result['Python_submissions'],0)
        self.assertIsNone(result['Python_AST_sequence_sha256'])

    def test_unknown_empty_and_invalid_sources_remain_unavailable(self):
        invalid=response();invalid['message']['tool_calls'][0]['function']['arguments']='{"code":'
        empty=response();empty['message']['tool_calls']=[]
        bad_python=response('if:')
        for value in ({'status':'error'},empty,invalid,bad_python):
            result=components(value)
            self.assertIsNone(result['Python_AST_sequence_sha256']);self.assertFalse(result['all_components_available'])

    def test_recorded_code_is_parsed_but_never_executed(self):
        result=components(response('raise RuntimeError("must not execute")'))
        self.assertTrue(result['all_components_available']);self.assertFalse(result['semantic_equivalence_claim'])

    def test_original_fingerprint_mismatch_is_not_silently_replaced(self):
        left=response();right=response(spans=['s1'])
        original=compare_call(old_call(left),old_call(right));original['syntax_equal']=True
        with self.assertRaisesRegex(ValueError,'fingerprint_disagrees'):
            compare(components(left),components(right),original)

    def test_one_run_ended_stays_unavailable(self):
        original=compare_call(old_call(response()),None)
        result=compare(components(response()),None,original)
        self.assertIsNone(result['Python_AST_equal']);self.assertFalse(result['original_target'])

    def test_shared_generation_is_not_counted_as_two_independent_samples(self):
        a=response();b=response(spans=['s1']);c=response('print(2)')
        pairs=[dict(left='A',right='B',rows=[dict(ordinal=1,prior_API_prefix_equal=True,**pair(a,b))]),
               dict(left='A',right='C',rows=[dict(ordinal=1,prior_API_prefix_equal=False,**pair(a,c))])]
        runs=[dict(run_id=k,task_id='known') for k in ('A','B','C')]
        result=summarize(pairs,runs)
        self.assertEqual(result['original_target_distinct_generations'],3)
        self.assertEqual(sum(x['distinct_generations'] for x in result['component_classes']),4)
        self.assertFalse(result['pairs_independent']);self.assertTrue(result['category_distinct_counts_are_not_additive'])
        matched=summarize(pairs,runs,matched_prefix_only=True)
        self.assertEqual(matched['original_target_positions'],1)
        self.assertEqual(matched['original_target_distinct_generations'],2)


if __name__=='__main__':unittest.main()
