import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from browsecomp_terminal import exclusive_json, load_terminal
from run_browsecomp_baseline import execute, read_question


class InferenceStub:
    def __init__(self, folder, responses):
        self.folder, self.responses, self.calls = folder, iter(responses), []
        self.started, self.tokens = time.monotonic(), 0
    def call(self, role, messages, tools):
        message, finish = next(self.responses)
        cid = f'call_{len(self.calls)+1:03d}'
        (self.folder / cid).mkdir()
        exclusive_json(self.folder / cid / 'response.json', {
            'status': 'ok', 'done_reason': finish, 'message': message})
        self.calls.append({'id': cid, 'status': 'ok', 'finish_reason': finish})
        self.tokens += 100
        return message


class ClientStub:
    def __init__(self):
        self.requests = []
    def request(self, name, args, timeout):
        self.requests.append((name, args))
        return {'result': {'status': 'ok', 'results': []}, 'wall_seconds': 0.01}


def tool(identifier, arguments='{"query":"synthetic query"}'):
    return {'id': identifier, 'type': 'function', 'function': {
        'name': 'search', 'arguments': arguments}}


class RunnerTests(unittest.TestCase):
    def test_first_terminal_answer_is_fixed_and_no_more_model_calls_occur(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, client = Path(tmp), ClientStub()
            responses = [({'role': 'assistant', 'content': '', 'tool_calls': [tool('x')]}, 'tool_calls'),
                         ({'role': 'assistant', 'content': 'Synthetic answer [7]'}, 'stop'),
                         ({'role': 'assistant', 'content': 'Must not be selected'}, 'stop')]
            infer = InferenceStub(folder, responses)
            result = execute({'phase': 'P15', 'max_tool_requests': 2, 'max_wall_seconds': 60},
                             {'query_id': '7', 'query': 'Synthetic task'}, folder, client, infer)
            self.assertTrue(result['submitted']); self.assertEqual(result['model_calls'], 2)
            self.assertEqual(len(client.requests), 1)
            self.assertEqual(load_terminal(folder)[1]['response'], 'Synthetic answer [7]')

    def test_tool_batch_cannot_exceed_its_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, client = Path(tmp), ClientStub()
            infer = InferenceStub(folder, [({'role': 'assistant', 'content': '',
                                            'tool_calls': [tool('x'), tool('y')]}, 'tool_calls')])
            result = execute({'phase': 'P15', 'max_tool_requests': 1, 'max_wall_seconds': 60},
                             {'query_id': '7', 'query': 'Synthetic task'}, folder, client, infer)
            self.assertFalse(result['submitted'])
            self.assertEqual(result['stop_reason'], 'tool_request_limit')
            self.assertEqual(len(client.requests), 1)
            events = json.loads((folder / 'events.json').read_text())
            self.assertEqual(events[1]['observation']['status'], 'skipped_tool_budget')

    def test_invalid_json_is_charged_and_never_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, client = Path(tmp), ClientStub()
            infer = InferenceStub(folder, [({'role': 'assistant', 'content': '',
                                            'tool_calls': [tool('x', '{broken')]}, 'tool_calls'),
                                           ({'role': 'assistant', 'content': 'Cannot determine'}, 'stop')])
            result = execute({'phase': 'P15', 'max_tool_requests': 2, 'max_wall_seconds': 60},
                             {'query_id': '7', 'query': 'Synthetic task'}, folder, client, infer)
            self.assertEqual(result['tool_attempts'], 1)
            self.assertEqual(client.requests, [])
            self.assertTrue(result['submitted'])  # Correctness remains unevaluated.

    def test_truncated_output_neither_submits_nor_executes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, client = Path(tmp), ClientStub()
            infer = InferenceStub(folder, [({'role': 'assistant', 'content': 'Partial',
                                            'tool_calls': [tool('x')]}, 'length')])
            result = execute({'phase': 'P15', 'max_tool_requests': 2, 'max_wall_seconds': 60},
                             {'query_id': '7', 'query': 'Synthetic task'}, folder, client, infer)
            self.assertFalse(result['submitted']); self.assertEqual(client.requests, [])
            self.assertIsNone(load_terminal(folder)[1])

    def test_changed_projection_or_label_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'questions.jsonl'
            path.write_text(json.dumps({'query_id': '7', 'query': 'Synthetic', 'answer': 'hidden'}) + '\n')
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):
                read_question(path, sha, ['7'], '7')
            with self.assertRaises(ValueError):
                read_question(path, '0' * 64, ['7'], '7')


if __name__ == '__main__':
    unittest.main()
