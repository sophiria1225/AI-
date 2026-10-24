"""Observed-response contract fixtures; no real AppWorld data or APIs."""
import copy
import gc
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from appworld_native_tools import NativeCatalog
from container_api_python import ApiChannel
from deferred_view_protocol import RemoteReadViews
from field_read_contract import CONTRACT_ID, FIELDS
from public_api_envelope import PROTOCOL
from public_api_result_transport import PublicResultTransport
from public_contract_read_views import (PublicContractReadHost, PublicReadAuthority,
                                        PublicContractReadProgram)
from shared_api_reservations import BudgetedApiChannel, RequestBudget
from test_persistent_read_view_python import TrustedSubprocessSession

SONG={'song_id':1,'title':'alpha','album_id':None,'duration':200,
      'artists':[{'id':2,'name':'artist'}],'genre':'ambient','rating':1,'like_count':0}


class Fixture:
    def __init__(self):self.song=copy.deepcopy(SONG);self.calls=[]
    def request(self, command):
        action=command['call'];self.calls.append(copy.deepcopy(action));api=action['api']
        if api=='show_song_library':value=[{**{k:copy.deepcopy(self.song[k]) for k in FIELDS},'added_at':'fixture'}]
        elif api=='show_song':value=copy.deepcopy(self.song)
        elif api=='show_album':value={'album_id':1}
        elif api=='like_song':self.song['like_count']+=1;value={'liked':True}
        else:raise ValueError('unknown fixture')
        envelope=json.dumps(dict(protocol=PROTOCOL,nonce=command['nonce'],status='returned',value=value))
        return {'ok':True,'result':dict(protocol=PROTOCOL,observation=envelope,declared_complete=False)}


def setup(*, defer=True, limit=8):
    arguments={'show_song_library':['access_token'],'show_song':['song_id'],
               'show_album':['album_id'],'like_song':['song_id','access_token']}
    cat=NativeCatalog([{'type':'function','function':{'name':'spotify__'+api,
        'parameters':{'type':'object','properties':{name:{} for name in params}}}}
        for api,params in arguments.items()]);cat.visible.update(cat.catalog)
    fixture=Fixture();budget=RequestBudget(limit)
    ch=BudgetedApiChannel(ApiChannel(cat,PublicResultTransport(fixture),limit),budget)
    host=PublicContractReadHost(ch,execution_scope='handwritten-fixture',verified_contract=CONTRACT_ID,defer=defer)
    client=RemoteReadViews(lambda p:json.loads(json.dumps(host.request(json.loads(json.dumps(p))))))
    return fixture,budget,host,client


class PublicContractReadViewTests(unittest.TestCase):
    def test_partial_requires_already_returned_library_and_its_acquisition_is_charged(self):
        fixture,b,host,c=setup()
        c.call('spotify','show_song_library',access_token='fixture-token')
        v=c.read('spotify','show_song',song_id=1)
        self.assertEqual(v['title'],'alpha');self.assertEqual(b.spent,1);self.assertEqual(b.pending,1)
        self.assertEqual(v['rating'],1);self.assertEqual(b.spent,2);self.assertEqual(b.pending,0)
        self.assertEqual([x['api'] for x in fixture.calls],['show_song_library','show_song'])

    def test_absent_observation_fetches_normally_in_both_policies(self):
        for defer in (False,True):
            fixture,b,host,c=setup(defer=defer)
            v=c.read('spotify','show_song',song_id=1)
            self.assertEqual(dict(v),SONG);self.assertEqual(b.spent,1);self.assertEqual(b.pending,0)

    def test_exact_response_reuse_is_available_to_eager_baseline_with_zero_remaining(self):
        for defer in (False,True):
            fixture,b,host,c=setup(defer=defer,limit=1)
            original=c.read('spotify','show_song',song_id=1)
            reused=c.read('spotify','show_song',song_id=1)
            self.assertEqual(dict(original),dict(reused));self.assertEqual(b.spent,1)
            self.assertEqual(host.exact_reuses,1);self.assertEqual(b.pending,0)

    def test_existing_read_only_handler_preserves_pending_snapshot(self):
        fixture,b,host,c=setup()
        c.call('spotify','show_song_library',access_token='fixture-token')
        v=c.read('spotify','show_song',song_id=1)
        c.call('spotify','show_album',album_id=1)
        self.assertEqual(b.spent,2);self.assertEqual(b.pending,1);self.assertEqual(host.epoch,0)
        self.assertEqual(v['rating'],1)

    def test_unknown_effect_fetches_before_mutation_and_invalidates_future_cache(self):
        fixture,b,host,c=setup()
        c.call('spotify','show_song_library',access_token='fixture-token')
        v=c.read('spotify','show_song',song_id=1)
        c.call('spotify','like_song',song_id=1,access_token='fixture-token')
        self.assertEqual([x['api'] for x in fixture.calls],['show_song_library','show_song','like_song'])
        self.assertEqual(v['like_count'],0);self.assertEqual(host.epoch,1)
        after=c.read('spotify','show_song',song_id=1)
        self.assertEqual(after['like_count'],1);self.assertEqual(b.spent,4)

    def test_catalog_rejection_does_not_materialize_surviving_views(self):
        fixture,b,host,c=setup()
        c.call('spotify','show_song_library',access_token='fixture-token')
        v=c.read('spotify','show_song',song_id=1)
        for api,args in [('not_visible',{}),('like_song',{'unexpected':True})]:
            with self.assertRaises(RuntimeError):c.call('spotify',api,**args)
        self.assertEqual(b.spent,1);self.assertEqual(b.pending,1);self.assertEqual(host.epoch,0)
        self.assertEqual(v['rating'],1)

    def test_released_partial_view_avoids_fetch_but_preserves_source_cost(self):
        fixture,b,host,c=setup()
        c.call('spotify','show_song_library',access_token='fixture-token')
        v=c.read('spotify','show_song',song_id=1);self.assertEqual(v['title'],'alpha')
        del v;gc.collect();c.flush_releases()
        self.assertEqual(b.spent,1);self.assertEqual(b.pending,0);self.assertEqual(len(fixture.calls),1)

    def test_revision_scope_and_conflicting_observations_do_not_create_grants(self):
        p=PublicReadAuthority('one',verified_contract=CONTRACT_ID)
        library=dict(app='spotify',api='show_song_library',args={'access_token':'fixture-token'})
        action=dict(app='spotify',api='show_song',args={'song_id':1})
        partial={k:copy.deepcopy(SONG[k]) for k in FIELDS}
        p.observe(library,[partial],0);self.assertIsNotNone(p.grant(action,0))
        other=PublicReadAuthority('two',verified_contract=CONTRACT_ID)
        self.assertIsNone(other.grant(action,0))
        changed=copy.deepcopy(partial);changed['title']='conflict';p.observe(library,[changed],0)
        self.assertIsNone(p.grant(action,0));self.assertIsNone(p.grant(action,1))
        with self.assertRaises(ValueError):PublicReadAuthority('one',verified_contract='unverified')

    def test_observed_partial_does_not_grant_an_undiscovered_api_capability(self):
        fixture,b,host,c=setup()
        c.call('spotify','show_song_library',access_token='fixture-token')
        host.channel.catalog.visible.remove('spotify__show_song')
        with self.assertRaises(RuntimeError):c.read('spotify','show_song',song_id=1)
        self.assertEqual(b.spent,1);self.assertEqual(b.pending,0)
        self.assertEqual(host.records,{})

    def test_public_provider_is_connected_to_actual_persistent_program_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture,b,host,c=setup();session=TrustedSubprocessSession(tmp)
            program=PublicContractReadProgram(session,b,execution_scope='handwritten-program',
                                              verified_contract=CONTRACT_ID)
            rows=[]
            try:
                sources=["call_api('spotify','show_song_library',access_token='fixture-token')\nv=read_view('spotify','show_song',song_id=1)\nprint(v['title'])",
                         "print(v['rating'])"]
                for index,source in enumerate(sources):
                    base=ApiChannel(host.channel.catalog,host.channel.bridge,b.limit-b.spent)
                    result=program(source,{},base,storage_root=tmp,record_dir=Path(tmp)/f'p{index}',
                                   timeout=5,on_record=rows.append)
                    self.assertEqual(result['status'],'ok')
                    self.assertEqual(result['api_requests'],1)
                self.assertEqual(b.spent,2);self.assertEqual(b.pending,0)
                self.assertEqual([r['action']['name'] for r in rows],
                                 ['spotify__show_song_library','spotify__show_song'])
            finally:session.close()


if __name__=='__main__':unittest.main()
