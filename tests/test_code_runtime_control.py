import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_code_control_appworld as runner
import code_agent_interface as interface
import test_p18_plan as fixture
from test_code_agent_execution import program
from code_runtime_prompts import control_system_prompt,CALLABLE_GUIDANCE
from run_code_appworld import code_system_prompt
from code_control_validation import validate
from run_native_batch import validate_schedule,public_body
from audit_code_execution import audit as code_audit
from audit_native_boundaries import audit as boundary_audit
ROOT=Path(__file__).resolve().parents[1]

class CodeRuntimeControl(unittest.TestCase):
    def plan(self):return json.loads((ROOT/'configs/P28_code_clarification_v01.json').read_text())
    def test_only_append_task_independent_guidance(self):
        p=self.plan()
        self.assertEqual(control_system_prompt(p),code_system_prompt()+CALLABLE_GUIDANCE)
        for task in p['task_ids']:self.assertNotIn(task,CALLABLE_GUIDANCE)
        p['code_runtime_guidance_version']='wrong'
        with self.assertRaises(ValueError):control_system_prompt(p)
    def test_fixed_all_four_and_no_budget_change(self):
        p=self.plan();validate(p);validate_schedule(p)
        for key,val in [('max_output_tokens',8192),('max_api_requests',81),('seed',43)]:
            bad=copy.deepcopy(p);bad[key]=val
            with self.assertRaises(ValueError):validate(bad)
        bad=copy.deepcopy(p);bad['run_order']=bad['run_order'][-1:]
        with self.assertRaises(ValueError):validate(bad)
        self.assertIn('P28',public_body([],{'phase':'P28','status':'waiting'}))
    def test_actual_model_request_and_nested_accounting(self):
        msg={'role':'assistant','content':'','tool_calls':[{'id':'p','type':'function','function':{
            'name':'run_python','arguments':json.dumps({'code':'fixture','span_ids':[]})}}]}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(fixture,'runner',runner),patch.object(runner,'execute_response',
                side_effect=lambda *a,**kw:interface.execute_response(*a,**kw,program=program)):
                summary,sent,requests=fixture.P18Controls().run_fixture(root,'P28',config_updates={
                    'arms':['code_guided'],'general_guidance_version':'appworld_public_rules_v1',
                    'code_runtime_guidance_version':'provided_callables_v1',
                    'api_budget_by_task':{'dev':80}},response_messages=[msg])
            self.assertEqual(summary['api_requests'],2)
            trial=root/'storage/records/context_pilot/P28_FIXTURE'
            request=json.loads((trial/'call_001/request.json').read_text())
            self.assertEqual(request['messages'][0]['content'],control_system_prompt(self.plan()))
            self.assertEqual(request['tools'],interface.CODE_TOOLS)
            self.assertEqual(code_audit(trial)['code_audit_errors'],[])
            from context_preservation import function
            with patch('inspect_appworld_api_schemas.load_public_tools',return_value=(
                [function(n,'fixture',{},[]) for n in ['api_docs__show_app_descriptions','supervisor__complete_task']],{},None)):
                self.assertEqual(boundary_audit(trial,root/'world')['audit_errors'],[])

if __name__=='__main__':unittest.main()
