"""Exercise actual process alarms without a model, network or generated code."""
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = ('local_llama', 'tool_choice_local_llama', 'fixed_budget_local_llama')
CHILD = r'''
import importlib, json, pathlib, signal, sys, tempfile, time
sys.path.insert(0, str(pathlib.Path.cwd() / 'scripts'))
adapter = importlib.import_module(sys.argv[1])
from inference_timeout_handler import inference_timeout_handler
mode = sys.argv[2]
config = dict(model='fixture', temperature=1.0, seed=57, num_predict=16,
              call_timeout_seconds=5, reasoning_budget_tokens=-1,
              tool_choice='auto')
tools = [{'type': 'function', 'function': {'name': 'fixture', 'parameters': {}}}]

def previous_handler(*args):
    raise RuntimeError('the caller handler must not handle the inference alarm')

previous = signal.SIG_DFL if mode == 'expire' else previous_handler
signal.signal(signal.SIGALRM, previous)

def fake_post(*args):
    if mode == 'expire':
        time.sleep(10)
        raise AssertionError('alarm did not interrupt the request')
    if mode == 'error':
        raise ValueError('fixture transport failure')
    return dict(usage=dict(prompt_tokens=13, completion_tokens=5, total_tokens=18),
                choices=[dict(finish_reason='stop', message=dict(role='assistant', content='done'))])

adapter.post = fake_post
with tempfile.TemporaryDirectory() as directory:
    with inference_timeout_handler():
        result = adapter.model_call(config, [], directory, 1, tools)
    folder = pathlib.Path(directory)
    print(json.dumps(dict(result=result,
        saved=json.loads((folder / 'response.json').read_text()),
        request=json.loads((folder / 'request.json').read_text()),
        raw_present=(folder / 'raw_response.json').exists(),
        handler_restored=signal.getsignal(signal.SIGALRM) == previous,
        remaining_alarm=signal.alarm(0))))
'''


class LocalInferenceAlarmTests(unittest.TestCase):
    def run_case(self, adapter, mode):
        run = subprocess.run([sys.executable, '-c', CHILD, adapter, mode],
                             cwd=ROOT, capture_output=True, text=True, timeout=6)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result['saved'], result['result'])
        self.assertTrue(result['handler_restored'])
        self.assertEqual(result['remaining_alarm'], 0)
        self.assertEqual(result['request']['max_tokens'], 16)
        self.assertEqual(result['request']['stream'], False)
        return result

    def test_default_alarm_cannot_kill_worker_before_timeout_record(self):
        for adapter in ADAPTERS:
            with self.subTest(adapter=adapter):
                value = self.run_case(adapter, 'expire')
                record = value['result']
                self.assertEqual(record['status'], 'error')
                self.assertEqual(record['error_kind'], 'timeout')
                self.assertEqual(record['timeout_scope'], 'run_wall')
                self.assertEqual(record['timeout_seconds'], 1)
                self.assertIsNone(record['input_tokens'])
                self.assertIsNone(record['output_tokens'])
                self.assertFalse(value['raw_present'])

    def test_success_keeps_terminal_usage_and_restores_caller_handler(self):
        for adapter in ADAPTERS:
            with self.subTest(adapter=adapter):
                value = self.run_case(adapter, 'success')
                self.assertEqual(value['result']['status'], 'ok')
                self.assertEqual(value['result']['input_tokens'], 13)
                self.assertEqual(value['result']['output_tokens'], 5)
                self.assertTrue(value['raw_present'])

    def test_request_error_preserves_unknown_usage_and_caller_handler(self):
        for adapter in ADAPTERS:
            with self.subTest(adapter=adapter):
                value = self.run_case(adapter, 'error')
                self.assertEqual(value['result']['error_kind'], 'request_or_response')
                self.assertIsNone(value['result']['input_tokens'])
                self.assertIsNone(value['result']['output_tokens'])
                self.assertFalse(value['raw_present'])


if __name__ == '__main__':
    unittest.main()
