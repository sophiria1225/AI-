"""P41: generation-only check at all P40 token-reservation stops.

No generated tool, Python program, task world, or final evaluator is executed.
This cannot repair an old trial or establish task success / time feasibility.
"""
import argparse
import ast
import datetime as dt
import json
from pathlib import Path
import signal
import subprocess
import time

from appworld_native_tools import NativeCatalog
from budget_signal import add_notification, digest
from code_agent_interface import CODE_TOOLS
from inference_cache_control import cache_measurement
from inspect_budget_admission import restore
from probe_inference_cache import live_identity
from residual_output_budget import ResidualInference, admission
from run_context_comparison import BudgetStop, write_json
from run_handoff_factors import ROOT, read, sha

SOURCES = ('scripts/residual_output_budget.py', 'scripts/probe_residual_output.py',
           'scripts/inspect_budget_admission.py', 'scripts/local_llama.py',
           'scripts/run_context_comparison.py', 'scripts/budget_signal.py',
           'scripts/native_conversation.py', 'scripts/code_agent_interface.py',
           'scripts/appworld_native_tools.py', 'scripts/probe_inference_cache.py',
           'scripts/inference_cache_control.py', 'scripts/model_provenance.py',
           'configs/P41_residual_output_v01.json', 'docs/experiments/P41_residual_output.md',
           'reports/P40_termination.json', 'reports/P40_admission_stopped.json',
           'tests/test_residual_output_budget.py', 'tests/test_residual_output_probe.py')


def syntax_only(message, known_spans):
    """Check the exposed function envelope and Python grammar, without exec."""
    calls = message.get('tool_calls') or []
    rows = []
    for call in calls:
        fn = call.get('function', {}) if isinstance(call, dict) else {}
        if not isinstance(fn, dict): fn = {}
        row = {'name': fn.get('name'), 'valid_envelope_and_syntax': False}
        try:
            args = json.loads(fn['arguments'])
            if fn['name'] == 'read_span':
                decoded = NativeCatalog([]).decode(fn)
                if decoded['span_id'] not in known_spans:
                    raise ValueError('unknown archived span')
            elif fn['name'] == 'run_python':
                if (type(args) is not dict or set(args) != {'code', 'span_ids'}
                        or type(args['code']) is not str or not 0 < len(args['code']) <= 20000
                        or type(args['span_ids']) is not list or len(args['span_ids']) > 160
                        or any(type(s) is not str for s in args['span_ids'])
                        or len(args['span_ids']) != len(set(args['span_ids']))
                        or not set(args['span_ids']) <= known_spans):
                    raise ValueError('invalid Python argument envelope or span reference')
                ast.parse(args['code'], mode='exec', feature_version=(3, 12))
            else:
                raise ValueError('not an exposed function')
            row['valid_envelope_and_syntax'] = True
        except (ValueError, KeyError, TypeError, SyntaxError) as error:
            row['error_type'] = type(error).__name__
        rows.append(row)
    return {'tool_calls_returned': len(calls), 'checks': rows,
            'all_tools_valid_envelope_and_syntax': bool(rows) and all(r['valid_envelope_and_syntax'] for r in rows),
            'tool_execution_calls': 0, 'task_success_evaluations': 0,
            'semantics_or_task_success_claim': False}


def sources(storage, root):
    plan = read(root / 'configs/P41_residual_output_v01.json')
    audit = read(root / 'reports/P40_admission_stopped.json')
    closed = read(root / 'reports/P40_termination.json')
    if (plan['phase'] != 'P41' or audit['status'] != 'complete'
            or not closed['all_planned_cells_accounted'] or closed['audit_errors']
            or audit['source_sha256']['reports/P40_termination.json'] != sha(root / 'reports/P40_termination.json')):
        raise ValueError('P40 termination/admission audit is not closed')
    cells = [r for r in closed['rows'] if r.get('stop_reason') == 'token_reservation_limit']
    if [r['run_id'] for r in cells] != plan['source_runs'] or [r['run_id'] for r in audit['rows']] != plan['source_runs']:
        raise ValueError('include all three admission stops, without selecting successes')
    prepared = []
    for cell, counted in zip(cells, audit['rows'], strict=True):
        folder = storage / 'records/context_pilot' / cell['run_id']
        if (sha(folder / 'conversation_private.json') != counted['conversation_sha256']
                or sha(folder / 'budget_signals.json') != cell['signal_source_sha256']):
            raise ValueError('saved rejected input changed')
        signal_row = read(folder / 'budget_signals.json')[-1]
        if signal_row['model_attempted'] or cell['unknown_usage_calls']:
            raise ValueError('only known, unattempted admission stops are eligible')
        config = read(folder / 'plan.json')
        base, _ = restore(read(folder / 'conversation_private.json')).for_model(config['observation_page_characters'])
        messages = add_notification(base, signal_row['state'], cell['arm'])
        if digest(messages) != counted['model_messages_sha256'] or digest(base) != signal_row['base_messages_sha256']:
            raise ValueError('input reconstruction differs')
        remaining = signal_row['state']['remaining']
        if remaining['api_calls'] <= 0 or remaining['model_calls'] <= 0:
            raise ValueError('another budget already prevents this diagnostic')
        choice = admission(remaining['logical_input_plus_output_tokens'], counted['next_input_tokens'],
                           config['max_output_tokens'], config['model']['num_ctx'], 'residual')
        fixed = admission(remaining['logical_input_plus_output_tokens'], counted['next_input_tokens'],
                          config['max_output_tokens'], config['model']['num_ctx'], 'fixed')
        if fixed['admitted'] or choice['selected_output_cap'] != counted['positive_output_capacity']:
            raise ValueError('admission decision differs from the closed audit')
        probe = {**config, 'model': {**config['model'], 'cache_prompt': False},
                 'seed': config['seed'] + cell['model_calls'], 'max_calls': 1,
                 'expected_input_tokens': counted['next_input_tokens'],
                 'max_total_tokens': remaining['logical_input_plus_output_tokens'],
                 'max_wall_seconds': plan['per_input_wall_seconds']}
        prepared.append({'run_id': cell['run_id'], 'config': probe, 'messages': messages,
                         'known_spans': set(read(folder / 'spans.json')), 'residual': choice, 'fixed': fixed,
                         'original_remaining_wall_seconds': remaining['wall_seconds_at_snapshot'],
                         'conversation_sha256': counted['conversation_sha256'],
                         'model_messages_sha256': counted['model_messages_sha256']})
    admitted = [p for p in prepared if p['residual']['admitted']]
    if (len(admitted) > plan['max_calls']
            or sum(p['residual']['input_tokens'] + p['residual']['selected_output_cap'] for p in admitted)
               > plan['max_total_tokens']):
        raise ValueError('diagnostic exceeds its fixed aggregate generation budget')
    return plan, prepared


def fingerprint(prepared):
    return [{k: p[k] for k in ('run_id', 'residual', 'fixed', 'model_messages_sha256',
                              'conversation_sha256', 'original_remaining_wall_seconds')} for p in prepared]


def prepare(storage, root):
    plan, prepared = sources(storage, root)
    identity, end = live_identity(storage, prepared[0]['config'], plan['max_wall_seconds'] + 60)
    target = root / 'reports/P41_activation_v01.json'
    if target.exists(): raise FileExistsError('preserve activation')
    result = {'phase': 'P41', 'source_sha256': {p: sha(root / p) for p in SOURCES},
              'inputs': fingerprint(prepared), 'model_identity': identity, 'server_lease_end': end,
              'prepared_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'model_calls': 0, 'environment_api_requests': 0, 'evaluator_calls': 0}
    write_json(target, result)
    print(json.dumps({'states': len(prepared), 'admitted': sum(p['residual']['admitted'] for p in prepared),
                      'model_calls': 0}))


def run(storage, root):
    plan, prepared = sources(storage, root)
    activation = read(root / 'reports/P41_activation_v01.json')
    if activation['source_sha256'] != {p: sha(root / p) for p in SOURCES} or activation['inputs'] != fingerprint(prepared):
        raise ValueError('frozen diagnostic inputs or implementation changed')
    identity, end = live_identity(storage, prepared[0]['config'], plan['max_wall_seconds'] + 60)
    if identity != activation['model_identity']: raise ValueError('server identity changed')
    folder = storage / 'records/context_pilot' / plan['batch_id']
    target = root / 'reports/P41_residual_output.json'
    if folder.exists() or target.exists(): raise FileExistsError('preserve every diagnostic attempt')
    folder.mkdir(); write_json(folder / 'plan.json', plan); write_json(folder / 'activation.json', activation)
    began = time.monotonic()
    result = {'phase': 'P41', 'status': 'running', 'active': None, 'rows': [],
              'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
              'model_identity': identity, 'server_lease_end': end, 'known_total_tokens': 0,
              'unknown_usage_calls': 0, 'model_calls': 0, 'environment_api_requests': 0,
              'evaluator_calls': 0, 'reserved_scenarios_read': 0, 'source_sha256': activation['source_sha256'],
              'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'task_success_claim': False, 'original_remaining_wall_feasibility_claim': False,
              'novel_method_claim': False}
    def save():
        result['updated_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        result['wall_seconds'] = time.monotonic() - began
        write_json(folder / 'status.json', result)
    save()
    try:
        for item in prepared:
            if (storage / '.runtime/P41.stop').exists(): raise InterruptedError('explicit stop')
            if plan['max_wall_seconds'] - (time.monotonic() - began) < plan['per_input_wall_seconds']:
                raise TimeoutError('diagnostic batch wall budget')
            current, _ = live_identity(storage, item['config'], plan['per_input_wall_seconds'] + 30)
            if current != identity: raise ValueError('server identity changed during diagnostic')
            out = folder / item['run_id']; out.mkdir()
            result['active'] = item['run_id']; save()
            infer = ResidualInference(item['config'], out)
            row = {**fingerprint([item])[0], 'status': 'running', 'model_calls': 0,
                   'known_total_tokens': 0, 'unknown_usage_calls': 0}
            result['rows'].append(row)
            try:
                message = infer.call('agent', item['messages'], CODE_TOOLS)
                response = read(out / 'call_001/response.json')
                measure = cache_measurement('cold_1', response, item['residual']['input_tokens'])
                row.update(status='generated', finish_reason=response['done_reason'],
                           syntax=syntax_only(message, item['known_spans']), cache_measurement=measure,
                           response_sha256=sha(out / 'call_001/response.json'),
                           request_sha256=sha(out / 'call_001/request.json'))
                if not measure['state_confirmed']: raise ValueError('fresh-input cache policy not satisfied')
                if infer.admissions[-1]['input_tokens'] != item['residual']['input_tokens']:
                    raise ValueError('input count changed from the prior reconstruction')
            except BudgetStop as error:
                row.update(status='not_admitted' if not infer.calls else 'generation_stopped', reason=str(error))
                if infer.calls or str(error) != 'token_reservation_limit' or item['residual']['admitted']:
                    raise
            finally:
                row.update(model_calls=len(infer.calls), known_total_tokens=infer.tokens,
                           unknown_usage_calls=sum(c['status'] != 'ok' for c in infer.calls),
                           admissions=infer.admissions, diagnostic_wall_seconds=time.monotonic() - infer.started)
                result['model_calls'] += row['model_calls']
                result['known_total_tokens'] += row['known_total_tokens']
                result['unknown_usage_calls'] += row['unknown_usage_calls']
                save()
            print(json.dumps({k: row.get(k) for k in ('run_id', 'status', 'known_total_tokens', 'finish_reason', 'syntax')}), flush=True)
        result['status'] = 'complete'
    except Exception as error:
        result.update(status='stopped', error_type=type(error).__name__)
        (folder / 'error_private.txt').write_text(str(error))
    finally:
        result['active'] = None
        result['all_three_states_accounted'] = len(result['rows']) == len(prepared) and result['status'] == 'complete'
        result['not_attempted_sources'] = [p['run_id'] for p in prepared if p['run_id'] not in {r['run_id'] for r in result['rows']}]
        save(); write_json(target, result)
    return 0 if result['status'] == 'complete' else 1


def interrupt(*_):
    raise TimeoutError('bounded diagnostic interrupted')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT); p.add_argument('--prepare', action='store_true')
    a = p.parse_args(); signal.signal(signal.SIGALRM, interrupt); signal.signal(signal.SIGTERM, interrupt)
    if a.prepare: prepare(a.storage_root, a.repo_root)
    else: raise SystemExit(run(a.storage_root, a.repo_root))
