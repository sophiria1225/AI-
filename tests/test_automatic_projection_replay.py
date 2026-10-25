"""Unit validation only: trusted host controls, no saved-code or Docker launch."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from automatic_field_projection import plan_projection
from automatic_projection_runtime import ProjectionWireClient, ProjectionApiChannel
from field_read_contract import CONTRACT_ID, FIELDS
from probe_automatic_projection_replay import (ActionTape, ReplayApiChannel, ReplayHost,
    ReplayPython, SavedResultTransport, boundary_snapshot, require_empty_observations)
from public_name_catalog import PublicNameCatalog
from shared_api_reservations import RequestBudget


SOURCE = """keys = [5, 9]
result = {}
for key in keys:
    record = call_api('spotify', 'show_song', song_id=key)
    result[key] = {'label': record['title']}
"""


def full(number):
    return {'song_id': number, 'title': 'synthetic-' + str(number), 'album_id': None,
            'artists': [{'id': 21, 'name': 'performer'}], 'duration': 190, 'extra': True}


def entry(api, args, value=None, *, error=None, sent=True):
    reply = {'id': 1, 'ok': error is None}
    reply.update(value=deepcopy(value), new_schemas={}) if error is None else reply.update(error=error)
    return {'request': {'kind': 'api', 'id': 1, 'app': 'spotify', 'api': api, 'arguments': args},
            'reply': reply, 'originally_sent': sent, 'declared_complete': False, 'effects_unknown': False}


def action(number):
    return {'app': 'spotify', 'api': 'show_song', 'args': {'song_id': number}}


def setup(policy):
    tools = [{'type': 'function', 'function': {'name': 'spotify__' + api,
        'parameters': {'type': 'object', 'properties': {arg: {}}}}}
        for api, arg in (('show_song', 'song_id'), ('show_song_library', 'access_token'), ('like_song', 'song_id'))]
    catalog = PublicNameCatalog(tools)
    transport = SavedResultTransport()
    budget = RequestBudget(100)
    transport.tape = ActionTape([])
    host = ReplayHost(ProjectionApiChannel(ReplayApiChannel(catalog, transport, 100), budget),
                      policy=policy, execution_scope='synthetic-replay-' + policy, verified_contract=CONTRACT_ID)
    host.expect(plan_projection(SOURCE))
    client = ProjectionWireClient(lambda app, api, packet: host.request(packet))
    def next_program(entries):
        transport.tape = ActionTape(entries)
        host.attach(ProjectionApiChannel(ReplayApiChannel(catalog, transport, 100), budget))
        host.expect(plan_projection(SOURCE))
    return host, client, transport, budget, next_program


class ProjectionReplayTests(unittest.TestCase):
    def test_fixed_prefix_cannot_reinject_original_observations(self):
        require_empty_observations([{'source': {'observations': []}} for _ in range(10)])
        for observations in ([{'saved_full_reply': {'extra': True}}], {}, None, ()):
            programs = [{'source': {'observations': []}} for _ in range(10)]
            programs[-1]['source']['observations'] = observations
            with self.assertRaisesRegex(ValueError, 'requires_empty_observations'):
                require_empty_observations(programs)

    def test_missing_action_is_not_arbitrarily_skippable(self):
        tape = ActionTape([entry('show_song', {'song_id': 5}, full(5))])
        with self.assertRaisesRegex(ValueError, 'unconsumed'):
            tape.finish()

    def test_order_and_arguments_must_match_even_for_projection(self):
        tape = ActionTape([entry('show_song', {'song_id': 5}, full(5))])
        with self.assertRaisesRegex(ValueError, 'order_or_arguments'):
            tape.partial(action(9), ['title'], {'title': full(9)['title']})

    def test_nonread_and_failed_read_cannot_be_skipped(self):
        cases = [entry('like_song', {'song_id': 5}, {'liked': True}),
                 entry('show_song', {'song_id': 5}, error='failure'),
                 entry('show_song', {'song_id': 5}, error='not sent', sent=False)]
        for saved in cases:
            tape = ActionTape([saved])
            request = saved['request']
            a = {'app': request['app'], 'api': request['api'], 'args': request['arguments']}
            with self.assertRaisesRegex(ValueError, 'matching_successful'):
                tape.partial(a, ['title'], {'title': 'synthetic-5'})

    def test_error_payload_must_match_saved_reply_exactly(self):
        saved = entry('show_song', {'song_id': 5}, error='ValueError: synthetic failure')
        tape = ActionTape([saved])
        tape.begin_call(action(5))
        tape.active_dispatched = True
        tape.finish_call({'ok': False, 'error': 'ValueError: synthetic failure'}, 0)
        tape.finish()
        wrapped = ActionTape([saved])
        wrapped.begin_call(action(5))
        wrapped.active_dispatched = True
        with self.assertRaisesRegex(ValueError, 'exception_payload_differs'):
            wrapped.finish_call({'ok': False, 'error': 'RuntimeError: ValueError: synthetic failure'}, 0)

    def test_partial_is_checked_against_saved_reply_after_lookup(self):
        tape = ActionTape([entry('show_song', {'song_id': 5}, full(5))])
        with self.assertRaisesRegex(ValueError, 'matching_successful'):
            tape.partial(action(5), ['title'], {'title': 'different'})

    def test_two_arm_independent_cache_paths_do_not_inject_future_full_values(self):
        counts = []
        for policy in ('eager_cached', 'automatic_projection_cached'):
            host, client, transport, budget, start = setup(policy)
            library = [{k: v for k, v in full(i).items() if k in FIELDS} for i in (5, 9)]
            start([entry('show_song_library', {'access_token': 'synthetic'}, library)])
            client.call('spotify', 'show_song_library', access_token='synthetic')
            transport.tape.finish()
            for _ in range(2):
                start([entry('show_song', {'song_id': i}, full(i)) for i in (5, 9)])
                if policy == 'automatic_projection_cached':
                    self.assertEqual(client.lookup('spotify', 'show_song', {'song_id': 5}, ['title']),
                                     {'title': full(5)['title']})
                else:
                    self.assertEqual(client.call('spotify', 'show_song', song_id=5), full(5))
                self.assertEqual(client.call('spotify', 'show_song', song_id=9), full(9))
                transport.tape.finish()
            self.assertEqual(len(host.provider.cache.exact), 1 if policy.startswith('automatic') else 2)
            counts.append(transport.saved_backend_responses)
            self.assertIsNone(transport.transport)
        self.assertEqual(counts, [3, 2])

    def test_miss_lookup_does_not_consume_tape_or_observe_future_value(self):
        host, client, transport, budget, start = setup('automatic_projection_cached')
        start([entry('show_song', {'song_id': 5}, full(5))])
        self.assertIsNone(client.lookup('spotify', 'show_song', {'song_id': 5}, ['title']))
        self.assertEqual(transport.tape.index, 0)
        self.assertFalse(host.provider.cache.exact)
        self.assertEqual(client.call('spotify', 'show_song', song_id=5), full(5))
        self.assertEqual(transport.tape.index, 1)
        transport.tape.finish()

    def test_recorded_predispatch_exception_is_not_counted_as_saved_backend(self):
        host, client, transport, budget, start = setup('eager_cached')
        start([entry('show_song', {'song_id': 5}, error='recorded capacity rejection', sent=False)])
        with self.assertRaisesRegex(RuntimeError, 'recorded capacity rejection'):
            client.call('spotify', 'show_song', song_id=5)
        transport.tape.finish()
        self.assertEqual((transport.saved_backend_responses, budget.spent), (0, 0))

    def test_same_action_changed_full_reply_rejects_ordinary_cache_skip(self):
        host, client, transport, budget, start = setup('eager_cached')
        start([entry('show_song', {'song_id': 5}, full(5))])
        client.call('spotify', 'show_song', song_id=5)
        changed = dict(full(5), extra=False)
        start([entry('show_song', {'song_id': 5}, changed)])
        with self.assertRaisesRegex(RuntimeError, 'protocol_failed'):
            client.call('spotify', 'show_song', song_id=5)
        self.assertEqual(transport.tape.failed, 'ordinary_complete_value_differs')

    def test_snapshot_absent_real_dict_and_plain_value_boundary(self):
        absent = boundary_snapshot({'items': [1, 2]}, ['record'], 1)
        self.assertEqual(absent['roots'], {'record': {'present': False}})
        first = boundary_snapshot({'record': full(9), 'result': {5: {'label': 'x'}}}, ['record'], 2)
        second = boundary_snapshot({'result': {5: {'label': 'x'}}, 'record': deepcopy(full(9))}, ['record'], 2)
        self.assertEqual(first, second)
        self.assertEqual(first['roots']['record']['type'], 'dict')
        self.assertNotIn('value', first['roots']['record'])
        underscore_a = boundary_snapshot({'_rows': [1]}, [], 1)
        underscore_b = boundary_snapshot({'_rows': [2]}, [], 1)
        self.assertNotEqual(underscore_a['plain_namespace_sha256'], underscore_b['plain_namespace_sha256'])
        changed = boundary_snapshot({'record': dict(full(9), extra=False)}, ['record'], 2)
        self.assertNotEqual(first['roots'], changed['roots'])

    def test_snapshot_never_invokes_repr_or_unknown_callbacks(self):
        class Unknown:
            def __repr__(self):
                raise AssertionError('must not inspect')
        value = boundary_snapshot({'unused': Unknown()}, [], 1)
        self.assertEqual(value['unsupported_names'], ['unused'])
        with self.assertRaises(ValueError):
            boundary_snapshot({'record': Unknown()}, ['record'], 1)

    def test_snapshot_control_is_one_control_and_zero_api(self):
        host, client, transport, budget, start = setup('eager_cached')
        start([])
        data = boundary_snapshot({}, ['record'], 1)
        self.assertIsNone(client.rpc('replay_boundary', data))
        self.assertEqual(host.boundaries, [data])
        self.assertEqual((budget.spent, transport.saved_backend_responses), (0, 0))

    def test_snapshot_bootstrap_compiles_without_running_generated_code(self):
        session = object.__new__(ReplayPython)
        session.policy, session.root_names = 'automatic_projection_cached', ('record',)
        source = session._bootstrap()
        compile(source, '<synthetic-bootstrap-only>', 'exec')
        self.assertEqual(source.count("_projection_client.rpc('replay_boundary'"), 1)
        self.assertIn("if not _projection_client.closed:", source)


if __name__ == '__main__':
    unittest.main()
