from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_saved_action_execution as runner
from test_matched_live_prefix import Bridge, Catalog, entry


class FakeSession:
    def __init__(self, *, change_stdout=False):
        self.count = 0; self.change_stdout = change_stdout
    def run(self, source, observations, channel, **kwargs):
        self.count += 1
        channel.exchange(entry()['request'])
        return dict(status='ok', stdout='changed' if self.change_stdout else 'saved',
            stdout_truncated=False, error=None, declared_complete=False, unknown_effects=False,
            api_requests=1, session_usable=True, program_index=self.count, wall_seconds=0.001)


def programs(count=2):
    return [dict(name=f'call_{n:03d}_01', source=dict(code='synthetic-only', observations=[],
            api_schemas={'demo__read': {'name': 'demo__read'}}), entries=[entry()],
            expected=dict(status='ok', stdout='saved', stdout_truncated=False, error=None,
                declared_complete=False, unknown_effects=False, api_requests=1,
                session_usable=True, program_index=n)) for n in range(1, count + 1)]


class RunnerTest(unittest.TestCase):
    def test_changed_stdout_stops_before_later_prefix_program(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); condition = {'prefix_programs': []}
            session = FakeSession(change_stdout=True); bridge = Bridge()
            with self.assertRaisesRegex(ValueError, 'no_suffix'):
                runner.reconstruct(programs(), session, Catalog(), bridge, SimpleNamespace(),
                    folder, folder, {'max_api_requests_per_condition': 80, 'program_timeout_seconds': 30},
                    runner.time.monotonic() + 30, lambda: False, condition)
            self.assertEqual(session.count, 1)
            self.assertEqual(len(bridge.calls), 1)
            self.assertEqual(condition['prefix_api_requests'], 1)
            self.assertFalse(condition['prefix_programs'][0]['public_prefix_matches'])

    def test_schema_mismatch_stops_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); p = programs(); p[0]['source']['api_schemas'] = {}
            session = FakeSession(); bridge = Bridge()
            with self.assertRaisesRegex(ValueError, 'schemas_differ'):
                runner.reconstruct(p, session, Catalog(), bridge, SimpleNamespace(),
                    folder, folder, {'max_api_requests_per_condition': 80, 'program_timeout_seconds': 30},
                    runner.time.monotonic() + 30, lambda: False, {'prefix_programs': []})
            self.assertEqual(session.count, 0)
            self.assertEqual(bridge.calls, [])

    def test_text_only_suffix_records_format_error_without_python_or_API(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            session = SimpleNamespace(programs=[{}] * 12, usable=True)
            transport = SimpleNamespace(fatal=False, complete=False)
            condition = dict(prefix_programs=[{}] * 12, prefix_api_requests=28)
            runner.suffix(dict(content='```python\nprint(1)\n```', tool_calls=[]), {}, session,
                Catalog(), transport, SimpleNamespace(), folder, folder,
                dict(max_api_requests_per_condition=80, program_timeout_seconds=30,
                     observation_page_characters=4000), runner.time.monotonic() + 30,
                lambda: False, condition)
            self.assertEqual(condition['suffix_saved_programs'], 0)
            self.assertEqual(condition['suffix_api_requests'], 0)
            self.assertTrue(condition['suffix_public_results'][0]['format_error_present'])
            self.assertIsNone(condition['suffix_public_results'][0]['status'])

    def test_private_binding_and_path_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp); path = storage / 'records/context_pilot/sample.json'
            path.parent.mkdir(parents=True); path.write_text('{"a":1}')
            name = str(path.relative_to(storage)); plan = dict(max_file_bytes=50,
                private_file_sha256={name: hashlib.sha256(path.read_bytes()).hexdigest()})
            self.assertEqual(runner.read_private(storage, plan, name), {'a': 1})
            path.write_text('{"a":2}')
            with self.assertRaisesRegex(ValueError, 'changed'):
                runner.read_private(storage, plan, name)
            with self.assertRaises(ValueError):
                runner.read_private(storage, plan, '../outside.json')

    def test_preparation_failure_is_retained_and_never_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repo'; storage = Path(tmp) / 'storage'
            (root / 'configs').mkdir(parents=True); (root / 'reports').mkdir()
            plan = dict(private_output='records/context_pilot/P94_saved_action_execution_v01',
                        experiment_prefix='P94_ACTION_V01', stop_marker='.runtime/P94.stop')
            (root / runner.PLAN).write_text(json.dumps(plan))
            def git(command, **kwargs):
                return '' if command[1] == 'status' else 'a' * 40
            with patch.object(runner.subprocess, 'check_output', side_effect=git), \
                 patch.object(runner, 'prepare', side_effect=ValueError('changed input')) as prepare, \
                 patch.object(runner, 'TypedBridgeProcess') as bridge:
                report = runner.run(storage, root)
                self.assertEqual(report['status'], 'stopped')
                self.assertEqual(report['environment_api_requests'], 0)
                self.assertEqual(report['saved_program_executions'], 0)
                self.assertEqual(sum(c['status'] == 'not_attempted' for c in report['conditions']), 18)
                self.assertEqual(prepare.call_count, 1); bridge.assert_not_called()
                with self.assertRaises(FileExistsError):
                    runner.run(storage, root)
                self.assertEqual(prepare.call_count, 1)


if __name__ == '__main__':
    unittest.main()
