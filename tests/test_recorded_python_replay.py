import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from recorded_python_replay import RecordedChannel, reply_from_receipt, replay_programs, load_programs


SCHEMA = {'name':'sample__read','description':'Synthetic only',
          'parameters':{'type':'object','properties':{'index':{'type':'integer'}}}}
SCHEMAS = {'sample__read': SCHEMA}
REQUEST = {'kind':'api','id':1,'app':'sample','api':'read','arguments':{'index':2}}
ENTRY = {'request':REQUEST,'reply':{'id':1,'ok':True,'value':{'count':7},'new_schemas':{}},
         'originally_sent':True,'declared_complete':False,'effects_unknown':False}
RESULT = {'status':'ok','stdout':'7\n','stdout_truncated':False,'error':None,
          'declared_complete':False,'unknown_effects':False,'api_requests':0,'wall_seconds':0.01}


class RecordedPythonReplay(unittest.TestCase):
    def channel(self, entries=None):
        return RecordedChannel(SCHEMAS, [ENTRY] if entries is None else entries, SCHEMAS)

    def test_matching_requests_use_only_saved_values(self):
        c = self.channel()
        result = c.exchange(copy.deepcopy(REQUEST))
        result['value']['count'] = 99
        self.assertEqual(ENTRY['reply']['value']['count'],7)
        self.assertFalse(c.rows[0]['api_request_sent'])
        self.assertTrue(c.rows[0]['recorded_api_request_sent'])
        self.assertTrue(c.compare_result(RESULT,RESULT)['observable_prefix_matches'])

    def test_name_argument_order_and_type_changes_stop(self):
        for field,value in [('app','other'),('id',2),('arguments',{'index':2.0}),
                            ('arguments',{'index':True}),('arguments',{'index':3})]:
            with self.subTest(field=field,value=value):
                c=self.channel();request=copy.deepcopy(REQUEST);request[field]=value
                with self.assertRaises(ValueError):c.exchange(request)
                self.assertTrue(c.fatal);self.assertEqual(c.rows,[])

    def test_extra_and_missing_requests_fail_correspondence(self):
        c=self.channel()
        self.assertFalse(c.compare_result(RESULT,RESULT)['observable_prefix_matches'])
        c.exchange(REQUEST)
        with self.assertRaises(ValueError):c.exchange({**REQUEST,'id':2})

    def test_print_and_exception_differences_are_separate(self):
        c=self.channel();c.exchange(REQUEST)
        actual={**RESULT,'stdout':'8\n','error':'NameError: missing','status':'execution_error'}
        out=c.compare_result(actual,RESULT)
        self.assertTrue(out['checks']['request_sequence'])
        self.assertFalse(out['checks']['stdout']);self.assertFalse(out['checks']['error'])
        self.assertFalse(out['observable_prefix_matches'])

    def test_receipt_reconstructs_json_text_and_discovery(self):
        span={'action':{'name':'sample__read','arguments':'{"index":2}'},
              'observation':{'observation':'{"count":7}','declared_complete':False}}
        event={'api_request_sent':True,'new_tools':['sample__read']}
        entry=reply_from_receipt(REQUEST,span,event,SCHEMAS)
        self.assertEqual(entry['reply']['value'],{'count':7})
        self.assertEqual(entry['reply']['new_schemas'],SCHEMAS)
        span['observation']['observation']='plain text response'
        self.assertEqual(reply_from_receipt(REQUEST,span,event,SCHEMAS)['reply']['value'],'plain text response')

    def test_rejections_are_not_promoted_to_success(self):
        for key in ('not_executed','format_error','api_error'):
            span={'action':{'name':'sample__read','arguments':'{"index":2}'},'observation':{key:'synthetic rejection'}}
            entry=reply_from_receipt(REQUEST,span,{'api_request_sent':key=='api_error','new_tools':[]},SCHEMAS)
            self.assertFalse(entry['reply']['ok']);self.assertEqual(entry['reply']['error'],'synthetic rejection')
        with self.assertRaises(ValueError):
            reply_from_receipt(REQUEST,span,{'effects_unknown':True},SCHEMAS)

    def test_schema_and_receipt_mismatch_rejected(self):
        with self.assertRaises(ValueError):RecordedChannel({'sample__read':{'name':'other'}},[],SCHEMAS)
        span={'action':{'name':'sample__read','arguments':'{"index":3}'},'observation':{}}
        with self.assertRaises(ValueError):reply_from_receipt(REQUEST,span,{},SCHEMAS)

    def test_replay_does_not_proceed_after_changed_output(self):
        class Session:
            calls=0
            def run(self,*args,**kwargs):
                self.calls+=1
                return {**RESULT,'stdout':'changed\n'}
        session=Session()
        program={'name':'p1','source':{'code':'print(7)','observations':[],'api_schemas':SCHEMAS},
                 'entries':[],'expected':RESULT,'source_sha256':{}}
        rows=replay_programs([program,{**program,'name':'p2'}],SCHEMAS,session,Path('/unused'),Path('/unused'))
        self.assertEqual(session.calls,1);self.assertEqual(len(rows),1)

    def test_loader_uses_outer_receipts_and_program_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            t=Path(tmp);p=t/'programs/agent_001_01';p.mkdir(parents=True)
            source={'code':'print(7)','observations':[],'api_schemas':SCHEMAS,'program_index':1}
            expected={**RESULT,'api_requests':1,'program_index':1,'session_usable':True}
            (p/'input_private.json').write_text(json.dumps(source))
            (p/'result_private.json').write_text(json.dumps(expected))
            done={'kind':'done','program_index':1,**{k:expected[k] for k in ('stdout','stdout_truncated','error')}}
            (p/'wire_private.jsonl').write_text(json.dumps({**REQUEST,'program_index':1})+'\n'+json.dumps(done)+'\n')
            events=[{'span_id':'s1','call':'agent_001','stage':'python_api','api_request_sent':True,'new_tools':[]},
                    {'span_id':'s2','call':'agent_001','stage':'model_tool','api_request_sent':False,'new_tools':[]}]
            spans={'s1':{'action':{'name':'sample__read','arguments':'{"index":2}'},
                         'observation':{'observation':'{"count":7}','declared_complete':False}},
                   's2':{'observation':{'api_receipts':[{'span_id':'s1'}]}}}
            (t/'events.json').write_text(json.dumps(events));(t/'spans.json').write_text(json.dumps(spans))
            programs=load_programs(t,SCHEMAS)
            self.assertEqual(len(programs),1);self.assertEqual(programs[0]['entries'][0]['reply']['value'],{'count':7})
            events[0]['call']='other';(t/'events.json').write_text(json.dumps(events))
            with self.assertRaises(ValueError):load_programs(t,SCHEMAS)


if __name__=='__main__':unittest.main()
