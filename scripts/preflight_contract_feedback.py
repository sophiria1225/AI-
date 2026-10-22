"""Synthetic container integration through the original code-tool adapter."""
import argparse
import datetime as dt
import json
from pathlib import Path
import time

from appworld_native_tools import NativeCatalog
from code_agent_interface import execute_response
from contract_comparison import FeedbackProgram
from persistent_api_python import PersistentApiPython
from run_handoff_factors import ROOT, sha


def probe(storage, root):
    target = root / 'reports/P47_runtime_checks.json'
    out = storage / 'records/context_pilot/P47_runtime_checks_v01'
    if target.exists() or out.exists():
        raise FileExistsError('preserve earlier runtime checks, including failures')
    out.mkdir(parents=True)
    began = time.monotonic()
    report = {'phase': 'P47_runtime_checks', 'all_checks_passed': False, 'rows': [],
              'model_calls': 0, 'environment_api_requests': 0, 'evaluator_calls': 0,
              'reserved_scenarios_read': 0, 'fixture_dispatches': 0,
              'started_at': dt.datetime.now(dt.timezone.utc).isoformat()}
    class Fixture:
        def __init__(self): self.calls = []
        def request(self, request):
            self.calls.append(request)
            call = request['call']
            return {'ok': True, 'result': {'observation': json.dumps(call['args'].get('value')),
                                          'declared_complete': call['api'] == 'finish'}}
    functions = [{'type': 'function', 'function': {'name': 'sample__' + name,
                  'parameters': {'type': 'object', 'properties': properties}}} for name, properties in
                 [('echo', {'value': {'type': 'integer'}}), ('finish', {})]]
    try:
        for mode in ('parameter_names', 'public_schema'):
            catalog = NativeCatalog(functions); catalog.visible.update(('sample__echo', 'sample__finish'))
            bridge = Fixture(); session = PersistentApiPython(storage, out / mode / 'session')
            runtime = FeedbackProgram(session.run, mode)
            recorded = []
            def record(row, display=True):
                recorded.append((row, display)); return f's{len(recorded)}'
            def run(code, number, remaining):
                if time.monotonic() - began > 120:
                    raise TimeoutError('bounded synthetic runtime probe')
                message = {'tool_calls': [{'id': f'fixture_{number}', 'type': 'function', 'function': {
                    'name': 'run_python', 'arguments': json.dumps({'code': code, 'span_ids': []})}}]}
                rows = execute_response(message, catalog, bridge, [], record, out=out / mode,
                    storage=storage, call_id=f'call_{number:03d}', remaining_api=lambda: remaining,
                    may_continue=lambda: True, remaining_wall=lambda: 15,
                    read_archive=lambda *_: None, program=runtime)
                return rows[-1]['observation']
            try:
                rejected = run('seen=call_api("sample","echo",value=7)\ncall_api("sample","echo",typo=9)', 1, 3)
                assert rejected['status'] == 'execution_error' and rejected['api_requests'] == 1
                assert 'contract_feedback' in rejected['error'] and len(bridge.calls) == 1
                budget = run('call_api("sample","echo",typo=8)', 2, 0)
                assert budget['api_requests'] == 0 and 'contract_feedback' not in budget['error']
                hidden = run('call_api("hidden","send",typo=8)', 3, 3)
                assert hidden['api_requests'] == 0 and 'contract_feedback' not in hidden['error']
                final = run('print(seen)\ncall_api("sample","finish")\ncall_api("sample","echo",value=99)', 4, 3)
                assert final['stdout'] == '7\n' and final['declared_complete'] and final['api_requests'] == 1
                assert len(bridge.calls) == 2 and len(runtime.feedback) == 1
                assert 'contract_feedback' not in final['error']
                assert all(all(r['controls'].values()) for r in [json.loads(p.read_text())
                    for p in (out / mode / 'programs').glob('*/result_private.json')])
            finally:
                state = session.close()
                report['fixture_dispatches'] += len(bridge.calls)
                report['rows'].append({'mode': mode, 'programs': len(session.programs),
                    'container_removed': state['container_removed'], 'feedback': runtime.summary()})
            assert state['container_removed']
        report['all_checks_passed'] = True
    except Exception as error:
        report['error_type'] = type(error).__name__
        (out / 'error_private.txt').write_text(str(error))
        raise
    finally:
        report['wall_seconds'] = time.monotonic() - began
        report['source_sha256'] = {name: sha(root / 'scripts' / name) for name in (
            'preflight_contract_feedback.py', 'contract_comparison.py', 'contract_feedback.py',
            'code_agent_interface.py', 'container_api_python.py', 'persistent_api_python.py')}
        text = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
        (out / 'status.json').write_text(text); target.write_text(text)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT); args = parser.parse_args()
    result = probe(args.storage_root, args.repo_root)
    print({k: result[k] for k in ('all_checks_passed', 'fixture_dispatches', 'wall_seconds')})
