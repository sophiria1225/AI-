import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from auth_origin_observations import MODES, analyze
from recorded_request_repetition import digest
from recovery_notices import RecoveryMonitor, POLICIES, NOTICES
from recovery_notice_comparison import run_order, cell_id, summarize, validate_plan
from recovery_notice_fixture import fixture, audit_fixture, auditor


def record(name='spotify__show_song', args=None, value=None, status='returned', **extra):
    return dict(action={'name':name,'arguments':args or {'song_id':1}},
        observation={'observation':json.dumps(value if value is not None else {'name':'song'})},
        api_request_sent=True, effects_unknown=False,
        api_execution={'bridge_request_sent':True,'automatic_retries':0,'status':status}, **extra)


def boundary(monitor, rows):
    monitor.begin(f'call_{len(monitor.boundaries)+1:03d}')
    for row in rows:
        monitor.observe(row)
    return monitor.finish()


class RecoveryMonitorTests(unittest.TestCase):
    def test_two_boundaries_and_single_offer_do_not_elide_any_request(self):
        for policy in POLICIES:
            m=RecoveryMonitor(policy)
            for i in range(5):
                result=boundary(m,[record()])
                self.assertEqual(result['drop_auth_argument']['fixed_two_boundary_candidate'],i==2)
            self.assertEqual(len(m.requests),5)
            self.assertEqual(len(m.offers),1)
            self.assertEqual(m.offers[0]['after_call'],'call_003')
            self.assertEqual(m.report()['api_elision_count'],0)

    def test_empty_boundary_changed_value_exception_or_other_action_breaks_streak(self):
        breakers=[[],[record(value={'name':'new'})], [record(status='raised')],
                  [record(),record(name='file_system__write_file')]]
        for breaker in breakers:
            m=RecoveryMonitor('factual')
            boundary(m,[record()]);boundary(m,[record()]);boundary(m,breaker)
            self.assertEqual(m.streaks['drop_auth_argument'],0)
            self.assertFalse(m.offered)

    def test_within_turn_duplicates_are_not_prior_model_progress(self):
        m=RecoveryMonitor('factual')
        for _ in range(3):
            boundary(m,[record(),record()])
        self.assertFalse(m.offered)

    def test_unknown_nonsent_effect_suppresses_notice(self):
        m=RecoveryMonitor('generic')
        boundary(m,[record()]);boundary(m,[record()])
        boundary(m,[record(),{'api_request_sent':False,'effects_unknown':True}])
        self.assertTrue(m.index.poisoned)
        self.assertFalse(m.offered)

    def test_notice_is_ephemeral_and_arguments_and_values_stay_private(self):
        m=RecoveryMonitor('factual')
        for _ in range(3):boundary(m,[record(value={'name':'private song title'})])
        messages=[{'role':'user','content':'existing budget'}]; before=copy.deepcopy(messages)
        supplied,offer=m.supply(messages,'call_004')
        self.assertEqual(messages,before)
        self.assertIn(NOTICES['factual'],supplied[-1]['content'])
        self.assertFalse(offer['model_attempted'])
        self.assertIsNone(m.supply(messages,'call_004')[1])
        self.assertNotIn('private song title',json.dumps(m.report()))
        self.assertNotIn('private song title',supplied[-1]['content'])

    def test_online_predicate_matches_closed_offline_definition_on_synthetic_receipts(self):
        m=RecoveryMonitor('factual');events=[];spans={};fixed=[];usage=[]
        for i in range(1,5):
            cid=f'call_{i:03d}';usage.append({'id':cid})
            token=f'synthetic_{i}'
            rows=[record('spotify__login',{'username':'fixture','password':'fixture'},
                         {'access_token':token,'token_type':'Bearer'}),
                  record('spotify__show_song_library',{'access_token':token,'page_index':0},[{'id':1}])]
            boundary(m,rows)
            for r in rows:
                sid=f's{len(events)+1}';spans[sid]=r
                events.append({'span_id':sid,'call':cid,'stage':'python_api',
                    'api_request_sent':True,'effects_unknown':False,'api_execution':r['api_execution']})
                fixed.append({'request_ordinal':len(events),'call_id':cid,'api_name':r['action']['name'],
                    'request_sha256':digest({'name':r['action']['name'],'arguments':r['action']['arguments']}),
                    'receipt_status':'returned','effects_unknown':False})
        old=analyze(events,spans,usage,fixed)
        self.assertEqual(m.requests,old['requests'])
        for actual,expected in zip(m.boundaries,old['model_boundaries'],strict=True):
            for mode in MODES:self.assertEqual(actual[mode],expected[mode])
        self.assertFalse(m.boundaries[2]['exact']['fixed_two_boundary_candidate'])
        self.assertTrue(m.boundaries[2]['drop_auth_argument']['fixed_two_boundary_candidate'])


class RecoveryWorkerTests(unittest.TestCase):
    def test_notice_is_counted_once_in_actual_input_and_auditable(self):
        starts=[]
        for policy in POLICIES:
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as folder:
                r=fixture(policy=policy,actions=('read','read','read','echo','finish'),
                          token_limit=10000,folder=folder)
                self.assertEqual(r['result']['stop_reason'],'agent_declared_complete')
                self.assertEqual(r['result']['api_requests'],5)
                self.assertEqual(len(r['programs']),5)
                self.assertTrue(r['result']['cleanup_confirmed'])
                self.assertTrue(all(c['cfg']['reasoning_budget_tokens']==-1 for c in r['captured']))
                sent=[any('<recovery_review_v1>' in (x.get('content') or '') for x in c['messages'])
                      for c in r['captured']]
                self.assertEqual(sent,[False,False,False,policy!='none',False])
                self.assertEqual(r['counted'],[c['messages'] for c in r['captured']])
                self.assertNotIn('<recovery_review_v1>',json.dumps(r['saved']['conversation_private']))
                checked=audit_fixture(folder,r,policy)
                self.assertEqual(checked['known_total_tokens'],r['result']['known_total_tokens'])
                if policy!='none':self.assertGreater(checked['known_total_tokens'],250)
                starts.append(r['captured'][:3])
        self.assertEqual(starts[0],starts[1]);self.assertEqual(starts[1],starts[2])

    def test_rejected_notice_input_is_not_a_model_intervention(self):
        with tempfile.TemporaryDirectory() as folder:
            r=fixture(policy='factual',actions=('read','read','read','finish'),token_limit=200,folder=folder)
            self.assertEqual(r['result']['model_calls'],3)
            offer=r['saved']['recovery_observations']['offers'][0]
            self.assertTrue(offer['included_in_supplied_messages'])
            self.assertFalse(offer['model_attempted'])
            audit_fixture(folder,r,'factual')

    def test_unknown_notice_dispatch_stays_unknown_and_unexecuted(self):
        for last in ('unknown','transport_error'):
            with self.subTest(last=last),tempfile.TemporaryDirectory() as folder:
                r=fixture(policy='factual',actions=('read','read','read',last),token_limit=10000,folder=folder)
                self.assertEqual(r['programs'],['read']*3)
                self.assertEqual(r['result']['unknown_usage_calls'],1)
                self.assertEqual(r['result']['model_calls'],4)
                self.assertTrue(r['saved']['recovery_observations']['offers'][0]['model_attempted'])
                audit_fixture(folder,r,'factual')

    def test_actual_notice_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            r=fixture(policy='factual',actions=('read','read','read','finish'),token_limit=10000,folder=folder)
            audit_fixture(folder,r,'factual')
            trial=Path(folder)/'records/context_pilot/BOC_P97_fixture'
            p=trial/'recovery_observations.json';d=json.loads(p.read_text())
            d['offers'][0]['after_call']='call_002';p.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,'recovery_observation_replay_differs'):
                audit_fixture(folder,r,'factual')

    def test_unknown_api_and_stop_do_not_start_another_model_request(self):
        for kw in ({'unknown_api':True},{'stop_after_api':True}):
            r=fixture(**kw)
            self.assertEqual(r['result']['model_calls'],1)


class RecoveryComparisonTests(unittest.TestCase):
    def test_fixed_complete_order(self):
        rows=run_order()
        self.assertEqual(len(rows),12)
        self.assertEqual(len({cell_id(n,p) for n,p in rows}),12)
        self.assertEqual(rows[:6],[(1,'none'),(1,'generic'),(1,'factual'),
                                  (2,'generic'),(2,'factual'),(2,'none')])

    def rows(self):
        return [dict(task_id=str(n),notice_policy=p,record_status='evaluated',success=True,
                     dispatched_notice_inputs=[{'call_id':'call_004', 'before_recovery_messages_sha256':'synthetic'}]
                     if n==4 and p!='none' else [],
                     unknown_usage_calls=0,known_total_tokens={'none':100,'generic':90,'factual':80}[p])
                for n,p in run_order()]

    def test_quality_loss_unknown_and_missing_block_positive_gate(self):
        self.assertTrue(summarize(self.rows(),[])['factual_notice_benefit_gate_met'])
        for change in ({'success':False},{'unknown_usage_calls':1},{'record_status':'not_run','success':None}):
            rows=self.rows();next(r for r in rows if r['notice_policy']=='factual').update(change)
            self.assertFalse(summarize(rows,[])['factual_notice_benefit_gate_met'])
        self.assertFalse(summarize(self.rows(),['audit failure'])['factual_notice_benefit_gate_met'])
        with self.assertRaises(ValueError):summarize(self.rows()[:-1],[])

    def test_no_notice_or_different_prior_history_cannot_establish_notice_benefit(self):
        for changed in ([],[{'call_id':'call_004','before_recovery_messages_sha256':'different'}]):
            rows=self.rows()
            for row in rows:
                if row['notice_policy']=='factual':row['dispatched_notice_inputs']=changed
            self.assertFalse(summarize(rows,[])['factual_notice_benefit_gate_met'])


if __name__=='__main__':unittest.main()
