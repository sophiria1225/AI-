"""Bounded pipe client. Timeout poisons the connection; late replies cannot be reused."""
import json
import os
from pathlib import Path
import selectors
import subprocess
import time

from browsecomp_bridge import MAX_REQUEST_BYTES


class CorpusClient:
    def __init__(self, python, index, java_home, errors_path, startup_timeout=180):
        env = os.environ.copy()
        env.update(JAVA_HOME=str(java_home), JAVA_TOOL_OPTIONS='-Xmx2g',
                   HF_HUB_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
        self.errors = Path(errors_path).open('x')
        self.process = subprocess.Popen(
            [str(python), str(Path(__file__).with_name('browsecomp_bridge.py')),
             '--index', str(index)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.errors, env=env, bufsize=0)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.pending = b''
        self.sequence = 0
        self.poisoned = False
        started = time.monotonic()
        try:
            self.ready = self._receive(startup_timeout)
            if self.ready != {'type': 'ready', 'protocol': 1, 'corpus_documents': 100195}:
                raise RuntimeError('retriever handshake differs from the frozen corpus')
            self.startup_seconds = time.monotonic() - started
        except BaseException:
            self.close()
            raise

    def _receive(self, timeout):
        deadline = time.monotonic() + timeout
        try:
            while b'\n' not in self.pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not self.selector.select(remaining):
                    raise TimeoutError('corpus bridge deadline')
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    raise RuntimeError('corpus bridge exited without a reply')
                self.pending += chunk
                if len(self.pending) > 2 * 1024 * 1024:
                    raise RuntimeError('corpus reply exceeds bounded protocol size')
            line, self.pending = self.pending.split(b'\n', 1)
            return json.loads(line)
        except BaseException:
            self.poisoned = True
            raise

    def request(self, name, arguments, timeout=60):
        if self.poisoned or self.process.poll() is not None:
            raise RuntimeError('corpus connection is unavailable; no implicit restart')
        self.sequence += 1
        data = (json.dumps({'id': self.sequence, 'op': 'tool', 'name': name,
                            'arguments': arguments}, ensure_ascii=False) + '\n').encode()
        if len(data) > MAX_REQUEST_BYTES:
            return {'id': self.sequence, 'ok': True, 'request_sent': False,
                    'wall_seconds': 0.0, 'result': {'status': 'invalid_arguments',
                    'error': 'tool request exceeds bounded protocol size'}}
        self.process.stdin.write(data)
        self.process.stdin.flush()
        value = self._receive(timeout)
        if value.get('id') != self.sequence:
            self.poisoned = True
            raise RuntimeError('corpus reply identity mismatch')
        if value.get('ok') is not True:
            self.poisoned = True
            raise RuntimeError('corpus backend failed; no empty-result substitution')
        value['request_sent'] = True
        return value

    def close(self):
        try:
            if self.process.stdin and not self.process.stdin.closed:
                self.process.stdin.close()
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=10)
        finally:
            self.selector.close()
            if self.process.stdout:
                self.process.stdout.close()
            self.errors.close()
