"""Common feedback through the trusted synthetic interpreter; no live APIs."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from api_error_comparison import ErrorPresentationProgram
from automatic_projection_runtime import POLICIES
from container_api_python import ApiChannel
from contract_comparison import FeedbackProgram
from field_read_contract import CONTRACT_ID
from online_projection_runtime import OnlineProjectionProgram
from public_api_result_transport import PublicResultTransport
from shared_api_reservations import RequestBudget
from test_automatic_projection_runtime import TrustedProjectionSession, KnownFailureFixture, LIBRARY, SOURCE
from test_public_read_views_live_probe import Fixture, catalog


def exercise(policy, sources, raw=None):
    raw = raw or Fixture()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        session = TrustedProjectionSession(folder, policy)
        bridge = PublicResultTransport(raw)
        budget = RequestBudget(30)
        adapter = OnlineProjectionProgram(session, budget, execution_scope='online-synthetic',
            verified_contract=CONTRACT_ID, policy=policy)
        cat, records, results = catalog(), [], []
        try:
            for number, source in enumerate(sources, 1):
                results.append(adapter(source, [], ApiChannel(cat, bridge, budget.available),
                    storage_root=folder, record_dir=folder / f'p{number}', timeout=5, on_record=records.append))
                if not session.usable:
                    break
            return {'results': results, 'summary': adapter.summary(), 'rows': adapter.program_rows,
                    'records': records, 'budget': budget, 'bridge': bridge}
        finally:
            session.close()


class OnlineProjectionRuntimeTests(unittest.TestCase):
    def test_exposed_invalid_argument_matches_existing_public_schema_feedback(self):
        feedback = FeedbackProgram(lambda source, observations, channel, **kw: channel, 'public_schema')
        legacy = ErrorPresentationProgram(feedback, 'error_exception')('', [],
            ApiChannel(catalog(), PublicResultTransport(Fixture()), 30))
        reply = legacy.exchange({'kind': 'api', 'id': 1, 'app': 'spotify', 'api': 'show_song',
                                  'arguments': {'song_id': 10, 'unexpected': True}})
        source = "call_api('spotify', 'show_song', song_id=10, unexpected=True)"
        for policy in POLICIES:
            run = exercise(policy, [source, "print(call_api('spotify', 'show_song', song_id=10)['title'])"])
            self.assertEqual([r['status'] for r in run['results']], ['execution_error', 'ok'])
            self.assertEqual(run['results'][0]['error'], 'RuntimeError: ' + reply['error'])
            self.assertEqual(run['records'][0]['observation'], legacy.rows[0]['observation'])
            summary = run['summary']
            self.assertEqual(summary['feedback']['feedback_events'], feedback.summary()['feedback_events'])
            self.assertEqual((summary['budget']['spent'], summary['budget']['pending']), (1, 0))
            self.assertFalse(summary['projection_failed'])
            self.assertTrue(summary['control_accounting_complete'])
            self.assertTrue(summary['schema_accounting_complete'])
            self.assertEqual(summary['program_attempts'], 2)
            self.assertGreater(summary['known_control_requests'], 0)

    def test_known_API_error_is_not_replaced_with_feedback_and_remains_recoverable(self):
        for policy in POLICIES:
            run = exercise(policy, ["call_api('spotify', 'show_song', song_id=12)", 'print(1)'], KnownFailureFixture())
            self.assertEqual(run['results'][0]['error'], 'RuntimeError: RuntimeError: synthetic known read failure')
            self.assertEqual(run['results'][1]['status'], 'ok')
            self.assertEqual(run['summary']['feedback']['feedback_events'], [])
            self.assertEqual(run['summary']['budget']['spent'], 1)
            self.assertFalse(run['summary']['budget']['stopped'])

    def test_both_policy_caches_and_projection_counts_are_actual(self):
        for policy in POLICIES:
            run = exercise(policy, [LIBRARY, SOURCE, SOURCE])
            summary = run['summary']
            optimized = policy == 'automatic_projection_cached'
            self.assertEqual(summary['projection_partial_hits'], 4 if optimized else 0)
            self.assertEqual(summary['ordinary_complete_cache_hits'], 1 if optimized else 3)
            self.assertEqual(summary['budget']['spent'], 2 if optimized else 4)
            self.assertEqual(summary['transformed_programs'], 2 if optimized else 0)
            self.assertEqual(summary['feedback']['checked_requests'], summary['budget']['spent'])
            self.assertTrue(all(row['evidence_recorded'] for row in run['rows']))

    def test_failure_after_partial_hit_is_stopped_with_complete_accounting(self):
        run = exercise('automatic_projection_cached', [LIBRARY, SOURCE, 'print(1)'], KnownFailureFixture())
        self.assertEqual(len(run['results']), 2)
        summary = run['summary']
        self.assertTrue(summary['projection_failed'])
        self.assertTrue(summary['budget']['stopped'])
        self.assertEqual(summary['budget']['spent'], 2)
        self.assertEqual(summary['projection_partial_hits'], 2)
        self.assertTrue(summary['control_accounting_complete'])
        self.assertEqual(run['results'][-1]['status'], 'harness_error')
        self.assertFalse(run['bridge'].fatal)


if __name__ == '__main__':
    unittest.main()
