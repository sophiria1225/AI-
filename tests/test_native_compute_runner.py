import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import native_compute_session as session
from audit_native_execution import audit
from audit_native_boundaries import audit as boundary_audit
import test_p18_plan as fixture


def message(cid, calls):
    return {'role': 'assistant', 'content': '', 'tool_calls': [
        {'id': f'{cid}_{i}', 'type': 'function',
         'function': {'name': name, 'arguments': json.dumps(arguments)}}
        for i, (name, arguments) in enumerate(calls)]}


def fake_compute(arguments, snapshot, *, storage_root, record_dir, timeout):
    actual = {'status': 'ok', 'content': '42', 'container_removed': True,
              'controls': {'fixture_isolated': True}, 'wall_seconds': .125}
    record_dir.mkdir(parents=True)
    (record_dir/'result_private.json').write_text(json.dumps(actual))
    return ({'computation_status': 'ok', 'content': '42', 'environment_state_changed': False},
            {k: v for k, v in actual.items() if k != 'content'})


class ComputeRunnerTests(unittest.TestCase):
    def test_snapshot_does_not_gain_same_response_receipts_or_assistant_text(self):
        with tempfile.TemporaryDirectory() as folder:
            value = session.NativeComputeSession({'max_executions': 1, 'timeout_seconds': 10},
                storage_root=Path(folder), output=Path(folder))
            spans = {'s1': {'id': 's1', 'action': None, 'observation': {'public': 1},
                             'assistant': 'PRIVATE'}}
            value.before_response(spans)
            value.bind_response('call1')
            spans['s1']['observation']['public'] = 2
            spans['s2'] = {'id': 's2', 'action': None, 'observation': {}}
            self.assertEqual(value.snapshot['s1']['observation']['public'], 1)
            self.assertNotIn('assistant', value.snapshot['s1'])
            with patch.object(session, 'compute', side_effect=fake_compute) as worker:
                bad = value.invoke({'span_ids': ['s2'], 'code': 'result="x"'})
                self.assertEqual(bad['computation_status'], 'input_error')
                worker.assert_not_called()
                self.assertEqual(value.invoke({'span_ids': ['s1'], 'code': 'result="x"'})['content'], '42')
                limited = value.invoke({'span_ids': ['s1'], 'code': 'result="x"'})
                self.assertEqual(limited['computation_status'], 'not_executed')
                self.assertEqual(worker.call_count, 1)
            self.assertEqual(value.summary()['attempts'], 3)
            self.assertEqual(value.summary()['executions'], 1)
            self.assertGreater(value.summary()['wall_seconds'], 0)

    def test_full_runner_cost_history_boundaries_and_tamper_detection(self):
        calls = [message('a', [('api_docs__show_app_descriptions', {})]),
                 message('b', [('compute_data', {'span_ids': ['s1'], 'code': 'result="42"'}),
                               ('compute_data', {'span_ids': ['s2'], 'code': 'result="future"'}),
                               ('compute_data', {'span_ids': ['s1'], 'code': 'result="overlimit"'})]),
                 message('c', [('supervisor__complete_task', {})])]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(session, 'compute', side_effect=fake_compute):
                result, sent, requests = fixture.P18Controls().run_fixture(root, 'P23', config_updates={
                    'arms': ['native_compute'], 'ordinary_compute': {'max_executions': 1, 'timeout_seconds': 10}},
                    response_messages=calls)
            self.assertEqual(result['stop_reason'], 'agent_declared_complete')
            self.assertEqual(result['known_total_tokens'], 33)
            self.assertEqual(result['api_requests'], 2)
            self.assertEqual(result['ordinary_compute']['attempts'], 3)
            self.assertEqual(result['ordinary_compute']['executions'], 1)
            self.assertEqual(result['boundary_records'], 4)
            trial = root/'storage/records/context_pilot/P23_FIXTURE'
            checked = audit(trial)
            for key in ('audit_errors', 'dispatch_audit_errors', 'history_audit_errors', 'compute_audit_errors'):
                self.assertEqual(checked[key], [], key)
            self.assertEqual(boundary_audit(trial, root/'world')['audit_errors'], [])
            p = trial/'compute_records.json'; records = json.loads(p.read_text())
            records[0]['input_sha256'] = 'wrong'; p.write_text(json.dumps(records))
            self.assertIn('computation input is not the pre-response public snapshot', audit(trial)['compute_audit_errors'])

    def test_control_errors_are_rejected_before_computation(self):
        with tempfile.TemporaryDirectory() as folder:
            for config in ({'max_executions': True, 'timeout_seconds': 10},
                           {'max_executions': 0, 'timeout_seconds': 10},
                           {'max_executions': 1, 'timeout_seconds': 31},
                           {'max_executions': 1, 'timeout_seconds': 10, 'extra': 1}):
                with self.assertRaises(ValueError):
                    session.NativeComputeSession(config, storage_root=folder, output=folder)

    def test_oversize_selected_data_does_not_count_as_a_launched_container(self):
        with tempfile.TemporaryDirectory() as folder:
            value = session.NativeComputeSession({'max_executions': 1, 'timeout_seconds': 10},
                storage_root=folder, output=folder)
            value.before_response({'s1': {'id': 's1', 'action': None,
                                         'observation': {'content': 'x'*1048576}}})
            value.bind_response('call1')
            with patch.object(session, 'compute') as worker:
                receipt = value.invoke({'span_ids': ['s1'], 'code': 'result="x"'})
                worker.assert_not_called()
            self.assertEqual(receipt['computation_status'], 'input_error')
            self.assertEqual(value.summary()['executions'], 0)
            self.assertEqual(value.summary()['attempts'], 1)

    def test_compute_infrastructure_failure_blocks_later_environment_mutation(self):
        def failing(*args, **kwargs):
            obs, meta = fake_compute(*args, **kwargs)
            obs['computation_status'] = meta['status'] = 'harness_error'
            meta['container_removed'] = False
            p = kwargs['record_dir']/'result_private.json'
            actual = json.loads(p.read_text()); actual.update(status='harness_error', container_removed=False)
            p.write_text(json.dumps(actual))
            return obs, meta
        calls = [message('a', [('api_docs__show_app_descriptions', {})]),
                 message('b', [('compute_data', {'span_ids': ['s1'], 'code': 'result="42"'}),
                               ('supervisor__complete_task', {})])]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(session, 'compute', side_effect=failing):
                result, sent, requests = fixture.P18Controls().run_fixture(root, 'P23', config_updates={
                    'arms': ['native_compute'], 'ordinary_compute': {'max_executions': 1, 'timeout_seconds': 10}},
                    response_messages=calls)
            self.assertEqual(result['stop_reason'], 'runtime_error')
            self.assertFalse(result['declared_complete'])
            self.assertEqual(result['api_requests'], 1)
            self.assertTrue(result['ordinary_compute']['fatal_harness_error'])
            trial = root/'storage/records/context_pilot/P23_FIXTURE'
            spans = json.loads((trial/'spans.json').read_text())
            self.assertEqual(spans['s3']['observation'], {'not_executed': 'ordinary computation harness failed'})
            self.assertEqual(audit(trial)['compute_audit_errors'], [])


if __name__ == '__main__':
    unittest.main()
