"""Once-only live bridge check: one known task, two programs, three APIs, no LLM.

Only new handwritten programs run in the existing restricted Python container.
Raw public replies remain private; no evaluator, DB inspection or saved code runs.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid

from code_agent_interface import execute_response
from inspect_appworld_api_schemas import load_public_tools
from persistent_api_python import PersistentApiPython
from public_api_envelope import PROTOCOL
from public_api_result_transport import PublicResultProgram, PublicResultTransport, TypedBridgeProcess
from public_name_catalog import PublicNameCatalog

ROOT = Path(__file__).resolve().parents[1]
STORAGE = Path('/Users/tp26013/AI-')
PLAN = ROOT / 'configs/public_api_live_preflight_v01.json'
SOURCES = (
    'scripts/preflight_public_api_live.py', 'scripts/appworld_typed_bridge.py',
    'scripts/public_api_envelope.py', 'scripts/public_api_result_transport.py',
    'scripts/code_agent_interface.py', 'scripts/container_api_python.py',
    'scripts/persistent_api_python.py', 'scripts/public_name_catalog.py',
    'scripts/appworld_native_tools.py', 'scripts/inspect_appworld_api_schemas.py',
    'configs/python_export_image_v01.json', 'configs/public_api_live_preflight_v01.json',
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, value):
    with path.open('x') as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


class RecordedBridge:
    """Preserve each attempt, and bound actual I/O by the active program deadline."""
    def __init__(self, raw, folder, deadline, *, clock=time.monotonic, stop=lambda: False):
        self.raw, self.folder, self.deadline = raw, Path(folder), deadline
        self.clock, self.stop = clock, stop
        self.attempts = []

    def request(self, command):
        started = self.clock()
        entry = {'command': command, 'raw_request_started': False}
        self.attempts.append(entry)
        previous = self.raw.timeout_seconds
        try:
            if self.stop():
                raise InterruptedError('explicit_live_preflight_stop')
            remaining = self.deadline - started
            if remaining <= 0:
                raise TimeoutError('live_preflight_deadline_before_dispatch')
            self.raw.timeout_seconds = min(previous, remaining)
            entry['raw_request_started'] = True
            response = self.raw.request(command)
            entry['response'] = response
            return response
        except Exception as error:
            entry['error'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        finally:
            self.raw.timeout_seconds = previous
            entry['wall_seconds'] = self.clock() - started
            write_new(self.folder / f'bridge_{len(self.attempts):02d}_private.json', entry)

    def close(self):
        return self.raw.close()


def confirm_initial_world(response, expected):
    if (type(response) is not dict or response.get('ok') is not True
            or type(response.get('result')) is not dict):
        raise ValueError('public_world_initialization_failed')
    public = dict(response['result'])
    if public.pop('api_result_protocol', None) != PROTOCOL:
        raise ValueError('typed_protocol_missing')
    if public.get('ground_truth_loaded') is not False or public != expected:
        raise ValueError('initial_public_world_does_not_match_known_source')
    return public


def programs():
    # No actual account or saved credential is read. Values stay in private files.
    user = 'typed-preflight-invalid-' + uuid.uuid4().hex
    password = uuid.uuid4().hex
    return [
        'saved_marker=37\n'
        'doc=call_api("api_docs","show_api_doc",app_name="phone",api_name="login")\n'
        'assert type(doc) is dict and doc["app_name"]=="phone" and doc["api_name"]=="login"\n'
        'print(type(doc).__name__)\n'
        f'call_api("phone","login",username={user!r},password={password!r})',
        'assert saved_marker==37\n'
        'assert type(doc) is dict and doc["app_name"]=="phone" and doc["api_name"]=="login"\n'
        'apps=call_api("api_docs","show_app_descriptions")\n'
        'assert type(apps) is list\n'
        'print(type(doc).__name__,type(apps).__name__)',
    ]


def main():
    spec = json.loads(PLAN.read_text())
    out = STORAGE / spec['private_output']
    target = ROOT / spec['report']
    appworld = STORAGE / '.runtime/appworld/r18_probe_01'
    world = appworld / 'experiments/outputs' / spec['experiment']
    if target.exists() or out.exists() or world.exists():
        raise FileExistsError('preserve_every_prior_live_preflight_attempt')
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT):
        raise ValueError('live_preflight_requires_clean_tracked_source')
    out.mkdir(parents=True)
    started = time.monotonic()
    deadline = started + spec['work_deadline_seconds']
    stopped = lambda: (STORAGE / spec['stop_marker']).exists()
    report = {
        'scope': 'ordinary_typed_bridge_known_task_contract_check',
        'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'all_checks_passed': False, 'task_id': spec['task_id'], 'programs': [],
        'task_initialization_attempts': 0, 'initial_world_confirmed': False,
        'model_calls': 0, 'evaluator_calls': 0, 'reserved_scenarios_read': 0,
        'database_contents_inspected': 0, 'saved_model_programs_executed': 0,
        'task_success_or_cost_improvement_measured': False, 'error_types': [],
    }
    raw = recorded = transport = session = None
    records, checks_passed = [], False
    try:
        expected_path = STORAGE / spec['known_public_task']
        if digest(expected_path) != spec['known_public_task_sha256']:
            raise ValueError('known_public_task_source_changed')
        expected = json.loads(expected_path.read_text())
        package = STORAGE / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld'
        for name, sha in spec['runtime_source_sha256'].items():
            if digest(package / name) != sha:
                raise ValueError('installed_runtime_source_changed')
        tools, schema_sources, _ = load_public_tools(appworld / 'data')
        if schema_sources != spec['public_schema_sha256']:
            raise ValueError('public_api_schema_sources_changed')
        report['public_schema_sha256'] = schema_sources
        report['known_public_task_sha256'] = spec['known_public_task_sha256']
        report['runtime_source_sha256'] = spec['runtime_source_sha256']
        if stopped():
            raise InterruptedError('explicit_live_preflight_stop')
        raw = TypedBridgeProcess(STORAGE / '.runtime/appworld/venv/bin/python', appworld, out,
                                 timeout_seconds=spec['bridge_timeout_seconds'])
        report['owned_bridge_pid'] = raw.process.pid
        recorded = RecordedBridge(raw, out, deadline, stop=stopped)
        transport = PublicResultTransport(recorded)
        report['task_initialization_attempts'] += 1
        response = transport.request({'op': 'init', 'task_id': spec['task_id'],
            'experiment': spec['experiment'], 'seed': spec['seed']})
        public = confirm_initial_world(response, expected)
        report['initial_world_confirmed'] = True
        report['initial_public_world_canonical_sha256'] = hashlib.sha256(
            json.dumps(public, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        session = PersistentApiPython(STORAGE, out / 'python_session')
        runtime = PublicResultProgram(session.run)
        catalog = PublicNameCatalog(tools)

        def sent_count():
            return sum(bool(row['api_request_sent']) for row in records)

        def record(row, display=True):
            records.append(row)
            write_new(out / f'record_{len(records):02d}_private.json', row)
            return f's{len(records)}'

        results = []
        for number, source in enumerate(programs(), 1):
            recorded.deadline = min(deadline, time.monotonic() + spec['program_timeout_seconds'])
            if stopped() or time.monotonic() >= recorded.deadline:
                raise InterruptedError('live_preflight_stopped_before_program')
            message = {'tool_calls': [{'id': f'handwritten_{number}', 'type': 'function',
                'function': {'name': 'run_python', 'arguments': json.dumps({'code': source, 'span_ids': []})}}]}
            rows = execute_response(message, catalog, transport, [], record, out=out, storage=STORAGE,
                call_id=f'program_{number:02d}', remaining_api=lambda: spec['max_api_requests'] - sent_count(),
                may_continue=lambda: not stopped() and time.monotonic() < recorded.deadline,
                remaining_wall=lambda: max(.01, recorded.deadline - time.monotonic()),
                read_archive=lambda *_: None, program=runtime)
            result = rows[-1]['observation']
            results.append(result)
            report['programs'].append({
                'number': number, 'status': result.get('status'), 'api_requests': result.get('api_requests'),
                'unknown_effects': result.get('unknown_effects'),
                'declared_complete': result.get('declared_complete'),
                'stdout_sha256': hashlib.sha256(result.get('stdout', '').encode()).hexdigest(),
            })
            if result.get('unknown_effects') or result.get('status') == 'harness_error':
                raise RuntimeError('live_program_cannot_continue')
            if number == 1:
                assert result['status'] == 'execution_error' and result['api_requests'] == 2
                assert result['stdout'] == 'dict\n'
                assert [r['status'] for r in transport.receipts] == ['returned', 'raised']
                assert transport.receipts[1].get('exception_type')
                assert session.usable and not session.closed
            else:
                assert result['status'] == 'ok' and result['api_requests'] == 1
                assert result['stdout'] == 'dict list\n'
            assert not result['declared_complete'] and not result['unknown_effects']
        assert len(results) == 2 and sent_count() == 3
        assert [r['status'] for r in transport.receipts] == ['returned', 'raised', 'returned']
        sent = [row for row in records if row['api_request_sent']]
        assert [row['action']['name'] for row in sent] == [
            'api_docs__show_api_doc', 'phone__login', 'api_docs__show_app_descriptions']
        assert all(row['api_execution']['automatic_retries'] == 0 for row in sent)
        assert len(session.controls) == 14 and all(session.controls.values())
        assert len(recorded.attempts) == 4 and time.monotonic() <= deadline
        report['all_container_controls_passed'] = True
        report['preserved_value_and_document_after_api_exception'] = True
        checks_passed = True
    except (Exception, KeyboardInterrupt) as error:
        report['error_types'].append(type(error).__name__)
        write_new(out / 'error_private.json', {'type': type(error).__name__, 'message': str(error)})
    finally:
        report['work_wall_seconds'] = time.monotonic() - started
        cleanup_started = time.monotonic()
        if session is not None:
            try:
                state = session.close()
                report['python_cleanup'] = {key: state[key] for key in
                    ('status', 'container_removed', 'cleanup_wall_seconds')}
            except Exception as error:
                report['error_types'].append('python_cleanup:' + type(error).__name__)
        if raw is not None:
            try:
                report['bridge_cleanup'] = raw.close()
            except Exception as error:
                report['error_types'].append('bridge_cleanup:' + type(error).__name__)
        report['cleanup_wall_seconds'] = time.monotonic() - cleanup_started
        report['api_requests_recorded'] = sum(bool(row['api_request_sent']) for row in records)
        report['api_execution_receipts'] = transport.receipts if transport else []
        report['bridge_request_attempts'] = len(recorded.attempts) if recorded else 0
        report['typed_requests_started'] = sum(
            a['raw_request_started'] and a['command']['op'] == 'call_typed'
            for a in recorded.attempts) if recorded else 0
        report['source_sha256'] = {name: digest(ROOT / name) for name in SOURCES}
        report['wall_seconds'] = time.monotonic() - started
        report['all_checks_passed'] = bool(checks_passed and not report['error_types']
            and report.get('python_cleanup', {}).get('container_removed')
            and report.get('bridge_cleanup', {}).get('process_stopped')
            and report.get('bridge_cleanup', {}).get('graceful')
            and report['typed_requests_started'] == report['api_requests_recorded'] == 3)
        write_new(out / 'status.json', report)
        write_new(target, report)
    print(json.dumps({key: report[key] for key in (
        'all_checks_passed', 'wall_seconds', 'api_requests_recorded', 'model_calls', 'error_types')}))
    return 0 if report['all_checks_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
