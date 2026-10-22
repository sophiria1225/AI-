"""Execute each P61 ordinary interface once on the same public boundary."""
import copy
from datetime import datetime, timezone
import signal
import time

from appworld_native_tools import NativeCatalog, dispatch_native_calls
from code_agent_interface import CODE_TOOLS, execute_response
from context_preservation import page_span
from native_data_compute import selected_receipts
from ordinary_continuation import ARMS, OrdinaryInference, conversation
from persistent_api_python import PersistentApiPython
from probe_prefix_replay import db_hashes
from recorded_python_replay import canonical
from run_context_comparison import Bridge, BudgetStop, write_json


def replay(prefix, catalog, bridge, db_directory, account):
    account.update(api_requests=0, observation_matches=0, unknown_effect_requests=0, db_files_match=False)
    for event in prefix['events']:
        if not event['api_request_sent']: continue
        span = prefix['spans'][event['span_id']]
        decoded = catalog.decode(span['action'])
        account['api_requests'] += 1
        try: response = bridge.request({'op': 'call', 'call': decoded})
        except BaseException:
            account['unknown_effect_requests'] += 1
            raise
        value = response['result'] if response['ok'] else {'api_error': response['error']}
        exposed = catalog.expose_requested_document(decoded) if response['ok'] else []
        if canonical(value) != canonical(span['observation']) or exposed != event['new_tools']:
            raise ValueError('replayed public response or discovery differs')
        account['observation_matches'] += 1
    expected = {n: v['sha256'] for n, v in prefix['manifest']['files'].items() if n.startswith('dbs/')}
    actual = db_hashes(db_directory)
    if actual != expected or sorted(catalog.visible) != prefix['manifest']['state']['visible_api_schemas']:
        raise ValueError('replayed DB bytes or public schema set differs')
    account.update(db_files_match=True, db_files=len(actual))


def run_branch(storage, plan, original, prefix, tools, arm, run_id):
    if arm not in ARMS or run_id != plan['run_ids'][ARMS.index(arm)]:
        raise ValueError('outside fixed two-condition order')
    trial = storage / 'records/context_pilot' / run_id
    appworld = storage / '.runtime/appworld/r18_probe_01'
    world = appworld / 'experiments/outputs' / run_id
    if trial.exists() or world.exists(): raise FileExistsError('preserve prior condition')
    trial.mkdir()
    config = copy.deepcopy(original)
    for name in ('max_calls', 'max_total_tokens', 'max_wall_seconds', 'max_output_tokens'):
        config[name] = plan[name]
    config.update(phase='P61', seed=plan['continuation_seed'], max_api_requests=80)
    write_json(trial / 'plan.json', config); write_json(trial / 'comparison_plan.json', plan)
    for name in ('public_task', 'usage', 'events', 'spans'):
        write_json(trial / ('public_task.json' if name == 'public_task' else 'prefix_' + name + '.json'), prefix[name])
    catalog = NativeCatalog(tools)
    bridge = session = infer = None
    started = time.monotonic(); setup = {'status': 'running', 'environment_replay': {}}
    reason = 'not_started'; complete = False; interrupted = False; suffix_api = 0
    spans = copy.deepcopy(prefix['spans']); events = []; formatting = {}; interface_seconds = 0

    def active():
        return (not complete and not (storage / '.runtime/P61.stop').exists()
                and time.monotonic()-infer.started < config['max_wall_seconds'])

    previous_handler = signal.getsignal(signal.SIGALRM)
    def setup_timeout(*_): raise TimeoutError('fixed setup wall limit')
    try:
        signal.signal(signal.SIGALRM, setup_timeout); signal.alarm(plan['max_setup_seconds'])
        bridge = Bridge(storage / '.runtime/appworld/venv/bin/python', appworld, trial)
        init = bridge.request({'op': 'init', 'task_id': plan['task_id'], 'experiment': run_id, 'seed': original['seed']})
        if not init['ok'] or init['result'] != prefix['public_task'] or init['result']['ground_truth_loaded']:
            raise ValueError('initial public world differs')
        replay(prefix, catalog, bridge, world / 'tasks' / plan['task_id'] / 'dbs', setup['environment_replay'])
        interface_started = time.monotonic()
        if arm == 'python': session = PersistentApiPython(storage, trial / 'python_session')
        view = conversation(prefix, arm)
        write_json(trial / 'conversation_private.json', view.messages())
        interface_seconds = time.monotonic()-interface_started
        setup.update(status='matched_observable_prefix', wall_seconds=interface_started-started)
        write_json(trial / 'setup.json', setup)
        signal.alarm(0); signal.signal(signal.SIGALRM, previous_handler)
        infer = OrdinaryInference(config, trial)
        infer.started -= interface_seconds
        while not complete:
            if (storage / '.runtime/P61.stop').exists(): raise InterruptedError('explicit P61 stop')
            if suffix_api >= 60: raise BudgetStop('api_request_limit')
            messages, formatting = view.for_model(config['observation_page_characters'])
            message = infer.call(messages, catalog.tools() if arm == 'native' else CODE_TOOLS)
            current = []; first = True; call_id = infer.calls[-1]['id']

            def record(row, display=True):
                nonlocal suffix_api, complete, first
                sid = f's{len(spans)+1}'
                spans[sid] = {'id': sid, 'assistant': (message.get('content') or '') if first else '',
                    'action': row['action'], 'observation': row['observation']}
                first = False
                if display: current.append(spans[sid])
                suffix_api += int(row['api_request_sent'])
                complete |= bool(row['observation'].get('declared_complete'))
                events.append({'call': call_id, 'span_id': sid, 'stage': 'model_tool' if display else 'python_api',
                    'api_request_sent': row['api_request_sent'], 'new_tools': row['new_tools'],
                    'effects_unknown': row.get('effects_unknown', False), 'declared_complete': complete})
                write_json(trial / 'events.json', events); write_json(trial / 'spans.json', spans)
                write_json(trial / 'progress.json', {'arm': arm, 'calls': len(infer.calls),
                    'known_tokens': infer.tokens, 'api_requests': suffix_api, 'declared_complete': complete})
                return sid

            archive = lambda sid, offset: page_span(spans, sid, offset, config['observation_page_characters'])
            if arm == 'native':
                rows = dispatch_native_calls(message, catalog, bridge, archive,
                    remaining_api_calls=60-suffix_api, may_continue=active, on_record=record)
            else:
                rows = execute_response(message, catalog, bridge, selected_receipts(list(spans), spans), record,
                    out=trial, storage=storage, call_id=call_id, remaining_api=lambda: 60-suffix_api,
                    may_continue=active, remaining_wall=lambda: config['max_wall_seconds']-(time.monotonic()-infer.started),
                    program=session.run, read_archive=archive)
            view.append(message, current); write_json(trial / 'conversation_private.json', view.messages())
            if any(r.get('effects_unknown') for r in rows): raise RuntimeError('unknown API effects')
            if session is not None and not session.usable: raise RuntimeError('Python session unavailable')
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
                    reason = 'cleanup_error'; write_json(trial / 'cleanup_error.json', {'type': type(error).__name__})
        calls = infer.calls if infer else []
        known = [c for c in calls if c['usage_known']]
        summary = {'run_id': run_id, 'task_id': plan['task_id'], 'arm': arm, 'stop_reason': reason,
            'declared_complete': complete, 'evaluation': 'not_run', 'final_success': None,
            'finished_at': datetime.now(timezone.utc).isoformat(), 'model_calls': len(calls),
            'known_total_tokens': infer.tokens if infer else 0, 'unknown_usage_calls': len(calls)-len(known),
            'prefix_model_calls': 12, 'prefix_known_total_tokens': 252602,
            'whole_task_known_tokens': 252602+(infer.tokens if infer else 0),
            'prefix_wall_seconds': prefix['manifest']['state']['elapsed_wall_seconds'],
            'interface_preparation_wall_seconds': interface_seconds,
            'whole_task_wall_seconds': prefix['manifest']['state']['elapsed_wall_seconds']+elapsed,
            'api_requests': suffix_api, 'prefix_api_requests': 20, 'total_task_api_requests': 20+suffix_api,
            'additional_contact_searches': sum(e['api_request_sent'] and spans[e['span_id']]['action']['name'] == 'phone__search_contacts' for e in events),
            'unknown_effect_requests': sum(bool(e['effects_unknown']) for e in events),
            'setup': setup, 'wall_seconds': elapsed, 'full_wall_seconds': time.monotonic()-started,
            'history_formatting': formatting, 'python_session': session.state if session else None,
            'explicit_stop': interrupted, 'full_process_equivalence_claim': False, 'novel_method_claim': False}
        write_json(trial / 'usage.json', calls); write_json(trial / 'events.json', events)
        write_json(trial / 'spans.json', spans); write_json(trial / 'setup.json', setup)
        write_json(trial / 'summary.json', summary)
    return summary
