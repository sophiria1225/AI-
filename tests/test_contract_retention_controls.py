import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from contract_retention_controls import detail_only_control
from documentation_print_origin import build_origin_view
from handoff_factors import split_turns
from native_conversation import NativeConversation,recover_turn

class DetailControlTests(unittest.TestCase):
    def fixture(self):
        task={'instruction':'synthetic'};conversation=NativeConversation('same guide',task)
        prefix={'public_task':task,'events':[],'spans':{}};programs=[]
        for index in range(8):
            call=f'call_{index+1:03d}';inner=f'i{index}';outer=f'o{index}'
            api='show_api_doc' if index%2 else 'show_api_descriptions'
            arguments={'app_name':'files',**({'api_name':'read'} if index%2 else {})}
            value={'description':('detailed contract' if index%2 else 'API listing')*300}
            code="print('literal task marker')\nprint(call_api('api_docs',"+repr(api)+','+','.join(
                k+'='+repr(v) for k,v in arguments.items())+'))'
            stdout='literal task marker\n'+str(value)+'\n'
            expected={'status':'ok','stdout':stdout,'stdout_truncated':False,'error':None,
                'unknown_effects':False,'declared_complete':False}
            obs={**expected,'api_receipts':[{'span_id':inner,'api':'api_docs__'+api,'api_request_sent':True}]}
            prefix['events'] += [{'call':call,'span_id':inner,'stage':'python_api','api_request_sent':True},
                                 {'call':call,'span_id':outer,'stage':'model_tool'}]
            prefix['spans'][inner]={'action':{'name':'api_docs__'+api,'arguments':json.dumps(arguments)},
                                   'observation':{'observation':json.dumps(value)}}
            action={'name':'run_python','arguments':json.dumps({'code':code,'span_ids':[]})}
            conversation.append({'role':'assistant','content':'','tool_calls':[
                {'id':call,'type':'function','function':action}]},[
                {'id':outer,'assistant':'','action':action,'observation':obs}])
            programs.append({'name':call+'_01','source':{'code':code},'expected':expected,
                'entries':[{'request':{'app':'api_docs','api':api,'arguments':arguments},
                    'reply':{'ok':True,'value':value},'originally_sent':True,'effects_unknown':False,
                    'declared_complete':False}]})
        prefix['conversation_private']=conversation.messages()
        return {'prefix':prefix,'programs':programs}

    def test_detail_control_retains_listings_latest_literals_actions_and_original(self):
        item=self.fixture();original=copy.deepcopy(item)
        view,meta=detail_only_control(item);before=build_origin_view(item)[0]['full_keep']
        self.assertEqual(item,original);self.assertEqual(meta['changed_outputs'],3)
        for index,(a,b) in enumerate(zip(split_turns(before.messages()),split_turns(view.messages()),strict=True)):
            self.assertEqual(a[0],b[0])
            if index%2==0 or index==7:self.assertEqual(a,b)
            else:
                observation=recover_turn(b)[0]['observation']
                self.assertIn('literal task marker',observation['stdout'])
                self.assertNotIn('detailed contract',observation['stdout'])
                self.assertEqual(observation['api_receipts'],recover_turn(a)[0]['observation']['api_receipts'])

    def test_changed_recorded_output_is_refused(self):
        item=self.fixture();item['programs'][1]['expected']['stdout']+='changed'
        with self.assertRaises(ValueError):detail_only_control(item)

if __name__=='__main__':unittest.main()
