"""Trusted task-local inventory capture, separate from generated programs.

The ordinary interpreter gains one host-only request at a closed program boundary.
It neither refreshes supplied bindings nor runs model source. Metadata and control
costs are recorded in both experiment modes. This is not a hostile-Python sandbox.
"""
import ast
from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path
import time
import types
import uuid

import checkpoint_runtime_inventory as inventory_core
from checkpoint_runtime_inventory import checked_inventory, digest, require
from region_projection_runtime import RegionProjectionPython, derived_region_bootstrap
from run_context_comparison import write_json

PROTOCOL = 'checkpoint_inventory_capture_v1'
MAX_REPLY_BYTES = 65536
MAX_CAPTURE_SECONDS = 10
MAX_CAPTURES = 3


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode() + b'\n'


def valid_hash(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def collector_source():
    """Bundle only the reviewed pure collector and its literal/captured constants."""
    source = inspect.getsource(inventory_core)
    tree = ast.parse(source)
    names = {'MAX_NAMESPACE_BINDINGS', 'MAX_NAME_CHARACTERS', 'RESERVED', '_TYPE', '_DICT', '_STR',
             '_DICT_ITEMS', '_DICT_LEN', '_STR_ISIDENTIFIER', '_STR_ISASCII', '_STR_STARTSWITH',
             '_STR_LEN', '_SORTED', '_KINDS'}
    selected = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = {n.id for target in node.targets for n in ast.walk(target) if isinstance(n, ast.Name)}
            if targets & names:
                require(targets <= names, 'collector_constant_declaration_changed')
                selected.append(ast.get_source_segment(source, node))
    return ('MAX_BINDINGS = ' + repr(inventory_core.MAX_BINDINGS) + '\n'
            + '\n'.join(selected) + '\n' + inspect.getsource(inventory_core.require) + '\n'
            + inspect.getsource(inventory_core.collect_inventory))


def derived_inventory_bootstrap(policy, execution_scope_sha256):
    require(policy == 'explicit_joined_fields' and valid_hash(execution_scope_sha256),
            'fixed_inventory_session_scope_required')
    original = derived_region_bootstrap(policy)
    anchor = "scope = {'__name__':'__main__'}\n"
    dispatch = '    packet = json.loads(line)\n'
    require(original.count(anchor) == original.count(dispatch) == 1, 'inventory_bootstrap_boundary_changed')
    install = (
        "_inventory_engine = types.ModuleType('trusted_checkpoint_inventory_v1')\n"
        f"exec(compile({collector_source()!r}, '<trusted inventory collector>', 'exec'), _inventory_engine.__dict__)\n"
        "import hashlib as _inventory_hashlib\n"
        f"_inventory_scope_sha256 = {execution_scope_sha256!r}\n"
        f"_inventory_protocol = {PROTOCOL!r}\n")
    handler = '''    if type(packet) is dict and packet.get('op') == 'checkpoint_inventory':
        _inventory_response = dict(kind='checkpoint_inventory', protocol=_inventory_protocol,
            request_sha256=_inventory_hashlib.sha256(line.encode()).hexdigest(),
            request_id=packet.get('request_id'), execution_scope_sha256=_inventory_scope_sha256,
            checkpoint_revision=packet.get('checkpoint_revision'), program_index=program_index,
            source_boundary_sha256=packet.get('source_boundary_sha256'), python=sys.version.split()[0],
            status='error', inventory=None, error_type=None)
        try:
            if (set(packet) != {'op','protocol','request_id','execution_scope_sha256',
                    'checkpoint_revision','program_index','source_boundary_sha256'}
                    or packet['protocol'] != _inventory_protocol
                    or packet['execution_scope_sha256'] != _inventory_scope_sha256
                    or type(packet['request_id']) is not str or len(packet['request_id']) != 32
                    or any(c not in '0123456789abcdef' for c in packet['request_id'])
                    or type(packet['checkpoint_revision']) is not int or not 1 <= packet['checkpoint_revision'] <= 3
                    or type(packet['program_index']) is not int or packet['program_index'] != program_index
                    or type(packet['source_boundary_sha256']) is not str or len(packet['source_boundary_sha256']) != 64
                    or any(c not in '0123456789abcdef' for c in packet['source_boundary_sha256'])):
                raise ValueError('invalid inventory boundary')
            _inventory_response['inventory'] = _inventory_engine.collect_inventory(scope)
            _inventory_response['status'] = 'ok'
        except BaseException as _inventory_error:
            _inventory_response['error_type'] = type(_inventory_error).__name__
        wire_out.write(json.dumps(_inventory_response,sort_keys=True,ensure_ascii=False,
            separators=(',', ':'),allow_nan=False)+'\\n')
        wire_out.flush()
        continue
'''
    result = original.replace(anchor, install + anchor).replace(dispatch, dispatch + handler)
    compile(result, '<trusted checkpoint inventory bootstrap>', 'exec')
    return result


def validate_response(response, request, request_bytes, expected_python):
    required = {'kind', 'protocol', 'request_sha256', 'request_id', 'execution_scope_sha256',
                'checkpoint_revision', 'program_index', 'source_boundary_sha256', 'python',
                'status', 'inventory', 'error_type'}
    require(type(response) is dict and set(response) == required
            and response['kind'] == 'checkpoint_inventory' and response['protocol'] == PROTOCOL
            and response['python'] == expected_python
            and response['request_sha256'] == hashlib.sha256(request_bytes).hexdigest(),
            'inventory_response_shape_or_request_binding')
    for key in ('request_id', 'execution_scope_sha256', 'checkpoint_revision', 'program_index', 'source_boundary_sha256'):
        require(type(response[key]) is type(request[key]) and response[key] == request[key],
                'inventory_response_boundary_changed')
    require(response['status'] == 'ok' and response['error_type'] is None,
            'inventory_capture_not_successful')
    return checked_inventory(response['inventory'])


class CheckpointInventoryPython(RegionProjectionPython):
    def __init__(self, storage_root, session_dir, *, policy, execution_scope):
        require(policy == 'explicit_joined_fields' and type(execution_scope) is str and execution_scope,
                'fixed_inventory_python_configuration_required')
        self.inventory_scope_sha256 = hashlib.sha256(execution_scope.encode()).hexdigest()
        super().__init__(storage_root, session_dir, policy=policy)

    def _bootstrap(self):
        return derived_inventory_bootstrap(self.policy, self.inventory_scope_sha256)

    def capture_inventory(self, *, revision, source_boundary_sha256, record_dir, timeout=MAX_CAPTURE_SECONDS):
        require(type(revision) is int and 1 <= revision <= MAX_CAPTURES and valid_hash(source_boundary_sha256)
                and type(timeout) in (int, float) and 0 < timeout <= MAX_CAPTURE_SECONDS,
                'bounded_inventory_capture_required')
        require(not self.closed and self.usable, 'usable_inventory_session_required')
        folder = Path(record_dir)
        folder.mkdir(parents=True, exist_ok=False)
        request = dict(op='checkpoint_inventory', protocol=PROTOCOL, request_id=uuid.uuid4().hex,
            execution_scope_sha256=self.inventory_scope_sha256, checkpoint_revision=revision,
            program_index=len(self.programs), source_boundary_sha256=source_boundary_sha256)
        payload = encoded(request)
        (folder / 'request_private.json').write_bytes(payload)
        result = dict(status='not_dispatched', checkpoint_revision=revision, program_index=len(self.programs),
            request_sha256=hashlib.sha256(payload).hexdigest(), response_sha256=None,
            request_bytes=len(payload), response_bytes=0, request_sent=False, inventory=None,
            execution_scope_sha256=self.inventory_scope_sha256, source_boundary_sha256=source_boundary_sha256,
            ordinary_program_count_unchanged=True, response_complete=False,
            new_model_calls=0, new_API_requests=0)
        began = time.monotonic()
        initial_programs = deepcopy(self.programs)
        buffer = b''
        try:
            if self.process is None:
                self._start()
            require(time.monotonic() - began < timeout, 'inventory_deadline_after_session_start')
            require(self.process.poll() is None, 'inventory_interpreter_stopped')
            result['request_sent'] = True
            self.process.stdin.write(payload)
            self.process.stdin.flush()
            while b'\n' not in buffer:
                remaining = timeout - (time.monotonic() - began)
                if remaining <= 0:
                    raise TimeoutError('inventory_capture_deadline')
                ready = self.selector.select(min(1, remaining))
                if not ready:
                    require(self.process.poll() is None, 'inventory_interpreter_stopped')
                    continue
                chunk = self.process.stdout.read1(MAX_REPLY_BYTES + 1)
                require(chunk, 'inventory_interpreter_eof')
                buffer += chunk
                require(len(buffer) <= MAX_REPLY_BYTES, 'bounded_inventory_reply_required')
            (folder / 'wire_private.jsonl').write_bytes(buffer)
            result.update(response_bytes=len(buffer), response_sha256=hashlib.sha256(buffer).hexdigest())
            line, extra = buffer.split(b'\n', 1)
            require(not extra, 'inventory_response_must_be_one_packet')
            response = json.loads(line)
            (folder / 'response_private.json').write_bytes(line + b'\n')
            snapshot = validate_response(response, request, payload, self.selection['expected_python'])
            require(self.programs == initial_programs, 'inventory_cannot_execute_or_append_program')
            result.update(status='ok', response_complete=True, inventory=snapshot, inventory_sha256=digest(snapshot))
        except Exception as error:
            result.update(status='failed_unknown' if result['request_sent'] else 'failed_not_dispatched',
                          error_type=type(error).__name__)
            self.usable = False
            try:
                self.close()
            except Exception as cleanup:
                result['cleanup_error_type'] = type(cleanup).__name__
            raise
        finally:
            if buffer:
                (folder / 'wire_private.jsonl').write_bytes(buffer)
                result.update(response_bytes=len(buffer), response_sha256=hashlib.sha256(buffer).hexdigest())
            result.update(wall_seconds=time.monotonic() - began, session_usable=self.usable and not self.closed)
            write_json(folder / 'result_private.json', result)
        return result


class CheckpointInventoryRuntime:
    def __init__(self, session, output, *, execution_scope):
        require(type(session) is CheckpointInventoryPython and type(execution_scope) is str and execution_scope,
                'exact_trusted_inventory_session_required')
        self.scope_sha256 = hashlib.sha256(execution_scope.encode()).hexdigest()
        require(session.inventory_scope_sha256 == self.scope_sha256, 'inventory_execution_scope_changed')
        self.session, self.output = session, Path(output)
        self.records = []
        self.contract_failed = False

    def capture(self, *, revision, source_boundary_sha256, deadline):
        require(not self.contract_failed, 'inventory_capture_contract_stopped')
        require(type(revision) is int and revision == len(self.records) + 1 and revision <= MAX_CAPTURES,
                'one_capture_per_sequential_accepted_revision')
        began = time.monotonic()
        record = dict(checkpoint_revision=revision, source_boundary_sha256=source_boundary_sha256,
                      status='starting', program_index=len(self.session.programs))
        self.records.append(record)
        try:
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'inventory_work_deadline_reached')
            result = self.session.capture_inventory(revision=revision,
                source_boundary_sha256=source_boundary_sha256,
                record_dir=self.output / 'checkpoint_inventory' / f'capture_{revision:03d}',
                timeout=min(MAX_CAPTURE_SECONDS, remaining))
            require(result['status'] == 'ok' and result['session_usable'] is True,
                    'successful_inventory_capture_required')
            record.update(deepcopy(result))
            return deepcopy(result)
        except Exception as error:
            result_path = self.output / 'checkpoint_inventory' / f'capture_{revision:03d}' / 'result_private.json'
            if result_path.is_file():
                record.update(json.loads(result_path.read_text()))
            if record['status'] == 'starting':
                record['status'] = 'failed_not_dispatched'
            record['error_type'] = type(error).__name__
            self.contract_failed = True
            raise
        finally:
            record['host_wall_seconds'] = time.monotonic() - began
            self.save()

    def save(self):
        write_json(self.output / 'checkpoint_inventory_capture_private.json', self.records)

    def summary(self):
        complete = all(r['status'] == 'ok' for r in self.records)
        return dict(captures=len(self.records), successful_captures=sum(r['status'] == 'ok' for r in self.records),
            capture_wall_seconds=sum(r['host_wall_seconds'] for r in self.records),
            known_request_bytes=sum(r.get('request_bytes', 0) for r in self.records),
            known_response_bytes=sum(r.get('response_bytes', 0) for r in self.records),
            unknown_capture_replies=sum(r.get('request_sent') is True and r.get('response_complete') is not True for r in self.records),
            capture_accounting_complete=complete, contract_failed=self.contract_failed,
            records_sha256=digest(self.records), environment_API_requests=0, model_calls=0,
            generated_programs_executed=0, ordinary_program_count_unchanged=True,
            control_wall_included_in_work_wall=True, values_disclosed=False, scalar_lengths_disclosed=False,
            trusted_engine_integrity_assumed=True, hostile_python_security_sandbox=False)
