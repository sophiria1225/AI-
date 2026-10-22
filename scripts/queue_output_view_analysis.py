"""After frozen P33 publication, build local review artifacts; no new inference.

Run in a dedicated clean worktree. This does not merge or publish unreviewed
slides, choose a new method, or start any held-out experiment.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


def run(root,storage,wait_seconds):
    def command(args,**kwargs):
        return subprocess.check_output(args,cwd=root,text=True,**kwargs).strip()
    origin=command(['git','remote','get-url','origin'])
    if origin not in ('https://github.com/sophiria1225/AI-','https://github.com/sophiria1225/AI-.git'):
        raise ValueError('unauthorized repository')
    if command(['git','branch','--show-current'])!='analysis/p33-review-20261022':
        raise ValueError('dedicated review worktree required')
    if command(['git','status','--porcelain']):raise ValueError('preserve modified review worktree')
    head=command(['git','rev-parse','HEAD'])
    state=storage/'.runtime/p33_analysis_status.json'
    if state.exists():raise FileExistsError('preserve prior analysis status')
    def save(**values):
        values.update(updated_at=dt.datetime.now(dt.timezone.utc).isoformat(),analysis_head=head,
                      new_inference_calls=0,new_api_requests=0)
        temp=state.with_suffix('.tmp')
        temp.write_text(json.dumps(values,ensure_ascii=False,indent=2)+'\n');temp.replace(state)
    save(status='waiting_for_complete_published_P33')
    deadline=time.monotonic()+wait_seconds;source_state=storage/'.runtime/p33_pipeline_status.json'
    while time.monotonic()<deadline:
        if (storage/'.runtime/p33_pipeline_error.txt').exists():
            save(status='source_pipeline_requires_review',source_status='error_recorded');return 1
        try:status=json.loads(source_state.read_text()) if source_state.exists() else {}
        except json.JSONDecodeError:
            # The existing frozen producer writes its small status in place.
            # Retry a concurrent write; never infer completion from partial JSON.
            time.sleep(1);continue
        if status.get('status')=='merged':break
        if status.get('status') in ('batch_stopped','audit_failed','ci_failed','pipeline_error',
                                   'ci_wait_timeout_branch_published'):
            save(status='source_pipeline_requires_review',source_status=status['status']);return 1
        time.sleep(15)
    else:save(status='bounded_wait_expired');return 1
    if not re.fullmatch(r'https://github.com/sophiria1225/AI-/pull/[0-9]+',status.get('pull_request','')):
        raise ValueError('published result repository differs')
    source=storage/'.runtime/worktrees/p33-run'
    actual=command(['git','-C',str(source),'rev-parse','HEAD'])
    if actual!=status['head']:raise ValueError('audited source branch changed')
    if command(['git','rev-parse','HEAD'])!=head or command(['git','status','--porcelain']):
        raise ValueError('review code changed while waiting')
    report=source/'reports/P33_comparison.json'
    target=root/'reports/P33_comparison.json'
    if target.exists():raise FileExistsError('preserve prior result')
    shutil.copyfile(report,target)
    save(status='profiling_complete_cohort',source_head=actual,
         comparison_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    log=storage/'.runtime/p33_analysis.log'
    with log.open('w') as stream:
        for name in ('profile_handoff_costs.py','diagnose_handoff_programs.py','output_view_decision.py'):
            args=[sys.executable,str(root/'scripts'/name),'--repo-root',str(root),'--storage-root',str(storage)]
            if name!='output_view_decision.py':args+=['--phase','P33']
            result=subprocess.run(args,cwd=root,stdout=stream,stderr=subprocess.STDOUT)
            if result.returncode:save(status='analysis_failed',script=name);return result.returncode
        save(status='rendering_closed_results',source_head=actual)
        args=[str(storage/'.runtime/reporting-venv/bin/python'),str(root/'scripts/build_output_view_report.py'),
              '--repo-root',str(root),'--output',str(root/'materials/20261022_p33'),'--pdf']
        result=subprocess.run(args,cwd=root,stdout=stream,stderr=subprocess.STDOUT)
        if result.returncode:save(status='render_requires_review');return result.returncode
    save(status='ready_for_visual_review',source_head=actual,
         folder=str(root/'materials/20261022_p33'),published=False)
    return 0


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo-root',type=Path,required=True)
    p.add_argument('--storage-root',type=Path,required=True);p.add_argument('--wait-seconds',type=int,default=7200)
    a=p.parse_args()
    if not 0<a.wait_seconds<=7200:raise ValueError('bounded wait required')
    try:raise SystemExit(run(a.repo_root,a.storage_root,a.wait_seconds))
    except Exception as exc:
        (a.storage_root/'.runtime/p33_analysis_error.txt').write_text(type(exc).__name__+': '+str(exc)+'\n')
        raise
