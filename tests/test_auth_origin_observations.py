import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from auth_origin_observations import ObservationIndex, analyze, LOGIN, MODES
from recorded_request_repetition import digest

READ = 'spotify__show_song_library'


def span(value):
    return {'observation': {'observation': json.dumps(value)}}


def login(index, token, user='person-a', call='call_001'):
    return index.observe(LOGIN, {'username': user, 'password': 'secret-'+user}, 'returned',
                         span({'access_token': token, 'token_type': 'Bearer'}), call)


def read(index, token, value=None, call='call_002', **extra):
    return index.observe(READ, {'access_token': token, **extra}, 'returned',
                         span([{'song_id': 1}] if value is None else value), call)


class AuthOriginTests(unittest.TestCase):
    def test_changed_token_same_login_request_links_only_observations(self):
        i = ObservationIndex(); login(i, 'token-a'); read(i, 'token-a')
        logged = login(i, 'token-b', call='call_003'); r = read(i, 'token-b', call='call_004')
        self.assertTrue(logged['repeated_successful_login'])
        self.assertIsNone(r['exact']['value_equal'])
        self.assertTrue(r['drop_auth_argument']['value_equal'])
        self.assertTrue(r['login_request_origin']['value_equal'])
        self.assertTrue(r['new_equal_observation_from_origin'])
        self.assertFalse(r['online_replacement_permission'])
        self.assertFalse(r['task_progress_established'])

    def test_different_credential_requests_do_not_share_origin(self):
        i = ObservationIndex(); login(i, 'token-a'); read(i, 'token-a')
        login(i, 'token-b', user='person-b'); r = read(i, 'token-b')
        self.assertTrue(r['drop_auth_argument']['value_equal'])
        self.assertIsNone(r['login_request_origin']['value_equal'])

    def test_unobserved_tokens_are_not_guessed_or_decoded(self):
        i = ObservationIndex(); read(i, 'unknown-a'); r = read(i, 'unknown-b')
        self.assertTrue(r['drop_auth_argument']['value_equal'])
        self.assertFalse(r['auth_origin_known'])
        self.assertIsNone(r['login_request_origin']['value_equal'])

    def test_later_login_does_not_reclassify_earlier_read(self):
        i = ObservationIndex(); early = read(i, 'token-a'); login(i, 'token-a')
        later = read(i, 'token-a', call='call_003')
        self.assertFalse(early['auth_origin_known'])
        self.assertTrue(later['exact']['value_equal'])
        self.assertIsNone(later['login_request_origin']['value_equal'])

    def test_page_and_other_argument_values_remain_distinct(self):
        i = ObservationIndex(); login(i, 'token-a'); read(i, 'token-a', page_index=0)
        login(i, 'token-b'); r = read(i, 'token-b', page_index=1)
        self.assertTrue(all(r[m]['previous_request_ordinal'] is None for m in MODES))

    def test_changed_read_result_is_not_counted_as_same_information(self):
        i = ObservationIndex(); login(i, 'token-a'); read(i, 'token-a')
        login(i, 'token-b'); r = read(i, 'token-b', value=[{'song_id': 2}])
        self.assertFalse(r['login_request_origin']['value_equal'])
        self.assertFalse(r['new_equal_observation_from_origin'])

    def test_known_exception_breaks_returned_pair(self):
        i = ObservationIndex(); login(i, 'token-a'); read(i, 'token-a')
        i.observe(READ, {'access_token': 'token-a'}, 'raised', {}, 'call_003')
        r = read(i, 'token-a', call='call_004')
        self.assertTrue(all(r[m]['value_equal'] is None for m in MODES))

    def test_collision_disables_origin_for_that_token(self):
        i = ObservationIndex(); login(i, 'collision'); read(i, 'collision')
        login(i, 'collision', user='person-b'); r = read(i, 'collision')
        self.assertFalse(r['auth_origin_known'])
        self.assertEqual(len(i.ambiguous), 1)
        self.assertFalse(r['new_equal_observation_from_origin'])

    def test_unknown_effect_suppresses_later_origin(self):
        i = ObservationIndex(); login(i, 'token-a'); read(i, 'token-a'); i.unknown_effect()
        login(i, 'token-b'); r = read(i, 'token-b')
        self.assertTrue(r['origin_suppressed_by_unknown'])
        self.assertFalse(r['auth_origin_known'])
        self.assertIsNone(r['login_request_origin']['value_equal'])

    def test_value_and_binding_bounds_are_reported(self):
        i = ObservationIndex(max_entries=1, max_value_bytes=32)
        login(i, 'token-a'); login(i, 'token-b')
        self.assertEqual(i.bounds['token_bindings'], 1)
        read(i, 'token-a', value=['x'*40]); r = read(i, 'token-a', value=['x'*40])
        self.assertFalse(r['exact']['both_returned'])

    def test_unsupported_login_shape_never_registers_token(self):
        i = ObservationIndex()
        r = i.observe(LOGIN, {'username': 'a'}, 'returned', span({'access_token': 'a'}), 'call_001')
        self.assertFalse(r['login_shape_supported'])
        self.assertEqual(i.tokens, {})

    def test_no_credentials_or_mutation_in_public_rows(self):
        i = ObservationIndex(); args={'access_token': 'raw-private-token', 'page_index': 0}; before=copy.deepcopy(args)
        logged=login(i, 'raw-private-token', user='private-user')
        r=i.observe(READ,args,'returned',span([1]),'call_002')
        self.assertEqual(args,before)
        public=json.dumps([logged,r])
        for value in ['raw-private-token','private-user','secret-private-user']:
            self.assertNotIn(value,public)


def fixture(empty_middle=False, other_last=False):
    events=[];spans={};fixed=[];usage=[{'id':f'call_{n:03d}'} for n in range(1,5 if empty_middle else 4)]
    calls=[1,2,4] if empty_middle else [1,2,3]
    for step,call in enumerate(calls):
        for name,args,value in [(LOGIN,{'username':'a','password':'b'},
                                {'access_token':f'token-{step}','token_type':'Bearer'}),
                               (READ,{'access_token':f'token-{step}'},[{'song_id':1}])]:
            ordinal=len(events)+1;sid=f'span-{ordinal}';cid=f'call_{call:03d}'
            spans[sid]={**span(value),'action':{'name':name,'arguments':json.dumps(args)}}
            events.append(dict(span_id=sid,call=cid,api_request_sent=True,stage='python_api',
                               api_execution=dict(bridge_request_sent=True,automatic_retries=0,status='returned')))
            fixed.append(dict(request_ordinal=ordinal,call_id=cid,api_name=name,
                              request_sha256=digest({'name':name,'arguments':args}),
                              receipt_status='returned',effects_unknown=False))
    if other_last:
        events[-1]['span_id']='other-last';spans['other-last']=spans.pop(f'span-{len(events)}')
        spans['other-last']['action']['name']='other__read';fixed[-1]['api_name']='other__read'
        args=json.loads(spans['other-last']['action']['arguments'])
        fixed[-1]['request_sha256']=digest({'name':'other__read','arguments':args})
    return events,spans,usage,fixed


class AuthOriginBoundaryTests(unittest.TestCase):
    def test_fixed_second_consecutive_candidate_is_after_receipt(self):
        r=analyze(*fixture()); calls=r['model_boundaries']
        self.assertFalse(calls[0]['login_request_origin']['all_reads_reobserved_with_only_repeated_logins'])
        self.assertFalse(calls[1]['login_request_origin']['fixed_two_boundary_candidate'])
        self.assertTrue(calls[2]['login_request_origin']['fixed_two_boundary_candidate'])
        self.assertTrue(calls[2]['drop_auth_argument']['fixed_two_boundary_candidate'])
        self.assertTrue(all(not x['exact']['fixed_two_boundary_candidate'] for x in calls))

    def test_empty_boundary_is_not_vacuously_repeated(self):
        r=analyze(*fixture(empty_middle=True));empty=r['model_boundaries'][2]
        self.assertEqual(empty['sent_requests'],0)
        self.assertTrue(all(not empty[m]['all_reads_reobserved_with_only_repeated_logins'] for m in MODES))
        self.assertFalse(r['model_boundaries'][-1]['login_request_origin']['fixed_two_boundary_candidate'])

    def test_other_operation_breaks_fixed_candidate(self):
        r=analyze(*fixture(other_last=True))
        self.assertFalse(r['model_boundaries'][-1]['login_request_origin']['fixed_two_boundary_candidate'])

    def test_fixed_request_mismatch_stops_instead_of_dropping_a_row(self):
        e,s,u,f=fixture();f[-1]['request_sha256']='changed'
        with self.assertRaisesRegex(ValueError,'closed_P95_request_mismatch'):
            analyze(e,s,u,f)


if __name__=='__main__':unittest.main()
