import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_event_view_probe import ROOT, audit, sha
from context_preservation import LEDGER_TOOL
from local_llama import parse_response, payload_for
from run_event_view_probe import messages_for, schedule, structural_outcome


def put(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n')


class EventAuditTests(unittest.TestCase):
    def fixture(self,folder):
        run,inputs=folder/'run',folder/'inputs'
        plan={'run_id':'P16_01','variants':['raw','execution_tag','quarantine'],
              'source_runs':['run1'],'conditions':['recorded','rejected_before_dispatch'],
              'first_seed':46,'max_calls':6,'temperature':1,'max_output_tokens':100}
        config={'model':{'model':'synthetic','temperature':1,'seed':46,'num_predict':100},
                'observation_page_characters':24000}
        cases={};manifest={'cases':[]}
        for condition in plan['conditions']:
            case={'case_id':condition,'condition':condition,'task':{'instruction':'perform change'},'tools':[],
                  'spans':{'s1':{'id':'s1','assistant':'proposed change',
                                'action':{'name':'app__change','arguments':'{}'},
                                'observation':{'observation':'returned'}}},
                  'receipts':{'s1':{'span_id':'s1','api_request_sent':True,'effects_unknown':False}}}
            if condition!='recorded':
                case['spans']['s1']['observation']={'format_error':'unknown parameter'}
                case['receipts']['s1']['api_request_sent']=False
            path=inputs/(condition+'.json');put(path,case);cases[condition]=case
            manifest['cases'].append({'case_id':condition,'source_run':'run1','condition':condition,'case_sha256':sha(path)})
        put(inputs/'manifest.json',manifest);put(run/'input_manifest.json',manifest)
        put(run/'plan.json',plan);put(run/'source/configs/P16_event_view_probe_v01.json',plan)
        names=['scripts/run_event_view_probe.py','scripts/execution_event_views.py','scripts/native_ledger_memory.py',
               'scripts/context_preservation.py','scripts/local_llama.py']
        for name in names:
            path=run/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((ROOT/name).read_bytes())
        names+=['configs/P16_event_view_probe_v01.json']
        put(run/'freeze_record.json',{'plan_sha256':sha(run/'source/configs/P16_event_view_probe_v01.json'),
                                     'input_manifest_sha256':sha(inputs/'manifest.json'),
                                     'source_hashes':{n:sha(run/'source'/n) for n in names}})
        put(run/'provenance.json',{'config':config})
        order=schedule(plan,manifest);put(run/'schedule.json',order)
        usages=[];results=[];counts=[]
        for i,item in enumerate(order,1):
            case=cases[item['case_id']];call_id=f'call_{i:03d}';call=run/call_id
            request=payload_for(config['model'],messages_for(case,item['variant'],24000),[LEDGER_TOOL])
            put(call/'request.json',request)
            value={'items':[{'key':'checked','requirement':'inspected response','status':'done','source_ids':['s1']}],
                   'constraints':[],'unresolved':[]}
            message={'role':'assistant','content':'','tool_calls':[{'function':{'name':'submit_ledger','arguments':json.dumps(value)}}]}
            raw={'usage':{'prompt_tokens':100,'completion_tokens':5,'total_tokens':105},
                 'choices':[{'finish_reason':'tool_calls','message':message}]}
            response=parse_response(raw);put(call/'raw_response.json',raw);put(call/'response.json',response)
            usages.append({'id':call_id,'role':'ledger','status':'ok','input_tokens':100,'output_tokens':5,
                           'predicted_input_tokens':100,'wall_seconds':1})
            outcome,ledger=structural_outcome(message,case);put(call/'ledger_private.json',ledger)
            results.append({**item,**outcome,'call_id':call_id,'known_tokens':105,
                            'request_sha256':sha(call/'request.json'),'response_sha256':sha(call/'response.json')})
            counts.append({**item,'input_tokens':100})
        put(run/'usage.json',usages);put(run/'results.json',results);put(run/'input_counts.json',counts)
        put(run/'status.json',{'status':'complete','model_calls':6,'completed_outputs':6,
                              'known_total_tokens':630,'unknown_usage_calls':0,'wall_seconds':6})
        return run,inputs

    def test_accounting_and_normal_controls_without_a_semantic_truth_claim(self):
        with tempfile.TemporaryDirectory() as d:
            run,inputs=self.fixture(Path(d));r=audit(run,inputs)
            self.assertEqual(r['audit_errors'],[])
            self.assertEqual(r['known_total_tokens'],630)
            self.assertFalse(r['semantic_review_complete'])
            self.assertEqual(r['unchanged_controls'][0]['unique_prepared_requests'],1)
            self.assertTrue(any(x['done_only_rejected_sources']==1 for x in r['rows']))

    def test_tampered_request_and_usage_are_detected(self):
        with tempfile.TemporaryDirectory() as d:
            run,inputs=self.fixture(Path(d));p=run/'call_001/request.json';a=json.loads(p.read_text())
            a['seed']=47;put(p,a)
            p=run/'usage.json';a=json.loads(p.read_text());a[0]['output_tokens']=9;put(p,a)
            errors=audit(run,inputs)['audit_errors']
            self.assertIn('call_001 prepared request differs',errors)
            self.assertIn('call_001 usage output_tokens',errors)

    def test_running_run_cannot_be_presented_as_a_final_audit(self):
        with tempfile.TemporaryDirectory() as d:
            run,inputs=self.fixture(Path(d));p=run/'status.json';a=json.loads(p.read_text());a['status']='running';put(p,a)
            with self.assertRaisesRegex(ValueError,'terminal run'):
                audit(run,inputs)


if __name__=='__main__':
    unittest.main()
