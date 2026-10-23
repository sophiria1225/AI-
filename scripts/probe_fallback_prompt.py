"""Six fixed offline renderings, after P81 closes; no inference or API calls."""
import argparse
from datetime import datetime,timezone
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import time

from fallback_prompt_reconstruction import IDS,interpret,sources
from inspect_input_exposure import check_resume
from probe_notice_calibration import confirmed_ci
from probe_prompt_identity import render_summary
from run_context_comparison import write_json
from run_handoff_factors import ROOT,read,sha

PLAN='configs/P83_fallback_prompt_v01.json'


class Interrupted(BaseException):pass


def interrupt(*_):raise Interrupted('explicit_P83_stop')


def closed_pipeline(storage,plan):
    folder=storage/plan['required_closed_pipeline'];status=read(folder/'status.json')
    final=read(folder/'server_final.json')
    if (status['status']!='complete' or not status.get('server_stopped') or not status.get('finished_at')
            or final['status']!='stopped' or final['supervisor_pid']!=status['server_supervisor_pid']):
        raise ValueError('P81_must_close_before_offline_reconstruction')
    for pid in (final['pid'],final['supervisor_pid']):
        try:os.kill(pid,0)
        except ProcessLookupError:continue
        raise ValueError('P81_owned_process_still_present')
    return {'status_sha256':sha(folder/'status.json'),'server_final_sha256':sha(folder/'server_final.json'),
            'owned_processes_absent':True}


def run(storage,head,ci_ids):
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=head or \
            subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
        raise ValueError('clean_fixed_execution_tree_required')
    origin=subprocess.check_output(['git','remote','get-url','origin'],cwd=ROOT,text=True).strip()
    if origin not in ('https://github.com/sophiria1225/AI-','https://github.com/sophiria1225/AI-.git'):
        raise ValueError('repository_scope_differs')
    if (storage/'.runtime/P83.stop').exists():raise Interrupted('explicit_P83_stop')
    plan=read(ROOT/PLAN);closure=closed_pipeline(storage,plan);resume=check_resume(storage)
    ci=confirmed_ci(head,ci_ids)
    build,model,command,variants,proof=sources(storage,ROOT,plan)
    folder=storage/'records/context_pilot'/plan['batch_id'];target=ROOT/'reports/P83_fallback_prompt.json'
    if folder.exists() or target.exists():raise FileExistsError('preserve_all_P83_attempts')
    folder.mkdir(parents=True)
    started=time.monotonic();process=None
    report={'phase':'P83','status':'running','git_commit':head,'ci':ci,'plan_sha256':sha(ROOT/PLAN),
        'P81_closure':closure,'research_resume':resume,'source_proof':proof,
        'started_at':datetime.now(timezone.utc).isoformat(),'rendered':{},'planned_inputs':list(IDS),
        'model_generations':0,'environment_api_requests':0,'evaluator_calls':0,
        'reserved_scenarios_read':0,'private_reasoning_inspected_semantically':False,
        'sampled_peak_rss_bytes':0,'max_wall_seconds':plan['max_wall_seconds'],
        'max_sampled_rss_bytes':plan['max_sampled_rss_bytes']}
    def save():
        report['wall_seconds']=time.monotonic()-started
        write_json(folder/'status.json',report)
    try:
        save();cases=[]
        for identity,request in variants.items():
            path=folder/(identity+'_request_private.json');write_json(path,request)
            if path.stat().st_size>plan['max_input_file_bytes']:raise ValueError('input_file_limit')
            cases.append({'id':identity,'request_path':str(path)})
        write_json(folder/'render_manifest_private.json',{'recorded_server_command':command,
            'model_path':str(model),'output_dir':str(folder),'cases':cases})
        with (folder/'renderer_private.log').open('w') as log:
            process=subprocess.Popen([str(storage/build['renderer_relative']),str(folder/'render_manifest_private.json')],
                stdout=log,stderr=log,start_new_session=True)
        report['renderer_pid']=process.pid;save()
        while process.poll() is None:
            if (storage/'.runtime/P83.stop').exists() or check_resume(storage)!=resume:raise Interrupted('explicit_P83_stop')
            if time.monotonic()-started>=plan['max_wall_seconds']:raise TimeoutError('offline_deadline')
            sample=subprocess.run(['ps','-o','rss=','-p',str(process.pid)],capture_output=True,text=True)
            if sample.returncode==0 and sample.stdout.strip():
                report['sampled_peak_rss_bytes']=max(report['sampled_peak_rss_bytes'],int(sample.stdout.strip())*1024)
                if report['sampled_peak_rss_bytes']>plan['max_sampled_rss_bytes']:raise MemoryError('offline_RSS_bound')
            time.sleep(.05)
        report['renderer_exit_code']=process.returncode
        if process.returncode:raise ValueError('renderer_failed_no_retry')
        if read(folder/'renderer_complete.json')!={'renderings':6,'decode_calls':0}:
            raise ValueError('six_renderings_required')
        meta=read(folder/'renderer_metadata_private.json')
        if (not meta['vocabulary_only'] or meta['inference_contexts_created'] or meta['decode_calls']
                or hashlib.sha256(meta['default_template'].encode()).hexdigest()!=plan['effective_template_sha256']):
            raise ValueError('vocabulary_only_or_exact_effective_template_differs')
        rendered={identity:read(folder/(identity+'_rendered_private.json')) for identity in IDS}
        if any(v['media_files'] or v['id']!=k for k,v in rendered.items()):raise ValueError('plain_text_case_identity_differs')
        for identity,value in rendered.items():
            report['rendered'][identity]={**render_summary(value),
                'private_request_sha256':sha(folder/(identity+'_request_private.json')),
                'private_rendering_sha256':sha(folder/(identity+'_rendered_private.json'))}
        report.update(interpret(rendered,proof))
        sources(storage,ROOT,plan)
        if time.monotonic()-started>=plan['max_wall_seconds']:raise TimeoutError('offline_analysis_deadline')
        report.update(status='complete',original_sources_unchanged=True,
            renderer_metadata_sha256=sha(folder/'renderer_metadata_private.json'))
    except (Exception,Interrupted) as error:
        report.update(status='stopped',error_type=type(error).__name__)
        (folder/'error_private.txt').write_text(str(error))
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
        report['renderer_exit_code']=process.returncode if process else None
        report['rendering_attempts']=sum((folder/(k+'_started.json')).exists() for k in IDS)
        report['completed_renderings']=sum((folder/(k+'_rendered_private.json')).exists() for k in IDS)
        report['finished_at']=datetime.now(timezone.utc).isoformat();save();write_json(target,report)
    print({k:report.get(k) for k in ('status','rendering_attempts','completed_renderings','wall_seconds')})
    return 0 if report['status']=='complete' else 1


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--expected-commit',required=True);p.add_argument('--ci-run-ids',nargs='+',required=True,type=int)
    a=p.parse_args();signal.signal(signal.SIGTERM,interrupt);signal.signal(signal.SIGINT,interrupt)
    raise SystemExit(run(a.storage_root.resolve(),a.expected_commit,a.ci_run_ids))
