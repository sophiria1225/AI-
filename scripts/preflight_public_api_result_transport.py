"""Finite synthetic integration: three containers, eight programs, no tasks/model.

The original code-tool adapter, Python runtime, budgets and receipt recording
are exercised. Only generated trusted fixture invocations execute on the host.
All outcomes, including failures, are saved once; do not retry into this output.
"""
import contextlib
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

from appworld_native_tools import NativeCatalog
from appworld_typed_bridge import execute_public_api
from code_agent_interface import execute_response
from persistent_api_python import PersistentApiPython
from public_api_envelope import PROTOCOL
from public_api_result_transport import PublicResultProgram, PublicResultTransport

ROOT = Path(__file__).resolve().parents[1]
STORAGE = Path('/Users/tp26013/AI-')
SOURCE_NAMES = ('appworld_typed_bridge.py', 'public_api_envelope.py',
                'public_api_result_transport.py', 'preflight_public_api_result_transport.py',
                'code_agent_interface.py', 'persistent_api_python.py', 'container_api_python.py')


class FixtureWorld:
    def __init__(self):
        self.effects = []
        self.complete = False
        self.syntax_checks = 0
        self.task = SimpleNamespace(api_docs={'fixture': {
            name: {'parameters': [{'name': 'value'}]} for name in ('echo', 'fail', 'finish', 'finish_fail', 'noise')}})

    def execute(self, source):
        from appworld.common.safety_guard import SafetyGuard
        def action(name, value=None):
            self.effects.append(name)
            if name.startswith('finish'): self.complete = True
            if name.endswith('fail'): raise ValueError('synthetic failure after effect')
            return value
        api = SimpleNamespace(**{name: (lambda value=None, name=name: action(name, value))
                                 for name in self.task.api_docs['fixture']})
        guard = SafetyGuard(); safe, reason = guard.is_syntax_safe(source)
        if not safe: raise ValueError('trusted_fixture_syntax_rejected: ' + reason)
        self.syntax_checks += 1
        capture = io.StringIO()
        try:
            guard.enable()
            with contextlib.redirect_stdout(capture):
                exec(compile(source, '<trusted fixture invocation>', 'exec'),
                     {'apis': SimpleNamespace(fixture=api)})
        finally:
            guard.disable()
        return capture.getvalue()

    def task_completed(self):
        return self.complete


class FixtureTransport:
    def __init__(self):
        self.world = FixtureWorld()
        self.requests = 0

    def request(self, command):
        if command['op'] != 'call_typed': raise ValueError('fixture_only_accepts_typed_calls')
        self.requests += 1
        result = execute_public_api(self.world, command['call'], command['nonce'])
        if command['call']['api'] == 'noise':
            result['observation'] = 'synthetic unrelated stdout\n' + result['observation']
        return {'ok': True, 'result': result}


def make_catalog():
    names = ('echo', 'fail', 'finish', 'finish_fail', 'noise')
    catalog = NativeCatalog([{'type': 'function', 'function': {'name': 'fixture__' + name,
        'parameters': {'type': 'object', 'properties': {'value': {}}}}} for name in names])
    catalog.visible.update(catalog.catalog)
    return catalog


def main():
    target = ROOT / 'reports/public_api_result_runtime_20261023.json'
    out = STORAGE / 'records/context_pilot/public_api_result_runtime_v01'
    if target.exists() or out.exists(): raise FileExistsError('preserve_prior_runtime_check')
    out.mkdir(parents=True)
    started = time.monotonic()
    report = {'scope': 'synthetic_typed_result_code_adapter_and_container_integration',
              'started_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'all_checks_passed': False,
              'programs': [], 'sessions': [], 'model_calls': 0, 'task_loads': 0,
              'appworld_api_requests': 0, 'evaluator_calls': 0, 'reserved_scenarios_read': 0,
              'database_contents_read': 0, 'saved_model_programs_executed': 0,
              'task_success_or_cost_improvement_measured': False}
    cases = {
        'ordinary': [
            ('saved=call_api("fixture","echo",value="null")\nprint(type(saved).__name__)\ncall_api("fixture","fail",value=7)', 8),
            ('print(saved)\nvalue=call_api("fixture","echo",value={"success":False})\nprint(value["success"])', 8),
            ('call_api("fixture","echo",value=9)', 0),
            ('call_api("fixture","echo",typo=9)', 8),
            ('call_api("fixture","finish")\ncall_api("fixture","echo",value=9)', 8),
            ('call_api("fixture","echo",value=9)', 8)],
        'unknown': [('try:\n    call_api("fixture","noise",value=7)\nexcept RuntimeError:\n    pass\ncall_api("fixture","echo",value=9)', 8)],
        'completion_exception': [('try:\n    call_api("fixture","finish_fail")\nexcept RuntimeError:\n    pass\ncall_api("fixture","echo",value=9)', 8)]}
    try:
        for name, programs in cases.items():
            raw = FixtureTransport(); transport = PublicResultTransport(raw)
            session = PersistentApiPython(STORAGE, out / name / 'session')
            runtime = PublicResultProgram(session.run); catalog = make_catalog(); records = []
            def record(row, display=True):
                records.append(row); return f's{len(records)}'
            results = []
            try:
                for number, (source, remaining) in enumerate(programs, 1):
                    if time.monotonic() - started > 120: raise TimeoutError('synthetic_check_budget')
                    message = {'tool_calls': [{'id': f'fixture_{number}', 'type': 'function', 'function': {
                        'name': 'run_python', 'arguments': json.dumps({'code': source, 'span_ids': []})}}]}
                    rows = execute_response(message, catalog, transport, [], record, out=out / name,
                        storage=STORAGE, call_id=f'call_{number:03d}', remaining_api=lambda: remaining,
                        may_continue=lambda: True, remaining_wall=lambda: min(15, 120 - (time.monotonic() - started)),
                        read_archive=lambda *_: None, program=runtime)
                    result = rows[-1]['observation']; results.append(result)
                    report['programs'].append({'session': name, 'program': number,
                        'status': result['status'], 'fixture_api_requests': result['api_requests'],
                        'declared_complete': result['declared_complete'], 'unknown_effects': result['unknown_effects'],
                        'receipt_count': len(result['api_receipts']),
                        'stdout_sha256': hashlib.sha256(result['stdout'].encode()).hexdigest()})
                if name == 'ordinary':
                    assert [r['api_requests'] for r in results] == [2, 1, 0, 0, 1, 0]
                    assert [r['status'] for r in results] == ['execution_error', 'ok'] + ['execution_error'] * 4
                    assert results[0]['stdout'] == 'str\n' and 'ValueError: synthetic failure' in results[0]['error']
                    assert results[1]['stdout'] == 'null\nFalse\n'
                    assert not any(r['unknown_effects'] for r in results)
                    assert results[4]['declared_complete'] and results[5]['declared_complete']
                    assert raw.world.effects == ['echo', 'fail', 'echo', 'finish']
                elif name == 'unknown':
                    assert results[0]['api_requests'] == 1 and results[0]['unknown_effects']
                    assert raw.world.effects == ['noise'] and not session.usable and session.closed
                    try:
                        session.run('print(1)', [], None, storage_root=STORAGE,
                                    record_dir=out / name / 'forbidden_resume', timeout=1)
                    except RuntimeError: pass
                    else: raise AssertionError('unknown_session_was_resumed')
                else:
                    assert results[0]['api_requests'] == 1 and results[0]['declared_complete']
                    assert not results[0]['unknown_effects'] and raw.world.effects == ['finish_fail']
                sent = [row for row in records if row['api_request_sent']]
                assert len(sent) == raw.requests == len(transport.receipts)
                assert all('api_execution' in row for row in sent)
                assert all(row['api_execution']['automatic_retries'] == 0 for row in sent)
                for path in (out / name / 'programs').glob('*/result_private.json'):
                    result = json.loads(path.read_text())
                    assert len(result['controls']) == 14 and all(result['controls'].values())
            finally:
                state = session.close()
                report['sessions'].append({'name': name, 'container_removed': state['container_removed'],
                    'programs': len(session.programs), 'fixture_dispatches': raw.requests,
                    'trusted_syntax_checks': raw.world.syntax_checks, 'receipts': transport.receipts})
            assert state['container_removed']
        assert len(report['programs']) == 8 and len(report['sessions']) == 3
        assert sum(r['fixture_dispatches'] for r in report['sessions']) == 6
        report['all_checks_passed'] = True
    except Exception as error:
        report['error_type'] = type(error).__name__
        (out / 'error_private.txt').write_text(str(error))
        raise
    finally:
        report['wall_seconds'] = time.monotonic() - started
        report['source_sha256'] = {f'scripts/{name}': hashlib.sha256((ROOT / 'scripts' / name).read_bytes()).hexdigest()
                                   for name in SOURCE_NAMES}
        import appworld.common.safety_guard as guard_module
        report['guard_source_sha256'] = hashlib.sha256(Path(guard_module.__file__).read_bytes()).hexdigest()
        text = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
        (out / 'status.json').write_text(text)
        with target.open('x') as handle: handle.write(text)
    print(json.dumps({k: report[k] for k in ['all_checks_passed', 'wall_seconds', 'model_calls', 'appworld_api_requests']}))


if __name__ == '__main__':
    main()
