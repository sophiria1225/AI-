"""Exercise the frozen handwritten sequence with a local synthetic service.

No Docker, AppWorld data, model output or real account credentials are used.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from field_read_contract import CONTRACT_ID, FIELDS
from probe_public_read_views_live import execute_programs, EXPECTED_API, EXPECTED_PENDING
from public_api_envelope import PROTOCOL
from public_api_result_transport import PublicResultTransport
from public_contract_read_views import PublicContractReadProgram
from public_name_catalog import PublicNameCatalog
from shared_api_reservations import RequestBudget
from test_persistent_read_view_python import TrustedSubprocessSession


class Fixture:
    def __init__(self, *, liked=False, length=3, missing_fallback=False, mutation_error=False):
        self.liked, self.length = liked, length
        self.missing_fallback, self.mutation_error = missing_fallback, mutation_error
        self.calls = []
        self.songs = [dict(song_id=i + 10, title=f'fixture-{i}', album_id=None,
            duration=200, artists=[{'id':7,'name':'fixture-artist'}], genre='fixture-genre',
            like_count=10, release_date='fixture-date') for i in range(3)]

    def request(self, command):
        action = command['call']; api = action['api']; args = action['args']
        self.calls.append(copy.deepcopy(action))
        status = 'returned'
        if api == 'show_account_passwords':
            value = [{'account_name':'spotify','password':'synthetic-password'}]
        elif api == 'show_profile': value = {'email':'fixture@example.invalid'}
        elif api == 'login': value = {'access_token':'synthetic-token'}
        elif api == 'show_song_library':
            value = [{**{k:copy.deepcopy(song[k]) for k in FIELDS},'added_at':'fixture'}
                     for song in self.songs[:self.length]]
        elif api == 'show_song_privates': value = {'liked':self.liked}
        elif api == 'show_song':
            if self.missing_fallback: raise TimeoutError('synthetic_lost_reply')
            value = copy.deepcopy(self.songs[args['song_id'] - 10])
        elif api in ('like_song','unlike_song'):
            assert (api == 'unlike_song') == self.liked
            self.songs[args['song_id'] - 10]['like_count'] += -1 if self.liked else 1
            self.liked = not self.liked
            value = {'message':'synthetic mutation'}
            if self.mutation_error: status = 'raised'
        else: raise ValueError('outside fixture')
        envelope = dict(protocol=PROTOCOL, nonce=command['nonce'], status=status)
        if status == 'returned': envelope['value'] = value
        else: envelope['error'] = {'type':'RuntimeError','message':'synthetic post-mutation error'}
        return {'ok':True,'result':dict(protocol=PROTOCOL,observation=json.dumps(envelope),
                                       declared_complete=False)}


def catalog():
    arguments = {
        'supervisor__show_account_passwords':[], 'supervisor__show_profile':[],
        'spotify__login':['username','password'],
        'spotify__show_song_library':['access_token','page_index','page_limit'],
        'spotify__show_song_privates':['song_id','access_token'],
        'spotify__show_song':['song_id'],
        'spotify__like_song':['song_id','access_token'],
        'spotify__unlike_song':['song_id','access_token'],
    }
    return PublicNameCatalog([{'type':'function','function':dict(name=api,
        parameters=dict(type='object',properties={key:{} for key in args}))}
        for api,args in arguments.items()])


class LiveReadViewPreparationTests(unittest.TestCase):
    def exercise(self, fixture, policy, stop_after=None):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            session = TrustedSubprocessSession(folder)
            transport = PublicResultTransport(fixture)
            budget = RequestBudget(12)
            program = PublicContractReadProgram(session,budget,execution_scope='synthetic',
                verified_contract=CONTRACT_ID,defer=policy=='deferred')
            condition = dict(policy=policy,programs=[])
            rows=[]; error=None
            try:
                execute_programs(program=program,session=session,transport=transport,catalog=catalog(),
                    budget=budget,folder=folder,storage=folder,condition=condition,
                    recorded=SimpleNamespace(deadline=0),deadline=time.monotonic()+30,
                    stop=lambda: stop_after is not None and len(condition['programs'])>=stop_after,
                    plan={'program_timeout_seconds':5},on_record=rows.append)
            except Exception as exc:
                error=exc
            finally:session.close()
            return SimpleNamespace(condition=condition,budget=budget,host=program.host,
                                   rows=rows,receipts=transport.receipts,error=error)

    def test_six_programs_match_with_strong_cache_baseline_and_both_mutation_directions(self):
        for liked in (False,True):
            outputs=[]
            for policy in ('eager','deferred'):
                fixture=Fixture(liked=liked); result=self.exercise(fixture,policy)
                self.assertIsNone(result.error)
                rows=result.condition['programs']
                self.assertEqual([r['api_requests'] for r in rows],EXPECTED_API[policy])
                self.assertEqual([r['budget']['pending'] for r in rows],EXPECTED_PENDING[policy])
                self.assertEqual(result.host.exact_reuses,1)
                self.assertFalse(result.host.records)
                self.assertEqual(len(fixture.calls),sum(EXPECTED_API[policy]))
                self.assertEqual(len(result.receipts),len(fixture.calls))
                self.assertEqual(sum(r['api_request_sent'] for r in result.rows),len(fixture.calls))
                self.assertTrue(all(r['status']=='returned' for r in result.receipts))
                self.assertEqual([r['client_setup_included'] for r in rows],[True]+[False]*5)
                outputs.append([r['stdout_sha256'] for r in rows])
            self.assertEqual(*outputs)

    def test_short_first_page_stops_without_paging_or_replacing_objects(self):
        fixture=Fixture(length=2); result=self.exercise(fixture,'deferred')
        self.assertIsInstance(result.error,ValueError)
        self.assertEqual(len(result.condition['programs']),1)
        self.assertEqual(result.condition['programs'][0]['status'],'execution_error')
        self.assertEqual(result.budget.spent,4)
        self.assertEqual([a['api'] for a in fixture.calls],
                         ['show_account_passwords','show_profile','login','show_song_library'])

    def test_lost_fallback_reply_preserves_unknown_receipt_and_stops_without_retry(self):
        fixture=Fixture(missing_fallback=True); result=self.exercise(fixture,'deferred')
        self.assertIsInstance(result.error,ValueError)
        self.assertEqual(len(result.condition['programs']),3)
        self.assertTrue(result.budget.stopped)
        self.assertEqual(result.budget.spent,7)
        self.assertEqual(result.receipts[-1]['status'],'unknown')
        self.assertEqual(sum(a['api']=='show_song' for a in fixture.calls),1)
        self.assertFalse(any(a['api'] in ('like_song','unlike_song') for a in fixture.calls))

    def test_known_exception_after_mutation_does_not_retry_or_read_the_new_value(self):
        fixture=Fixture(mutation_error=True); result=self.exercise(fixture,'deferred')
        self.assertIsInstance(result.error,ValueError)
        self.assertEqual(len(result.condition['programs']),6)
        self.assertEqual(result.condition['programs'][-1]['status'],'execution_error')
        self.assertEqual(result.budget.spent,9)
        self.assertEqual(result.receipts[-1]['status'],'raised')
        self.assertEqual(fixture.calls[-1]['api'],'like_song')
        self.assertEqual(fixture.songs[1]['like_count'],11)

    def test_stop_before_future_field_does_not_materialize_pending_view(self):
        fixture=Fixture(); result=self.exercise(fixture,'deferred',stop_after=2)
        self.assertIsInstance(result.error,InterruptedError)
        self.assertEqual(len(result.condition['programs']),2)
        self.assertEqual(result.budget.spent,6)
        self.assertEqual(result.budget.pending,1)
        self.assertFalse(any(a['api']=='show_song' for a in fixture.calls))


if __name__=='__main__':unittest.main()
