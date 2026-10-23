"""Opt-in API result transport for the existing task-local Python runtime.

Admission, API budgets and completion remain in ApiChannel. Only a new bridge
process implements call_typed; an old untyped reply is never guessed or repaired.
Known invocation exceptions do not imply rollback. Unknown replies latch the
transport closed to further API dispatch across Python programs.
"""
import json
import os
from pathlib import Path
import selectors
import subprocess
import time
import uuid

from public_api_envelope import (
    PROTOCOL, MAX_REPLY_BYTES, InvalidExecutionEnvelope, decode_reply,
    unique_object, reject_constant,
)


class TypedBridgeProcess:
    """Separate typed-only server, with bounded nonblocking request/reply I/O."""
    MAX_FRAME_BYTES = 2 * MAX_REPLY_BYTES + 4096

    def __init__(self, python, root, output, *, timeout_seconds=90):
        if not 0 < timeout_seconds <= 90: raise ValueError('bridge_timeout_limit')
        self.timeout_seconds = timeout_seconds
        self.failed = False
        self.closed = False
        self.close_status = None
        env = os.environ.copy()
        env['APPWORLD_ROOT'] = str(root)
        self.errors = (Path(output) / 'bridge.stderr').open('w')
        script = Path(__file__).with_name('appworld_typed_bridge.py')
        try:
            self.process = subprocess.Popen(
                [str(python), str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=self.errors, bufsize=0, cwd=root, env=env)
        except Exception:
            self.errors.close()
            raise
        self.selector = selectors.DefaultSelector()
        os.set_blocking(self.process.stdin.fileno(), False)
        os.set_blocking(self.process.stdout.fileno(), False)
        self.selector.register(self.process.stdout, selectors.EVENT_READ)

    def request(self, value):
        if self.failed or self.closed: raise RuntimeError('bridge_transport_stopped')
        data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8') + b'\n'
        if len(data) > self.MAX_FRAME_BYTES: raise ValueError('bridge_request_size_limit')
        deadline = time.monotonic() + self.timeout_seconds
        offset = 0; received = bytearray(); writing = True
        self.selector.register(self.process.stdin, selectors.EVENT_WRITE)
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise TimeoutError('typed_bridge_request_timeout')
                for key, _ in self.selector.select(remaining):
                    if key.fileobj is self.process.stdin:
                        try: count = os.write(self.process.stdin.fileno(), data[offset:offset + 65536])
                        except BlockingIOError: continue
                        if count <= 0: raise RuntimeError('bridge_stdin_closed')
                        offset += count
                        if offset == len(data):
                            self.selector.unregister(self.process.stdin); writing = False
                    else:
                        try: chunk = os.read(self.process.stdout.fileno(), 65536)
                        except BlockingIOError: continue
                        if not chunk: raise RuntimeError('bridge_stdout_closed_before_reply')
                        received.extend(chunk)
                        if len(received) > self.MAX_FRAME_BYTES:
                            raise InvalidExecutionEnvelope('bridge_reply_size_limit')
                        if b'\n' in received:
                            line, extra = received.split(b'\n', 1)
                            if extra or offset != len(data):
                                raise InvalidExecutionEnvelope('unexpected_bridge_output')
                            return json.loads(line.decode('utf-8'), object_pairs_hook=unique_object,
                                              parse_constant=reject_constant)
        except Exception:
            self.failed = True
            raise
        finally:
            if writing: self.selector.unregister(self.process.stdin)

    def close(self):
        if self.closed: return self.close_status
        graceful = False
        try:
            if self.process.poll() is None and not self.failed:
                try:
                    response = self.request({'op': 'close'})
                    self.process.wait(timeout=15)
                    graceful = (response == {'ok': True, 'result': {'closed': True}}
                                and self.process.returncode == 0)
                    self.failed |= not graceful
                except Exception:
                    self.failed = True
            if self.process.poll() is None:
                self.process.terminate()
                try: self.process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self.process.kill(); self.process.wait(timeout=5)
            self.close_status = {'process_stopped': self.process.poll() is not None,
                                 'graceful': graceful, 'transport_failed': self.failed}
            return self.close_status
        finally:
            self.selector.close()
            self.process.stdin.close(); self.process.stdout.close(); self.errors.close()
            self.closed = True


class PublicResultTransport:
    """Adapt typed values/errors to the original channel, retaining all receipts."""
    def __init__(self, transport):
        self.transport = transport
        self.receipts = []
        self.nonces = set()
        self.fatal = False
        self.complete = False

    def close(self):
        return self.transport.close()

    def request(self, command):
        if type(command) is not dict or command.get('op') not in ('init', 'call', 'close'):
            raise ValueError('unsupported_typed_transport_command')
        if command['op'] != 'call':
            if command['op'] == 'init' and (self.fatal or self.receipts):
                raise ValueError('cannot_reinitialize_used_transport')
            try:
                response = self.transport.request(command)
            except Exception:
                if command['op'] == 'init': self.fatal = True
                raise
            if command['op'] == 'init' and (type(response) is not dict or response.get('ok') is not True
                    or type(response.get('result')) is not dict
                    or response['result'].get('api_result_protocol') != PROTOCOL):
                self.fatal = True
                raise InvalidExecutionEnvelope('typed_bridge_initialization_not_confirmed')
            return response
        if set(command) != {'op', 'call'}:
            raise ValueError('invalid_typed_call_command')
        if self.fatal or self.complete:
            raise InvalidExecutionEnvelope('transport_has_stopped_dispatch')
        receipt = {'protocol': PROTOCOL, 'status': 'unknown', 'bridge_request_sent': False,
                   'automatic_retries': 0, 'rollback_guaranteed': False}
        self.receipts.append(receipt)
        started = time.monotonic()
        try:
            nonce = uuid.uuid4().hex
            if nonce in self.nonces:
                raise InvalidExecutionEnvelope('reused_invocation_nonce')
            self.nonces.add(nonce)
            receipt['nonce'] = nonce
            receipt['bridge_request_sent'] = True
            response = self.transport.request({'op': 'call_typed', 'call': command['call'], 'nonce': nonce})
            if (type(response) is not dict or set(response) != {'ok', 'result'}
                    or response['ok'] is not True):
                raise InvalidExecutionEnvelope('bridge_did_not_report_a_typed_result')
            result = response['result']
            if (type(result) is not dict or set(result) != {'protocol', 'observation', 'declared_complete'}
                    or result['protocol'] != PROTOCOL or type(result['declared_complete']) is not bool):
                raise InvalidExecutionEnvelope('bridge_result_shape')
            decoded = decode_reply(result['observation'], nonce)
            receipt.update(status=decoded.status, raw_reply_sha256=decoded.raw_reply_sha256,
                           declared_complete=result['declared_complete'])
            self.complete |= result['declared_complete']
            if decoded.status == 'raised':
                receipt['exception_type'] = decoded.error_type
                return {'ok': False, 'error': f'{decoded.error_type}: {decoded.error_message}'}
            # JSON-encode even returned strings: the legacy channel decodes once.
            # Returning raw "1" or "null" would otherwise change its Python type.
            return {'ok': True, 'result': {'observation': json.dumps(decoded.value, ensure_ascii=False,
                allow_nan=False), 'declared_complete': self.complete}}
        except Exception as error:
            self.fatal = True
            receipt.update(status='unknown' if receipt['bridge_request_sent'] else 'not_dispatched',
                           failure_type=type(error).__name__)
            raise
        finally:
            receipt['transport_and_decode_wall_seconds'] = time.monotonic() - started


class PublicResultProgram:
    """Connect the opt-in transport through the unchanged code-tool adapter."""
    def __init__(self, program):
        self.program = program

    def __call__(self, source, observations, channel, **kwargs):
        if not isinstance(channel.bridge, PublicResultTransport):
            raise ValueError('typed_result_program_requires_typed_transport')
        return self.program(source, observations, _ReceiptChannel(channel), **kwargs)


class _ReceiptChannel:
    def __init__(self, base):
        self.base = base

    def __getattr__(self, name):
        return getattr(self.base, name)

    def exchange(self, packet):
        transport = self.base.bridge
        self.base.fatal |= transport.fatal
        self.base.complete |= transport.complete
        before = len(transport.receipts)
        reply = self.base.exchange(packet)
        new = transport.receipts[before:]
        row = self.base.rows[-1]
        if len(new) > 1 or new and not row['api_request_sent']:
            self.base.fatal = transport.fatal = True
            raise RuntimeError('typed_receipt_dispatch_mismatch')
        if new:
            row['api_execution'] = dict(new[0])
            if not new[0]['bridge_request_sent']:
                # A nonce/preflight failure is proven to precede transport.
                row.update(api_request_sent=False, effects_unknown=False,
                           observation={'not_executed': 'typed dispatch rejected before transport'})
                self.base.remaining += 1
                reply['error'] = row['observation']['not_executed']
        self.base.fatal |= transport.fatal
        self.base.complete |= transport.complete
        return reply
