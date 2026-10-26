"""Handwritten synthetic expected outputs, independent of serialized snapshots."""
import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'scripts'), str(Path(__file__).resolve().parent)]
from copy import deepcopy
from observed_field_obligations import *
import observed_field_obligations as module
from partitioned_export_monitor import PartitionedExportMonitor
from test_public_output_grounding import TASK


def make(*, complete=True, wanted=(11,22,33)):
    m = PartitionedExportMonitor(deepcopy(TASK), execution_scope='fixture')
    # Explicit source scope: song and album empty, two playlist partitions.
    m._page('song', {'page_index':0,'page_limit':20}, [])
    m._page('album', {'page_index':0,'page_limit':20}, [])
    m._page('playlist', {'page_index':0,'page_limit':20,'is_public':False},
            [{'playlist_id':1,'song_ids':list(wanted),'is_public':False}])
    if complete:
        m._page('playlist', {'page_index':0,'page_limit':20,'is_public':True}, [])
    return m


def store(m):
    with patch.object(module,'verify_partitioned_export_sources',return_value=CONTRACT_ID):
        result=ObservedFieldObligations(deepcopy(TASK),execution_scope='fixture',public_source_directory='synthetic')
    result.monitor=m
    return result


def resolve(snapshot,monitor,*,cursor=0,limit=16):
    return store(monitor).query(op='page',handle=snapshot['sha256'],cursor=cursor,limit=limit)


def song(m, sid, title='Synthetic title', artists=None):
    m._song({'song_id':sid,'title':title,'artists':artists or [{'id':101,'name':'Synthetic artist'}]}, sid)


def part(m, sid, aids=(201,202)):
    m._song({'id':sid,'title':'Synthetic partial','artist_ids':list(aids)}, partial=True)


class ObligationTests(unittest.TestCase):
    def test_closed_empty_is_known_not_task_success(self):
        p=capture(make(wanted=()))['payload']
        self.assertEqual(p['counts']['target_entities'],0)
        self.assertTrue(p['all_required_fields_observed']);self.assertFalse(p['official_task_success_claimed'])
    def test_open_scope_has_no_total_or_obligations(self):
        p=capture(make(complete=False))['payload']
        self.assertEqual(p['enumeration'],'open');self.assertIsNone(p['counts']);self.assertEqual(p['pending'],[])
    def test_taint_overrides_complete_boolean_flags(self):
        m=make();m.taints.add('synthetic_unknown');p=capture(m)['payload']
        self.assertEqual(p['enumeration'],'unknown');self.assertIsNone(p['counts']);self.assertEqual(p['pending'],[])
    def test_exact_two_field_requirements_independent_expected(self):
        p=capture(make())['payload']
        self.assertEqual([(r['song_id'],r['missing_fields']) for r in p['pending']],
                         [(11,['title','artists']),(22,['title','artists']),(33,['title','artists'])])
        self.assertEqual(p['counts'],{'target_entities':3,'complete_entities':0,'pending_entities':3,
              'missing_title':3,'missing_artists':3,'missing_artist_name_entities':0,'retired_field_obligations':0})
    def test_known_title_does_not_complete_artist_field(self):
        m=make();part(m,22);p=capture(m)['payload']
        self.assertEqual(p['pending'][1],{'song_id':22,'missing_fields':['artists'],
                                       'observed_artist_ids_without_names':[201,202]})
    def test_dependency_join_retires_only_satisfied_song(self):
        m=make();part(m,22);m._artist({'artist_id':201,'name':'A'});m._artist({'artist_id':202,'name':'B'})
        p=capture(m)['payload'];self.assertEqual([r['song_id'] for r in p['pending']],[11,33]);self.assertEqual(p['counts']['complete_entities'],1)
    def test_direct_reply_retires_required_fields(self):
        m=make();song(m,11);p=capture(m)['payload'];self.assertEqual([r['song_id']for r in p['pending']],[22,33])
    def test_extra_observed_entity_not_added_to_scope(self):
        m=make();song(m,999);self.assertEqual(capture(m)['payload']['counts']['target_entities'],3)
    def test_known_missing_dependency_deduplicated(self):
        m=make();part(m,11,(201,202));part(m,22,(202,203))
        self.assertEqual(capture(m)['payload']['counts']['missing_artist_name_entities'],3)
    def test_changed_metadata_is_unknown_not_latest_wins(self):
        m=make();song(m,11,'A');song(m,11,'B');self.assertEqual(capture(m)['payload']['enumeration'],'unknown')
    def test_snapshot_hash_tamper_rejected(self):
        s=capture(make());s['payload']['pending'].pop()
        with self.assertRaisesRegex(ValueError,'snapshot_hash'):notice(s,'counts_only')
    def test_stale_snapshot_after_new_evidence_rejected(self):
        m=make();s=capture(m);song(m,11)
        r=resolve(s,m);self.assertEqual(r['status'],'stale_snapshot');self.assertEqual(r['rows'],[]);self.assertNotEqual(r['snapshot']['handle'],s['sha256'])
    def test_other_execution_scope_rejected(self):
        m=make();s=capture(m);m.execution_scope_sha256=digest('other')
        r=resolve(s,m);self.assertEqual(r['status'],'stale_snapshot');self.assertEqual(r['rows'],[])
    def test_same_capability_returns_exact_same_rows_both_modes(self):
        m=make();part(m,22);s=capture(m)
        views=[notice(s,mode)for mode in ('counts_only','entity_fields')]
        self.assertEqual(views[0]['handle'],views[1]['handle'])
        a=resolve(s,m,limit=2);b=resolve(s,m,limit=2);self.assertEqual(a,b)
        self.assertEqual([r['song_id']for r in a['rows']],[11,22]);self.assertEqual(a['next_cursor'],2)
    def test_resolver_pagination_no_silent_omission(self):
        m=make();s=capture(m);one=resolve(s,m,limit=2);two=resolve(s,m,cursor=one['next_cursor'],limit=2)
        self.assertEqual([r['song_id']for r in one['rows']+two['rows']],[11,22,33]);self.assertTrue(two['complete_page'])
    def test_bool_cursor_rejected(self):
        m=make();s=capture(m)
        with self.assertRaisesRegex(ValueError,'cursor'):resolve(s,m,cursor=True)
    def test_notice_only_granularity_differs(self):
        s=capture(make());a=notice(s,'counts_only');b=notice(s,'entity_fields')
        self.assertEqual(a['counts'],b['counts']);self.assertEqual(a['entity_fields'],[])
        self.assertEqual(len(b['entity_fields']),3);self.assertEqual(b['omitted_entities'],0)
    def test_both_modes_same_hard_byte_budget(self):
        s=capture(make(wanted=tuple(range(1,400))))
        for mode in ('counts_only','entity_fields'):self.assertLessEqual(len(encoded(notice(s,mode,byte_limit=768))),768)
        a=notice(s,'entity_fields',byte_limit=768)
        self.assertGreater(a['omitted_entities'],0);self.assertEqual(a['displayed_entities']+a['omitted_entities'],399)
    def test_notice_never_discloses_metadata_or_credentials(self):
        m=make();part(m,22);m.tokens['spotify'].add('synthetic-credential-fingerprint');s=capture(m)
        body=encoded(notice(s,'entity_fields')).decode()
        for secret in ('synthetic@example.test','Synthetic partial','synthetic-credential-fingerprint','synthetic.csv'):
            self.assertNotIn(secret,body)
    def test_only_accepted_checkpoint_captures(self):
        c=CheckpointDisclosure('entity_fields');self.assertIsNone(c.prepare(store(make()),1,accepted=False))
        self.assertEqual(c.captures,0);c.prepare(store(make()),1,accepted=True);self.assertEqual(c.captures,1)
    def test_transient_actor_archive_and_count_send_identity(self):
        c=CheckpointDisclosure('entity_fields');c.prepare(store(make()),1,accepted=True)
        original=[{'role':'system','content':'common'},{'role':'user','content':'ordinary task'}];saved=deepcopy(original)
        first=c.actor_view(original);self.assertEqual(first,c.actor_view(original));self.assertEqual(original,saved)
        c.model_submitted(attempted=False);self.assertEqual(first,c.actor_view(original))
        c.model_submitted(attempted=True);self.assertEqual(c.actor_view(original),original);self.assertEqual(c.submitted,1)
    def test_boundary_change_before_actor_is_rejected(self):
        m=make();c=CheckpointDisclosure('entity_fields');c.prepare(store(m),1,accepted=True);song(m,11)
        with self.assertRaisesRegex(ValueError,'capture_boundary_changed'):
            c.actor_view([{'role':'system','content':'common'}])

    def test_unknown_model_outcome_after_dispatch_still_consumes(self):
        c=CheckpointDisclosure('counts_only');c.prepare(store(make()),1,accepted=True);c.model_submitted(attempted=True)
        self.assertIsNone(c.pending)
    def test_same_revision_does_not_duplicate_notice(self):
        c=CheckpointDisclosure('entity_fields');c.prepare(store(make()),1,accepted=True);c.model_submitted(attempted=True)
        with self.assertRaisesRegex(ValueError,'revision'):c.prepare(store(make()),1,accepted=True)
    def test_all_fields_observed_is_not_export_completion(self):
        m=make();[song(m,sid)for sid in (11,22,33)];p=capture(m)['payload']
        self.assertTrue(p['all_required_fields_observed']);self.assertFalse(p['official_task_success_claimed'])
        self.assertIsNone(m.backup);self.assertIsNone(m.deletion)
    def test_wrong_monitor_subclass_is_not_trusted(self):
        class Other(PartitionedExportMonitor):pass
        m=Other(deepcopy(TASK),execution_scope='fixture')
        with self.assertRaisesRegex(ValueError,'trusted_exact'):capture(m)

    def test_raw_anchor_captures_but_never_discloses(self):
        c=CheckpointDisclosure('raw_anchor');c.prepare(store(make()),1,accepted=True)
        messages=[{'role':'system','content':'common'}]
        self.assertEqual(c.actor_view(messages),messages);self.assertEqual(c.captures,1)
        c.model_submitted(attempted=True);self.assertEqual(c.submitted,0);self.assertIsNone(c.pending)

    def test_fresh_snapshot_after_stale_then_page_is_usable(self):
        m=make();st=store(m);old=st.query(op='snapshot',handle=None,cursor=0,limit=16)
        self.assertEqual(old['rows'],[]);song(m,11)
        stale=st.query(op='page',handle=old['snapshot']['handle'],cursor=0,limit=16)
        self.assertEqual(stale['status'],'stale_snapshot');self.assertEqual(stale['rows'],[])
        page=st.query(op='page',handle=stale['snapshot']['handle'],cursor=0,limit=16)
        self.assertEqual([row['song_id']for row in page['rows']],[22,33])

    def test_snapshot_query_shape_and_count_only_response(self):
        st=store(make());r=st.query(op='snapshot',handle=None,cursor=0,limit=16)
        self.assertEqual(r['rows'],[]);self.assertEqual(r['total'],3);self.assertFalse(r['complete_page'])
        for args in (dict(op='snapshot',handle='0'*64,cursor=0,limit=16),
                     dict(op='snapshot',handle=None,cursor=1,limit=16),
                     dict(op='page',handle=None,cursor=0,limit=16),
                     dict(op='page',handle='G'*64,cursor=0,limit=16),
                     dict(op='page',handle=r['snapshot']['handle'],cursor=0,limit=True)):
            with self.assertRaises(ValueError):st.query(**args)

    def test_unknown_fresh_page_preserves_null(self):
        m=make();m.taints.add('unknown');st=store(m)
        r=st.query(op='snapshot',handle=None,cursor=0,limit=16)
        page=st.query(op='page',handle=r['snapshot']['handle'],cursor=0,limit=16)
        self.assertEqual(page['status'],'unknown');self.assertIsNone(page['total']);self.assertEqual(page['rows'],[])

    def test_metadata_contract_omission_is_unknown_not_partial(self):
        m=make();m._song({'song_id':11,'title':'observed'},11)
        self.assertEqual(capture(m)['payload']['enumeration'],'unknown')
        valid=make();part(valid,11)
        self.assertEqual(capture(valid)['payload']['enumeration'],'closed')
        self.assertEqual(capture(valid)['payload']['pending'][0]['missing_fields'],['artists'])

    def test_field_retirement_tracks_fields_not_job_success(self):
        m=make();part(m,11);p=capture(m)['payload']
        self.assertEqual(p['counts']['retired_field_obligations'],1)
        m._artist({'artist_id':201,'name':'A'});m._artist({'artist_id':202,'name':'B'})
        p=capture(m)['payload'];self.assertEqual(p['counts']['retired_field_obligations'],2)
        self.assertFalse(p['official_task_success_claimed'])

    def test_duplicate_observations_do_not_accumulate_obligations(self):
        m=make();part(m,11);a=capture(m);part(m,11);b=capture(m)
        self.assertEqual(a,b)

    def test_query_response_byte_limit_and_explicit_remainder(self):
        m=make(wanted=tuple(range(1,400)));st=store(m)
        r=st.query(op='page',handle=st.capture()['sha256'],cursor=0,limit=32)
        self.assertLessEqual(len(encoded(r)),RESPONSE_BYTE_LIMIT)
        self.assertEqual(r['total'],399);self.assertEqual(r['next_cursor'],32)
        self.assertFalse(r['complete_page'])

    def test_caller_error_is_distinct_from_contract_failure(self):
        st=store(make())
        with self.assertRaises(ObligationQueryError):
            st.query(op='page',handle='bad',cursor=0,limit=16)
        with self.assertRaises(ObligationQueryError):
            st.query(op='page',handle=st.capture()['sha256'],cursor=100,limit=16)
        with patch.object(st,'capture',side_effect=ValueError('synthetic_core_contract')):
            try:st.query(op='snapshot',handle=None,cursor=0,limit=16)
            except ValueError as error:self.assertNotIsInstance(error,ObligationQueryError)
            else:self.fail('core failure must propagate')

    def test_single_row_transport_overflow_is_contract_failure(self):
        m=make(wanted=(11,));part(m,11,tuple(10**30+i for i in range(512)))
        st=store(m)
        try:st.query(op='page',handle=st.capture()['sha256'],cursor=0,limit=16)
        except ValueError as error:
            self.assertNotIsInstance(error,ObligationQueryError)
            self.assertEqual(str(error),'query_row_exceeds_response_budget')
        else:self.fail('unrepresentable source row must not be silently omitted')

    def test_prepared_runtime_packet_does_not_recapture_for_views(self):
        st=store(make());packet=st.capture()
        for mode in MODES:
            c=CheckpointDisclosure(mode)
            with patch.object(st,'capture',side_effect=AssertionError('duplicate capture')):
                c.prepare_packet(packet,1,accepted=True)
                a=c.actor_view([{'role':'system','content':'same'}])
                b=c.actor_view([{'role':'system','content':'same'}])
            self.assertEqual(a,b);self.assertEqual(c.captures,1)

    def test_prepare_packet_integrity_and_cross_revision_scope(self):
        st=store(make());packet=st.capture();bad=deepcopy(packet);bad['payload']['counts']['target_entities']=999
        c=CheckpointDisclosure('entity_fields')
        with self.assertRaisesRegex(ValueError,'snapshot_hash'):c.prepare_packet(bad,1,accepted=True)
        c.prepare_packet(packet,1,accepted=True);c.model_submitted(attempted=True)
        st.monitor.execution_scope_sha256=digest('other-execution')
        with self.assertRaisesRegex(ValueError,'scope_changed'):c.prepare_packet(st.capture(),2,accepted=True)

    def test_rejected_revision_never_captures(self):
        st=store(make());c=CheckpointDisclosure('entity_fields')
        with patch.object(st,'capture',side_effect=AssertionError('rejected capture')):
            self.assertIsNone(c.prepare(st,1,accepted=False))
        self.assertEqual(c.captures,0);self.assertIsNone(c.pending)

if __name__=='__main__': unittest.main(verbosity=2)
