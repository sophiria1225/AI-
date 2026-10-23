"""P76 worker: same public/Python state, optional all-turn reasoning retention.

Derived from the frozen P71 worker. Both conditions restore persistent Python.
Historical runners stay unchanged; unknown generation is never retried.
"""
import copy
import datetime
import time

from public_name_catalog import PublicNameCatalog
from code_agent_interface import execute_response
from public_display import CODE_TOOLS
from context_preservation import page_span
from contract_comparison import FeedbackProgram
from handoff_factors import replay_environment
from reasoning_comparison import ARMS, ReasoningInference, build_condition
from native_data_compute import selected_receipts
from persistent_api_python import PersistentApiPython
from recorded_python_replay import replay_programs
from run_context_comparison import Bridge, BudgetStop, write_json


def run_branch(storage, root, plan, source_plan, tools, schemas, prepared, arm, run_id):
    boundary_call = prepared['prefix']['manifest']['state']['model_calls']
    if plan['phase'] != 'P76' or boundary_call != 8 or arm not in ARMS:
        raise ValueError('outside the fixed reasoning-history comparison')
    trial = storage/'records/context_pilot'/run_id
    if trial.exists(): raise FileExistsError('preserve every prior branch')
    appworld = storage/'.runtime/appworld/r18_probe_01'
    world = appworld/'experiments/outputs'/run_id
    if world.exists(): raise FileExistsError('preserve prior simulated world')
    trial.mkdir(parents=True)
    task_id, prefix = prepared['task_id'], prepared['prefix']
    config = copy.deepcopy(source_plan)
    for field in ('max_calls','max_total_tokens','max_wall_seconds'):
        config[field] = plan[field]
    config.update(phase=plan['phase'], seed=source_plan['seed']+boundary_call,
                  max_api_requests=source_plan['api_budget_by_task'][task_id])
    write_json(trial/'plan.json', config)
    write_json(trial/'factor_plan.json', plan)
    write_json(trial/'prefix_usage.json', prefix['usage'])
    write_json(trial/'prefix_events.json', prefix['events'])
    write_json(trial/'prefix_spans.json', prefix['spans'])
    write_json(trial/'public_task.json', prefix['public_task'])
    write_json(trial/'source_identity.json', {k:prepared[k] for k in
               ('task_id','source_run','source_sha256','boundary_manifest_sha256')})
    catalog = PublicNameCatalog(tools)
    bridge = session = infer = feedback_runtime = None
    setup_started = time.monotonic()
    setup = {'status':'running','environment_replay':{},'python_replay':None}
    reason, complete = 'not_started', False
    prefix_api = prefix['manifest']['state']['api_requests']
    suffix_api = 0
    spans, events = copy.deepcopy(prefix['spans']), []
    formatting = {}
    transfer = {}
    try:
        bridge = Bridge(storage/'.runtime/appworld/venv/bin/python', appworld, trial)
        initialized = bridge.request({'op':'init','task_id':task_id,'experiment':run_id,'seed':source_plan['seed']})
        if not initialized['ok'] or initialized['result'] != prefix['public_task'] or initialized['result']['ground_truth_loaded']:
            raise ValueError('initial public world differs')
        setup['environment_replay'] = replay_environment(prefix, catalog, bridge, world/'tasks'/task_id/'dbs',
            deadline=setup_started+plan['max_setup_seconds'], clock=time.monotonic,
            accounting=setup['environment_replay'])
        session = PersistentApiPython(storage, trial/'python_session')
        replayed = replay_programs(prepared['programs'], schemas, session, trial/'prefix_python', storage)
        setup['python_replay'] = {'programs':len(replayed),'api_requests_sent':0,
                                  'checks':replayed}
        if len(replayed)!=len(prepared['programs']) or not all(r['observable_prefix_matches'] for r in replayed):
            raise ValueError('reconstructed Python prefix differs')
        if time.monotonic()-setup_started > plan['max_setup_seconds']:
            raise TimeoutError('reconstruction exceeded setup deadline')
        setup_wall=time.monotonic()-setup_started
        conversation, transfer = build_condition(prepared, arm, storage)
        write_json(trial/'conversation_private.json', conversation.messages())
        setup.update(status='matched_observable_prefix',wall_seconds=time.monotonic()-setup_started)
        write_json(trial/'setup.json', setup)
        infer = ReasoningInference(config, trial, arm)
        feedback_runtime = FeedbackProgram(session.run, 'public_schema')
        infer.started -= transfer['transfer_wall_seconds']
        setup['wall_seconds'] = setup_wall
        write_json(trial/'setup.json', setup)
        while not complete:
            if (storage / '.runtime/P76.stop').exists():
                raise InterruptedError('explicit experiment stop')
            if prefix_api+suffix_api >= config['max_api_requests']:
                raise BudgetStop('api_request_limit')
            messages, formatting = conversation.for_model(config['observation_page_characters'])
            infer.set_environment_usage(prefix_api, suffix_api)
            message = infer.call('agent', messages, CODE_TOOLS)
            call_id = infer.calls[-1]['id']
            current_spans = []
            first = True

            def record(row, display=True):
                nonlocal suffix_api, complete, first
                sid = f's{len(spans)+1}'
                spans[sid] = {'id':sid,'assistant':(message.get('content') or '') if first else '',
                              'action':row['action'],'observation':row['observation']}
                first = False
                if display: current_spans.append(spans[sid])
                suffix_api += int(row['api_request_sent'])
                complete |= bool(row['observation'].get('declared_complete'))
                events.append({'call':call_id,'span_id':sid,'stage':'model_tool' if display else 'python_api',
                               'api_request_sent':row['api_request_sent'],'new_tools':row['new_tools'],
                               'effects_unknown':row.get('effects_unknown',False),'declared_complete':complete})
                write_json(trial/'spans.json', spans)
                write_json(trial/'events.json', events)
                write_json(trial/'progress.json', {'arm':arm,'task_id':task_id,'calls':len(infer.calls),
                    'tokens':infer.tokens,'api_requests':suffix_api,'prefix_api_requests':prefix_api,
                    'unknown_usage_calls':sum(c['status']!='ok' for c in infer.calls)})
                return sid

            rows = execute_response(message, catalog, bridge, selected_receipts(list(spans),spans), record,
                out=trial,storage=storage,call_id=call_id,
                remaining_api=lambda:config['max_api_requests']-prefix_api-suffix_api,
                may_continue=lambda:time.monotonic()-infer.started<config['max_wall_seconds'] and not complete,
                remaining_wall=lambda:config['max_wall_seconds']-(time.monotonic()-infer.started),
                program=feedback_runtime,
                read_archive=lambda sid,offset:page_span(spans,sid,offset,config['observation_page_characters']))
            conversation.append(message,current_spans)
            write_json(trial/'conversation_private.json', conversation.messages())
            if any(r.get('effects_unknown') for r in rows):
                raise RuntimeError('unknown API effect; no retry')
            if not session.usable or any(r['observation'].get('status')=='harness_error' for r in rows):
                raise RuntimeError('interpreter unavailable; no retry')
        reason = 'agent_declared_complete'
    except BudgetStop as error:
        reason = str(error)
    except Exception as error:
        reason = 'setup_failure' if infer is None else 'runtime_error'
        if (infer is not None and infer.calls and infer.calls[-1]['status'] != 'ok'
                and str(error) == 'model failure; usage unknown, no free retry'):
            reason = 'model_usage_unknown'
        if infer is None: setup['status']='failed'
        write_json(trial/'error_private.json',{'type':type(error).__name__,'message':str(error)})
    finally:
        continuation_seconds = time.monotonic()-infer.started if infer else 0
        setup.setdefault('wall_seconds',time.monotonic()-setup_started)
        for resource in (session,bridge):
            if resource is not None:
                try: resource.close()
                except Exception as error:
                    reason = 'cleanup_error'
                    write_json(trial/'cleanup_error.json',{'type':type(error).__name__})
        calls = infer.calls if infer else []
        known = [c for c in calls if c['status']=='ok']
        write_json(trial/'usage.json',calls)
        write_json(trial/'spans.json',spans)
        write_json(trial/'events.json',events)
        write_json(trial/'setup.json',setup)
        summary = {'run_id':run_id,'task_id':task_id,'arm':arm,'stop_reason':reason,
            'declared_complete':complete,'evaluation':'not_run','final_success':None,
            'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'model_calls':len(calls),'known_total_tokens':infer.tokens if infer else 0,
            'unknown_usage_calls':len(calls)-len(known),
            'usage_by_role':{'agent':{'calls':len(calls),'unknown_usage':len(calls)-len(known),
               'input_tokens':sum(c['input_tokens'] for c in known),'output_tokens':sum(c['output_tokens'] for c in known)}},
            'api_requests':suffix_api,'prefix_api_requests':prefix_api,
            'total_task_api_requests':prefix_api+suffix_api,
            'setup':setup,'transfer':transfer,'wall_seconds':continuation_seconds,
            'full_wall_seconds':time.monotonic()-setup_started,
            'unknown_effect_requests':sum(e['effects_unknown'] for e in events),
            'history_formatting':formatting,'python_session':session.state if session else None,
            'full_process_equivalence_claim':False, 'catalog_policy': 'public_names', 'history_policy': arm}
        if feedback_runtime is not None:summary['contract_feedback']=feedback_runtime.summary()
        write_json(trial/'summary.json',summary)
    return summary

