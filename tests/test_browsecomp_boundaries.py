import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from browsecomp_bridge import MAX_REQUEST_BYTES, serve
from browsecomp_terminal import exclusive_json, load_terminal, write_terminal
from browsecomp_tools import CorpusTools
from browsecomp_judge_contract import official_contract


class Corpus:
    num_docs = 100195
    def search(self, query, k):
        if query == 'fail':
            raise ValueError('synthetic broken index')
        return []
    def get_document(self, docid):
        return None


class ProtocolTests(unittest.TestCase):
    def test_backend_failure_is_not_empty_success(self):
        with self.assertRaises(ValueError):
            CorpusTools(Corpus()).dispatch('search', {'query': 'fail'})
        source = io.BytesIO((json.dumps({'id': 1, 'op': 'tool', 'name': 'search',
                                       'arguments': {'query': 'fail'}}) + '\n').encode())
        out = io.StringIO()
        with patch('sys.stderr', io.StringIO()):
            serve(Corpus(), source, out)
        ready, error = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(ready['corpus_documents'], 100195)
        self.assertFalse(error['ok'])
        self.assertNotIn('result', error)
        self.assertEqual(error['id'], 1)

    def test_oversized_frame_does_not_execute_its_suffix(self):
        out = io.StringIO()
        with self.assertRaises(ValueError):
            serve(Corpus(), io.BytesIO(b'x' * (MAX_REQUEST_BYTES + 1) + b'\n'), out)
        self.assertEqual(len(out.getvalue().splitlines()), 1)


class TerminalTests(unittest.TestCase):
    def make_run(self, folder, text='Synthetic answer [7]'):
        (folder / 'call_001').mkdir()
        exclusive_json(folder / 'call_001/response.json', {
            'status': 'ok', 'done_reason': 'stop',
            'message': {'role': 'assistant', 'content': text, 'tool_calls': []}})
        return text

    def test_submitted_answer_is_bound_and_cannot_be_reselected(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            text = self.make_run(folder)
            write_terminal(folder, {'query_id': '7'}, text, 'call_001')
            summary, answer = load_terminal(folder)
            self.assertTrue(summary['submitted']); self.assertEqual(answer['response'], text)
            with self.assertRaises(FileExistsError):
                write_terminal(folder, {'query_id': '7'}, 'better answer', 'call_001')
            (folder / 'final_answer.json').write_text('{}')
            with self.assertRaises(ValueError):
                load_terminal(folder)

    def test_no_label_gate_accepts_an_unfinished_or_truncated_run(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            text = self.make_run(folder)
            with self.assertRaises(FileNotFoundError):
                load_terminal(folder)
            response = json.loads((folder / 'call_001/response.json').read_text())
            response['done_reason'] = 'length'
            (folder / 'call_001/response.json').write_text(json.dumps(response))
            with self.assertRaises(ValueError):
                write_terminal(folder, {'query_id': '7'}, text, 'call_001')
            write_terminal(folder, {'query_id': '7', 'stop_reason': 'output_limit'})
            self.assertEqual(load_terminal(folder)[1], None)


class OfficialSourceTests(unittest.TestCase):
    def test_changed_source_is_rejected_before_any_execution(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / 'changed.py'
            source.write_text('raise RuntimeError("must not execute")\n')
            with self.assertRaises(ValueError):
                official_contract(source)


if __name__ == '__main__':
    unittest.main()
