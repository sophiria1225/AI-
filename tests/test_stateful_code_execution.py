import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_stateful_code_appworld as runner
import test_p18_plan as fixture
from test_code_agent_execution import program
from code_agent_interface import CODE_TOOLS
from code_runtime_prompts import CALLABLE_GUIDANCE
from stateful_code_prompts import stateful_system_prompt,FRESH,PERSISTENT
from audit_code_execution import audit as code_audit
from audit_native_boundaries import audit as boundary_audit

class Session:
    def __init__(self,storage,folder):
        self.folder=folder;folder.mkdir();self.usable=True
        self.state={'session_id':'fixture_session','namespace_scope':'one_task','status':'not_started',
            'container_removed':False,'process_memory_checkpointed':False,'programs':[]}
        self.save()
    def save(self):(self.folder/'session_private.json').write_text(json.dumps(self.state))
    def run(self,*args,**kwargs):
        result=program(*args,**kwargs)
        i=len(self.state['programs'])+1
        result.update(session_id=self.state['session_id'],program_index=i,
            persistent_namespace=True,container_removed=False,session_usable=True)
        folder=kwargs['record_dir'];(folder/'result_private.json').write_text(json.dumps(result))
        p=folder/'input_private.json';v=json.loads(p.read_text());v['program_index']=i;p.write_text(json.dumps(v))
        p=folder/'wire_private.jsonl';rows=[json.loads(r) for r in p.read_text().splitlines()]
        p.write_text(''.join(json.dumps({**r,'program_index':i})+'\n' for r in rows))
        self.state.update(status='active');self.state['programs'].append({'program_index':i});self.save()
        return result
    def close(self):
        self.usable=False;self.state.update(status='closed',container_removed=True);self.save();return self.state

class StatefulExecution(unittest.TestCase):
    def test_actual_requests_boundaries_and_lifecycle_are_auditable(self):
        msg={'role':'assistant','content':'','tool_calls':[{'id':'p','type':'function','function':{
            'name':'run_python','arguments':json.dumps({'code':'fixture','span_ids':[]})}}]}
        cfg={'arms':['code_guided'],'general_guidance_version':'appworld_public_rules_v1',
            'code_runtime_guidance_version':'provided_callables_v1','python_state_version':'task_namespace_v1',
            'api_budget_by_task':{'dev':80}}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(fixture,'runner',runner),patch.object(runner,'PersistentApiPython',Session):
                summary,sent,requests=fixture.P18Controls().run_fixture(root,'P29',
                    config_updates=cfg,response_messages=[msg])
            self.assertEqual(summary['stop_reason'],'agent_declared_complete')
            self.assertEqual(summary['api_requests'],2)
            self.assertTrue(summary['python_session']['container_removed'])
            trial=root/'storage/records/context_pilot/P29_FIXTURE'
            request=json.loads((trial/'call_001/request.json').read_text())
            prompt=stateful_system_prompt({**cfg,'phase':'P29'})
            self.assertEqual(request['messages'][0]['content'],prompt)
            self.assertIn(PERSISTENT,prompt);self.assertNotIn(FRESH,prompt);self.assertIn(CALLABLE_GUIDANCE,prompt)
            self.assertEqual(request['tools'],CODE_TOOLS)
            self.assertEqual(code_audit(trial)['code_audit_errors'],[])
            from context_preservation import function
            with patch('inspect_appworld_api_schemas.load_public_tools',return_value=(
                [function(n,'fixture',{},[]) for n in ['api_docs__show_app_descriptions','supervisor__complete_task']],{},None)):
                self.assertEqual(boundary_audit(trial,root/'world')['audit_errors'],[])
            p=trial/'programs/call_001_01/result_private.json';r=json.loads(p.read_text());r['session_id']='different';p.write_text(json.dumps(r))
            self.assertTrue(code_audit(trial)['code_audit_errors'])

if __name__=='__main__':unittest.main()
