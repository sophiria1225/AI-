"""Handwritten synthetic interpreter/host integration; no task or model calls."""
import json
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from automatic_field_projection import plan_projection
from automatic_projection_runtime import (AutomaticProjectionHost, AutomaticProjectionProgram,
    AutomaticProjectionPython, ProjectionWireClient, ProjectionWireFault, derived_bootstrap, POLICIES)
from container_api_python import ApiChannel
from field_read_contract import CONTRACT_ID
from public_api_envelope import PROTOCOL
from public_api_result_transport import PublicResultTransport
from shared_api_reservations import BudgetedApiChannel, RequestBudget
from test_persistent_read_view_python import TrustedSubprocessSession
from test_public_read_views_live_probe import Fixture, catalog


SOURCE = '''indices = [10, 11, 12]
rows = {}
seen = set()
for index in indices:
    last = call_api('spotify', 'show_song', song_id=index)
    rows[index] = {'title': last['title'], 'people': [person['name'] for person in last['artists']]}
    seen.add(index)
print(rows)
print(len(seen))
'''
LIBRARY = "library = call_api('spotify', 'show_song_library', access_token='fixture-token')"


class TrustedProjectionSession(AutomaticProjectionPython):
    def __init__(self, folder, policy):
        TrustedSubprocessSession.__init__(self, folder)
        self.policy = policy

    def _start(self):
        self.stderr = (self.folder/'stderr.txt').open('wb')
        self.process = subprocess.Popen([sys.executable, '-I', '-S', '-u', '-c',
            derived_bootstrap(self.policy)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=self.stderr)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.created_monotonic = time.monotonic()

    def close(self):
        result = TrustedSubprocessSession.close(self)
        self.usable = False
        self.state['container_removed'] = True  # There was no container in this fixture.
        return result


class KnownFailureFixture(Fixture):
    def request(self, command):
        action = command['call']
        if action['api'] == 'show_song' and action['args']['song_id'] == 12:
            self.calls.append(action)
            envelope = dict(protocol=PROTOCOL, nonce=command['nonce'], status='raised',
                error={'type': 'RuntimeError', 'message': 'synthetic known read failure'})
            return {'ok': True, 'result': dict(protocol=PROTOCOL,
                observation=json.dumps(envelope), declared_complete=False)}
        return super().request(command)


class AutomaticProjectionRuntimeTests(unittest.TestCase):
    def test_protocol_fault_is_closed_without_retry_but_known_API_error_is_distinct(self):
        for reply in ({'id':1,'ok':True,'fatal':False},
                      {'id':1,'ok':False,'fatal':False,'error':None},
                      {'id':3,'ok':True,'fatal':False,'value':1}):
            calls = []
            def wire(*args, **kwargs):
                calls.append(kwargs)
                return reply
            client = ProjectionWireClient(wire)
            with self.assertRaises(ProjectionWireFault):
                client.call('spotify', 'show_song', song_id=10)
            self.assertTrue(client.closed); self.assertEqual(len(calls), 1)
            with self.assertRaises(RuntimeError):
                client.call('spotify', 'show_song', song_id=10)
            self.assertEqual(len(calls), 1)
        client = ProjectionWireClient(lambda *a, **k: {'id':1,'ok':False,'fatal':False,'error':'known rejection'})
        with self.assertRaisesRegex(RuntimeError, 'known rejection'):
            client.call('spotify', 'show_song', song_id=10)
        self.assertFalse(client.closed)

    def exercise(self, policy, sources, raw=None):
        raw = raw or Fixture()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            session = TrustedProjectionSession(folder, policy)
            bridge = PublicResultTransport(raw)
            budget = RequestBudget(30)
            adapter = AutomaticProjectionProgram(session, budget, execution_scope='synthetic',
                verified_contract=CONTRACT_ID, policy=policy)
            cat = catalog(); records = []; results = []; evidence = []
            try:
                for number, source in enumerate(sources, 1):
                    result = adapter(source, {}, ApiChannel(cat, bridge, budget.available),
                        storage_root=folder, record_dir=folder/f'program_{number:02d}',
                        timeout=5, on_record=records.append)
                    results.append(result)
                    evidence.append(json.loads((folder/f'program_{number:02d}'/
                                                'projection_program_private.json').read_text()))
                    if not session.usable:
                        break
                return dict(results=results, evidence=evidence, host=adapter.host, budget=budget,
                    records=records, raw=raw, bridge=bridge, session_usable=session.usable)
            finally:
                session.close()

    def test_real_wire_two_cells_keep_final_complete_value_and_do_not_seed_free_full_cache(self):
        outcomes = []
        for policy in POLICIES:
            run = self.exercise(policy, [LIBRARY, SOURCE, SOURCE, "print(last['genre'])"])
            self.assertEqual([r['status'] for r in run['results']], ['ok']*4)
            outcomes.append([r['stdout'] for r in run['results']])
            self.assertEqual(run['budget'].spent, 4 if policy == 'eager_cached' else 2)
            self.assertEqual(sum(r['api_request_sent'] for r in run['records']), run['budget'].spent)
            self.assertFalse(run['budget'].pending)
            self.assertFalse(run['host'].projection_failed)
            self.assertEqual(len(run['host'].program_reports), 4)
            expected = policy == 'automatic_projection_cached'
            self.assertEqual(run['evidence'][1]['execution_transform_report'][0]['transformed'], expected)
            self.assertEqual(run['evidence'][1]['original_generated_source_unchanged'], not expected)
            if expected:
                self.assertEqual([e['kind'] for e in run['host'].projection_events], ['partial']*4)
                self.assertEqual(run['host'].ordinary_complete_reuses, 1)
        self.assertEqual(*outcomes)

    def test_later_full_reads_pay_the_materialization_cost(self):
        all_full = "print(call_api('spotify', 'show_song', song_id=10)['genre'])\nprint(call_api('spotify', 'show_song', song_id=11)['genre'])"
        for policy in POLICIES:
            run = self.exercise(policy, [LIBRARY, SOURCE, all_full])
            self.assertEqual([r['status'] for r in run['results']], ['ok']*3)
            self.assertEqual(run['budget'].spent, 4)

    def test_known_terminal_failure_stops_projection_without_claiming_unknown_API_effects(self):
        run = self.exercise('automatic_projection_cached', [LIBRARY, SOURCE, 'print(123)'], KnownFailureFixture())
        self.assertEqual(len(run['results']), 2)
        self.assertEqual(run['results'][-1]['status'], 'harness_error')
        self.assertTrue(run['host'].projection_failed)
        self.assertTrue(run['budget'].stopped)
        self.assertFalse(run['session_usable'])
        self.assertFalse(run['bridge'].fatal)
        self.assertFalse(run['results'][-1]['unknown_effects'])
        self.assertEqual(run['budget'].spent, 2)
        self.assertEqual(run['bridge'].receipts[-1]['status'], 'raised')
        self.assertIsNone(run['evidence'][-1]['original_generated_source_unchanged'])

    def test_ordinary_error_before_any_projected_value_remains_recoverable(self):
        run = self.exercise('automatic_projection_cached', ['print(undefined_name)', 'print(123)'])
        self.assertEqual([r['status'] for r in run['results']], ['execution_error', 'ok'])
        self.assertFalse(run['host'].projection_failed)
        self.assertFalse(run['budget'].stopped)

    def test_ordinary_API_and_catalog_errors_preserve_exact_reply_and_accounting(self):
        cases = [('show_song', {'song_id': 12}, KnownFailureFixture, 1),
                 ('undiscovered_fixture_api', {}, Fixture, 0),
                 ('show_song', {'song_id': 10, 'unexpected_argument': 1}, Fixture, 0)]
        for api, arguments, fixture, expected_sent in cases:
            direct = BudgetedApiChannel(ApiChannel(catalog(), PublicResultTransport(fixture()), 30),
                                        RequestBudget(30))
            reply = direct.exchange(dict(kind='api', id=1, app='spotify', api=api,
                                         arguments=arguments))
            self.assertFalse(reply['ok'])
            source = f"call_api('spotify', {api!r}, **{arguments!r})"
            for policy in POLICIES:
                with self.subTest(api=api, arguments=arguments, policy=policy):
                    run = self.exercise(policy, [source, 'print(123)'], fixture())
                    self.assertEqual([r['status'] for r in run['results']], ['execution_error', 'ok'])
                    self.assertEqual(run['results'][0]['error'], 'RuntimeError: ' + reply['error'])
                    self.assertEqual(run['budget'].spent, expected_sent)
                    self.assertEqual(len(run['records']), 1)
                    self.assertEqual(run['records'][0]['api_request_sent'], bool(expected_sent))
                    self.assertEqual(run['records'][0]['observation'], direct.rows[0]['observation'])
                    self.assertFalse(run['budget'].pending)
                    self.assertFalse(run['budget'].stopped)
                    self.assertFalse(run['host'].projection_failed)

    def test_prior_builtin_change_takes_eager_path_without_report_hash_failure(self):
        for policy in POLICIES:
            run = self.exercise(policy, [
                LIBRARY, "import builtins\nbuiltins.abs = lambda value: value", SOURCE])
            self.assertEqual([r['status'] for r in run['results']], ['ok']*3)
            self.assertFalse(run['host'].projection_failed)
            self.assertTrue(run['evidence'][-1]['static_eligible'])
            self.assertNotEqual(run['evidence'][-1]['transformed_sha256'],
                                run['evidence'][-1]['source_sha256'])
            self.assertFalse(run['evidence'][-1]['execution_transform_report'][0]['transformed'])
            self.assertEqual(run['evidence'][-1]['executed_source_sha256'],
                             run['evidence'][-1]['source_sha256'])
            self.assertEqual(run['budget'].spent, 4)
            self.assertFalse(run['host'].projection_events)

    def test_lookup_does_not_bypass_stopped_budget_or_api_capability(self):
        raw = Fixture(); cat = catalog(); budget = RequestBudget(10)
        bridge = PublicResultTransport(raw)
        host = AutomaticProjectionHost(BudgetedApiChannel(ApiChannel(cat, bridge, 10), budget),
            execution_scope='synthetic', verified_contract=CONTRACT_ID,
            policy='automatic_projection_cached')
        host.expect(plan_projection(SOURCE))
        budget.stopped = True
        reply = host.request({'id':1,'op':'projection_lookup','releases':[],
            'args':{'app':'spotify','api':'show_song','args':{'song_id':10},'fields':['title']}})
        self.assertFalse(reply['ok']); self.assertTrue(reply['fatal'])
        self.assertEqual(len(raw.calls), 0)
        self.assertFalse(bridge.fatal)

    def test_failure_is_recorded_even_if_completion_was_already_set(self):
        raw = Fixture(); cat = catalog(); budget = RequestBudget(10)
        bridge = PublicResultTransport(raw)
        base = ApiChannel(cat, bridge, 10)
        host = AutomaticProjectionHost(BudgetedApiChannel(base, budget),
            execution_scope='synthetic', verified_contract=CONTRACT_ID,
            policy='automatic_projection_cached')
        host.expect(plan_projection(SOURCE))
        base.complete = True; budget.stopped = True
        reply = host.request({'id':1,'op':'projection_stop','releases':[],
            'args':{'reason':'automatic_projection_execution_failed'}})
        self.assertTrue(reply['ok']); self.assertTrue(host.projection_failed)
        self.assertFalse(base.fatal)

    def test_success_report_cannot_invent_partial_hits(self):
        raw = Fixture(); cat = catalog(); budget = RequestBudget(10)
        bridge = PublicResultTransport(raw)
        host = AutomaticProjectionHost(BudgetedApiChannel(ApiChannel(cat, bridge, 10), budget),
            execution_scope='synthetic', verified_contract=CONTRACT_ID,
            policy='automatic_projection_cached')
        plan = plan_projection(SOURCE); host.expect(plan)
        reply = host.request({'id':1,'op':'projection_report','releases':[], 'args':{
            'source_sha256':plan.source_sha256,'transformed_sha256':plan.transformed_sha256,
            'transformed':True,'hits':1,'misses':0,'failed':False,
            'reason':'bounded_normal_path_projection'}})
        self.assertFalse(reply['ok']); self.assertTrue(reply['fatal'])
        self.assertFalse(host.program_reports)


if __name__ == '__main__':
    unittest.main()
