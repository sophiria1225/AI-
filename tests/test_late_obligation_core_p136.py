"""Handwritten P136 evidence/selection boundaries. No model/API/program run."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path[:0] = [str(Path(__file__).resolve().parents[1]/'scripts'), str(Path(__file__).parent)]
import late_obligation_monitor_p136 as monitor_module
from late_obligation_monitor_p136 import LateObligationMonitor, CONTRACT_ID, AUXILIARY_READ
from late_obligation_core_p136 import (capture, notice, selected_prefix_length, encoded, digest,
    CheckpointDisclosure, LateFieldObligations, VERSION, FIELDS, COUNT_MAX)
from test_partitioned_export_monitor import Fixture as PreviousFixture
from test_public_output_grounding import TASK


class Fixture(PreviousFixture):
    def __init__(self):
        super().__init__()
        self.monitor = LateObligationMonitor(deepcopy(TASK), execution_scope='synthetic_execution')


def ready(ids=(11,22,33)):
    f = Fixture().sources()
    f.partition(False, songs=ids); f.partition(True, ids=())
    return f


def synthetic(ids, mask, *, refs=0, scope='1'*64, enumeration='closed'):
    n=len(ids)
    counts=dict(target_entities=n, complete_entities=0, pending_entities=n,
        missing_title=n if 'title' in mask else 0, missing_artists=n if 'artists' in mask else 0,
        missing_artist_name_entities=refs, retired_field_obligations=n*(2-len(mask)))
    p=dict(version=VERSION, public_source_contract_id=CONTRACT_ID, execution_scope_sha256=scope,
        requirement_sha256='2'*64, evidence_sha256='3'*64, enumeration=enumeration,
        taint_reasons=[], source_complete={'song':True,'album':True,'playlist':enumeration=='closed'},
        counts=counts if enumeration=='closed' else None,
        pending=[dict(song_id=i,missing_fields=list(mask),observed_artist_ids_without_names=[])for i in ids]if enumeration=='closed'else[],
        all_required_fields_observed=False, official_task_success_claimed=False)
    return dict(payload=p,sha256=digest(p))


class LateMonitorTests(unittest.TestCase):
    def test_auxiliary_read_preserves_closed_scope_without_adding_liked_ids(self):
        f=ready();before=capture(f.monitor)
        f.send(AUXILIARY_READ,{'access_token':'synthetic-token'},[
            {'playlist_id':999,'song_ids':[888],'title':'Never acquired target metadata'}])
        after=capture(f.monitor)
        self.assertEqual(after['payload']['enumeration'],'closed')
        for k in ('counts','pending','source_complete'):self.assertEqual(before['payload'][k],after['payload'][k])
        self.assertNotEqual(before['sha256'],after['sha256'])
        self.assertNotIn(888,f.monitor.source_state()[1]);self.assertFalse(f.monitor.songs)
    def test_source_contract_distinct_and_actual_public_source_verifier(self):
        import partitioned_export_monitor as old
        self.assertNotEqual(CONTRACT_ID,old.CONTRACT_ID)
        package=Path('/Users/tp26013/AI-/.runtime/appworld/venv/lib/python3.12/site-packages/appworld')
        if package.exists():self.assertEqual(monitor_module.verify_late_obligation_sources(package),CONTRACT_ID)
        identity=monitor_module.contract_identity()
        self.assertEqual(identity['monitor_source_sha256'],hashlib.sha256(Path(monitor_module.__file__).read_bytes()).hexdigest())
    def test_cross_principal_return_stays_unknown(self):
        f=ready();f.send(AUXILIARY_READ,{'access_token':'other'},[])
        self.assertIn('unverified_auxiliary_principal',f.monitor.taints)
        self.assertIsNone(capture(f.monitor)['payload']['counts'])
    def test_raised_and_unsent_are_non_evidence(self):
        for kw in ({'status':'raised'},{'sent':False}):
            f=ready();before=capture(f.monitor);f.send(AUXILIARY_READ,{'access_token':'synthetic-token'},[],**kw)
            self.assertEqual(capture(f.monitor),before)
    def test_unknown_or_malformed_protocol_does_not_clear_taint(self):
        f=ready();f.send(AUXILIARY_READ,{'access_token':'synthetic-token'},[],unknown=True)
        f.send(AUXILIARY_READ,{'access_token':'synthetic-token'},[])
        self.assertEqual(capture(f.monitor)['payload']['enumeration'],'unknown')
        g=ready();event,span=g.send(AUXILIARY_READ,{'access_token':'synthetic-token'},[],sent=False)
        event['span_id']='fresh';span['id']='fresh';event['api_request_sent']=True
        event['api_execution']={'protocol':'wrong','nonce':'nonce-fresh','status':'returned','bridge_request_sent':True,'automatic_retries':0}
        g.monitor.observe(event,span);self.assertTrue(g.monitor.taints)
    def test_nonce_replay_rejected_without_rewriting_original_action(self):
        f=ready();e,s=f.send(AUXILIARY_READ,{'access_token':'synthetic-token'},[])
        e=deepcopy(e);s=deepcopy(s);e['span_id']='fresh';s['id']='fresh'
        with self.assertRaisesRegex(ValueError,'unique_typed_dispatch_nonce'):f.monitor.observe(e,s)
        self.assertEqual(s['action']['name'],AUXILIARY_READ)
    def test_mutation_delete_and_old_taints_sticky(self):
        for api in ('spotify__add_song_to_library','spotify__delete_account'):
            f=ready();f.send(api,{'access_token':'synthetic-token','song_id':11},{'message':'returned'})
            f.send(AUXILIARY_READ,{'access_token':'synthetic-token'},[])
            self.assertEqual(capture(f.monitor)['payload']['enumeration'],'unknown')
    def test_auxiliary_invalid_args_or_shape_fail_closed(self):
        for args,value in [({'page_limit':True},[]),({'page_index':True},[]),({'extra':1},[]),({'sort_by':'other'},[]),({},{}),({},[{}]*6)]:
            f=ready();f.send(AUXILIARY_READ,{'access_token':'synthetic-token',**args},value)
            self.assertTrue(f.monitor.taints)
    def test_no_superclass_capture_or_monkeypatch_escape(self):
        f=PreviousFixture().sources()
        with self.assertRaisesRegex(ValueError,'trusted_exact_monitor'):capture(f.monitor)
        class Other(LateObligationMonitor):pass
        with self.assertRaisesRegex(ValueError,'trusted_exact_monitor'):capture(Other(deepcopy(TASK),execution_scope='x'))


class MatchedSelectionTests(unittest.TestCase):
    def test_same_ids_counts_digit_width_and_mask_have_same_selection(self):
        for digits in (1,46,90):
            ids=[10**digits+i for i in range(64)]
            for cap in (768,2048):
                variants=[synthetic(ids,['title','artists']),synthetic(ids,['artists'],refs=262144),synthetic(ids,['title'],scope='4'*64)]
                selection=[]
                for p in variants:
                    a,b=notice(p,'ids_only',byte_limit=cap),notice(p,'entity_fields',byte_limit=cap)
                    self.assertEqual(a,{**b,'entity_fields':[{'song_id':r['song_id']}for r in b['entity_fields']]})
                    selection.append([r['song_id']for r in a['entity_fields']])
                    self.assertEqual(a['displayed_entities'],selected_prefix_length(ids,byte_limit=cap))
                    self.assertLessEqual(len(encoded(a)),cap);self.assertLessEqual(len(encoded(b)),cap)
                self.assertEqual(selection[0],selection[1]);self.assertEqual(selection[1],selection[2])
    def test_ids_do_not_fill_spare_bytes_and_max_16(self):
        ids=list(range(1,65));p=synthetic(ids,list(FIELDS));a=notice(p,'ids_only');b=notice(p,'entity_fields')
        self.assertEqual(a['displayed_entities'],16);self.assertEqual(a['omitted_entities'],48)
        self.assertEqual(a['displayed_entities'],b['displayed_entities'])
        self.assertLess(len(encoded(a)),len(encoded(b)))
    def test_open_unknown_null_and_no_handle_anywhere(self):
        for state in ('open','unknown'):
            p=synthetic([1],list(FIELDS),enumeration=state)
            a=notice(p,'ids_only');self.assertEqual(a,notice(p,'entity_fields'))
            self.assertIsNone(a['counts']);self.assertIsNone(a['omitted_entities']);self.assertEqual(a['entity_fields'],[])
            self.assertNotIn('handle',encoded(a).decode());self.assertNotIn(p['sha256'],encoded(a).decode())
    def test_private_scope_does_not_change_public_notice(self):
        a=synthetic([1,2],list(FIELDS));b=synthetic([1,2],list(FIELDS),scope='9'*64)
        self.assertNotEqual(a['sha256'],b['sha256'])
        for mode in ('ids_only','entity_fields'):self.assertEqual(notice(a,mode),notice(b,mode))
    def test_count_overflow_mask_or_unsorted_ids_rejected(self):
        p=synthetic([1],['artists'],refs=262145)
        with self.assertRaisesRegex(ValueError,'bounded_closed_counts'):notice(p,'entity_fields')
        for ids in ([2,1],[1,1],[True],[-1]):
            with self.assertRaises(ValueError):notice(synthetic(ids,['artists']),'ids_only')
        with self.assertRaises(ValueError):notice(synthetic([1],['other']),'entity_fields')
    def test_snapshot_hash_tamper_and_no_query_capability(self):
        p=synthetic([1],list(FIELDS));p['payload']['pending']=[]
        with self.assertRaisesRegex(ValueError,'snapshot_hash'):notice(p,'ids_only')
        self.assertFalse(hasattr(LateFieldObligations,'query'))
    def test_transient_once_and_private_scope_bound(self):
        p=synthetic([1],list(FIELDS));c=CheckpointDisclosure('ids_only');c.prepare_packet(p,1,accepted=True)
        messages=[{'role':'system','content':'original'},{'role':'user','content':'task'}]
        before=deepcopy(messages);self.assertEqual(c.actor_view(messages),c.actor_view(messages));self.assertEqual(messages,before)
        c.model_submitted(attempted=False);self.assertIsNotNone(c.pending)
        c.model_submitted(attempted=True);self.assertIsNone(c.pending);self.assertEqual(c.actor_view(messages),messages)
        with self.assertRaisesRegex(ValueError,'scope_changed'):c.prepare_packet(synthetic([1],list(FIELDS),scope='9'*64),2,accepted=True)
    def test_raw_same_capture_without_exposure(self):
        p=capture(ready().monitor);c=CheckpointDisclosure('raw_anchor');c.prepare_packet(p,1,accepted=True)
        self.assertIsNone(notice(p,'raw_anchor'));self.assertEqual(c.captures,1)
        c.model_submitted(attempted=True);self.assertEqual(c.submitted,0)

if __name__=='__main__':unittest.main()
