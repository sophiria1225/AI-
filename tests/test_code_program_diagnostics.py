import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from diagnose_code_programs import classify

class ProgramDiagnostics(unittest.TestCase):
    def test_runtime_failure_after_effect_is_not_no_effect_and_error_text_is_private(self):
        u=[{'id':'c1','finish_reason':'stop'},{'id':'c2','finish_reason':'length'}]
        events=[{'call':'c1','span_id':'s1','stage':'python_api','api_request_sent':True},
                {'call':'c1','span_id':'s2','stage':'model_tool','api_request_sent':False},
                {'call':'c2','span_id':'s3','stage':'model_tool','api_request_sent':False}]
        spans={'s1':{'observation':{}},'s2':{'observation':{'status':'code_error'}},
               's3':{'observation':{'format_error':'tool call required'}}}
        programs={'c1':[{'status':'code_error','error':'KeyError: sensitive-fixture',
                        'api_requests':1}]}
        d=classify(u,events,spans,programs)
        self.assertEqual(d['program_errors_after_api_dispatch'],1)
        self.assertEqual(d['call_flags']['no_api_dispatched'],1)
        self.assertEqual(d['program_error_types'],{'KeyError':1})
        self.assertNotIn('sensitive-fixture',json.dumps(d))
        self.assertNotIn('no_api_dispatched',d['call_rows'][0]['flags'])
        self.assertIn('generation_limit',d['call_rows'][1]['flags'])

    def test_unrecognized_exception_name_is_not_published_as_a_label(self):
        d=classify([],[],{}, {'c1':[{'status':'code_error','error':'private-label: x','api_requests':0}]})
        self.assertEqual(d['program_error_types'],{'other_error':1})
        self.assertNotIn('private-label',json.dumps(d))

if __name__=='__main__':unittest.main()
