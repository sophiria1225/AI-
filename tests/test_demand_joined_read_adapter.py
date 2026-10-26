"""Handwritten data only; no API, worker, subprocess or generated-program execution."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from appworld_native_tools import NativeCatalog
from deferred_read_obligations import Assumptions
from deferred_view_protocol import ReadAuthority
from demand_joined_read_adapter import DemandJoinedReadAdapter, DemandJoinContractError
from joined_public_read_views import JOINED_CONTRACT_ID, JoinedPublicReadAuthority
from public_name_catalog import PublicNameCatalog
from shared_api_reservations import RequestBudget


SONG = {'song_id': 1, 'title': 'synthetic title', 'album_id': 9, 'duration': 120,
        'artists': [{'id': 4, 'name': 'four'}, {'id': 2, 'name': 'two'}], 'genre': 'synthetic genre'}
ALBUM = {'album_id': 9, 'artists': [{'id': 2, 'name': 'two'}, {'id': 4, 'name': 'four'}],
         'songs': [{'id': 1, 'title': SONG['title'], 'artist_ids': [2, 4]}]}
PLAYLIST = {'playlist_id': 8, 'songs': [{'id': 1, 'title': SONG['title'], 'artist_ids': [4, 2]}]}
TOOLS = [{'type': 'function', 'function': {'name': 'spotify__show_song',
          'parameters': {'type': 'object', 'properties': {'song_id': {'type': 'integer'}}}}}]


def action(api='show_song', **args):
    return dict(app='spotify', api=api, args=args or {'song_id': 1})


class DemandJoinedAdapterTests(unittest.TestCase):
    def setUp(self):
        self.verifier = patch('demand_joined_read_adapter.verify_joined_implementation',
                              return_value=JOINED_CONTRACT_ID).start()
        self.addCleanup(patch.stopall)

    def fixture(self, *, source=True, complete=False, limit=10, native=False):
        provider = JoinedPublicReadAuthority('synthetic-execution', verified_contract=JOINED_CONTRACT_ID)
        if source:
            provider.observe(action('show_album', album_id=9), deepcopy(ALBUM), 0)
            provider.observe(action('show_playlist', playlist_id=8, access_token='synthetic'), deepcopy(PLAYLIST), 0)
        if complete:
            provider.observe(action(), deepcopy(SONG), 0)
        catalog = (NativeCatalog if native else PublicNameCatalog)(deepcopy(TOOLS))
        budget, state = RequestBudget(limit), {'epoch': 0}
        adapter = DemandJoinedReadAdapter(provider, catalog, budget, lambda: state['epoch'],
                                          public_source_directory=Path('/synthetic/public/source'))
        return adapter, provider, catalog, budget, state

    def test_constructor_verifies_actual_source_and_rejects_unverified_contract(self):
        self.fixture()
        self.verifier.assert_called_once_with(Path('/synthetic/public/source'))
        for result in ('wrong-contract', ValueError('synthetic verifier failure')):
            self.verifier.reset_mock()
            self.verifier.side_effect = result if isinstance(result, Exception) else None
            self.verifier.return_value = result
            provider = JoinedPublicReadAuthority('synthetic', verified_contract=JOINED_CONTRACT_ID)
            budget = RequestBudget(10)
            with self.assertRaisesRegex(DemandJoinContractError, 'public_implementation_verification_failed'):
                DemandJoinedReadAdapter(provider, PublicNameCatalog(TOOLS), budget, lambda: 0,
                                        public_source_directory=Path('/synthetic/source'))
            self.assertTrue(budget.stopped)
        with self.assertRaises(TypeError):
            DemandJoinedReadAdapter(None, None, None, lambda: 0, verified_contract=JOINED_CONTRACT_ID)

    def test_no_authority_and_missing_needed_field_are_normal_misses(self):
        adapter, provider, _, budget, _ = self.fixture(source=False)
        before = budget.snapshot()
        first = adapter.lookup_fields(action(), ['title', 'artists'], 0)
        self.assertEqual((first.kind, first.value, first.reason), ('miss', None, 'no_observed_authority'))
        provider.observe(action('show_album', album_id=9), deepcopy(ALBUM), 0)
        second = adapter.lookup_fields(action(), ['title', 'artists'], 0)
        self.assertEqual((second.kind, second.value, second.reason), ('miss', None, 'required_fields_not_observed'))
        self.assertEqual(budget.snapshot(), before)
        self.assertFalse(adapter.failed)
        self.assertEqual(adapter.summary()['normal_misses'], 2)

    def test_partial_copies_only_demanded_values_in_existing_playlist_order(self):
        adapter, provider, _, budget, _ = self.fixture()
        before = budget.snapshot()
        result = adapter.lookup_fields(action(), ['title', 'artists'], 0)
        self.assertEqual(result.kind, 'partial')
        self.assertEqual(result.fields, ('title', 'artists'))
        self.assertEqual(result.value, {key: SONG[key] for key in result.fields})
        result.value['artists'][0]['name'] = 'caller mutation'
        self.assertEqual(provider.lookup(action(), 0)[1]['artists'], SONG['artists'])
        self.assertEqual(budget.snapshot(), before)
        self.assertEqual(budget.events, [])
        self.assertEqual(adapter.summary()['partial_hits'], 1)

    def test_valid_partial_lacking_duration_does_not_stop_shared_budget(self):
        adapter, _, _, budget, _ = self.fixture()
        result = adapter.lookup_fields(action(), ['title', 'duration'], 0)
        self.assertEqual(result.kind, 'miss')
        self.assertEqual(result.reason, 'required_fields_not_observed')
        self.assertFalse(budget.stopped)

    def test_complete_hit_returns_no_value_and_retains_common_ordinary_cache(self):
        adapter, provider, _, budget, _ = self.fixture(complete=True)
        before = deepcopy(provider.base.cache.exact)
        result = adapter.lookup_fields(action(), ['title'], 0)
        self.assertEqual((result.kind, result.value, result.reason),
                         ('complete', None, 'ordinary_complete_cache_path'))
        self.assertEqual(provider.base.cache.exact, before)
        self.assertEqual(provider.lookup(action(), 0), ('complete', SONG))
        self.assertEqual(budget.spent, 0)

    def test_observed_conflict_retains_existing_normal_miss_behavior(self):
        adapter, provider, _, budget, _ = self.fixture()
        changed = deepcopy(PLAYLIST); changed['songs'][0]['title'] = 'conflicting title'
        provider.observe(action('show_playlist', playlist_id=8, access_token='synthetic'), changed, 0)
        self.assertEqual(adapter.lookup_fields(action(), ['title'], 0).kind, 'miss')
        self.assertFalse(budget.stopped)

    def test_no_new_capability_is_granted_by_having_values(self):
        for native in (False, True):
            with self.subTest(native=native):
                adapter, _, catalog, budget, _ = self.fixture(native=native)
                if not native:
                    del catalog.catalog['spotify__show_song']
                with self.assertRaisesRegex(DemandJoinContractError, 'ordinary_public_capability_or_schema_rejected'):
                    adapter.lookup_fields(action(), ['title'], 0)
                self.assertTrue(budget.stopped)
        adapter, _, catalog, _, _ = self.fixture(native=True)
        catalog.visible.add('spotify__show_song')
        self.assertEqual(adapter.lookup_fields(action(), ['title'], 0).kind, 'partial')

    def test_invalid_trusted_demands_and_actions_are_sticky_fatal(self):
        cases = [([], action()), (['title', 'title'], action()), (['genre'], action()),
                 ('title', action()), ([True], action()), (['title'], action(song_id=True)),
                 (['title'], action(song_id=-1)), (['title'], action(song_id=1, other=2)),
                 (['title'], {'app': 'spotify', 'api': 'show_album', 'args': {'album_id': 9}})]
        for fields, request in cases:
            with self.subTest(fields=fields, request=request):
                adapter, _, _, budget, _ = self.fixture()
                with self.assertRaises(DemandJoinContractError): adapter.lookup_fields(request, fields, 0)
                reason = adapter.failure_reason
                with self.assertRaisesRegex(DemandJoinContractError, reason):
                    adapter.lookup_fields(action(), ['title'], 0)
                self.assertTrue(budget.stopped)
                self.assertEqual(adapter.summary()['fatal_failures'], 1)
                self.assertEqual(adapter.summary()['partial_hits'], 0)

    def test_malformed_lookup_fields_and_identity_are_not_a_miss(self):
        cases = [('unknown', {}), ['partial', {'song_id': 1, 'title': 'synthetic'}],
                 ('partial', {}), ('partial', {'song_id': 2, 'title': 'synthetic'}),
                 ('partial', {'song_id': 1, 'title': 9}),
                 ('partial', {'song_id': 1, 'title': 'synthetic', 'unknown': None}),
                 ('partial', {'song_id': 1, 'artists': [{'id': True, 'name': 'synthetic'}]})]
        for found in cases:
            with self.subTest(found=found):
                adapter, provider, _, budget, _ = self.fixture()
                with patch.object(provider, 'lookup', return_value=found), self.assertRaises(DemandJoinContractError):
                    adapter.lookup_fields(action(), ['title'], 0)
                self.assertTrue(budget.stopped)

    def test_partial_grant_contradictions_are_fatal_even_when_field_is_missing(self):
        for kind in ('missing', 'wrong_epoch', 'bad_assumption', 'changed_value', 'non_typed'):
            with self.subTest(kind=kind):
                adapter, provider, _, budget, _ = self.fixture()
                value = provider.lookup(action(), 0)[1]
                if kind == 'changed_value': value['title'] = 'changed'
                grant = ReadAuthority(1 if kind == 'wrong_epoch' else 0, value,
                                      Assumptions(False, True, True) if kind == 'bad_assumption' else Assumptions(True, True, True))
                if kind == 'missing': grant = None
                if kind == 'non_typed': grant = {'epoch': 0, 'partial': value}
                with patch.object(provider, 'grant', return_value=grant), self.assertRaises(DemandJoinContractError):
                    adapter.lookup_fields(action(), ['duration'], 0)
                self.assertTrue(budget.stopped)

    def test_complete_label_must_match_existing_full_response_cache(self):
        adapter, provider, _, budget, _ = self.fixture()
        with patch.object(provider, 'lookup', return_value=('complete', deepcopy(SONG))), \
                self.assertRaisesRegex(DemandJoinContractError, 'complete_authority_not_bound_to_ordinary_cache'):
            adapter.lookup_fields(action(), ['title'], 0)
        self.assertTrue(budget.stopped)

    def test_proper_barrier_invalidation_allows_new_epoch_but_stale_or_changed_epoch_is_fatal(self):
        adapter, provider, _, budget, state = self.fixture()
        provider.invalidate(); state['epoch'] = 1
        self.assertEqual(adapter.lookup_fields(action(), ['title'], 1).kind, 'miss')
        self.assertFalse(budget.stopped)
        for kind in ('stale_argument', 'stale_provider', 'changes_during_lookup', 'boolean_epoch'):
            with self.subTest(kind=kind):
                adapter, provider, _, budget, state = self.fixture()
                if kind == 'stale_argument': state['epoch'] = 1
                elif kind == 'stale_provider': state['epoch'] = 1
                elif kind == 'boolean_epoch': state['epoch'] = False
                original = provider.lookup
                def changing(request, epoch):
                    result = original(request, epoch); state['epoch'] += 1
                    return result
                with patch.object(provider, 'lookup', side_effect=changing if kind == 'changes_during_lookup' else original):
                    with self.assertRaises(DemandJoinContractError):
                        adapter.lookup_fields(action(), ['title'], 1 if kind == 'stale_provider' else 0)
                self.assertTrue(budget.stopped)

    def test_scope_contract_bounds_and_shared_binding_changes_are_fatal(self):
        for kind in ('scope', 'contract', 'bounds', 'catalog', 'budget', 'null_budget'):
            with self.subTest(kind=kind):
                adapter, provider, _, budget, _ = self.fixture()
                if kind == 'scope': provider.base.scope = 'different'
                elif kind == 'contract': provider.base.cache.verified_contract = 'wrong'
                elif kind == 'bounds': provider.max_entities -= 1
                elif kind == 'catalog': adapter.catalog = PublicNameCatalog(TOOLS)
                elif kind == 'budget': adapter.budget = RequestBudget(10)
                elif kind == 'null_budget': adapter.budget = None
                with self.assertRaises(DemandJoinContractError): adapter.lookup_fields(action(), ['title'], 0)
                self.assertTrue(budget.stopped)

    def test_zero_free_capacity_can_reuse_but_stopped_ledger_cannot(self):
        adapter, _, _, budget, _ = self.fixture(limit=0)
        self.assertEqual(adapter.lookup_fields(action(), ['title'], 0).kind, 'partial')
        self.assertEqual(budget.snapshot()['available'], 0)
        budget.stopped = True
        with self.assertRaises(DemandJoinContractError): adapter.lookup_fields(action(), ['title'], 0)

    def test_reentrant_trusted_callback_cannot_recover_and_return_a_value(self):
        adapter, _, catalog, budget, _ = self.fixture()
        original = catalog.decode
        def reentrant(fn):
            try: adapter.lookup_fields(action(), ['title'], 0)
            except DemandJoinContractError: pass
            return original(fn)
        with patch.object(catalog, 'decode', side_effect=reentrant), self.assertRaises(DemandJoinContractError):
            adapter.lookup_fields(action(), ['title'], 0)
        self.assertTrue(budget.stopped)
        self.assertEqual(adapter.summary()['partial_hits'], 0)


if __name__ == '__main__':
    unittest.main()
