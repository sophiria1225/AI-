import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from budget_visibility_comparison import canonical_messages
from protocol_stable_history import StableReferenceConversation, fallback_inspection_view
from reasoning_history import ReasoningConversation
from inspect_budget_fallback_references import classify_first_difference


def history(cls, prefix, arguments=('{','{}'), large=False):
    c = cls('system', {'instruction':'literal raw-a remains data'})
    for i,args in enumerate(arguments,1):
        call={'id':f'{prefix}-{i}','type':'function',
              'function':{'name':'run_python','arguments':args}}
        response={'role':'assistant','content':'literal raw-a remains data',
                  'reasoning_content':'opaque synthetic raw-a', 'tool_calls':[call]}
        c.append(response,[{'id':f's{i}','assistant':response['content'],
            'action':call['function'],'observation':{'format_error':'unchanged invalid request',
                'data':'x'*2000 if large else 'literal raw-a'}}])
    return c


class StableReferenceHistoryTests(unittest.TestCase):
    def test_nested_fallback_is_real_old_gap_and_new_source_renaming_closes_it(self):
        a,b=[history(ReasoningConversation,p) for p in ('random-a','random-b')]
        self.assertNotEqual(canonical_messages(a.for_model()[0]),canonical_messages(b.for_model()[0]))
        a,b=[history(StableReferenceConversation,p) for p in ('random-a','random-b')]
        before=a.messages(); rendered,stats=a.for_model()
        self.assertEqual(rendered,b.for_model()[0]); self.assertEqual(a.messages(),before)
        self.assertEqual(stats,{'text_fallback_turns':1,'paged_spans':0})
        self.assertEqual(json.loads(rendered[2]['content'])['tool_call_records'][0]['id'],'transport_reference_1')
        self.assertEqual(rendered[4]['tool_calls'][0]['id'],'transport_reference_2')
        self.assertEqual(rendered[5]['tool_call_id'],'transport_reference_2')

    def test_normal_history_matches_existing_policy_and_literal_data_is_unchanged(self):
        old=history(ReasoningConversation,'raw-a',('{}','{}'))
        new=history(StableReferenceConversation,'raw-a',('{}','{}'))
        self.assertEqual(new.for_model()[0],canonical_messages(old.for_model()[0]))
        for old_m,new_m in zip(old.for_model()[0],new.for_model()[0]):
            self.assertEqual(old_m.get('content'),new_m.get('content'))
            self.assertEqual(old_m.get('reasoning_content'),new_m.get('reasoning_content'))

    def test_invalid_arguments_and_paging_remain_invalid_with_same_error_receipts(self):
        for args in ('{','[]','null','42'):
            old=history(ReasoningConversation,'a',(args,),large=True)
            new=history(StableReferenceConversation,'b',(args,),large=True)
            a,astats=old.for_model(300); b,bstats=new.for_model(300)
            self.assertEqual(astats,bstats); self.assertEqual(astats['paged_spans'],1)
            self.assertEqual(a[3:],b[3:])
            self.assertEqual(json.loads(b[2]['content'])['tool_call_records'][0]['function']['arguments'],args)
            self.assertEqual(a[2]['reasoning_content'],b[2]['reasoning_content'])

    def test_multiple_calls_and_no_tool_turn_keep_order_and_all_receipts(self):
        c=StableReferenceConversation('system',{})
        calls=[{'id':f'raw-{i}','type':'function','function':{'name':'run_python','arguments':a}}
               for i,a in enumerate(('{}','[]'))]
        c.append({'role':'assistant','content':'batch','tool_calls':calls},
                 [{'id':f's{i}','assistant':'batch' if i==0 else '', 'action':v['function'],
                   'observation':{'rejected':i==1}} for i,v in enumerate(calls)])
        c.append({'role':'assistant','content':'plain'},
                 [{'id':'s2','assistant':'plain','action':None,'observation':{'format_error':'no call'}}])
        rendered,stats=c.for_model(); records=json.loads(rendered[2]['content'])['tool_call_records']
        self.assertEqual([r['id'] for r in records],['transport_reference_1','transport_reference_2'])
        self.assertEqual([r['function'] for r in records],[r['function'] for r in calls])
        self.assertEqual(len(json.loads(rendered[3]['content'])['recorded_results']),2)
        self.assertEqual(rendered[-2]['content'],'plain'); self.assertEqual(stats['text_fallback_turns'],1)

    def test_generated_json_lookalike_is_never_rewritten(self):
        c=StableReferenceConversation('system',{})
        text=json.dumps({'assistant_text':'literal','tool_call_records':[{'id':'data-id'}]})
        c.append({'role':'assistant','content':text},
                 [{'id':'s1','assistant':text,'action':None,'observation':{'value':text}}])
        self.assertEqual(c.for_model()[0],c.messages())

    def test_diagnostic_only_removes_bound_fallback_ids_and_keeps_originals(self):
        a,b=[history(ReasoningConversation,p) for p in ('random-a','random-b')]
        original=copy.deepcopy(a.messages())
        av,paths=fallback_inspection_view(a); bv,other=fallback_inspection_view(b)
        self.assertEqual(av,bv); self.assertEqual(paths,other); self.assertEqual(a.messages(),original)
        self.assertEqual(paths[0]['path'],'/messages/2/content[JSON]/tool_call_records/0/id')
        self.assertNotIn('random-a',str(paths)); self.assertNotIn('opaque',str(paths))

    def test_malformed_source_and_wrong_diagnostic_renderer_are_rejected(self):
        c=history(StableReferenceConversation,'random'); c._messages[3]['tool_call_id']='orphan'
        with self.assertRaises(ValueError):c.for_model()
        with self.assertRaises(ValueError):fallback_inspection_view(history(StableReferenceConversation,'random'))

    def test_diagnostic_separates_clock_ids_combination_and_other_content(self):
        base={'available':True,'request_sha256':'left','fallback_ids_normalized_sha256':'f',
              'fallback_ids_and_current_wall_normalized_sha256':'both','bound_reference_paths':[]}
        for wall, fallback, combined, expected in (
            (True,False,True,'current_wall_only'),
            (False,True,True,'renderer_bound_fallback_ids_only'),
            (False,False,True,'current_wall_and_renderer_bound_fallback_ids'),
            (False,False,False,'other_request_fields')):
            right={**base,'request_sha256':'right',
                'fallback_ids_normalized_sha256':'f' if fallback else 'different',
                'fallback_ids_and_current_wall_normalized_sha256':'both' if combined else 'different'}
            result=classify_first_difference({'first_request_difference':1,
                'first_request_difference_is_current_wall_only':wall},[base],[right])
            self.assertEqual(result['first_request_difference_kind'],expected)
            self.assertFalse(result['causal_effect_identified'])

    def test_missing_or_equal_requests_cannot_be_called_a_first_difference(self):
        comparison={'first_request_difference':1}
        for left,right in (({'available':False},{'available':True}),
                ({'available':True,'request_sha256':'same'},{'available':True,'request_sha256':'same'})):
            with self.assertRaises(ValueError):classify_first_difference(comparison,[left],[right])
        self.assertEqual(classify_first_difference({'first_request_difference':None},[],[]),
                         {'first_request_difference_kind':'none_observed'})


if __name__=='__main__':unittest.main()
