import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from diagnose_handoff_programs import matching_prefix_requests,require_complete
from handoff_factors import ARMS


class HandoffProgramDiagnosticsTests(unittest.TestCase):
    def test_partial_duplicate_or_changed_phase_is_not_a_completed_cohort(self):
        rows=[{'task_id':str(i),'arm':a,'run_id':str(i)+a} for i in range(4) for a in ARMS]
        report={'phase':'P31','rows':rows,'all_sixteen_reviewed':True,'audit_errors':[]}
        status={'status':'complete','completed':[r['run_id'] for r in rows]}
        require_complete(report,status,'P31')
        for changed in [{**report,'rows':rows[:-1]},{**report,'rows':rows[:-1]+rows[:1]},
                        {**report,'phase':'P32'},{**report,'audit_errors':['unaccounted cost']}]:
            with self.assertRaises(ValueError):require_complete(changed,status,'P31')
        with self.assertRaises(ValueError):require_complete(report,{**status,'status':'running'},'P31')

    def test_matching_arguments_can_have_changed_results_and_include_writes(self):
        def span(value,args=None):
            return {'action':{'name':'app__write','arguments':json.dumps(args or {'private':'not-for-publication','id':1})},'observation':{'value':value}}
        pe=[{'span_id':'p1','api_request_sent':True},{'span_id':'p2','api_request_sent':True}]
        ps={'p1':span('old'),'p2':span('latest')}
        ev=[{'span_id':'s1','api_request_sent':True},{'span_id':'s2','api_request_sent':True},
            {'span_id':'not_sent','api_request_sent':False}]
        ss={'s1':span('latest',{'id':1,'private':'not-for-publication'}),'s2':span('changed')}
        result=matching_prefix_requests(pe,ps,ev,ss)
        self.assertEqual(result['requests_matching_prefix'],2)
        self.assertEqual(result['same_public_observation_as_last_prefix_request'],1)
        self.assertEqual(result['different_public_observation_from_last_prefix_request'],1)
        self.assertFalse(result['unnecessary_request_claim'])
        self.assertNotIn('not-for-publication',json.dumps(result))

    def test_different_arguments_or_api_are_not_assumed_equivalent(self):
        def span(name,arg):return {'action':{'name':name,'arguments':json.dumps({'path':arg})},'observation':{}}
        pe=[{'span_id':'p','api_request_sent':True}];ps={'p':span('a','/root/x')}
        ev=[{'span_id':'s','api_request_sent':True}]
        for item in [span('a','x'),span('b','/root/x')]:
            self.assertEqual(matching_prefix_requests(pe,ps,ev,{'s':item})['requests_matching_prefix'],0)
