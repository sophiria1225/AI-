"""Close P101 once using the existing report CLI after a recorded idle-watcher correction."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def report_command(python, execution_root):
    # ROOT is derived from the executed script location; this CLI has no --repo-root option.
    return [python,execution_root/'scripts/build_choice_context_report.py',
            '--output',execution_root/'materials/20261024_p101_results','--pdf']


def run(storage,execution_root,head,correction_sha):
    rt=storage/'.runtime';correction=rt/'P101_reporting_command_correction_20261025.json'
    if sha(correction)!=correction_sha:raise ValueError('fixed_correction_receipt_required')
    fixed=read(correction)
    if (fixed['executed_head']!=head or fixed['replacement_script_sha256']!=sha(Path(__file__))
            or fixed['original_watcher_stages']!=[] or fixed['original_watcher_absent'] is not True
            or fixed['generation_conditions_changed'] or fixed['generation_outcomes_read']):
        raise ValueError('recorded_idle_watcher_correction_required')
    probe=subprocess.run(['ps','-p',str(fixed['original_watcher_pid']),'-o','pid='],
                         capture_output=True,text=True,timeout=10)
    if probe.returncode!=1 or probe.stdout.strip():raise ValueError('original_watcher_still_present')
    if ((execution_root/'reports/P101_choice_context.json').exists()
            or (execution_root/'reports/P101_choice_context_audit_failure.json').exists()
            or (execution_root/'materials/20261024_p101_results').exists()):
        raise FileExistsError('never_retry_existing_P101_closure_stage')
    ops=rt/'P101_closure_operations_v02';ops.mkdir(exist_ok=False)
    (ops/'lock').write_text(str(os.getpid()))
    state=dict(status='waiting',started_at=datetime.now(timezone.utc).isoformat(),head=head,
        correction_sha256=correction_sha,stages=[],new_model_generations=0,new_API_requests=0,new_evaluations=0)
    began=time.monotonic()
    def save():
        state['wall_seconds']=time.monotonic()-began
        tmp=ops/'status.tmp';tmp.write_text(json.dumps(state,indent=2)+'\n');tmp.replace(ops/'status.json')
    def stopped():return any((rt/n).exists() for n in ('P101.stop','P101_reports.stop'))
    def command(name,argv,timeout):
        if stopped():raise InterruptedError('explicit_stop')
        start=time.monotonic();log=ops/(name+'.log');child=None
        with log.open('x') as stream:
            try:
                child=subprocess.Popen([str(a) for a in argv],cwd=execution_root,stdout=stream,
                    stderr=subprocess.STDOUT,start_new_session=True)
                while child.poll() is None:
                    if stopped() or time.monotonic()-start>timeout:
                        raise RuntimeError('owned_stage_stopped_or_timed_out:'+name)
                    time.sleep(.5)
                if child.returncode:raise RuntimeError('stage_failed_no_retry:'+name)
            finally:
                if child is not None and child.poll() is None:
                    os.killpg(child.pid,signal.SIGTERM)
                    try:child.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
                state['stages'].append(dict(name=name,exit_code=child.returncode if child else None,
                    wall_seconds=time.monotonic()-start,log_sha256=sha(log)));save()
    try:
        save()
        while True:
            if stopped():raise InterruptedError('explicit_stop')
            if time.monotonic()-began>27000:raise TimeoutError('finite_closure_wait_deadline')
            try:pipeline=read(storage/'records/context_pilot/P101_pipeline_v01/status.json')
            except (FileNotFoundError,json.JSONDecodeError):pipeline={}
            if pipeline.get('status') in ('complete','stopped') and pipeline.get('server_stopped'):break
            time.sleep(15)
        state['status']='closing';save()
        if (pipeline['git_commit']!=head or sha(correction)!=correction_sha
                or fixed['replacement_script_sha256']!=sha(Path(__file__))):
            raise ValueError('fixed_P101_execution_and_correction_required')
        if subprocess.check_output(['git','rev-parse','HEAD'],cwd=execution_root,text=True,timeout=10).strip()!=head:
            raise ValueError('original_execution_head_changed')
        if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=execution_root,text=True,timeout=10).strip():
            raise ValueError('original_tracked_execution_source_changed')
        sys.path.insert(0,str(execution_root/'scripts'))
        from run_whole_task_tool_choice_pipeline import checked_ci
        state['verified_ci']=checked_ci(execution_root,head);save()
        start=read(execution_root/'reports/P101_start_provenance_20261024.json')
        if (start['head']!=head or not start['both_workflows_and_jobs_success']
                or start['plan_sha256']!=sha(execution_root/'configs/P101_choice_context_v01.json')
                or start['closure_watcher_sha256']!=fixed['original_watcher_sha256']
                or sha(rt/'P101_closure_watcher.py')!=fixed['original_watcher_sha256']):
            raise ValueError('preserved_original_start_provenance_required')
        for rel in ('configs/P101_choice_context_v01.json','configs/P101_reporting_v01.json','reports/P101_initial_checks.json'):
            for name,value in read(execution_root/rel)['source_sha256'].items():
                if sha(execution_root/name)!=value:raise ValueError('frozen_P101_source_changed:'+name)
        python=rt/'p3_ci_venv/bin/python';reporting=rt/'reporting-venv/bin/python'
        command('audit',[python,execution_root/'scripts/audit_choice_context.py',
            '--storage-root',storage,'--repo-root',execution_root],195)
        result=read(execution_root/'reports/P101_choice_context.json')
        if result['audit_errors'] or len(result['rows'])!=36 or not result['owned_processes_absent']:
            raise ValueError('closed_all_planned_slots_required')
        command('report',report_command(reporting,execution_root),180)
        state.update(status='complete_pending_visual_review',finished_at=datetime.now(timezone.utc).isoformat(),
            audit_sha256=sha(execution_root/'reports/P101_choice_context.json'),
            report_manifest_sha256=sha(execution_root/'materials/20261024_p101_results/build_manifest.json'),
            report_pdf_sha256=sha(execution_root/'materials/20261024_p101_results/AI_harness_choice_context_20261024.pdf'))
    except BaseException as error:
        state.update(status='stopped',error_type=type(error).__name__,error=str(error)[:300]);save();raise
    finally:save()
    print(json.dumps({k:state.get(k) for k in ('status','wall_seconds','head','audit_sha256','error_type')}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root',type=Path,required=True)
    parser.add_argument('--execution-root',type=Path,required=True)
    parser.add_argument('--head',required=True);parser.add_argument('--correction-sha',required=True)
    args=parser.parse_args();run(args.storage_root.resolve(),args.execution_root.resolve(),args.head,args.correction_sha)
