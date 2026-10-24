import copy
import gc
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from coalesced_contract_read_views import CoalescedContractReadHost, CoalescedContractReadProgram
from container_api_python import ApiChannel
from deferred_view_protocol import RemoteReadViews
from explicit_deferred_read_views import ClosedReadView
from field_read_contract import CONTRACT_ID, FIELDS
from shared_api_reservations import BudgetedApiChannel, RequestBudget
from test_public_contract_read_views import setup as original_setup, SONG
from test_persistent_read_view_python import TrustedSubprocessSession


def setup(*, defer=True, limit=8):
    raw, budget, previous, _ = original_setup(defer=defer,limit=limit)
    host=CoalescedContractReadHost(previous.channel,execution_scope='fixture-shared',
                                verified_contract=CONTRACT_ID,defer=defer)
    client=RemoteReadViews(lambda p:json.loads(json.dumps(host.request(json.loads(json.dumps(p))))))
    return raw,budget,host,client


def library(client):client.call('spotify','show_song_library',access_token='fixture-token')
def song(client):return client.read('spotify','show_song',song_id=1)


class CoalescedContractReadTests(unittest.TestCase):
    def test_tight_budget_regression_against_original_deferred_and_eager(self):
        raw,b,h,c=original_setup(limit=2);library(c);first=song(c)
        with self.assertRaises(RuntimeError):song(c)
        self.assertEqual((b.spent,b.pending),(1,1))
        self.assertEqual(dict(first),SONG)
        for factory,defer in ((original_setup,False),(setup,True)):
            raw,b,h,c=factory(limit=2,defer=defer);library(c)
            first,second=song(c),song(c)
            self.assertEqual(dict(first),dict(second))
            self.assertEqual((b.spent,b.pending),(2,0))
            self.assertEqual(len(raw.calls),2)

    def test_two_pending_reads_fetch_only_once_with_plentiful_budget(self):
        observed=[]
        for factory in (original_setup,setup):
            raw,b,h,c=factory();library(c);a,both=song(c),song(c)
            self.assertEqual(dict(a),dict(both));observed.append(len(raw.calls))
        self.assertEqual(observed,[3,2])

    def test_one_release_preserves_other_view_and_reservation(self):
        raw,b,h,c=setup(limit=2);library(c);a,other=song(c),song(c)
        del a;gc.collect();c.flush_releases()
        self.assertEqual((b.spent,b.pending,len(h.records)),(1,1,1))
        self.assertEqual(other['rating'],1)
        self.assertEqual((b.spent,b.pending),(2,0))

    def test_last_release_cancels_without_fetch(self):
        raw,b,h,c=setup(limit=2);library(c);views=[song(c),song(c),song(c)]
        self.assertEqual((b.pending,len(h.records),h.coalesced_reuses),(1,3,2))
        views.clear();gc.collect();c.flush_releases()
        self.assertEqual((b.spent,b.pending),(1,0))
        self.assertEqual(h.records,{});self.assertEqual(h.pending_groups,{})

    def test_mutation_materializes_group_once_and_preserves_old_snapshot(self):
        raw,b,h,c=setup();library(c);a,other=song(c),song(c)
        c.call('spotify','like_song',song_id=1,access_token='fixture-token')
        self.assertEqual([x['api'] for x in raw.calls],['show_song_library','show_song','like_song'])
        self.assertEqual((a['like_count'],other['like_count']),(0,0))
        new=song(c);self.assertEqual(new['like_count'],1)
        self.assertEqual((b.spent,b.pending,h.epoch),(4,0,1));self.assertEqual(h.pending_groups,{})

    def test_distinct_objects_and_tasks_do_not_share_reservations(self):
        raw,b,h,c=setup();library(c)
        # A second explicitly observed fixture response, not hidden task data.
        second={k:copy.deepcopy(SONG[k]) for k in FIELDS};second['song_id']=2
        h.provider.observe(dict(app='spotify',api='show_song_library',args={'access_token':'fixture-token'}),[second],h.epoch)
        a=song(c);other=c.read('spotify','show_song',song_id=2)
        self.assertEqual(b.pending,2);self.assertEqual(len(h.pending_groups),2)
        _,b2,h2,c2=setup(limit=2);library(c2);separate=song(c2)
        self.assertEqual(b2.pending,1);self.assertIsNot(h.records['view_0'],h2.records['view_0'])
        self.assertEqual((a['title'],other['title'],separate['title']),('alpha',)*3)

    def test_catalog_validation_cannot_be_bypassed_by_pending_hit(self):
        raw,b,h,c=setup();library(c);a=song(c)
        h.channel.catalog.visible.remove('spotify__show_song')
        with self.assertRaises(RuntimeError):song(c)
        self.assertEqual((b.spent,b.pending,h.coalesced_reuses),(1,1,0))
        self.assertEqual(a['title'],'alpha')

    def test_invalid_release_packet_does_not_cancel_a_group(self):
        raw,b,h,c=setup();library(c);a,other=song(c),song(c)
        for releases in (['view_0','view_0'],['absent']):
            with self.assertRaises(ValueError):h.request(dict(id=h.last_id+1,op='flush',args={},releases=releases))
        self.assertEqual((b.pending,len(h.records)),(1,2))
        self.assertEqual(dict(a),dict(other))

    def test_complete_cached_response_keeps_ordinary_eager_and_deferred_behavior(self):
        for defer in (False,True):
            raw,b,h,c=setup(limit=1,defer=defer)
            a,other=song(c),song(c)
            self.assertEqual(dict(a),dict(other));self.assertEqual(b.spent,1)
            self.assertEqual(h.exact_reuses,1);self.assertEqual(h.coalesced_reuses,0)

    def test_separately_charged_complete_read_satisfies_the_pending_group(self):
        raw,b,h,c=setup(limit=3);library(c);a,other=song(c),song(c)
        full=c.call('spotify','show_song',song_id=1)
        self.assertEqual((b.spent,b.pending),(2,0))
        self.assertEqual(dict(a),full);self.assertEqual(dict(other),full)
        self.assertEqual((b.spent,b.pending),(2,0))
        self.assertEqual(h.materialization_cache_reuses,1);self.assertEqual(len(raw.calls),2)

    def test_fulfilled_reservation_is_released_before_next_mutation_admission(self):
        raw,b,h,c=setup(limit=3);library(c);a,other=song(c),song(c)
        c.call('spotify','show_song',song_id=1)
        c.call('spotify','like_song',song_id=1,access_token='fixture-token')
        self.assertEqual((a['like_count'],other['like_count']),(0,0))
        self.assertEqual((b.spent,b.pending),(3,0))
        self.assertEqual([x['api'] for x in raw.calls],['show_song_library','show_song','like_song'])

    def test_lost_control_reply_keeps_one_reservation_and_does_not_retry(self):
        raw,b,h,c=setup(limit=2);library(c);a=song(c)
        def lost(packet):
            h.request(packet)
            raise TimeoutError('fixture lost control reply')
        c.exchange=lost
        with self.assertRaises(TimeoutError):song(c)
        self.assertTrue(c.closed);self.assertEqual((b.spent,b.pending),(1,1))
        self.assertEqual(len(h.records),2)
        with self.assertRaises(ClosedReadView):a['title']
        self.assertEqual(len(raw.calls),1)

    def test_changed_partial_contract_stops_all_shared_views_without_retry(self):
        raw,b,h,c=setup();library(c);a,other=song(c),song(c)
        raw.song['title']='bad fixture contract'
        with self.assertRaises(RuntimeError):dict(a)
        self.assertTrue(b.stopped);self.assertTrue(c.closed);self.assertEqual(b.spent,2)
        with self.assertRaises(ClosedReadView):dict(other)
        self.assertEqual(len(raw.calls),2)

    def test_group_survives_program_channel_change_but_not_different_budget(self):
        raw,b,h,c=setup();library(c);a,other=song(c),song(c)
        base=ApiChannel(h.channel.catalog,h.channel.bridge,b.limit-b.spent)
        h.attach(BudgetedApiChannel(base,b))
        self.assertEqual(dict(a),dict(other));self.assertEqual(b.spent,2)
        base=ApiChannel(h.channel.catalog,h.channel.bridge,8)
        with self.assertRaises(ValueError):h.attach(BudgetedApiChannel(base,RequestBudget(8)))

    def test_persistent_adapter_uses_same_interface_and_corrected_API_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw,b,h,c=setup(limit=2);session=TrustedSubprocessSession(tmp)
            program=CoalescedContractReadProgram(session,b,execution_scope='fixture-program',
                                               verified_contract=CONTRACT_ID)
            rows=[]
            try:
                sources=["call_api('spotify','show_song_library',access_token='fixture-token')\na=read_view('spotify','show_song',song_id=1)\nb=read_view('spotify','show_song',song_id=1)\nprint(a['title'],b['title'])",
                         "del a\nprint(b['rating'])"]
                for i,source in enumerate(sources):
                    base=ApiChannel(h.channel.catalog,h.channel.bridge,b.limit-b.spent)
                    result=program(source,{},base,storage_root=tmp,record_dir=Path(tmp)/f'p{i}',timeout=5,on_record=rows.append)
                    self.assertEqual(result['status'],'ok');self.assertEqual(result['api_requests'],1)
                self.assertEqual(b.spent,2);self.assertEqual(b.pending,0)
                self.assertEqual(program.host.coalesced_reuses,1)
                self.assertEqual(len(rows),2)
            finally:session.close()


if __name__=='__main__':unittest.main()
