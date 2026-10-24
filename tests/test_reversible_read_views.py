"""Synthetic certified effects; no real service, model or task execution."""
import copy
import gc
from itertools import product
import json
import unittest

from test_public_contract_read_views import SONG, FIELDS, setup as ordinary_setup
from deferred_view_protocol import RemoteReadViews
from explicit_deferred_read_views import ClosedReadView
from field_read_contract import CONTRACT_ID
from public_api_envelope import PROTOCOL
from reversible_read_views import IntegerEffect, ReversibleReadHost


def authority(action, epoch):
    if action['app'] != 'spotify' or action['api'] != 'like_song':return None
    return IntegerEffect('spotify','show_song','song_id',action['args']['song_id'],
        'like_count',1,{'liked':True},True,True,True)


def setup(*, limit=10, defer=True, allow=True, depth=32, grant=authority):
    fixture,b,original,_=ordinary_setup(limit=limit,defer=defer)
    host=ReversibleReadHost(original.channel,execution_scope='synthetic-certified-effects',
        verified_contract=CONTRACT_ID,defer=defer,allow_reversible=allow,
        max_patch_depth=depth,effect_authority=grant)
    client=RemoteReadViews(lambda p:json.loads(json.dumps(host.request(json.loads(json.dumps(p))))))
    return fixture,b,host,client


def acquire(client):
    client.call('spotify','show_song_library',access_token='fixture-token')
    return client.read('spotify','show_song',song_id=1)


def mutate(client):return client.call('spotify','like_song',song_id=1,access_token='fixture-token')


class ReversibleReadViewTests(unittest.TestCase):
    def test_old_unknown_field_is_reconstructed_after_successful_mutation(self):
        f,b,h,c=setup();v=acquire(c);alias=v;del v
        mutate(c)
        self.assertEqual([x['api'] for x in f.calls],['show_song_library','like_song'])
        self.assertEqual(b.pending,1);self.assertEqual(alias['like_count'],0)
        self.assertEqual(f.song['like_count'],1);self.assertEqual(b.spent,3)
        self.assertEqual(h.reconstruction_steps,1);self.assertEqual(b.pending,0)

    def test_last_alias_dies_after_mutation_without_fetching_old_snapshot(self):
        f,b,h,c=setup();v=acquire(c);held={'v':v};del v;mutate(c)
        self.assertEqual(held['v']['title'],SONG['title']);del held;gc.collect();c.flush_releases()
        self.assertEqual(b.spent,2);self.assertEqual(b.pending,0)
        self.assertEqual(h.records,{});self.assertEqual(h.undo,{})

    def test_old_reconstruction_never_contaminates_current_complete_cache(self):
        f,b,h,c=setup();old=acquire(c);mutate(c)
        self.assertEqual(old['like_count'],0)
        current=c.read('spotify','show_song',song_id=1)
        self.assertEqual(current['like_count'],1);self.assertEqual(h.exact_reuses,1)
        self.assertEqual(b.spent,3)

    def test_multiple_live_versions_keep_distinct_undo_ranges(self):
        f,b,h,c=setup();first=acquire(c);mutate(c)
        second=acquire(c);mutate(c)
        self.assertEqual(second['like_count'],1);self.assertEqual(first['like_count'],0)
        self.assertEqual(f.song['like_count'],2);self.assertEqual(h.reconstruction_steps,3)

    def test_patch_bound_materializes_before_the_next_mutation(self):
        f,b,h,c=setup(depth=1);old=acquire(c);mutate(c);mutate(c)
        self.assertEqual([x['api'] for x in f.calls],
            ['show_song_library','like_song','show_song','like_song'])
        self.assertEqual(old['like_count'],0);self.assertEqual(b.pending,0)
        self.assertEqual(h.undo,{})

    def test_no_certificate_and_disabled_policy_keep_original_barrier(self):
        for kwargs in ({'grant':lambda a,e:None},{'allow':False},{'defer':False}):
            f,b,h,c=setup(**kwargs);old=acquire(c);mutate(c)
            self.assertEqual(old['like_count'],0)
            self.assertEqual([x['api'] for x in f.calls],
                ['show_song_library','show_song','like_song'])
            self.assertEqual(h.effect_events,[])

    def test_budget_refusal_preserves_pending_read_and_sends_no_mutation(self):
        f,b,h,c=setup(limit=2);v=acquire(c)
        with self.assertRaises(RuntimeError):mutate(c)
        self.assertEqual(b.spent,1);self.assertEqual(b.pending,1)
        self.assertEqual(v['like_count'],0);self.assertEqual(f.song['like_count'],0)

    def test_unknown_effect_flushes_and_reconstructs_old_value_first(self):
        f,b,h,c=setup();v=acquire(c);mutate(c)
        # Existing show_album is audited read-only. Removing the certificate for
        # the next like operation forces the original conservative barrier.
        h.effect_authority=lambda a,e:None;mutate(c)
        self.assertEqual(v['like_count'],0);self.assertEqual(f.song['like_count'],2)
        self.assertEqual([x['api'] for x in f.calls],
            ['show_song_library','like_song','show_song','like_song'])

    def test_wrong_success_receipt_freezes_without_retry_or_free_cancellation(self):
        def wrong(a,e):
            p=authority(a,e)
            if p is None:return None
            return IntegerEffect(p.read_app,p.read_api,p.identity_argument,p.identity,p.field,p.change,
                                 {'unexpected':True},True,True,True)
        f,b,h,c=setup(grant=wrong);v=acquire(c)
        with self.assertRaises(RuntimeError):mutate(c)
        self.assertTrue(b.stopped);self.assertEqual(b.spent,2);self.assertEqual(b.pending,1)
        self.assertEqual(len(f.calls),2)
        with self.assertRaises(ClosedReadView):v['title']

    def test_reconstruction_rejects_wrong_type_and_preserves_actual_charge(self):
        f,b,h,c=setup();v=acquire(c);mutate(c);f.song['like_count']=True
        with self.assertRaises(RuntimeError):v['like_count']
        self.assertTrue(b.stopped);self.assertEqual(b.spent,3);self.assertEqual(b.pending,0)

    def test_known_mutation_exception_freezes_even_if_an_effect_already_occurred(self):
        f,b,h,c=setup();v=acquire(c);original=f.request
        def raises_after_effect(command):
            result=original(command)
            if command['call']['api']=='like_song':
                envelope=dict(protocol=PROTOCOL,nonce=command['nonce'],status='raised',
                    error={'type':'ValueError','message':'synthetic mutation failed after an effect'})
                result={'ok':True,'result':dict(protocol=PROTOCOL,observation=json.dumps(envelope),declared_complete=False)}
            return result
        f.request=raises_after_effect
        with self.assertRaises(RuntimeError):mutate(c)
        self.assertEqual(h.channel.rows[-1]['api_execution']['status'],'raised')
        self.assertEqual(f.song['like_count'],1);self.assertTrue(b.stopped)
        self.assertEqual(b.spent,2);self.assertEqual(b.pending,1);self.assertEqual(h.undo,{})
        with self.assertRaises(ClosedReadView):v['title']

    def test_unknown_api_receipt_preserves_unknown_effect_without_inverse_guess(self):
        f,b,h,c=setup();v=acquire(c);original=f.request
        def wrong_nonce(command):
            result=original(command)
            if command['call']['api']=='like_song':
                envelope=json.loads(result['result']['observation']);envelope['nonce']='wrong-synthetic-nonce'
                result['result']['observation']=json.dumps(envelope)
            return result
        f.request=wrong_nonce
        with self.assertRaises(RuntimeError):mutate(c)
        self.assertEqual(h.channel.rows[-1]['api_execution']['status'],'unknown')
        self.assertEqual(f.song['like_count'],1);self.assertTrue(b.stopped)
        self.assertEqual(b.pending,1);self.assertEqual(h.undo,{})
        with self.assertRaises(ClosedReadView):v['title']

    def test_lost_mutation_reply_keeps_actual_effect_and_no_automatic_retry(self):
        f,b,h,c=setup();v=acquire(c)
        def lost(packet):h.request(packet);raise TimeoutError('synthetic lost control reply')
        c.exchange=lost
        with self.assertRaises(TimeoutError):mutate(c)
        self.assertTrue(c.closed);self.assertEqual(f.song['like_count'],1)
        self.assertEqual(b.spent,2);self.assertEqual(b.pending,1)
        self.assertEqual(len(f.calls),2)

    def test_certificate_is_explicit_and_bounds_are_checked(self):
        with self.assertRaises(ValueError):
            IntegerEffect('spotify','show_song','song_id',True,'like_count',1,{},True,True,True)
        with self.assertRaises(ValueError):setup(depth=0)
        p=IntegerEffect('spotify','show_song','song_id',1,'like_count',1,{},False,True,True)
        self.assertFalse(p.permitted())
        self.assertEqual(p.relation({'app':'spotify','api':'show_song','args':{'song_id':2}}),'unchanged')
        self.assertEqual(p.relation({'app':'spotify','api':'show_album','args':{'album_id':1}}),'unsupported')

    def test_shared_complete_response_discharges_both_policies_without_double_fetch(self):
        for allow in (False,True):
            f,b,h,c=setup(allow=allow);a=acquire(c)
            other=c.read('spotify','show_song',song_id=1)
            self.assertEqual(b.pending,2);mutate(c)
            self.assertEqual(a['like_count'],other['like_count'])
            self.assertEqual(a['like_count'],0)
            self.assertEqual(sum(x['api']=='show_song' for x in f.calls),1)
            self.assertEqual(h.exact_materialization_reuses,1);self.assertEqual(b.pending,0)

    def test_negative_change_reconstructs_a_larger_old_value(self):
        def grant(a,e):
            p=authority(a,e)
            if p is None:return None
            return IntegerEffect(p.read_app,p.read_api,p.identity_argument,p.identity,p.field,-1,
                                 p.expected_reply,True,True,True)
        f,b,h,c=setup(grant=grant);f.song['like_count']=5
        original=f.request
        def negative(command):
            result=original(command)
            if command['call']['api']=='like_song':f.song['like_count']-=2
            return result
        f.request=negative;v=acquire(c);mutate(c)
        self.assertEqual(f.song['like_count'],4);self.assertEqual(v['like_count'],5)

    def test_false_effect_attestation_can_return_wrong_old_field_without_detection(self):
        # Counterexample: a successful recount can also repair a stale counter.
        # The success message alone cannot certify a +1 delta from its old value.
        f,b,h,c=setup();f.song['like_count']=17;v=acquire(c);original=f.request
        def recount(command):
            result=original(command)
            if command['call']['api']=='like_song':f.song['like_count']=5
            return result
        f.request=recount;mutate(c)
        self.assertEqual(v['like_count'],4)
        self.assertNotEqual(v['like_count'],17)
        self.assertFalse(b.stopped)  # The wrongly attested premise is not self-checking.

    def test_all_256_short_sequences_match_eager_values_and_end_state(self):
        # Independent eager snapshots define the observations. Both actual
        # deferred policies also share complete-response materialization reuse.
        for sequence in product(('read','mutate','inspect','discard'),repeat=4):
            expected=[];saved=[];count=0
            for op in sequence:
                if op=='read':saved.append(count)
                elif op=='mutate':count+=1
                elif op=='inspect':expected.append([dict(SONG,like_count=n) for n in saved])
                elif saved:saved.pop()
            expected.append([dict(SONG,like_count=n) for n in saved])
            costs=[]
            for allow in (False,True):
                f,b,h,c=setup(allow=allow,limit=20,depth=2)
                c.call('spotify','show_song_library',access_token='fixture-token')
                views=[];observed=[]
                for op in sequence:
                    if op=='read':views.append(c.read('spotify','show_song',song_id=1))
                    elif op=='mutate':mutate(c)
                    elif op=='inspect':observed.append([dict(v) for v in views])
                    elif views:views.pop();c.flush_releases()
                observed.append([dict(v) for v in views])
                self.assertEqual(observed,expected,sequence)
                self.assertEqual(f.song['like_count'],count,sequence)
                views.clear();c.flush_releases()
                self.assertEqual(b.pending,0,sequence);self.assertEqual(h.undo,{},sequence)
                self.assertLessEqual(b.spent+b.pending,b.limit)
                costs.append(b.spent)
            self.assertLessEqual(costs[1],costs[0],sequence)


if __name__=='__main__':unittest.main()
