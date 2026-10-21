import io
import json
from pathlib import Path
import selectors
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from browsecomp_client import CorpusClient


def fixture_client(code):
    client = object.__new__(CorpusClient)
    client.process = subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
    client.selector = selectors.DefaultSelector()
    client.selector.register(client.process.stdout, selectors.EVENT_READ)
    client.pending, client.sequence, client.poisoned = b'', 0, False
    client.errors = io.StringIO()
    return client


class DeadlineTests(unittest.TestCase):
    def test_partial_line_does_not_block_past_deadline(self):
        client = fixture_client('import os,time; os.write(1,b"{\\\"partial\\\":"); time.sleep(5)')
        try:
            with self.assertRaises(TimeoutError):
                client._receive(0.05)
            self.assertTrue(client.poisoned)
            with self.assertRaises(RuntimeError):
                client.request('search', {'query': 'synthetic'})
        finally:
            client.close()

    def test_wrong_response_identity_cannot_be_used_by_next_request(self):
        client = fixture_client('import sys,json; json.loads(sys.stdin.readline()); '
                                'print(json.dumps({"id":999,"ok":True,"result":{}}),flush=True)')
        try:
            with self.assertRaises(RuntimeError):
                client.request('search', {'query': 'synthetic'}, timeout=2)
            self.assertTrue(client.poisoned)
        finally:
            client.close()


if __name__ == '__main__':
    unittest.main()
