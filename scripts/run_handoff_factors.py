"""One-time 2 x 2 continuation probe on four fixed development prefixes.

The reconstruction and continuation accounts remain separate. This script never
uses independent evaluation to choose a state, condition or final artifact.
"""
import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time
import urllib.request

from appworld_native_tools import NativeCatalog
from code_agent_interface import CODE_TOOLS, execute_response
from context_preservation import page_span
from handoff_factors import ARMS, BOUNDARY_CALL, handoff_conversation, prefix_at_fixed_boundary, replay_environment
from inspect_appworld_api_schemas import load_public_tools
from model_provenance import check_live_model
from native_data_compute import selected_receipts
from persistent_api_python import PersistentApiPython
from recorded_python_replay import load_programs, replay_programs
from run_context_comparison import Bridge, BudgetStop, Inference, write_json
from run_recorded_replay import check_ready

ROOT = Path(__file__).resolve().parents[1]


def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_sources(storage, root):
    source_plan = check_ready(storage, root)
    plan = read(root/'configs/P31_handoff_factors_v01.json')
    if (plan['source_runs'] != [r[2] for r in source_plan['run_order']]
            or plan['arms'] != list(ARMS) or plan['boundary_after_model_calls'] != BOUNDARY_CALL
            or plan['recent_complete_turns'] != 1):
        raise ValueError('outside the fixed development factorial plan')
    replay = read(root/'reports/P30_recorded_replay.json')
    if (not replay['all_four_attempted'] or not replay['all_observable_prefixes_match']
            or replay['source_sha256']['P29_comparison'] != sha(root/'reports/P29_comparison.json')):
        raise ValueError('complete P30 correspondence has not been established')
    tools, schema_hashes, _ = load_public_tools(storage/'.runtime/appworld/r18_probe_01/data')
    schemas = {t['function']['name']: t['function'] for t in tools}
    prepared = []
    for task, _, run_id in source_plan['run_order']:
        trial = storage/'records/context_pilot'/run_id
        provenance = read(trial/'provenance.json')
        if provenance['public_schema_hashes'] != schema_hashes:
            raise ValueError('public schemas changed')
        for name, digest in provenance['sources'].items():
            if sha(root/'scripts'/name) != digest:
                raise ValueError('original execution adapter changed: '+name)
        spec = storage/'.runtime/appworld/r18_probe_01/data/tasks'/task/'specs.json'
        if sha(spec) != provenance['spec_sha256']:
            raise ValueError('original task specification changed')
        prefix = prefix_at_fixed_boundary(trial)
        prefix_call_ids = {c['id'] for c in prefix['usage']}
        programs = [p for p in load_programs(trial, schemas)
                    if p['name'].rsplit('_', 1)[0] in prefix_call_ids]
        if not programs:
            raise ValueError('fixed boundary has no Python work state')
        if sum(len(p['entries']) for p in programs) != sum(
                e['stage']=='python_api' for e in prefix['events']):
            raise ValueError('Python prefix does not cover original API receipts')
        # Check all four history interventions before any continuation inference.
        for arm in ARMS:
            handoff_conversation(prefix['conversation_private'], prefix['public_task'], arm)
        prepared.append({'task_id':task, 'source_run':run_id, 'prefix':prefix, 'programs':programs,
                         'source_sha256':{n:sha(trial/n) for n in
                            ('events.json','spans.json','summary.json','provenance.json','plan.json')},
                         'boundary_manifest_sha256':sha(trial/'boundaries/manifests'/f'call_{BOUNDARY_CALL:03d}.json')})
    return plan, source_plan, tools, schemas, prepared


def run_branch(storage, root, plan, source_plan, tools, schemas, prepared, arm, run_id):
    boundary_call=prepared['prefix']['manifest']['state']['model_calls']
    if plan['phase'] not in ('P31','P32','P33','P38','P40','P45') or boundary_call!=plan['boundary_after_model_calls']:
        raise ValueError('wrong prespecified boundary or phase')
    if plan['phase']=='P33':
        from handoff_output_views import ARMS as VIEW_ARMS
        if arm not in VIEW_ARMS or boundary_call!=8:
            raise ValueError('outside output-view comparison')
    if plan['phase']=='P38':
        from projected_read_runtime import ARMS as READ_ARMS
        if arm not in READ_ARMS or boundary_call!=8 or prepared['source_run']!='P29_04_CODE':
            raise ValueError('outside fixed field-read mechanism check')
    if plan['phase']=='P40':
        from budget_signal import ARMS as BUDGET_ARMS
        if arm not in BUDGET_ARMS or boundary_call!=8:
            raise ValueError('outside fixed budget-notification comparison')
    if plan['phase']=='P45':
        from documentation_comparison import ARMS as DOC_ARMS
        if arm not in DOC_ARMS or boundary_call!=8:
            raise ValueError('outside fixed documentation-display comparison')
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
    catalog = NativeCatalog(tools)
    bridge = session = infer = field_runtime = None
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
        if arm.endswith('_keep'):
            replayed = replay_programs(prepared['programs'], schemas, session, trial/'prefix_python', storage)
            setup['python_replay'] = {'programs':len(replayed),'api_requests_sent':0,
                                      'checks':replayed}
            if len(replayed)!=len(prepared['programs']) or not all(r['observable_prefix_matches'] for r in replayed):
                raise ValueError('reconstructed Python prefix differs')
        if time.monotonic()-setup_started > plan['max_setup_seconds']:
            raise TimeoutError('reconstruction exceeded setup deadline')
        setup_wall=time.monotonic()-setup_started
        if plan['phase']=='P33':
            from handoff_output_views import build_view
            conversation,transfer=build_view(prefix,arm,session,storage,trial,schemas,catalog)
        elif plan['phase']=='P38':
            from field_read_contract import verify_public_implementation
            from projected_read_runtime import ProjectedReadRuntime, make_conversation
            transfer_started=time.monotonic()
            verified=verify_public_implementation(storage/'.runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps/spotify')
            field_runtime=ProjectedReadRuntime(arm.removesuffix('_keep'),execution_scope=run_id,verified_contract=verified)
            field_runtime.seed(prefix['events'],prefix['spans'])
            field_runtime.install(session,storage,trial/'field_helper_install',catalog)
            conversation=make_conversation(prefix)
            transfer={'transfer_wall_seconds':time.monotonic()-transfer_started,
                      'field_read_mode':field_runtime.cache.mode,'original_api_semantics_unchanged':True}
        elif plan['phase']=='P40':
            conversation, transfer = handoff_conversation(prefix['conversation_private'], prefix['public_task'], 'full_keep', boundary_call)
        elif plan['phase']=='P45':
            from documentation_comparison import build_condition
            conversation, transfer = build_condition(prepared, arm)
        else:
            conversation, transfer = handoff_conversation(prefix['conversation_private'], prefix['public_task'], arm,boundary_call)
        write_json(trial/'conversation_private.json', conversation.messages())
        setup.update(status='matched_observable_prefix',wall_seconds=time.monotonic()-setup_started)
        write_json(trial/'setup.json', setup)
        if plan['phase']=='P40':
            from budget_signal import BudgetInference
            infer = BudgetInference(config, trial, arm)
        elif plan['phase']=='P45':
            from documentation_comparison import OriginBudgetInference
            infer = OriginBudgetInference(config, trial, arm)
        else:
            infer = Inference(config, trial)
        if plan['phase'] in ('P33','P38','P45'):
            # Inspection is real controller work, charged to the continuation
            # wall budget. Reconstruction remains separate experimental setup.
            infer.started-=transfer['transfer_wall_seconds']
            setup['wall_seconds']=setup_wall
            write_json(trial/'setup.json',setup)
        while not complete:
            if plan['phase']=='P45' and (storage/'.runtime/P45.stop').exists():
                raise InterruptedError('explicit P45 stop')
            if prefix_api+suffix_api >= config['max_api_requests']:
                raise BudgetStop('api_request_limit')
            messages, formatting = conversation.for_model(config['observation_page_characters'])
            if plan['phase'] in ('P40','P45'):
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
                program=field_runtime.program(session) if field_runtime else session.run,
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
            'full_process_equivalence_claim':False}
        if field_runtime is not None:summary['projected_reads']=field_runtime.summary()
        write_json(trial/'summary.json',summary)
    return summary


def publish_status(status,output):
    from watch_pro_comparison import gh_api
    phase=status['phase']
    issue_number={'P31':145,'P32':150}[phase]
    marker=f'<!-- harness-handoff-factor:{phase}_batch_v01 -->'
    lines=[marker,f'{phase}：会話履歴 × Python作業状態の固定地点比較',
           '',f"状態: {status['status']} / 完了 {len(status['completed'])}/16 / 実行中 {status['active'] or 'なし'}",'',
           '| 課題番号 | 条件 | 最終成功 | 後続生成 | 既知token | 後続API |',
           '|---|---|---:|---:|---:|---:|']
    for row in status['rows']:
        lines.append(f"| {row['run_id'].split('_')[1]} | {row['arm']} | {row.get('success','未評価')} | {row['model_calls']} | {row['known_total_tokens']:,} | {row['api_requests']} |")
    lines+=['','共通前半・環境再構成の費用は別に全件記録。全16件の監査前に効果を確定しない。',
            f"既知４課題・１seed・{status['boundary_after_model_calls']}応答後。完全プロセス復元／新規方式／再編の有効性の証明ではない。"]
    body='\n'.join(lines)
    (output/'progress.md').write_text(body+'\n')
    try:
        if status.get('comment_id'):
            endpoint=f"repos/sophiria1225/AI-/issues/comments/{int(status['comment_id'])}"
            old=gh_api(endpoint)
            if (not old.get('body','').startswith(marker)
                    or old.get('issue_url')!=f'https://api.github.com/repos/sophiria1225/AI-/issues/{issue_number}'):
                raise ValueError('progress destination differs')
            result=gh_api(endpoint,method='PATCH',payload={'body':body})
        else:
            issue=gh_api(f'repos/sophiria1225/AI-/issues/{issue_number}')
            if issue['html_url']!=f'https://github.com/sophiria1225/AI-/issues/{issue_number}':
                raise ValueError('Issue identity differs')
            result=gh_api(f'repos/sophiria1225/AI-/issues/{issue_number}/comments',method='POST',payload={'body':body})
        status.update(comment_id=result['id'],comment_url=result['html_url'])
        status.pop('publish_error',None)
    except Exception as exc:
        status['publish_error']=type(exc).__name__


def run(storage, root, publish=False, phase='P31'):
    if phase=='P31':
        plan, source_plan, tools, schemas, prepared = prepare_sources(storage,root)
    elif phase=='P32':
        from later_handoff_sources import prepare_later_sources
        previous=read(root/'reports/P31_comparison.json')
        if not previous['all_sixteen_reviewed'] or previous['audit_errors']:
            raise ValueError('wait for the whole P31 review')
        plan, source_plan, tools, schemas, prepared = prepare_later_sources(storage,root)
    else:raise ValueError('unknown phase')
    checked=read(root/f'reports/{phase}_prefix_checks.json')
    if not checked['all_four_attempted'] or not checked['all_observable_prefixes_match']:
        raise ValueError('all four fixed-prefix preflights must pass')
    for name,digest in checked['source_hashes'].items():
        if sha(root/name)!=digest:raise ValueError('preflight source changed')
    freeze = read(root/f'reports/{phase}_activation_v01.json')
    for name,digest in freeze['source_hashes'].items():
        if sha(root/name)!=digest: raise ValueError('frozen implementation or plan changed')
    if freeze['source_boundaries'] != [p['boundary_manifest_sha256'] for p in prepared]:
        raise ValueError('frozen prefix selection changed')
    runtime = read(storage/'.runtime/model_server.json')
    with urllib.request.urlopen(source_plan['model']['base_url']+'/props',timeout=10) as response:
        props=json.load(response)
    check_live_model(source_plan['model_selection'],runtime,props,root=storage,
                     expected_ctx=source_plan['model']['num_ctx'],expected_cache=('q8_0','q8_0'))
    output=storage/'records/context_pilot'/plan['batch_id']
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'frozen_plan.json',plan)
    write_json(output/'activation.json',freeze)
    rows=[]
    status={'status':'running','phase':phase,'boundary_after_model_calls':plan['boundary_after_model_calls'],
            'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'completed':[],'rows':rows,'active':None,
            'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()}
    for number,item in enumerate(prepared,1):
        arms=list(ARMS[number-1:]+ARMS[:number-1])
        for arm in arms:
            rid=f'{phase}_{number:02d}_{arm.upper()}'
            status.update(active=rid,updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
            if publish:publish_status(status,output)
            write_json(output/'status.json',status)
            result=run_branch(storage,root,plan,source_plan,tools,schemas,item,arm,rid)
            row={k:result[k] for k in ('run_id','task_id','arm','stop_reason','model_calls','known_total_tokens',
                                      'unknown_usage_calls','api_requests','prefix_api_requests','wall_seconds')}
            if result['setup']['status']!='matched_observable_prefix':
                rows.append(row);status.update(status='stopped_setup_mismatch',active=None)
                if publish:publish_status(status,output)
                write_json(output/'status.json',status)
                return 1
            evaluation=subprocess.run([str(storage/'.runtime/appworld/venv/bin/python'),
                str(root/'scripts/evaluate_context_trial.py'),'--appworld-root',str(storage/'.runtime/appworld/r18_probe_01'),
                '--trial',str(storage/'records/context_pilot'/rid)],capture_output=True,text=True,timeout=180)
            (output/f'{rid}_evaluation.log').write_text(evaluation.stdout+evaluation.stderr)
            if evaluation.returncode:
                rows.append(row);status.update(status='stopped_evaluation_error',active=None)
                if publish:publish_status(status,output)
                write_json(output/'status.json',status);return 1
            row['success']=read(storage/'records/context_pilot'/rid/'evaluation.json')['official_success']
            rows.append(row);status['completed'].append(rid)
            write_json(output/'status.json',status)
            print(json.dumps(row),flush=True)
    status.update(status='complete',active=None,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    if publish:publish_status(status,output)
    write_json(output/'status.json',status)
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--storage-root',type=Path,required=True)
    parser.add_argument('--repo-root',type=Path,default=ROOT);parser.add_argument('--publish',action='store_true')
    parser.add_argument('--phase',choices=('P31','P32'),default='P31');args=parser.parse_args()
    def timeout(*_): raise TimeoutError('bounded local inference timeout')
    signal.signal(signal.SIGALRM,timeout)
    raise SystemExit(run(args.storage_root,args.repo_root,args.publish,args.phase))
