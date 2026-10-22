"""Run one fixed P64 condition from a fresh public task, never from a solution."""
import copy
from datetime import datetime, timezone
import signal
import time

from appworld_native_tools import NativeCatalog
from code_agent_interface import execute_response
from context_preservation import page_span
from native_conversation import NativeConversation
from native_data_compute import selected_receipts
from ordinary_continuation import OrdinaryInference
from persistent_api_python import PersistentApiPython
from probe_prefix_replay import db_hashes
from public_name_catalog import PublicNameCatalog
from public_name_comparison import interface
from run_context_comparison import Bridge, BudgetStop, write_json


def run_condition(storage, plan, original, tasks, tools, task_id, arm, run_id):
    if [task_id, arm, run_id] not in plan['run_order']:
        raise ValueError('outside fixed four-condition schedule')
    trial = storage / 'records/context_pilot' / run_id
    appworld = storage / '.runtime/appworld/r18_probe_01'
    if trial.exists() or (appworld / 'experiments/outputs' / run_id).exists():
        raise FileExistsError('preserve original condition')
    trial.mkdir()
    config = copy.deepcopy(original)
    config['max_api_requests'] = plan['api_budget_by_task'][task_id]
    prompt, definitions = interface(arm, config)
    config.update(phase='P64', arm=arm)
    write_json(trial / 'plan.json', config); write_json(trial / 'comparison_plan.json', plan)
    catalog = NativeCatalog(tools) if arm == 'documented' else PublicNameCatalog(tools)
    bridge = session = infer = None
    started = time.monotonic(); setup = {'status': 'running'}
    reason = 'not_started'; complete = interrupted = False; api_requests = 0
    spans = {}; events = []; formatting = {}; interface_seconds = 0

    def active():
        return (not complete and not (storage / '.runtime/P64.stop').exists()
                and time.monotonic()-infer.started < config['max_wall_seconds'])

    previous_handler = signal.getsignal(signal.SIGALRM)
    def setup_timeout(*_): raise TimeoutError('fixed setup wall limit')
    try:
        signal.signal(signal.SIGALRM, setup_timeout); signal.alarm(plan['max_setup_seconds'])
        bridge = Bridge(storage / '.runtime/appworld/venv/bin/python', appworld, trial)
        init = bridge.request({'op': 'init', 'task_id': task_id, 'experiment': run_id, 'seed': config['seed']})
        if not init['ok'] or init['result'] != tasks[task_id]['public_task'] or init['result']['ground_truth_loaded']:
            raise ValueError('initial public task differs')
        initial_hashes = db_hashes(appworld / 'experiments/outputs' / run_id / 'tasks' / task_id / 'dbs')
        if initial_hashes != tasks[task_id]['initial_database_hashes']:
            raise ValueError('initial saved database bytes differ')
        write_json(trial / 'public_task.json', init['result'])
        interface_started = time.monotonic()
        session = PersistentApiPython(storage, trial / 'python_session')
        view = NativeConversation(prompt, init['result'])
        write_json(trial / 'conversation_private.json', view.messages())
        write_json(trial / 'interface_tools.json', definitions)
        interface_seconds = time.monotonic()-interface_started
        setup.update(status='matched_public_task_start', wall_seconds=interface_started-started,
                     replay_api_requests=0, future_receipts_supplied=0,
                     initial_database_hashes=initial_hashes)
        write_json(trial / 'setup.json', setup)
        signal.alarm(0); signal.signal(signal.SIGALRM, previous_handler)
        infer = OrdinaryInference(config, trial); infer.started -= interface_seconds
        while not complete:
            if (storage / '.runtime/P64.stop').exists(): raise InterruptedError('explicit P64 stop')
            if api_requests >= config['max_api_requests']: raise BudgetStop('api_request_limit')
            messages, formatting = view.for_model(config['observation_page_characters'])
            message = infer.call(messages, definitions)
            current = []; first = True; call_id = infer.calls[-1]['id']

            def record(row, display=True):
                nonlocal api_requests, complete, first
                sid = f's{len(spans)+1}'
                spans[sid] = {'id': sid, 'assistant': (message.get('content') or '') if first else '',
                    'action': row['action'], 'observation': row['observation']}
                first = False
                if display: current.append(spans[sid])
                api_requests += int(row['api_request_sent'])
                complete |= bool(row['observation'].get('declared_complete'))
                events.append({'call': call_id, 'span_id': sid, 'stage': 'model_tool' if display else 'python_api',
                    'api_request_sent': row['api_request_sent'], 'new_tools': row['new_tools'],
                    'effects_unknown': row.get('effects_unknown', False), 'declared_complete': complete})
                write_json(trial / 'events.json', events); write_json(trial / 'spans.json', spans)
                write_json(trial / 'progress.json', {'task_id': task_id, 'arm': arm, 'calls': len(infer.calls),
                    'known_tokens': infer.tokens, 'api_requests': api_requests, 'declared_complete': complete})
                return sid

            rows = execute_response(message, catalog, bridge, selected_receipts(list(spans), spans), record,
                out=trial, storage=storage, call_id=call_id,
                remaining_api=lambda: config['max_api_requests']-api_requests, may_continue=active,
                remaining_wall=lambda: config['max_wall_seconds']-(time.monotonic()-infer.started),
                program=session.run,
                read_archive=lambda sid, offset: page_span(spans, sid, offset, config['observation_page_characters']))
            view.append(message, current); write_json(trial / 'conversation_private.json', view.messages())
            if any(r.get('effects_unknown') for r in rows): raise RuntimeError('unknown API effects')
            if not session.usable: raise RuntimeError('Python session unavailable')
        reason = 'agent_declared_complete'
    except BudgetStop as error:
        reason = str(error)
    except BaseException as error:
        interrupted = isinstance(error, (InterruptedError, KeyboardInterrupt, SystemExit))
        reason = 'explicit_stop' if interrupted else 'setup_failure' if infer is None else 'runtime_error'
        if infer is None: setup['status'] = 'failed'
        write_json(trial / 'error_private.json', {'type': type(error).__name__, 'message': str(error)})
    finally:
        signal.alarm(0); signal.signal(signal.SIGALRM, previous_handler)
        elapsed = time.monotonic()-infer.started if infer else 0
        setup.setdefault('wall_seconds', time.monotonic()-started)
        for obj in (session, bridge):
            if obj is not None:
                try: obj.close()
                except BaseException as error:
                    reason = 'cleanup_error'
                    write_json(trial / 'cleanup_error_private.json', {'type': type(error).__name__})
        calls = infer.calls if infer else []
        known = [c for c in calls if c['usage_known']]
        summary = {'run_id': run_id, 'task_id': task_id, 'arm': arm, 'stop_reason': reason,
            'declared_complete': complete, 'evaluation': 'not_run', 'final_success': None,
            'finished_at': datetime.now(timezone.utc).isoformat(), 'model_calls': len(calls),
            'known_total_tokens': infer.tokens if infer else 0, 'unknown_usage_calls': len(calls)-len(known),
            'api_requests': api_requests,
            'unknown_effect_requests': sum(bool(e['effects_unknown']) and e['api_request_sent'] for e in events),
            'unknown_effect_events': sum(bool(e['effects_unknown']) for e in events),
            'setup': setup, 'interface_preparation_wall_seconds': interface_seconds,
            'wall_seconds': elapsed, 'full_wall_seconds': time.monotonic()-started,
            'history_formatting': formatting, 'python_session': session.state if session else None,
            'explicit_stop': interrupted, 'novel_method_claim': False}
        for name, value in [('usage', calls), ('events', events), ('spans', spans),
                            ('setup', setup), ('summary', summary)]:
            write_json(trial / (name + '.json'), value)
    return summary
