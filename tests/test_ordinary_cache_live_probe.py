"""Synthetic service and handwritten programs; no AppWorld, model or task data."""
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ordinary_complete_read_cache import OrdinaryCachedReadProgram
from ordinary_cache_live_plan import (POLICIES, EXPECTED_API, EXPECTED_PENDING,
    EXPECTED_EXACT_REUSES, EXPECTED_COALESCED_REUSES, EXPECTED_MATERIALIZATION_CACHE_REUSES)
from field_read_contract import CONTRACT_ID
from probe_ordinary_cache_live import execute_programs
from public_api_result_transport import PublicResultTransport
from shared_api_reservations import RequestBudget
from test_persistent_read_view_python import TrustedSubprocessSession
from test_public_read_views_live_probe import Fixture, catalog


class OrdinaryCacheLiveTests(unittest.TestCase):
    def exercise(self, fixture, policy, stop_after=None):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            session = TrustedSubprocessSession(folder)
            transport = PublicResultTransport(fixture)
            budget = RequestBudget(20)
            program = OrdinaryCachedReadProgram(session, budget, execution_scope='synthetic-P106',
                verified_contract=CONTRACT_ID, defer=policy != 'eager_cached')
            condition = dict(policy=policy, programs=[])
            rows, error = [], None
            try:
                execute_programs(program=program, session=session, transport=transport,
                    catalog=catalog(), budget=budget, folder=folder, storage=folder,
                    condition=condition, recorded=SimpleNamespace(deadline=0),
                    deadline=time.monotonic()+30,
                    stop=lambda: stop_after is not None and len(condition['programs']) >= stop_after,
                    plan={'program_timeout_seconds':5}, on_record=rows.append)
            except Exception as exc:
                error = exc
            finally:
                session.close()
            return SimpleNamespace(condition=condition, budget=budget, host=program.host,
                                   rows=rows, receipts=transport.receipts, error=error)

    def test_both_cached_policies_match_observations_with_both_mutation_directions(self):
        for liked in (False, True):
            outputs = []
            for policy in POLICIES:
                fixture = Fixture(liked=liked)
                result = self.exercise(fixture, policy)
                self.assertIsNone(result.error, (policy, result.error))
                rows = result.condition['programs']
                self.assertEqual([r['api_requests'] for r in rows], EXPECTED_API[policy])
                self.assertEqual([r['budget']['pending'] for r in rows], EXPECTED_PENDING[policy])
                self.assertEqual(result.host.exact_reuses, EXPECTED_EXACT_REUSES[policy])
                self.assertEqual(getattr(result.host, 'coalesced_reuses', 0), EXPECTED_COALESCED_REUSES[policy])
                self.assertEqual(getattr(result.host, 'materialization_cache_reuses', 0),
                                 EXPECTED_MATERIALIZATION_CACHE_REUSES[policy])
                self.assertEqual(result.host.ordinary_complete_reuses, 1 if policy == 'eager_cached' else 0)
                self.assertFalse(result.host.records)
                self.assertEqual(len(fixture.calls), sum(EXPECTED_API[policy]))
                self.assertEqual(len(result.receipts), len(fixture.calls))
                self.assertEqual(sum(r['api_request_sent'] for r in result.rows), len(fixture.calls))
                self.assertTrue(all(r['status'] == 'returned' for r in result.receipts))
                self.assertEqual([r['client_setup_included'] for r in rows], [True]+[False]*6)
                self.assertTrue(all(r['control_requests'] > 0 and r['control_request_bytes'] > 0
                                    and r['control_reply_bytes'] > 0 for r in rows))
                outputs.append([r['stdout_sha256'] for r in rows])
            self.assertTrue(all(o == outputs[0] for o in outputs))

    def test_short_library_keeps_failed_attempt_and_does_not_replace_objects(self):
        fixture = Fixture(length=2)
        result = self.exercise(fixture, 'coalesced_cached')
        self.assertIsInstance(result.error, ValueError)
        self.assertEqual(len(result.condition['programs']), 1)
        self.assertEqual(result.condition['programs'][0]['status'], 'execution_error')
        self.assertEqual(result.budget.spent, 4)
        self.assertEqual(fixture.calls[-1]['api'], 'show_song_library')

    def test_lost_shared_materialization_is_one_charged_attempt_without_retry(self):
        fixture = Fixture(missing_fallback=True)
        result = self.exercise(fixture, 'coalesced_cached')
        self.assertIsInstance(result.error, ValueError)
        self.assertEqual(len(result.condition['programs']), 3)
        self.assertEqual(result.budget.spent, 7)
        self.assertTrue(result.budget.stopped)
        self.assertEqual(result.receipts[-1]['status'], 'unknown')
        self.assertEqual(sum(a['api'] == 'show_song' for a in fixture.calls), 1)
        self.assertFalse(any(a['api'] in ('like_song', 'unlike_song') for a in fixture.calls))

    def test_known_post_mutation_error_retains_cost_without_retry_or_new_read(self):
        fixture = Fixture(mutation_error=True)
        result = self.exercise(fixture, 'coalesced_cached')
        self.assertIsInstance(result.error, ValueError)
        self.assertEqual(len(result.condition['programs']), 7)
        self.assertEqual(result.condition['programs'][-1]['status'], 'execution_error')
        self.assertEqual(result.budget.spent, 11)
        self.assertEqual(result.receipts[-1]['status'], 'raised')
        self.assertEqual(fixture.calls[-1]['api'], 'like_song')

    def test_explicit_stop_does_not_materialize_remaining_references(self):
        for policy, pending in [('eager_cached', 0), ('coalesced_cached', 1)]:
            fixture = Fixture()
            result = self.exercise(fixture, policy, stop_after=2)
            self.assertIsInstance(result.error, InterruptedError)
            self.assertEqual(len(result.condition['programs']), 2)
            self.assertEqual((result.budget.spent, result.budget.pending),
                             (7 if policy == 'eager_cached' else 6, pending))
            self.assertEqual(sum(a['api'] == 'show_song' for a in fixture.calls),
                             1 if policy == 'eager_cached' else 0)


if __name__ == '__main__':
    unittest.main()
