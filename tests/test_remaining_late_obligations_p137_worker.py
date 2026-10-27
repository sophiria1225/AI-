"""Actual worker/rolling/typed wire, with handwritten external-I/O fixture only."""
import json
from pathlib import Path
import tempfile
import unittest
from remaining_late_obligations_worker_fixture_p137 import fixture, audit_fixture, ROOT
from late_obligation_core_p136 import NOTICE_PREFIX
from public_display import CODE_TOOLS

MODES=('raw_anchor','ids_only','entity_fields')
SLOTS=((1,'entity_fields'),(2,'entity_fields'),(2,'ids_only'),(2,'raw_anchor'))


class LateWorkerTests(unittest.TestCase):
    def test_all_four_same_initial_payload_safe_aux_and_paid_capture(self):
        first=[]
        for replication,mode in SLOTS:
            if True:
                with self.subTest(mode=mode,replication=replication),tempfile.TemporaryDirectory() as td:
                    r=fixture(mode=mode,replication=replication,
                        actions=('seed','liked')+('echo',)*6+('finish',),folder=td)
                    self.assertEqual(r['result']['stop_reason'],'agent_declared_complete')
                    checked=audit_fixture(td,r)
                    self.assertTrue(checked['obligation_accounting_complete'])
                    self.assertEqual(checked['obligation_queries'],0)
                    self.assertEqual(checked['obligation_final_enumeration'],'closed')
                    self.assertEqual(checked['known_total_tokens'],r['result']['known_total_tokens'])
                    control=r['result']['obligation_control']
                    self.assertFalse(control['contract_failed']);self.assertFalse(control['query_interface_exposed'])
                    self.assertFalse(control['public_snapshot_handle_exposed'])
                    self.assertEqual(control['runtime']['checkpoint_captures'],2)
                    self.assertEqual(control['entity_rows_exposed'],0 if mode=='raw_anchor'else 4)
                    self.assertEqual(control['field_rows_exposed'],4 if mode=='entity_fields'else 0)
                    self.assertEqual(r['saved']['obligation_queries_private'],[])
                    first.append((replication,r['captured'][0]['messages'],r['captured'][0]['tools']))
                    for c in r['captured']:
                        if c['role']=='agent':self.assertEqual(c['tools'],CODE_TOOLS)
                        else:self.assertNotIn(NOTICE_PREFIX,json.dumps(c['messages']))
                    self.assertNotIn(NOTICE_PREFIX,json.dumps(r['saved']['conversation_private']))
                    for c in r['saved']['obligation_captures_private']:
                        self.assertEqual([x['song_id']for x in c['packet']['payload']['pending']],[11,22])
        rows=[r for r in first if r[0]==2]
        self.assertEqual(rows[0][1:],rows[1][1:]);self.assertEqual(rows[1][1:],rows[2][1:])
    def test_unadvertised_query_is_ordinary_error_all_modes(self):
        for mode in MODES:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td:
                r=fixture(mode=mode,replication=2,actions=('seed','query','query_then_echo','finish'),folder=td)
                self.assertEqual(r['result']['stop_reason'],'agent_declared_complete')
                checked=audit_fixture(td,r)
                self.assertEqual(checked['obligation_queries'],0)
                self.assertEqual(r['saved']['obligation_queries_private'],[])
                self.assertFalse(any('obligation_query_index'in e for e in r['saved']['events']))
    def test_known_cost_unknown_actor_and_focus_retained(self):
        options=[dict(actions=('seed',)+('echo',)*8+('unknown',)),
                 dict(actions=('seed',)+('echo',)*8+('transport_error',)),
                 dict(actions=('seed',)+('echo',)*9,summary_mode='unknown'),
                 dict(actions=('seed',)+('echo',)*9,summary_mode='transport_error')]
        for opts in options:
            with self.subTest(opts=opts),tempfile.TemporaryDirectory() as td:
                r=fixture(mode='entity_fields',folder=td,**opts);checked=audit_fixture(td,r)
                self.assertEqual(checked['unknown_usage_calls'],1)
                self.assertEqual(checked['known_total_tokens'],r['result']['known_total_tokens'])
                self.assertGreater(checked['known_total_tokens'],0)
    def test_rejected_focus_and_no_checkpoint_no_exposure(self):
        for opts in [dict(actions=('seed','finish')),dict(actions=('seed',)+('echo',)*8+('finish',),summary_mode='invalid')]:
            with self.subTest(opts=opts),tempfile.TemporaryDirectory() as td:
                r=fixture(mode='entity_fields',folder=td,**opts);checked=audit_fixture(td,r)
                self.assertEqual(checked['obligation_checkpoint_captures'],0)
                self.assertEqual(checked['obligation_notice_actor_calls'],0)
                self.assertEqual(r['result']['obligation_control']['field_rows_exposed'],0)
    def test_setup_unknown_api_cleanup_and_explicit_stop(self):
        for opts in [dict(unknown_api=True),dict(cleanup_ok=False),dict(stop_after_api=True),dict(first_cached=1)]:
            with self.subTest(opts=opts),tempfile.TemporaryDirectory() as td:
                r=fixture(mode='ids_only',replication=2,folder=td,**opts);checked=audit_fixture(td,r)
                self.assertEqual(checked['known_total_tokens'],r['result']['known_total_tokens'])
                self.assertEqual(checked['unknown_usage_calls'],r['result']['unknown_usage_calls'])

    def test_real_actor_and_focus_alarm_save_unknown_cleanup_and_restore_handler(self):
        import signal
        for role in ('agent','focus'):
            before=signal.getsignal(signal.SIGALRM)
            with self.subTest(role=role),tempfile.TemporaryDirectory()as td:
                r=fixture(mode='entity_fields',folder=td,actions=('seed',)+('echo',)*9,
                          real_alarm_role=role)
                result=r['result'];self.assertEqual(result['unknown_usage_calls'],1)
                self.assertTrue(result['cleanup_confirmed'])
                self.assertIn(result['stop_reason'],('wall_limit_during_model_call','model_usage_unknown'))
                self.assertEqual(r['saved']['usage'][-1]['role'],role)
                self.assertIsNone(r['saved']['usage'][-1]['input_tokens'])
                self.assertIsNone(r['saved']['usage'][-1]['output_tokens'])
                self.assertEqual(r['saved']['terminal_usage'][-1]['status'],'error')
                self.assertEqual(signal.getsignal(signal.SIGALRM),before)

if __name__=='__main__':unittest.main()
