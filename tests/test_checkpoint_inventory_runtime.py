"""Handwritten local wire fixtures; no Docker, model, task API or saved code."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time
from types import MethodType
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from checkpoint_inventory_runtime import (CheckpointInventoryPython, CheckpointInventoryRuntime,
    PROTOCOL, derived_inventory_bootstrap, encoded, validate_response)
from container_api_python import ApiChannel
from joined_public_read_views import JOINED_CONTRACT_ID
from public_api_result_transport import PublicResultTransport
from region_projection_runtime import RegionProjectionProgram
from shared_api_reservations import RequestBudget
from test_persistent_read_view_python import TrustedSubprocessSession
from test_public_read_views_live_probe import Fixture, catalog

SCOPE = 'inventory-synthetic'
SCOPE_SHA = hashlib.sha256(SCOPE.encode()).hexdigest()


def synthetic_session(folder, *, scope=SCOPE, bootstrap_override=None, storage_root=None):
    """Exact production class, local trusted process transport only."""
    session = CheckpointInventoryPython.__new__(CheckpointInventoryPython)
    TrustedSubprocessSession.__init__(session, folder, storage_root)
    session.policy = 'explicit_joined_fields'
    session.inventory_scope_sha256 = hashlib.sha256(scope.encode()).hexdigest()
    def start(self):
        self.stderr = (self.folder / 'stderr.txt').open('wb')
        bootstrap = bootstrap_override or self._bootstrap()
        self.process = subprocess.Popen([sys.executable, '-I', '-S', '-u', '-c', bootstrap],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.created_monotonic = time.monotonic()
    def close(self):
        value = TrustedSubprocessSession.close(self)
        self.usable = False
        self.state['container_removed'] = True  # No actual container is created.
        return value
    session._start = MethodType(start, session)
    session.close = MethodType(close, session)
    return session


class InventoryRuntimeTests(unittest.TestCase):
    def test_actual_trusted_wire_does_not_execute_a_program_or_touch_values(self):
        source = '''values = {'a': [1, 2]}
cyclic = []; cyclic.append(cyclic)
token = 'NEVER_DISCLOSE_SYNTHETIC_VALUE'
_hidden = 'PRIVATE_SYNTHETIC'
class Trap:
    def __len__(self): raise RuntimeError('custom len called')
    def __repr__(self): raise RuntimeError('custom repr called')
    def __getattribute__(self, name): raise RuntimeError('custom attr called')
trap = Trap()
class Sub(list):
    def __len__(self): raise RuntimeError('subclass len called')
sub = Sub([1, 2])
identity_before = id(values)
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = synthetic_session(root)
            runtime = CheckpointInventoryRuntime(session, root, execution_scope=SCOPE)
            budget = RequestBudget(8)
            raw = Fixture()
            bridge = PublicResultTransport(raw)
            with patch('region_projection_runtime.verify_joined_implementation', return_value=JOINED_CONTRACT_ID), \
                 patch('demand_joined_read_adapter.verify_joined_implementation', return_value=JOINED_CONTRACT_ID):
                adapter = RegionProjectionProgram(session, budget, execution_scope=SCOPE,
                    public_source_directory=root, policy='explicit_joined_fields')
                cat = catalog()
                try:
                    result = adapter(source, [], ApiChannel(cat, bridge, budget.available), storage_root=root,
                        record_dir=root / 'program_01', timeout=5)
                    self.assertEqual(result['status'], 'ok')
                    before = deepcopy(session.programs)
                    capture = runtime.capture(revision=1, source_boundary_sha256='a' * 64, deadline=time.monotonic() + 5)
                    rows = {r['name']: r for r in capture['inventory']['bindings']}
                    self.assertEqual(rows['values'], dict(name='values', type='dict', length=1))
                    self.assertEqual(rows['cyclic']['length'], 1)
                    self.assertIsNone(rows['token']['length'])
                    for key in ('trap', 'Trap', 'sub', 'Sub', '_hidden', 'observations', 'api_schemas', 'read_fields', 'call_api'):
                        self.assertNotIn(key, rows)
                    self.assertNotIn('NEVER_DISCLOSE', json.dumps(capture))
                    self.assertEqual(session.programs, before)
                    result = adapter("print(id(values) == identity_before); print(values['a'][1]); print(len(cyclic))", [],
                        ApiChannel(cat, bridge, budget.available), storage_root=root, record_dir=root / 'program_02', timeout=5)
                    self.assertEqual(result['stdout'], 'True\n2\n1\n')
                    self.assertEqual(len(session.programs), 2)
                    self.assertEqual(budget.spent, 0)
                    self.assertTrue(runtime.summary()['capture_accounting_complete'])
                    self.assertGreater(runtime.summary()['known_request_bytes'], 0)
                    self.assertGreater(runtime.summary()['known_response_bytes'], 0)
                    self.assertGreater(runtime.summary()['capture_wall_seconds'], 0)
                finally:
                    session.close()

    def test_empty_session_capture_is_real_and_not_a_generated_program(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = synthetic_session(Path(tmp))
            try:
                result = session.capture_inventory(revision=1, source_boundary_sha256='b' * 64,
                    record_dir=Path(tmp) / 'capture', timeout=5)
                self.assertEqual(result['inventory']['bindings'], [])
                self.assertEqual(result['program_index'], 0)
                self.assertEqual(session.programs, [])
            finally:
                session.close()

    def test_boundary_echo_type_and_nonce_must_match(self):
        request = dict(op='checkpoint_inventory', protocol=PROTOCOL, request_id='1' * 32,
            execution_scope_sha256=SCOPE_SHA, checkpoint_revision=1, program_index=0, source_boundary_sha256='b' * 64)
        payload = encoded(request)
        response = dict(kind='checkpoint_inventory', **{k: v for k, v in request.items() if k != 'op'},
            request_sha256=hashlib.sha256(payload).hexdigest(), python='synthetic', status='ok', error_type=None,
            inventory=dict(eligible_binding_count=0, truncated=False, bindings=[]))
        self.assertEqual(validate_response(response, request, payload, 'synthetic')['bindings'], [])
        for key, value in (('checkpoint_revision', True), ('program_index', False), ('request_id', '2' * 32),
                           ('execution_scope_sha256', '0' * 64), ('request_sha256', '0' * 64), ('status', 'error')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_response({**response, key: value}, request, payload, 'synthetic')

    def test_unknown_capture_closes_session_and_preserves_sent_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = synthetic_session(root, bootstrap_override='import sys\nfor line in sys.stdin:\n    pass\n')
            runtime = CheckpointInventoryRuntime(session, root, execution_scope=SCOPE)
            try:
                with self.assertRaises(TimeoutError):
                    runtime.capture(revision=1, source_boundary_sha256='a' * 64, deadline=time.monotonic() + .08)
                self.assertTrue(runtime.contract_failed)
                self.assertTrue(session.closed)
                self.assertEqual(runtime.summary()['unknown_capture_replies'], 1)
                self.assertGreater(runtime.summary()['known_request_bytes'], 0)
                self.assertFalse(runtime.summary()['capture_accounting_complete'])
                with self.assertRaises(ValueError):
                    runtime.capture(revision=1, source_boundary_sha256='a' * 64, deadline=time.monotonic() + 1)
                self.assertEqual(len(runtime.records), 1)
            finally:
                session.close()

    def test_capture_is_bounded_sequential_and_scope_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = synthetic_session(root)
            try:
                with self.assertRaises(ValueError):
                    CheckpointInventoryRuntime(session, root, execution_scope='different')
                runtime = CheckpointInventoryRuntime(session, root, execution_scope=SCOPE)
                for revision in (True, 0, 2, 4):
                    with self.subTest(revision=revision), self.assertRaises(ValueError):
                        runtime.capture(revision=revision, source_boundary_sha256='a' * 64, deadline=time.monotonic() + 1)
                self.assertEqual(runtime.records, [])
                self.assertIsNone(session.process)
            finally:
                session.close()


if __name__ == '__main__':
    unittest.main()
