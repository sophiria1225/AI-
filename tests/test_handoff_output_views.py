import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from handoff_output_views import ARMS, make_view
from handoff_factors import split_turns
from native_conversation import NativeConversation, recover_turn


def fixture():
    task={'instruction':'synthetic required task'}
    c=NativeConversation('unchanged public guide',task)
    for i in range(8):
        call={'id':f'c{i}','type':'function','function':{'name':'run_python',
              'arguments':json.dumps({'code':f'print({i})','span_ids':[]})}}
        observation={'status':'ok','stdout':'DATA-'*300,'stdout_truncated':False,
                     'api_receipts':[{'span_id':f'inner{i}','api':'synthetic__read'}],
                     'declared_complete':False,'unknown_effects':False,'error':None}
        if i==2:observation.update(status='execution_error',error='synthetic failure')
        if i==4:observation['stdout']='short'
        c.append({'role':'assistant','content':f'public note {i}','tool_calls':[call]},[
            {'id':f's{i}','assistant':'','action':call['function'],'observation':observation}])
    return task,c.messages()


class OutputViewTests(unittest.TestCase):
    def test_only_stdout_of_eligible_old_successes_changes(self):
        task,messages=fixture();original=copy.deepcopy(messages)
        view,meta=make_view(messages,task,'stdout_mask_keep')
        self.assertEqual(messages,original)
        self.assertEqual(meta['masked_span_count'],5)
        before=split_turns(messages);after=split_turns(view.messages())
        for i,(a,b) in enumerate(zip(before,after)):
            self.assertEqual(a[0],b[0])
            oa=recover_turn(a)[0]['observation'];ob=recover_turn(b)[0]['observation']
            if i in (2,4,7):self.assertEqual(a,b)
            else:
                for key in set(oa)-{'stdout'}:self.assertEqual(oa[key],ob[key])
                self.assertEqual(ob['stdout_view']['source_span_id'],f's{i}')
                self.assertTrue(ob['stdout_view']['omitted'])
        self.assertEqual(view.messages()[1],messages[1])

    def test_full_view_is_information_identical_after_common_notice(self):
        task,messages=fixture()
        view,meta=make_view(messages,task,'full_keep')
        self.assertEqual(view.messages()[1:],messages[1:])
        self.assertEqual(meta['masked_span_count'],0)

    def test_index_only_adds_boundary_inventory(self):
        task,messages=fixture()
        base,_=make_view(messages,task,'stdout_mask_keep')
        indexed,_=make_view(messages,task,'stdout_mask_index_keep',inventory_text='synthetic inventory')
        self.assertEqual(base.messages()[1:],indexed.messages()[1:])
        self.assertEqual(indexed.messages()[0]['content'],base.messages()[0]['content']+'\nsynthetic inventory')

    def test_incorrect_inventory_assignment_rejected(self):
        task,messages=fixture()
        with self.assertRaises(ValueError):make_view(messages,task,'stdout_mask_index_keep')
        with self.assertRaises(ValueError):make_view(messages,task,'full_keep',inventory_text='extra')
        with self.assertRaises(ValueError):make_view(messages,task,'recent_keep')

    def test_later_outputs_are_not_masked_again(self):
        task,messages=fixture();view,_=make_view(messages,task,'stdout_mask_keep')
        view.append({'role':'assistant','content':'later'},[{'id':'new','assistant':'later',
            'action':None,'observation':{'stdout':'fresh'*1000}}])
        rendered,_=view.for_model()
        self.assertIn('fresh'*1000,rendered[-1]['content'])

    def test_unknown_effect_and_completion_are_not_hidden(self):
        task,messages=fixture()
        for key in ('unknown_effects','declared_complete'):
            altered=copy.deepcopy(messages)
            data=json.loads(altered[3]['content']);data['observation'][key]=True
            altered[3]['content']=json.dumps(data)
            view,_=make_view(altered,task,'stdout_mask_keep')
            a=recover_turn(split_turns(altered)[0])[0]
            b=recover_turn(split_turns(view.messages())[0])[0]
            self.assertEqual(a,b)


if __name__=='__main__':unittest.main()
