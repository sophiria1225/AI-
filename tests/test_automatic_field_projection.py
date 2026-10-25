"""Synthetic source and public-contract fixtures; no model or benchmark tasks."""
import builtins
import contextlib
from copy import deepcopy
from dataclasses import asdict
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from automatic_field_projection import (ProjectionRuntime, execute_projection,
                                        plan_projection)
from appworld_native_tools import NativeCatalog
from container_api_python import ApiChannel
from deferred_view_protocol import RemoteReadViews
from field_read_contract import CONTRACT_ID, FIELDS
from ordinary_complete_read_cache import OrdinaryCachedReadHost
from public_api_envelope import PROTOCOL
from public_api_result_transport import PublicResultTransport
from shared_api_reservations import BudgetedApiChannel, RequestBudget


SOURCE = '''keys = [2, 5, 9]
collected = {}
visited = set()
for key in keys:
    entry = call_api('spotify', 'show_song', song_id=key)
    collected[key] = {'label': entry['title'], 'people': [person['name'] for person in entry['artists']]}
    visited.add(key)
print(collected)
print(len(visited))
'''


def song(identity):
    return {'song_id': identity, 'title': 'record-' + str(identity), 'album_id': None,
            'duration': 180, 'artists': [{'id': identity + 20, 'name': 'performer'}],
            'private_to_full': ['preserved', identity]}


class Fixture:
    def __init__(self):
        self.calls = []
        self.fail = None
        self.bad_body = None

    def request(self, command):
        action = command['call']
        self.calls.append(deepcopy(action))
        if action['api'] == 'show_song_library':
            value = [{k: v for k, v in song(i).items() if k in FIELDS} for i in (2, 5, 9)]
        else:
            identity = action['args']['song_id']
            if identity == self.fail:
                raise RuntimeError('synthetic_terminal_read_failure')
            value = song(identity)
            if identity == self.bad_body:
                value['artists'] = [{'id': 40}]
        envelope = json.dumps(dict(protocol=PROTOCOL, nonce=command['nonce'], status='returned', value=value))
        return {'ok': True, 'result': dict(protocol=PROTOCOL, observation=envelope, declared_complete=False)}


def setup(*, observed=True):
    raw = Fixture()
    definitions = [('show_song_library', 'access_token'), ('show_song', 'song_id')]
    catalog = NativeCatalog([{'type': 'function', 'function': {'name': 'spotify__' + api,
        'parameters': {'type': 'object', 'properties': {argument: {}}}}} for api, argument in definitions])
    catalog.visible.update(catalog.catalog)
    budget = RequestBudget(30)
    channel = BudgetedApiChannel(ApiChannel(catalog, PublicResultTransport(raw), 30), budget)
    host = OrdinaryCachedReadHost(channel, execution_scope='projection-synthetic',
                                  verified_contract=CONTRACT_ID, defer=False)
    client = RemoteReadViews(lambda packet: json.loads(json.dumps(host.request(json.loads(json.dumps(packet))))))
    full = client.call
    scope = {'call_api': full}
    stops = []

    def lookup(app, api, args, fields):
        budget._ready()
        action = {'app': app, 'api': api, 'args': args}
        decoded = catalog.decode({'name': app + '__' + api, 'arguments': json.dumps(args)})
        if set(decoded) != {'app', 'api', 'args'}:
            raise ValueError('synthetic_catalog_rejection')
        grant = host.provider.grant(action, host.epoch)
        found = host.provider.lookup(action, host.epoch)
        if grant is None or found[0] != 'partial':
            return None
        return {field: deepcopy(grant.partial[field]) for field in fields}

    def stop(reason):
        stops.append(reason)
        budget.stopped = True

    runtime = ProjectionRuntime(full, lookup, stop)
    if observed:
        full('spotify', 'show_song_library', access_token='synthetic-credential')
    return raw, budget, host, scope, runtime, stops


def run(source, scope, runtime, optimized=True):
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        if optimized:
            info = execute_projection(asdict(plan_projection(source)), scope, runtime)
        else:
            exec(compile(source, '<synthetic-eager>', 'exec'), scope, scope)
            info = {'transformed': False}
    return capture.getvalue(), info


class AutomaticFieldProjectionTests(unittest.TestCase):
    def test_normal_stdout_full_final_root_and_no_internal_namespace(self):
        results = []
        for optimized in (False, True):
            raw, budget, host, scope, runtime, stops = setup()
            output, info = run(SOURCE, scope, runtime, optimized)
            self.assertEqual(scope['entry'], song(9))
            self.assertEqual(type(scope['entry']), dict)
            self.assertEqual(scope['key'], 9)
            self.assertFalse(any(n.startswith('_harness_projection_') for n in scope))
            self.assertFalse(stops)
            results.append((output, scope['collected'], scope['visited']))
            self.assertEqual(budget.spent, 2 if optimized else 4)
            self.assertEqual(runtime.hits, 2 if optimized else 0)
            if optimized:
                self.assertTrue(info['transformed'])
                self.assertEqual([c['args'].get('song_id') for c in raw.calls], [None, 9])
        self.assertEqual(results[0], results[1])

    def test_two_programs_compare_with_ordinary_cache_in_both_arms(self):
        # Full replies omitted in program one are NOT inserted into ordinary cache.
        counts = []
        for optimized in (False, True):
            raw, budget, host, scope, runtime, stops = setup()
            first = run(SOURCE, scope, runtime, optimized)[0]
            second = run(SOURCE, scope, runtime, optimized)[0]
            self.assertEqual(first, second)
            self.assertEqual(scope['entry'], song(9))
            self.assertFalse(stops)
            self.assertEqual(len(host.provider.cache.exact), 1 if optimized else 3)
            self.assertEqual(host.ordinary_complete_reuses, 1 if optimized else 3)
            self.assertEqual(runtime.hits, 4 if optimized else 0)
            counts.append(budget.spent)
        self.assertEqual(counts, [4, 2])  # cumulative difference 2, never 2 + 3

    def test_later_eager_full_reads_correctly_consume_missing_cache_entries(self):
        later = """keys = [2, 5, 9]
for key in keys:
    entry = call_api('spotify', 'show_song', song_id=key)
    print(entry)
"""
        totals = []
        for optimized in (False, True):
            raw, budget, host, scope, runtime, stops = setup()
            run(SOURCE, scope, runtime, optimized)
            run(later, scope, runtime, optimized)
            totals.append(budget.spent)
        self.assertEqual(totals, [4, 4])

    def test_missing_observations_use_full_calls_without_invented_fields(self):
        raw, budget, host, scope, runtime, stops = setup(observed=False)
        run(SOURCE, scope, runtime)
        self.assertEqual((budget.spent, runtime.hits, runtime.misses), (3, 0, 2))
        self.assertEqual(scope['entry'], song(9))
        self.assertEqual(len(host.provider.cache.exact), 3)

    def test_complete_hit_uses_ordinary_cache_path(self):
        raw, budget, host, scope, runtime, stops = setup()
        runtime.fetch_full('spotify', 'show_song', song_id=2)
        run(SOURCE, scope, runtime)
        self.assertEqual((budget.spent, runtime.hits, host.ordinary_complete_reuses), (3, 1, 1))

    def test_empty_singleton_and_duplicate_boundaries(self):
        for keys in ([], [5], [2, 2, 9]):
            outcomes = []
            for optimized in (False, True):
                raw, budget, host, scope, runtime, stops = setup()
                sentinel = {'unchanged': True}
                scope['entry'] = sentinel
                source = SOURCE.replace('[2, 5, 9]', repr(keys))
                stdout, info = run(source, scope, runtime, optimized)
                self.assertEqual(scope['entry'], song(keys[-1]) if keys else sentinel)
                outcomes.append((stdout, scope['entry'], scope['collected']))
                self.assertFalse(stops)
            self.assertEqual(outcomes[0], outcomes[1])

    def test_terminal_api_failure_stops_without_recovery_fetch(self):
        raw, budget, host, scope, runtime, stops = setup()
        raw.fail = 9
        original_root = {'from_previous_program': True}
        scope['entry'] = original_root
        with self.assertRaises(Exception):
            run(SOURCE, scope, runtime)
        self.assertTrue(budget.stopped)
        self.assertTrue(runtime.failed)
        self.assertEqual(stops, ['automatic_projection_execution_failed'])
        self.assertIs(scope['entry'], original_root)  # fault state is NOT claimed equivalent
        self.assertEqual([c['args'].get('song_id') for c in raw.calls], [None, 9])
        self.assertFalse(any(n.startswith('_harness_projection_') for n in scope))
        with self.assertRaisesRegex(RuntimeError, 'stopped'):
            run(SOURCE, scope, runtime)
        self.assertEqual(len(raw.calls), 2)

    def test_body_failure_stops_and_does_not_materialize_earlier_roots(self):
        raw, budget, host, scope, runtime, stops = setup()
        raw.bad_body = 9
        with self.assertRaises(KeyError):
            run(SOURCE, scope, runtime)
        self.assertTrue(budget.stopped)
        self.assertEqual([c['args'].get('song_id') for c in raw.calls], [None, 9])
        self.assertEqual(scope['entry']['artists'], [{'id': 40}])
        self.assertEqual(len(stops), 1)

    def test_invalid_lookup_projection_is_fatal(self):
        raw, budget, host, scope, runtime, stops = setup()
        runtime.lookup_fields = lambda *args: {'title': 'invented_incomplete_shape'}
        with self.assertRaisesRegex(RuntimeError, 'contract_false'):
            run(SOURCE, scope, runtime)
        self.assertTrue(budget.stopped)
        self.assertEqual(budget.spent, 1)

    def test_conditional_later_loop_is_eager_and_first_loop_still_supported(self):
        source = SOURCE + """more = [2, 11]
for key in more:
    if key not in collected:
        entry = call_api('spotify', 'show_song', song_id=key)
        collected[key] = {'label': entry['title'], 'people': [person['name'] for person in entry['artists']]}
print(collected)
"""
        self.assertEqual(len(plan_projection(source).sites), 1)
        results = []
        for optimized in (False, True):
            raw, budget, host, scope, runtime, stops = setup()
            out, _ = run(source, scope, runtime, optimized)
            results.append((out, scope['entry'], scope['collected']))
            self.assertEqual(scope['entry'], song(11))
        self.assertEqual(results[0], results[1])

    def test_unsupported_effects_and_root_escapes_fall_back_whole_program(self):
        sources = [SOURCE + "unknown_callback()\n", SOURCE + "import math\n", "match 7:\n    case _harness_projection_v1: pass\n" + SOURCE,
            SOURCE + "try:\n    print(1)\nexcept Exception:\n    pass\n",
            SOURCE + "len = 4\n", SOURCE + "print(globals())\n", SOURCE + "print(entry is collected)\n",
            SOURCE.replace("{'label': entry['title'], 'people': [person['name'] for person in entry['artists']]}", 'entry'),
            SOURCE.replace("[person['name'] for person in entry['artists']]", "entry['artists']"),
            SOURCE.replace('    visited.add(key)', "    alias = entry\n    visited.add(key)"),
            SOURCE.replace('    visited.add(key)', "    call_api('spotify', 'like_song', song_id=key)"),
            SOURCE.replace('    visited.add(key)', "    entry['title'] = 'changed'"),
            SOURCE.replace('[2, 5, 9]', repr(list(range(1, 514))))]
        for source in sources:
            with self.subTest(source=source[-80:]):
                plan = plan_projection(source)
                self.assertFalse(plan.eligible)
                self.assertEqual(plan.transformed_source, source)

    def test_shadowed_builtin_runtime_guard_runs_original(self):
        raw, budget, host, scope, runtime, stops = setup()
        printed = []
        scope['print'] = lambda value: printed.append(value)
        _, info = run(SOURCE, scope, runtime)
        self.assertFalse(info['transformed'])
        self.assertEqual(budget.spent, 4)
        self.assertEqual(runtime.hits, 0)
        self.assertEqual(len(printed), 2)
        self.assertFalse(stops)

    def test_root_alias_from_previous_program_remains_unchanged(self):
        raw, budget, host, scope, runtime, stops = setup()
        prior = {'prior': ['snapshot']}
        scope.update(entry=prior, old_alias=prior)
        run(SOURCE, scope, runtime)
        self.assertIs(scope['old_alias'], prior)
        self.assertEqual(scope['entry'], song(9))
        self.assertIsNot(scope['entry'], prior)

    def test_unknown_persistent_object_forces_eager_before_implicit_callback(self):
        raw, budget, host, scope, runtime, stops = setup()
        class PriorObject:
            def __str__(self):
                return 'custom-object'
        scope['prior'] = PriorObject()
        _, info = run('print(prior)\n' + SOURCE, scope, runtime)
        self.assertFalse(info['transformed'])
        self.assertEqual((budget.spent, runtime.hits), (4, 0))
        self.assertFalse(stops)

    def test_literal_list_mutation_invalidates_candidate(self):
        for mutation in ('keys.append(12)', 'keys[0] = 12', 'alias = keys\nalias[0] = 12', 'alias = keys\nalias += [-1]', 'alias = []\nalias = other = keys\nalias.append(-1)', 'alias, other = [keys, 0]', 'alias = []\nholder = [keys]\nalias = holder[0]\nalias.append(-1)'):
            source = SOURCE.replace('collected = {}', mutation + '\ncollected = {}')
            self.assertFalse(plan_projection(source).eligible)

    def test_no_projection_failure_preserves_ordinary_error_and_root(self):
        raw, budget, host, scope, runtime, stops = setup(observed=False)
        raw.fail = 9
        with self.assertRaises(Exception):
            run(SOURCE, scope, runtime)
        self.assertEqual(scope['entry'], song(5))
        self.assertFalse(runtime.failed)
        self.assertFalse(stops)

    def test_error_before_loop_does_not_stop_capability(self):
        raw, budget, host, scope, runtime, stops = setup()
        with self.assertRaises(ZeroDivisionError):
            run('print(1 / 0)\n' + SOURCE, scope, runtime)
        self.assertFalse(budget.stopped)
        self.assertFalse(stops)
        self.assertEqual(runtime.hits, 0)

    def test_mutated_builtin_module_is_not_accepted_as_canonical(self):
        raw, budget, host, scope, runtime, stops = setup()
        plan = asdict(plan_projection(SOURCE))
        original_print = builtins.print
        printed = []
        try:
            builtins.print = lambda value: printed.append(value)
            rejected = plan_projection(SOURCE)
            self.assertFalse(rejected.eligible)
            self.assertEqual(rejected.reason, 'builtin_module_changed')
            info = execute_projection(plan, scope, runtime)
        finally:
            builtins.print = original_print
        self.assertFalse(info['transformed'])
        self.assertEqual(info['reason'], 'builtin_module_changed')
        self.assertEqual((budget.spent, runtime.hits), (4, 0))
        self.assertEqual(len(printed), 2)
        self.assertFalse(stops)

    def test_hash_mismatch_does_not_execute(self):
        raw, budget, host, scope, runtime, stops = setup()
        plan = asdict(plan_projection(SOURCE))
        plan['transformed_source'] += '\nprint(1)'
        with self.assertRaisesRegex(ValueError, 'hash_mismatch'):
            execute_projection(plan, scope, runtime)
        self.assertEqual(budget.spent, 1)


if __name__ == '__main__':
    unittest.main()
