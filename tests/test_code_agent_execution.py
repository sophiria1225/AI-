import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_code_appworld as runner
import code_agent_interface as interface
import test_p18_plan as fixture
from audit_native_boundaries import audit


def program(code, observations, channel, **kw):
    folder=kw['record_dir'];folder.mkdir(parents=True)
    (folder/'input_private.json').write_text(json.dumps({'code':code,'observations':observations,'api_schemas':{}}))
    packets=[]
    for app, api in [('api_docs','show_app_descriptions'),('supervisor','complete_task')]:
        packet={'kind':'api','id':channel.last_id+1,'app':app,'api':api,'arguments':{}}
        packets.append(packet);channel.exchange(packet)
        kw['on_record'](channel.rows[-1])
    result={'status':'ok','stdout':'done','stdout_truncated':False,'api_requests':2,
            'declared_complete':channel.complete,'unknown_effects':channel.fatal,
            'container_removed':True,'controls':{str(n):True for n in range(14)}}
    (folder/'result_private.json').write_text(json.dumps(result))
    (folder/'wire_private.jsonl').write_text(''.join(json.dumps(p)+'\n' for p in packets))
    return result


class CodeExecution(unittest.TestCase):
    def test_nested_apis_are_counted_without_becoming_extra_model_results(self):
        message={'role':'assistant','content':'','tool_calls':[{
            'id':'program_1','type':'function','function':{
                'name':'run_python','arguments':json.dumps({'code':'fixture','span_ids':[]})}}]}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(fixture,'runner',runner), patch.object(runner,'execute_response',
                    side_effect=lambda *a,**kw: interface.execute_response(*a,**kw,program=program)):
                summary,sent,requests=fixture.P18Controls().run_fixture(root,'P27',
                    config_updates={'arms':['code_guided'],'general_guidance_version':'appworld_public_rules_v1',
                                    'api_budget_by_task':{'dev':80}},response_messages=[message])
            self.assertEqual(summary['model_calls'],1)
            self.assertEqual(summary['api_requests'],2)
            self.assertEqual(summary['stop_reason'],'agent_declared_complete')
            trial=root/'storage/records/context_pilot/P27_FIXTURE'
            spans=json.loads((trial/'spans.json').read_text())
            self.assertEqual(list(spans),['s1','s2','s3'])
            last=json.loads((trial/'conversation_private.json').read_text())[-1]
            self.assertEqual(last['tool_call_id'],'program_1')
            visible=json.loads(last['content'])['observation']
            self.assertEqual([x['span_id'] for x in visible['api_receipts']],['s1','s2'])
            from context_preservation import function
            with patch('inspect_appworld_api_schemas.load_public_tools', return_value=(
                    [function(n,'fixture',{},[]) for n in ['api_docs__show_app_descriptions','supervisor__complete_task']],{},None)):
                self.assertEqual(audit(trial,root/'world')['audit_errors'],[])
            self.assertEqual(len(sent),2)
            from audit_code_execution import audit as code_audit
            self.assertEqual(code_audit(trial)['code_audit_errors'],[])
            path=trial/'programs/call_001_01/result_private.json'
            forged=json.loads(path.read_text());forged['api_requests']=1
            path.write_text(json.dumps(forged))
            self.assertTrue(code_audit(trial)['code_audit_errors'])
    def test_new_or_unknown_receipts_are_not_passed_to_program(self):
        records=[]
        calls=[{'function':{'name':'run_python','arguments':json.dumps({'code':'x','span_ids':['future']})}}]
        fake=lambda *a,**k: self.fail('must reject before computation')
        result=interface.execute_response({'tool_calls':calls},None,None,[],
            lambda r,**kw:records.append(r),out=Path('.'),storage=Path('.'),call_id='x',
            remaining_api=lambda:80,may_continue=lambda:True,remaining_wall=lambda:30,
            read_archive=lambda *a:None,program=fake)
        self.assertIn('format_error',result[0]['observation'])
        self.assertEqual(len(records),1)
