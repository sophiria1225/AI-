"""Frozen twelve-cell output-view comparison, with separately charged setup."""
import argparse
import datetime
import json
from pathlib import Path
import signal
import subprocess
import time
import urllib.request

from appworld_native_tools import NativeCatalog
from code_agent_interface import CODE_TOOLS
from handoff_factors import replay_environment
from handoff_output_views import ARMS, build_view
from later_handoff_sources import prepare_later_sources
from local_llama import count_input
from model_provenance import check_live_model
from persistent_api_python import PersistentApiPython
from recorded_python_replay import replay_programs
from run_context_comparison import Bridge, write_json
from run_handoff_factors import ROOT, read, sha, run_branch


def sources(storage, root):
    prior, source_plan, tools, schemas, prepared = prepare_later_sources(storage, root)
    plan = read(root/'configs/P33_output_views_v01.json')
    if plan['phase']!='P33' or plan['arms']!=list(ARMS):
        raise ValueError('wrong output-view plan')
    for key in ('source_plan','source_runs','boundary_after_model_calls','max_calls',
                'max_total_tokens','max_wall_seconds','max_setup_seconds','recent_complete_turns'):
        if plan[key]!=prior[key]:raise ValueError('source or budget changed: '+key)
    completed=read(root/'reports/P32_comparison.json')
    if not completed['all_sixteen_reviewed'] or completed['audit_errors']:
        raise ValueError('P32 cohort not closed')
    return plan, source_plan, tools, schemas, prepared


def model_ready(storage, source_plan):
    runtime=read(storage/'.runtime/model_server.json')
    base=source_plan['model']['base_url']
    with urllib.request.urlopen(base+'/props',timeout=10) as response:props=json.load(response)
    check_live_model(source_plan['model_selection'],runtime,props,root=storage,
                     expected_ctx=source_plan['model']['num_ctx'],expected_cache=('q8_0','q8_0'))
    with urllib.request.urlopen(base+'/slots',timeout=10) as response:slots=json.load(response)
    if len(slots)!=1 or any(s.get('is_processing') for s in slots):
        raise ValueError('require the idle single inference slot')
    return {'model_revision':runtime['model_revision'],'runtime':runtime['runtime'],
            'ctx_size':runtime['ctx_size'],'started_at':runtime['started_at']}


def frozen_hashes(root):
    paths=list((root/'scripts').glob('*.py'))
    paths += [root/n for n in ('configs/P33_output_views_v01.json',
        'configs/P29_stateful_code_v01.json','configs/python_export_image_v01.json',
        'reports/P32_comparison.json','reports/P30_recorded_replay.json')]
    return {str(p.relative_to(root)):sha(p) for p in sorted(paths)}


def preflight(storage, root):
    plan, source_plan, tools, schemas, prepared=sources(storage,root)
    identity=model_ready(storage,source_plan)
    output=storage/'records/context_pilot/P33_preflight_v01'
    target=root/'reports/P33_prefix_checks.json'
    if output.exists() or target.exists():raise FileExistsError('preserve preflight')
    output.mkdir(parents=True);rows=[];started=time.monotonic()
    appworld=storage/'.runtime/appworld/r18_probe_01'
    for number,item in enumerate(prepared,1):
        rid=f'P33_PREFIX_V01_{number:02d}';out=output/rid;out.mkdir()
        prefix=item['prefix'];task=item['task_id'];world=appworld/'experiments/outputs'/rid
        if world.exists():raise FileExistsError('preserve simulated world')
        bridge=session=None;at=time.monotonic()
        row={'source_run':item['source_run'],'boundary_manifest_sha256':item['boundary_manifest_sha256'],
             'status':'not_started','environment':{},'views':{}}
        try:
            bridge=Bridge(storage/'.runtime/appworld/venv/bin/python',appworld,out)
            initial=bridge.request({'op':'init','task_id':task,'experiment':rid,'seed':source_plan['seed']})
            if not initial['ok'] or initial['result']!=prefix['public_task'] or initial['result']['ground_truth_loaded']:
                raise ValueError('initial public state differs')
            catalog=NativeCatalog(tools)
            replay_environment(prefix,catalog,bridge,world/'tasks'/task/'dbs',
                deadline=at+plan['max_setup_seconds'],clock=time.monotonic,accounting=row['environment'])
            session=PersistentApiPython(storage,out/'python_session')
            replayed=replay_programs(item['programs'],schemas,session,out/'programs',storage)
            if len(replayed)!=len(item['programs']) or not all(x['observable_prefix_matches'] for x in replayed):
                raise ValueError('Python prefix differs')
            row['replayed_programs']=len(replayed)
            cfg={**source_plan['model'],'temperature':source_plan['agent_temperature'],
                 'seed':source_plan['seed']+8,'num_predict':source_plan['max_output_tokens']}
            for arm in ARMS:
                view,meta=build_view(prefix,arm,session,storage,out,schemas,catalog)
                messages,formatting=view.for_model(source_plan['observation_page_characters'])
                count=count_input(cfg,messages,CODE_TOOLS)
                if count['input_tokens']+cfg['num_predict']>min(cfg['num_ctx'],plan['max_total_tokens']):
                    raise ValueError('initial view does not fit existing context/budget')
                write_json(out/(arm+'_private.json'),messages)
                row['views'][arm]={'input_tokens':count['input_tokens'],
                    'masked_span_count':meta['masked_span_count'],
                    'removed_observation_characters':sum(c['serialized_observation_characters_removed'] for c in meta['masked_spans']),
                    'inventory_measurement':meta.get('inventory_measurement'),
                    'input_sha256':sha(out/(arm+'_private.json'))}
            row['status']='matched_observable_prefix'
        except Exception as exc:
            row.update(status='failed',error_type=type(exc).__name__)
            (out/'error_private.txt').write_text(str(exc))
        finally:
            for resource in (session,bridge):
                if resource:
                    try:resource.close()
                    except Exception as exc:row.update(status='cleanup_error',error_type=type(exc).__name__)
            row['container_removed']=session.state['container_removed'] if session else None
            row['wall_seconds']=time.monotonic()-at
            rows.append(row);write_json(out/'summary.json',row)
    result={'phase':'P33_preflight','rows':rows,'all_four_attempted':len(rows)==4,
            'all_observable_prefixes_match':len(rows)==4 and all(r['status']=='matched_observable_prefix' for r in rows),
            'model_identity':identity,'model_calls':0,'evaluator_invocations':0,
            'setup_api_requests':sum(r['environment'].get('api_requests',0) for r in rows),
            'input_count_requests':sum(len(r['views']) for r in rows),'wall_seconds':time.monotonic()-started,
            'source_hashes':frozen_hashes(root),'actual_savings_or_quality_claim':False}
    write_json(output/'summary.json',result);write_json(target,result)
    print(json.dumps({k:result[k] for k in ('all_observable_prefixes_match','setup_api_requests','input_count_requests','wall_seconds')}))
    return 0 if result['all_observable_prefixes_match'] else 1


def activate(root):
    checked=read(root/'reports/P33_prefix_checks.json')
    if not checked['all_observable_prefixes_match'] or checked['source_hashes']!=frozen_hashes(root):
        raise ValueError('preflight did not pass for current sources')
    target=root/'reports/P33_activation_v01.json'
    if target.exists():raise FileExistsError('preserve activation')
    write_json(target,{'phase':'P33','source_hashes':frozen_hashes(root),
        'preflight_sha256':sha(root/'reports/P33_prefix_checks.json'),
        'source_boundaries':[r['boundary_manifest_sha256'] for r in checked['rows']],
        'all_twelve_conditions_frozen_before_inference':True})


def publish_status(status, output):
    from watch_pro_comparison import gh_api
    marker='<!-- harness-output-views:P33_batch_v01 -->';issue=168
    lines=[marker,'P33：操作を残した出力省略と状態一覧の比較',
           f"状態: {status['status']} / 完了 {len(status['completed'])}/12 / 実行中 {status['active'] or 'なし'}",'',
           '| 課題 | 条件 | 成功 | 生成 | 既知token | API |','|---|---|---:|---:|---:|---:|']
    for r in status['rows']:
        lines.append(f"| {r['task_id']} | {r['arm']} | {r.get('success','未評価')} | {r['model_calls']} | {r['known_total_tokens']} | {r['api_requests']} |")
    lines+=['','全４既知課題×３条件。全件終了前に優劣を確定しない。入力一覧・整形も課金し、復元は別枠で記録。',
            '出力省略と状態一覧は通常対照。新規性・性能維持・一般化は未確立。']
    body='\n'.join(lines);(output/'progress.md').write_text(body+'\n')
    try:
        if status.get('comment_id'):
            endpoint=f"repos/sophiria1225/AI-/issues/comments/{int(status['comment_id'])}"
            old=gh_api(endpoint)
            if not old.get('body','').startswith(marker) or old.get('issue_url')!=f'https://api.github.com/repos/sophiria1225/AI-/issues/{issue}':
                raise ValueError('progress destination differs')
            result=gh_api(endpoint,method='PATCH',payload={'body':body})
        else:result=gh_api(f'repos/sophiria1225/AI-/issues/{issue}/comments',method='POST',payload={'body':body})
        status.update(comment_id=result['id'],comment_url=result['html_url']);status.pop('publish_error',None)
    except Exception as exc:status['publish_error']=type(exc).__name__


def run(storage, root, publish=False):
    plan,source_plan,tools,schemas,prepared=sources(storage,root)
    frozen=read(root/'reports/P33_activation_v01.json')
    if (frozen['source_hashes']!=frozen_hashes(root)
            or frozen['preflight_sha256']!=sha(root/'reports/P33_prefix_checks.json')
            or frozen['source_boundaries']!=[p['boundary_manifest_sha256'] for p in prepared]):
        raise ValueError('frozen experiment changed')
    identity=model_ready(storage,source_plan)
    output=storage/'records/context_pilot'/plan['batch_id'];output.mkdir(parents=True,exist_ok=False)
    write_json(output/'frozen_plan.json',plan);write_json(output/'activation.json',frozen)
    status={'phase':'P33','status':'running','rows':[],'completed':[],'active':None,
        'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'model_identity':identity,
        'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()}
    def save():
        status['updated_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        if publish:publish_status(status,output)
        write_json(output/'status.json',status)
    for number,item in enumerate(prepared,1):
        offset=(number-1)%len(ARMS)
        for arm in ARMS[offset:]+ARMS[:offset]:
            rid=f'P33_{number:02d}_{arm.upper()}';status['active']=rid;save()
            result=run_branch(storage,root,plan,source_plan,tools,schemas,item,arm,rid)
            row={k:result[k] for k in ('run_id','task_id','arm','stop_reason','model_calls',
                'known_total_tokens','unknown_usage_calls','api_requests','prefix_api_requests','wall_seconds')}
            if result['setup']['status']!='matched_observable_prefix':
                status['rows'].append(row);status.update(status='stopped_setup_mismatch',active=None);save();return 1
            evaluation=subprocess.run([str(storage/'.runtime/appworld/venv/bin/python'),
                str(root/'scripts/evaluate_context_trial.py'),'--appworld-root',str(storage/'.runtime/appworld/r18_probe_01'),
                '--trial',str(storage/'records/context_pilot'/rid)],capture_output=True,text=True,timeout=180)
            (output/(rid+'_evaluation.log')).write_text(evaluation.stdout+evaluation.stderr)
            if evaluation.returncode:
                status['rows'].append(row);status.update(status='stopped_evaluation_error',active=None);save();return 1
            row['success']=read(storage/'records/context_pilot'/rid/'evaluation.json')['official_success']
            status['rows'].append(row);status['completed'].append(rid);save()
            print(json.dumps(row),flush=True)
    status.update(status='complete',active=None,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat());save()
    return 0


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--repo-root',type=Path,default=ROOT);p.add_argument('--publish',action='store_true')
    p.add_argument('--phase',choices=('P33',),default='P33')
    p.add_argument('--preflight',action='store_true');p.add_argument('--activate',action='store_true');a=p.parse_args()
    def timeout(*_):raise TimeoutError('bounded local inference timeout')
    signal.signal(signal.SIGALRM,timeout)
    if a.preflight:raise SystemExit(preflight(a.storage_root,a.repo_root))
    if a.activate:activate(a.repo_root)
    else:raise SystemExit(run(a.storage_root,a.repo_root,a.publish))
