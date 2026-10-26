"""Trusted synthetic controls/loader only; no Docker or saved generated code."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import probe_region_projection_replay as replay
from compact_api_receipts import encode_receipts
from contract_comparison import FeedbackProgram
from contract_feedback import UNKNOWN_PARAMETER, make_feedback, canonical as feedback_canonical
from automatic_projection_runtime import ProjectionApiChannel
from joined_public_read_views import JOINED_CONTRACT_ID
from region_projection_runtime import RegionWireClient, POLICIES
from public_name_catalog import PublicNameCatalog
from public_api_envelope import PROTOCOL
from shared_api_reservations import RequestBudget
from test_automatic_projection_replay import full, entry, action

SOURCE = """indices = [number for number in [5, 9]]
rows = {}
for number in indices:
    last = call_api('spotify', 'show_song', song_id=number)
    rows[number] = {'title': last['title']}
"""
TOOLS = [{'type': 'function', 'function': {'name': 'spotify__' + api,
    'parameters': {'type': 'object', 'properties': {arg: {}}}}}
    for api, arg in (('show_song', 'song_id'), ('show_song_library', 'access_token'))]


def host_fixture(policy):
    catalog, transport, budget = PublicNameCatalog(TOOLS), replay.SavedResultTransport(), RequestBudget(80)
    feedback = FeedbackProgram(lambda s, o, c, **kw: c, 'public_schema')
    def channel():
        value = ProjectionApiChannel(replay.ReplayApiChannel(catalog, transport, 80), budget)
        value.receipted = feedback('', [], value.receipted)
        return value
    with patch('region_projection_runtime.verify_joined_implementation', return_value=JOINED_CONTRACT_ID), \
         patch('demand_joined_read_adapter.verify_joined_implementation', return_value=JOINED_CONTRACT_ID):
        host = replay.RegionReplayHost(channel(), policy=policy, execution_scope='synthetic-replay',
                                       public_source_directory=Path('/synthetic/public'))
    client = RegionWireClient(lambda app, api, packet: host.request(packet))
    def program(entries):
        transport.tape = replay.FrontierTape(entries)
        host.attach(channel())
        host.expect(replay.plan_region_projection(SOURCE))
    return host, client, transport, budget, program, feedback


def frontier(number):
    result = entry('show_song', {'song_id': number})
    result.update(frontier=True, reply=None, originally_sent=False)
    return result


def loader_fixture(root, *, raised=False, feedback=False):
    """Two synthetic program records; second ends at the sole unreceipted call."""
    events, spans, control_id = [], {}, 0
    schemas = {tool['function']['name']: tool['function'] for tool in TOOLS}
    for number in (1, 2):
        call = f'call_{number:03d}'
        directory = root / 'programs' / (call + '_01'); directory.mkdir(parents=True)
        code = "last = call_api('spotify', 'show_song', song_id=5)"
        source = dict(code=code, observations=[], program_index=number, api_schemas=schemas)
        sid = 's' + str(len(events) + 1)
        sent = not (number == 1 and feedback)
        args = {'wrong_id': 5} if not sent else {'song_id': 5}
        row = dict(action=dict(name='spotify__show_song', arguments=json.dumps(args)),
                   observation={'observation': json.dumps(full(5)), 'declared_complete': False},
                   api_request_sent=sent, new_tools=[])
        error = None
        if number == 1 and raised:
            row['observation'] = {'api_error': 'SyntheticError: keep this exact message'}
            error = 'RuntimeError: ' + row['observation']['api_error']
        if number == 1 and feedback:
            row['observation'] = {'format_error': UNKNOWN_PARAMETER}
            value = make_feedback(row, schemas, 'public_schema')
            row['observation']['contract_feedback'] = value
            error = 'RuntimeError: ' + feedback_canonical(dict(format_error=UNKNOWN_PARAMETER, contract_feedback=value))
        event = dict(span_id=sid, call=call, stage='python_api', api_request_sent=sent,
                     effects_unknown=False, new_tools=[], declared_complete=False)
        if sent:
            event['api_execution'] = dict(protocol=PROTOCOL, status='raised' if number == 1 and raised else 'returned',
                bridge_request_sent=True, automatic_retries=0, nonce=f'{number:032x}', raw_reply_sha256='a'*64)
        events.append(event); spans[sid] = dict(id=sid, action=row['action'], observation=row['observation'])
        receipt = dict(span_id=sid, api='spotify__show_song', api_request_sent=sent)
        wire = []
        def control(op, args):
            nonlocal control_id
            control_id += 1
            wire.append(dict(kind='api', id=len(wire)+1, program_index=number, app='__harness_views__',
                api='control', arguments=dict(packet=dict(id=control_id, op=op, args=args, releases=[]))))
        control('call', dict(app='spotify', api='show_song', args=args))
        report = dict(source_sha256=hashlib.sha256(code.encode()).hexdigest(), transformed=False, hits=0)
        reports = []
        if number == 2:
            control('call', action(9)); error = replay.ORIGINAL_FRONTIER_ERROR
        elif error is None:
            control('projection_report', report); reports.append(report)
        result = dict(program_index=number, status='execution_error' if error else 'ok', session_usable=True,
            unknown_effects=False, api_requests=int(sent), stdout='', stdout_truncated=False,
            error=error, declared_complete=False)
        wire.append(dict(kind='done', program_index=number, python='3.12', stdout='', stdout_truncated=False, error=error))
        outer_id = 's' + str(len(events)+1)
        events.append(dict(span_id=outer_id, call=call, stage='model_tool', api_request_sent=False,
                           new_tools=[], effects_unknown=False))
        spans[outer_id] = dict(id=outer_id, action=dict(name='run_python', arguments=json.dumps({'code': code, 'span_ids': []})),
            observation={**{key: result[key] for key in ('status','stdout','stdout_truncated','error','declared_complete','unknown_effects','api_requests')},
                         'api_receipts': encode_receipts([receipt])})
        for filename, value in (('input_private.json', source), ('result_private.json', result),
            ('projection_program_private.json', dict(projection_failed=False, source_sha256=report['source_sha256'],
                                                     execution_transform_report=reports))):
            (directory / filename).write_text(json.dumps(value))
        (directory / 'wire_private.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in wire))
    for name, value in (('events.json', events), ('spans.json', spans)):
        (root / name).write_text(json.dumps(value))
    return schemas


class RegionReplayTests(unittest.TestCase):
    def test_dependency_closure_binds_transitive_imports_without_unrelated_online_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'scripts').mkdir(); (root / 'tests').mkdir()
            for name, source in (('probe.py', 'from helper import value'), ('helper.py', 'value = 1'),
                                 ('unrelated_online.py', 'raise RuntimeError()')):
                (root / 'scripts' / name).write_text(source)
            files = replay.dependency_files(root, ['scripts/probe.py'])
            self.assertEqual({p.name for p in files}, {'probe.py', 'helper.py'})

    def test_failure_retains_all_48_slots_without_invented_savings(self):
        key = (1, POLICIES[0], 1)
        rows = replay.retain_slots([], {key})
        self.assertEqual(len(rows), 48)
        self.assertEqual(rows[0]['record_status'], 'attempted_without_complete_evidence')
        self.assertEqual(sum(r['record_status'] == 'not_run' for r in rows), 47)
        self.assertTrue(all(r['saved_backend_responses'] is None and r['projection_hits'] is None for r in rows))
        with self.assertRaises(ValueError):
            replay.retain_slots([], {(1, POLICIES[0], 13)})

    def test_loader_binds_control_sequence_receipts_and_only_final_frontier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); schemas = loader_fixture(root)
            programs = replay.load_region_programs(root, schemas, expected_count=2)
            self.assertEqual([len(p['entries']) for p in programs], [1, 2])
            self.assertIsNone(programs[-1]['entries'][-1]['reply'])
            self.assertTrue(programs[-1]['entries'][-1]['frontier'])
            self.assertTrue(all(p['source']['observations'] == [] for p in programs))
            spans = replay.read(root / 'spans.json'); spans['s2']['observation']['api_receipts'] = encode_receipts([])
            (root / 'spans.json').write_text(json.dumps(spans))
            with self.assertRaisesRegex(ValueError, 'request_receipt_count'):
                replay.load_region_programs(root, schemas, expected_count=2)

    def test_loader_keeps_raised_and_decorated_error_exact_without_double_feedback(self):
        for options in ({'raised': True}, {'feedback': True}):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); schemas = loader_fixture(root, **options)
                programs = replay.load_region_programs(root, schemas, expected_count=2)
                first = programs[0]['entries'][0]
                self.assertEqual(programs[0]['expected']['error'], 'RuntimeError: ' + first['reply']['error'])
                host, client, transport, budget, program, feedback = host_fixture(POLICIES[0])
                program([first])
                with self.assertRaises(RuntimeError) as error:
                    client.call('spotify', 'show_song', **first['request']['arguments'])
                self.assertEqual(str(error.exception), first['reply']['error'])
                self.assertEqual(budget.spent, int(first['originally_sent']))
                self.assertEqual(feedback.summary()['feedback_events'], [])
                transport.tape.finish()

    def test_duplicate_nonce_unknown_effect_and_source_mismatch_are_rejected(self):
        for mode in ('nonce', 'unknown', 'source', 'frontier_try'):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); schemas = loader_fixture(root)
                if mode in ('nonce', 'unknown'):
                    rows = replay.read(root / 'events.json')
                    if mode == 'nonce': rows[2]['api_execution']['nonce'] = rows[0]['api_execution']['nonce']
                    else: rows[0]['effects_unknown'] = True
                    (root / 'events.json').write_text(json.dumps(rows))
                else:
                    path = root / 'programs/call_002_01/input_private.json'
                    source = replay.read(path)
                    source['code'] = 'try:\n    pass\nexcept Exception:\n    pass' if mode == 'frontier_try' else 'different = 1'
                    path.write_text(json.dumps(source))
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    replay.load_region_programs(root, schemas, expected_count=2)

    def test_frontier_is_exact_position_even_when_same_action_appeared_earlier(self):
        for policy in POLICIES:
            host, client, transport, budget, program, _ = host_fixture(policy)
            program([entry('show_song', {'song_id': 5}, full(5)), frontier(5)])
            self.assertEqual(client.call('spotify', 'show_song', song_id=5), full(5))
            before_events = deepcopy(budget.events)
            with patch.object(host.provider, 'lookup', side_effect=AssertionError('frontier cannot query provider')):
                with self.assertRaisesRegex(RuntimeError, replay.FRONTIER_ERROR):
                    if policy == POLICIES[1]: client.lookup('spotify','show_song',{'song_id':5},['title'])
                    else: client.call('spotify','show_song',song_id=5)
            self.assertEqual(budget.events, before_events)
            self.assertEqual((budget.spent, transport.saved_backend_responses), (1, 1))
            self.assertTrue(transport.tape.frontier_reached)
            self.assertEqual(host.ordinary_complete_reuses, 0)
            self.assertFalse(host.frontier_controls[0]['provider_lookup_performed'])
            transport.tape.finish()

    def test_partial_validation_never_observes_omitted_full_reply(self):
        host, client, transport, budget, program, _ = host_fixture(POLICIES[1])
        program([entry('show_song_library', {'access_token':'synthetic'}, [full(5), full(9)])])
        client.call('spotify','show_song_library',access_token='synthetic'); transport.tape.finish()
        program([entry('show_song',{'song_id':5},full(5)), entry('show_song',{'song_id':5},full(5)), frontier(9)])
        self.assertEqual(client.lookup('spotify','show_song',{'song_id':5},['title']), {'title': full(5)['title']})
        self.assertEqual((budget.spent, transport.saved_backend_responses), (1, 1))
        self.assertEqual(host.provider.lookup(action(5), host.epoch)[0], 'partial')
        client.call('spotify','show_song',song_id=5)
        self.assertEqual((budget.spent, transport.saved_backend_responses), (2, 2))
        self.assertEqual(host.ordinary_complete_reuses, 0)
        with self.assertRaisesRegex(RuntimeError, replay.FRONTIER_ERROR):
            client.lookup('spotify','show_song',{'song_id':9},['title'])
        transport.tape.finish()

    def test_partial_future_value_mismatch_stops_instead_of_becoming_authority(self):
        host, client, transport, budget, program, _ = host_fixture(POLICIES[1])
        program([entry('show_song_library', {'access_token':'synthetic'}, [full(5)])])
        client.call('spotify','show_song_library',access_token='synthetic')
        changed = full(5); changed['title'] = 'different synthetic saved reply'
        program([entry('show_song', {'song_id':5}, changed)])
        with self.assertRaisesRegex(RuntimeError, 'partial_hit_not_a_matching'):
            client.lookup('spotify','show_song',{'song_id':5},['title'])
        self.assertEqual(budget.spent, 1)
        self.assertTrue(host.projection_failed)
        self.assertEqual(host.provider.lookup(action(5), host.epoch)[1]['title'], full(5)['title'])

    def test_bootstrap_retains_isolation_and_frontier_skips_boundary_snapshot(self):
        for policy in POLICIES:
            with tempfile.TemporaryDirectory() as tmp:
                source = replay.RegionReplayPython(Path(tmp), Path(tmp)/'session', policy=policy, root_names=['last'])._bootstrap()
                compile(source, '<trusted synthetic replay bootstrap>', 'exec')
                self.assertIn("if not _projection_client.closed:", source)
                self.assertEqual(source.count("rpc('replay_boundary'"), 1)
        self.assertEqual(replay.MAX_PROGRAMS, 48)
        self.assertEqual((replay.TOTAL_SECONDS, replay.PROGRAM_SECONDS, replay.CLEANUP_RESERVE_SECONDS), (1800,30,120))


if __name__ == '__main__':
    unittest.main()
