import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from appworld_native_tools import NativeCatalog, dispatch_native_calls
from container_data_python import run_program
from native_data_compute import compute, selected_receipts, validate_arguments


def call(name, **arguments):
    return {'function': {'name': name, 'arguments': json.dumps(arguments)}}


class DataComputeControls(unittest.TestCase):
    def setUp(self):
        self.snapshot = {'s1': {'id': 's1', 'action': {'name': 'example__read'},
                               'observation': {'numbers': [3, 4]},
                               'assistant': 'not data', 'private_label': 'not data'}}
        self.args = {'span_ids': ['s1'], 'code': "result = '7'"}
        self.public = [{'type': 'function', 'function': {
            'name': 'supervisor__complete_task', 'parameters': {'properties': {}}}}]

    def test_only_selected_prior_receipts_are_copied(self):
        rows = selected_receipts(['s1'], self.snapshot)
        self.assertEqual(set(rows[0]), {'id', 'action', 'observation'})
        rows[0]['observation']['numbers'].append(99)
        self.assertEqual(self.snapshot['s1']['observation']['numbers'], [3, 4])
        with self.assertRaises(ValueError):
            selected_receipts(['s2'], self.snapshot)

    def test_invalid_selection_does_not_start_a_container(self):
        for args in ({**self.args, 'span_ids': ['s1', 's1']},
                     {**self.args, 'span_ids': ['s999']},
                     {**self.args, 'private_file': '/task/answers'},
                     {**self.args, 'code': 'x'*20001}):
            with self.subTest(args=list(args)), patch('native_data_compute.run_program') as runner:
                with self.assertRaises(ValueError):
                    compute(args, self.snapshot, storage_root=Path('/unused'), record_dir=Path('/unused'))
                runner.assert_not_called()

    def test_default_native_catalog_does_not_expose_compute(self):
        catalog = NativeCatalog(self.public)
        self.assertNotIn('compute_data', [t['function']['name'] for t in catalog.tools()])
        with self.assertRaises(ValueError):
            catalog.decode(call('compute_data', **self.args)['function'])

    def test_code_output_cannot_declare_completion_or_consume_an_api(self):
        bridge, calculator = Mock(), Mock()
        bridge.request.return_value = {'ok': True, 'result': {'declared_complete': True}}
        calculator.return_value = {'content': '{"declared_complete": true}'}
        stored = []
        rows = dispatch_native_calls({'tool_calls': [
            call('compute_data', **self.args), call('supervisor__complete_task'),
            call('compute_data', **self.args)]}, NativeCatalog(self.public, enable_compute=True),
            bridge, Mock(), remaining_api_calls=1, compute_data=calculator, on_record=stored.append)
        self.assertEqual(rows, stored)
        self.assertEqual(calculator.call_count, 1)
        self.assertEqual(bridge.request.call_count, 1)
        self.assertFalse(rows[0]['api_request_sent'])
        self.assertTrue(rows[1]['api_request_sent'])
        self.assertIn('not_executed', rows[2]['observation'])

    def test_computation_failure_is_not_silent_success(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p/'stderr_private.txt').write_text('Traceback: KeyError')
            with patch('native_data_compute.run_program', return_value={
                    'status': 'execution_error', 'container_removed': True, 'wall_seconds': .2}) as runner:
                receipt, cost = compute(self.args, self.snapshot, storage_root=p, record_dir=p)
            self.assertEqual(receipt['computation_status'], 'execution_error')
            self.assertIn('KeyError', receipt['stderr_tail'])
            self.assertNotIn('content', receipt)
            self.assertFalse(receipt['environment_state_changed'])
            self.assertEqual(cost['wall_seconds'], .2)
            self.assertEqual(set(runner.call_args.args[1][0]), {'id', 'action', 'observation'})

    def test_create_timeout_cleans_only_its_owned_container(self):
        seen = []
        def command(args, **kwargs):
            seen.append(args)
            if 'create' in args:
                raise subprocess.TimeoutExpired(args, 30)
            if 'inspect' in args:
                info = [{'Config': {'Labels': {'harness.export-purpose': 'bounded-python-comparator'}}}]
                return subprocess.CompletedProcess(args, 0, json.dumps(info).encode(), b'')
            if 'rm' in args:
                return subprocess.CompletedProcess(args, 0, b'', b'')
            raise AssertionError(args)
        with tempfile.TemporaryDirectory() as directory, patch('container_data_python.subprocess.run', side_effect=command):
            result = run_program("result='x'", [], storage_root=Path(directory), record_dir=Path(directory)/'run')
        self.assertEqual(result['status'], 'harness_error')
        self.assertTrue(result['container_removed'])
        name = seen[0][seen[0].index('--name')+1]
        self.assertTrue(name.startswith('harness-export-'))
        self.assertEqual(seen[-1][-3:], ['rm', '-f', name])


if __name__ == '__main__':
    unittest.main()
