"""Identity, order, conflicts and epoch boundaries for observed public joins."""
import copy
import gc
import json
from pathlib import Path
import tempfile
import unittest

from test_public_contract_read_views import SONG as BASIC_SONG
from test_persistent_read_view_python import TrustedSubprocessSession
from appworld_native_tools import NativeCatalog
from container_api_python import ApiChannel
from deferred_view_protocol import RemoteReadViews
from field_read_contract import FIELDS
from joined_public_read_views import (JOINED_CONTRACT_ID, JoinedPublicReadAuthority,
                                      JoinedPublicReadHost, JoinedPublicReadProgram)
from public_api_envelope import PROTOCOL
from public_api_result_transport import PublicResultTransport
from shared_api_reservations import BudgetedApiChannel, RequestBudget

SONG = dict(BASIC_SONG,artists=[{'id':4,'name':'four'},{'id':2,'name':'two'}])
ALBUM = dict(album_id=9,artists=[{'id':2,'name':'two'},{'id':4,'name':'four'}],
             songs=[{'id':1,'title':SONG['title'],'artist_ids':[2,4]}])
PLAYLIST = dict(playlist_id=8,songs=[{'id':1,'title':SONG['title'],'artist_ids':[4,2]}])


def action(api,**args):return dict(app='spotify',api=api,args=args)
def target():return action('show_song',song_id=1)
def album():return action('show_album',album_id=9)
def playlist():return action('show_playlist',playlist_id=8,access_token='synthetic-token')
def provider(**kwargs):return JoinedPublicReadAuthority('fixture',verified_contract=JOINED_CONTRACT_ID,**kwargs)


class Fixture:
    def __init__(self):self.song=copy.deepcopy(SONG);self.calls=[]
    def request(self, command):
        call=command['call'];self.calls.append(copy.deepcopy(call));api=call['api']
        if api=='show_album':value=copy.deepcopy(ALBUM)
        elif api=='show_playlist':value=copy.deepcopy(PLAYLIST)
        elif api=='show_song':value=copy.deepcopy(self.song)
        elif api=='show_song_library':value=[{k:copy.deepcopy(self.song[k]) for k in FIELDS}]
        elif api=='like_song':self.song['like_count']+=1;value={'liked':True}
        else:raise ValueError('unsupported synthetic call')
        envelope=dict(protocol=PROTOCOL,nonce=command['nonce'],status='returned',value=value)
        return {'ok':True,'result':dict(protocol=PROTOCOL,observation=json.dumps(envelope),declared_complete=False)}


def setup(*,defer=True,limit=10):
    arguments={'show_song':['song_id'],'show_song_library':['access_token'],
        'show_album':['album_id'],'show_playlist':['playlist_id','access_token'],
        'like_song':['song_id','access_token']}
    catalog=NativeCatalog([{'type':'function','function':{'name':'spotify__'+api,
        'parameters':{'type':'object','properties':{p:{} for p in args}}}}
        for api,args in arguments.items()]);catalog.visible.update(catalog.catalog)
    f=Fixture();b=RequestBudget(limit);base=ApiChannel(catalog,PublicResultTransport(f),limit)
    h=JoinedPublicReadHost(BudgetedApiChannel(base,b),execution_scope='fixture',
        verified_contract=JOINED_CONTRACT_ID,defer=defer)
    c=RemoteReadViews(lambda p:json.loads(json.dumps(h.request(json.loads(json.dumps(p))))))
    return f,b,h,c


class JoinedPublicReadViewTests(unittest.TestCase):
    def test_album_gives_only_observed_title_and_identity_not_guessed_artists(self):
        p=provider();p.observe(album(),ALBUM,0)
        self.assertEqual(p.lookup(target(),0),('partial',{'song_id':1,'title':SONG['title']}))

    def test_playlist_order_is_preserved_when_joined_with_album_artist_names(self):
        p=provider();p.observe(album(),ALBUM,0);p.observe(playlist(),PLAYLIST,0)
        found=p.lookup(target(),0)
        self.assertEqual(found[0],'partial');self.assertEqual(found[1]['artists'],SONG['artists'])
        self.assertNotIn('duration',found[1]);self.assertNotIn('album_id',found[1])

    def test_missing_artist_name_never_fills_a_partial_artist_list(self):
        p=provider();p.observe(playlist(),PLAYLIST,0)
        p.observe(album(),dict(ALBUM,artists=ALBUM['artists'][:1]),0)
        self.assertEqual(set(p.lookup(target(),0)[1]),{'song_id','title'})

    def test_future_source_does_not_mutate_an_earlier_returned_grant(self):
        p=provider();p.observe(playlist(),PLAYLIST,0);old=p.lookup(target(),0)
        p.observe(album(),ALBUM,0)
        self.assertNotIn('artists',old[1]);self.assertIn('artists',p.lookup(target(),0)[1])

    def test_conflicting_title_blocks_current_authority(self):
        p=provider();p.observe(album(),ALBUM,0)
        changed=copy.deepcopy(PLAYLIST);changed['songs'][0]['title']='different'
        p.observe(playlist(),changed,0);self.assertIsNone(p.lookup(target(),0))

    def test_conflicting_artist_name_blocks_join(self):
        p=provider();p.observe(album(),ALBUM,0);p.observe(playlist(),PLAYLIST,0)
        changed=copy.deepcopy(ALBUM);changed['artists'][0]['name']='different'
        p.observe(album(),changed,0);self.assertIsNone(p.lookup(target(),0))

    def test_conflicting_order_blocks_an_otherwise_complete_cached_response(self):
        p=provider();p.observe(target(),SONG,0)
        changed=copy.deepcopy(PLAYLIST);changed['songs'][0]['artist_ids']=[2,4]
        p.observe(playlist(),changed,0);self.assertIsNone(p.lookup(target(),0))

    def test_epoch_change_and_explicit_invalidation_clear_every_source(self):
        p=provider();p.observe(album(),ALBUM,0);p.observe(playlist(),PLAYLIST,0)
        self.assertIsNone(p.lookup(target(),1));p.observe(playlist(),PLAYLIST,1)
        self.assertNotIn('artists',p.lookup(target(),1)[1]);p.cache.invalidate()
        self.assertIsNone(p.lookup(target(),1));self.assertIsNone(provider().lookup(target(),0))

    def test_mismatched_response_identity_and_missing_token_do_not_create_authority(self):
        for call,value in [(album(),dict(ALBUM,album_id=True)),
                           (action('show_playlist',playlist_id=8),PLAYLIST),
                           (action('show_playlist',playlist_id=8,access_token=''),PLAYLIST)]:
            p=provider();p.observe(call,value,0);self.assertIsNone(p.lookup(target(),0))

    def test_boolean_artist_id_is_not_numeric_identity(self):
        p=provider();bad=copy.deepcopy(PLAYLIST);bad['songs'][0]['artist_ids']=[True]
        p.observe(playlist(),bad,0);p.observe(album(),ALBUM,0)
        self.assertNotIn('artists',p.lookup(target(),0)[1])
        self.assertIsNone(p.lookup(action('show_song',song_id=True),0))

    def test_malformed_complete_response_is_not_admitted_through_the_baseline_cache(self):
        p=provider();p.observe(target(),dict(SONG,duration=True),0)
        self.assertIsNone(p.lookup(target(),0))
        self.assertEqual(p.base.cache.exact,{})

    def test_entity_bound_refuses_new_entities_without_eviction_or_invented_names(self):
        p=provider(max_entities=1);p.observe(album(),ALBUM,0);p.observe(playlist(),PLAYLIST,0)
        self.assertGreater(p.bounds_rejected,0);self.assertNotIn('artists',p.lookup(target(),0)[1])
        other=copy.deepcopy(ALBUM);other['songs'][0]['id']=99;p.observe(album(),other,0)
        self.assertIsNone(p.lookup(action('show_song',song_id=99),0))

    def test_unreviewed_source_does_not_supply_partial_fields(self):
        p=provider();p.observe(action('search_songs',query='fixture'),[SONG],0)
        self.assertIsNone(p.lookup(target(),0))

    def test_actual_host_charges_sources_and_defers_unknown_fields(self):
        f,b,h,c=setup();c.call('spotify','show_album',album_id=9)
        c.call('spotify','show_playlist',playlist_id=8,access_token='synthetic-token')
        v=c.read('spotify','show_song',song_id=1)
        self.assertEqual(v['artists'],SONG['artists']);self.assertEqual(b.spent,2)
        self.assertEqual(b.pending,1);self.assertEqual(v['genre'],SONG['genre'])
        self.assertEqual(b.spent,3);self.assertEqual(b.pending,0)

    def test_complete_response_reuse_is_given_to_both_policies(self):
        for defer in (False,True):
            f,b,h,c=setup(defer=defer,limit=1)
            v=c.read('spotify','show_song',song_id=1);again=c.read('spotify','show_song',song_id=1)
            self.assertEqual(dict(v),dict(again));self.assertEqual(b.spent,1)
            self.assertEqual(h.exact_reuses,1)

    def test_unknown_mutation_keeps_old_snapshot_and_clears_join_facts(self):
        f,b,h,c=setup();c.call('spotify','show_album',album_id=9)
        v=c.read('spotify','show_song',song_id=1)
        c.call('spotify','like_song',song_id=1,access_token='synthetic-token')
        self.assertEqual([x['api'] for x in f.calls],['show_album','show_song','like_song'])
        self.assertEqual(v['like_count'],0);self.assertIsNone(h.provider.lookup(target(),h.epoch))

    def test_final_alias_death_keeps_acquisition_cost_and_cancels_only_pending_fetch(self):
        f,b,h,c=setup();c.call('spotify','show_album',album_id=9)
        v=c.read('spotify','show_song',song_id=1);self.assertEqual(v['title'],SONG['title'])
        del v;gc.collect();c.flush_releases()
        self.assertEqual(b.spent,1);self.assertEqual(b.pending,0);self.assertEqual(h.records,{})

    def test_partial_facts_do_not_grant_an_unpublished_api_capability(self):
        f,b,h,c=setup();c.call('spotify','show_album',album_id=9)
        h.channel.catalog.visible.remove('spotify__show_song')
        with self.assertRaises(RuntimeError):c.read('spotify','show_song',song_id=1)
        self.assertEqual(b.spent,1);self.assertEqual(b.pending,0)

    def test_adapter_preserves_alias_across_real_python_program_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            f,b,h,c=setup();session=TrustedSubprocessSession(tmp)
            program=JoinedPublicReadProgram(session,b,execution_scope='fixture-program',
                verified_contract=JOINED_CONTRACT_ID)
            try:
                sources=["call_api('spotify','show_album',album_id=9)\nv=read_view('spotify','show_song',song_id=1)\nheld=v\nprint(v['title'])",
                         "print(held['genre'])"]
                for i,source in enumerate(sources):
                    base=ApiChannel(h.channel.catalog,h.channel.bridge,b.limit-b.spent)
                    result=program(source,{},base,storage_root=tmp,record_dir=Path(tmp)/f'p{i}',timeout=5)
                    self.assertEqual(result['status'],'ok');self.assertEqual(result['api_requests'],1)
                self.assertEqual(b.spent,2);self.assertEqual(b.pending,0)
            finally:session.close()


if __name__=='__main__':unittest.main()
