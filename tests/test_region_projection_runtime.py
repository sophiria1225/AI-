"""Handwritten synthetic wire integration; no task data, model or real API."""
import json
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from container_api_python import ApiChannel
from joined_public_read_views import JOINED_CONTRACT_ID
from public_api_result_transport import PublicResultTransport
from region_projection_runtime import (
    POLICIES, RegionProjectionProgram, RegionProjectionPython, derived_region_bootstrap,
)
from shared_api_reservations import RequestBudget
from test_automatic_projection_runtime import KnownFailureFixture, LIBRARY
from test_persistent_read_view_python import TrustedSubprocessSession
from test_public_read_views_live_probe import Fixture, catalog


SOURCE = '''import json
indices = [value for value in [10, 11, 12]]
rows = {}
for index in indices:
    last = call_api('spotify', 'show_song', song_id=index)
    rows[index] = {'title': last['title'], 'people': [person['name'] for person in last['artists']]}
print(json.dumps(rows))
'''


class TrustedRegionSession(RegionProjectionPython):
    def __init__(self, folder, policy):
        TrustedSubprocessSession.__init__(self, folder)
        self.policy = policy

    def _start(self):
        self.stderr = (self.folder / 'stderr.txt').open('wb')
        self.process = subprocess.Popen([sys.executable, '-I', '-S', '-u', '-c',
            derived_region_bootstrap(self.policy)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=self.stderr)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.created_monotonic = time.monotonic()

    def close(self):
        result = TrustedSubprocessSession.close(self)
        self.usable = False
        self.state['container_removed'] = True  # Fixture never creates a container.
        return result


def exercise(policy, sources, raw=None, timeout=5):
    raw = raw or Fixture()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        session = TrustedRegionSession(folder, policy)
        bridge = PublicResultTransport(raw)
        budget = RequestBudget(30)
        with patch('region_projection_runtime.verify_joined_implementation', return_value=JOINED_CONTRACT_ID), \
             patch('demand_joined_read_adapter.verify_joined_implementation', return_value=JOINED_CONTRACT_ID):
            adapter = RegionProjectionProgram(session, budget, execution_scope='region-synthetic',
                public_source_directory=folder, policy=policy)
            cat, records, results, evidence = catalog(), [], [], []
            try:
                for number, source in enumerate(sources, 1):
                    directory = folder / f'program_{number:02d}'
                    result = adapter(source, [], ApiChannel(cat, bridge, budget.available),
                        storage_root=folder, record_dir=directory, timeout=timeout, on_record=records.append)
                    results.append(result)
                    evidence.append(json.loads((directory / 'projection_program_private.json').read_text()))
                    if not session.usable:
                        break
                return dict(results=results, evidence=evidence, summary=adapter.summary(),
                    budget=budget, records=records, host=adapter.host, raw=raw)
            finally:
                session.close()


class RegionRuntimeTests(unittest.TestCase):
    def test_dynamic_loop_preserves_next_cell_full_root_and_all_receipts(self):
        outcomes = []
        for policy in POLICIES:
            run = exercise(policy, [LIBRARY, SOURCE, "print(last['genre'])"])
            self.assertEqual([r['status'] for r in run['results']], ['ok'] * 3)
            outcomes.append([r['stdout'] for r in run['results']])
            auto = policy == POLICIES[1]
            self.assertEqual(run['budget'].spent, 2 if auto else 4)
            self.assertEqual(sum(r['api_request_sent'] for r in run['records']), run['budget'].spent)
            self.assertEqual(run['summary']['automatic_region_partial_hits'], 2 if auto else 0)
            self.assertTrue(run['summary']['control_accounting_complete'])
            self.assertTrue(run['summary']['schema_accounting_complete'])
            self.assertFalse(run['summary']['projection_failed'])
            report = run['evidence'][1]['execution_transform_report'][0]
            self.assertEqual(report['transformed'], auto)
            if auto:
                self.assertTrue(all(s['completed'] for s in report['segments']))
                self.assertIsNone(run['evidence'][1]['executed_source_sha256'])
        self.assertEqual(*outcomes)

    def test_explicit_demand_is_the_same_capability_in_both_policies(self):
        source = "print(read_fields('spotify', 'show_song', ['title', 'artists'], song_id=10))"
        outcomes = []
        for policy in POLICIES:
            run = exercise(policy, [LIBRARY, source, source])
            self.assertEqual([r['status'] for r in run['results']], ['ok'] * 3)
            self.assertEqual(run['budget'].spent, 1)
            self.assertEqual(run['summary']['explicit_field_partial_hits'], 2)
            self.assertEqual(run['summary']['automatic_region_partial_hits'], 0)
            self.assertEqual(run['summary']['ordinary_complete_cache_hits'], 0)
            outcomes.append([r['stdout'] for r in run['results']])
        self.assertEqual(*outcomes)

    def test_explicit_miss_then_complete_uses_the_ordinary_cache(self):
        source = "print(read_fields('spotify', 'show_song', ['title'], song_id=10))"
        for policy in POLICIES:
            run = exercise(policy, [source, source])
            self.assertEqual([r['status'] for r in run['results']], ['ok'] * 2)
            self.assertEqual(run['budget'].spent, 1)
            self.assertEqual(run['summary']['ordinary_complete_cache_hits'], 1)
            self.assertEqual(run['summary']['explicit_field_partial_hits'], 0)
            self.assertEqual([e['kind'] for e in run['host'].field_events], ['miss', 'complete'])

    def test_bad_explicit_fields_are_recoverable_and_do_not_dispatch(self):
        for fields in ("['unknown']", "['title', 'title']", "[]", "'title'"):
            for policy in POLICIES:
                source = f"read_fields('spotify', 'show_song', {fields}, song_id=10)"
                run = exercise(policy, [source, 'print(1)'])
                self.assertEqual([r['status'] for r in run['results']], ['execution_error', 'ok'])
                self.assertEqual(run['budget'].spent, 0)
                self.assertFalse(run['budget'].stopped)
                self.assertFalse(run['summary']['projection_failed'])

    def test_known_read_error_after_auto_partial_is_sticky_and_counted(self):
        run = exercise(POLICIES[1], [LIBRARY, SOURCE, 'print(1)'], KnownFailureFixture())
        self.assertEqual(len(run['results']), 2)
        self.assertEqual(run['results'][-1]['status'], 'harness_error')
        self.assertTrue(run['budget'].stopped)
        self.assertEqual(run['budget'].spent, 2)
        self.assertEqual(run['summary']['automatic_region_partial_hits'], 2)
        self.assertTrue(run['summary']['control_accounting_complete'])
        report = run['evidence'][-1]['execution_transform_report'][0]
        self.assertEqual(report['execution_status'], 'execution_error')
        self.assertTrue(report['failed'])
        self.assertFalse(report['segments'][-1]['completed'])
        self.assertEqual(report['regions'][-1]['hits_after'], 2)

    def test_syntax_failure_has_no_prefix_effect_and_keeps_failure_report(self):
        source = LIBRARY + '\n' + SOURCE + '\nbreak\n'
        for policy in POLICIES:
            run = exercise(policy, [source, 'print(1)'])
            self.assertEqual([r['status'] for r in run['results']], ['execution_error', 'ok'])
            self.assertEqual(run['budget'].spent, 0)
            self.assertFalse(run['budget'].stopped)
            report = run['evidence'][0]['execution_transform_report'][0]
            self.assertEqual(report['execution_status'], 'execution_error')
            self.assertEqual(report['segments'], [])

    def test_future_full_reads_pay_for_prior_partial_reuse(self):
        later = "print(call_api('spotify', 'show_song', song_id=10)['genre'])\nprint(call_api('spotify', 'show_song', song_id=11)['genre'])"
        for policy in POLICIES:
            run = exercise(policy, [LIBRARY, SOURCE, later])
            self.assertEqual([r['status'] for r in run['results']], ['ok'] * 3)
            self.assertEqual(run['budget'].spent, 4)
            self.assertFalse(run['summary']['projection_failed'])

    def test_hard_timeout_after_partial_is_sticky_with_missing_trace_explicit(self):
        run = exercise(POLICIES[1], [LIBRARY, SOURCE + '\nwhile True:\n    pass\n', 'print(1)'], timeout=0.2)
        self.assertEqual(len(run['results']), 2)
        final = run['results'][-1]
        self.assertEqual(final['status'], 'harness_error')
        self.assertEqual(final['underlying_execution_status'], 'timeout')
        self.assertEqual(final['contract_stop_reason'], 'region_execution_report_missing_after_partial')
        self.assertTrue(run['budget'].stopped)
        self.assertTrue(run['summary']['projection_failed'])
        self.assertEqual(run['summary']['automatic_region_partial_hits'], 2)
        self.assertFalse(run['summary']['execution_trace_accounting_complete'])
        self.assertFalse(run['summary']['control_accounting_complete'])
        self.assertEqual(run['evidence'][-1]['execution_transform_report'], [])


if __name__ == '__main__':
    unittest.main()
