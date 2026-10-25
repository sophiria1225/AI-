"""One bounded, authorized P122 -> P123 continuation using isolated worktrees.

Wait for the existing collector, publish the closed cohort and fixed plan, check
both exact-head CI events/jobs, then launch P123 once and collect its closed data.
No scope choice depends on intermediate or favorable outcomes. No new variant is
launched after P123 without another finite research plan.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from receipt_reasoning_history import require
from run_handoff_factors import read, sha
from whole_task_rolling_checkpoint import validate_plan

REPOSITORY='sophiria1225/AI-'


def run(root, storage, expected_head):
    rt=storage/'.runtime'; editor=rt/'worktrees/p107-prep'
    status_path=rt/'P122_to_P123_continuation_status.json'
    require(not status_path.exists(),'continuation_already_started_preserve_attempt')
    state={'phase':'P122_to_P123_continuation','status':'starting','source_head':expected_head,
           'started_at':datetime.now(timezone.utc).isoformat(),'pid':os.getpid(),
           'source_sha256':sha(Path(__file__)),'worktree':str(root),'stages':[]}
    child=None

    def save(stage=None):
        if stage:state['status']=stage
        state['updated_at']=datetime.now(timezone.utc).isoformat()
        tmp=status_path.with_suffix('.tmp');tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
        tmp.replace(status_path)

    def stopped():
        return any((rt/n).exists() for n in ('checkpoint_continuation.stop','P122.stop','P123.stop'))

    def check_stop():
        if stopped():raise InterruptedError('explicit_research_stop')

    def on_signal(*_):
        (rt/'checkpoint_continuation.stop').touch()
        (rt/'P123.stop').touch()
        if child is not None and child.poll() is None:child.terminate()

    signal.signal(signal.SIGTERM,on_signal);signal.signal(signal.SIGINT,on_signal)

    def command(args, label, timeout=120, cwd=None):
        nonlocal child
        check_stop()
        path=rt/f'P122_to_P123_{label}.log'
        began=time.monotonic()
        with path.open('x') as log:
            child=subprocess.Popen(args,cwd=cwd or root,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            state['child_pid']=child.pid;save(label)
            try:
                while child.poll() is None:
                    check_stop()
                    if time.monotonic()-began>timeout:raise TimeoutError(label+'_deadline')
                    time.sleep(1)
                code=child.returncode
            finally:
                if child.poll() is None:
                    child.terminate()
                    try:child.wait(timeout=60)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=15)
                child=None;state.pop('child_pid',None)
        state['stages'].append({'name':label,'exit_code':code,'wall_seconds':time.monotonic()-began});save()
        require(code==0,label+'_failed_no_retry')
        return path.read_text()

    def git(*args):
        check_stop()
        return subprocess.check_output(['git',*args],cwd=root,text=True,timeout=30).strip()

    def copy_new(source,target):
        if target.exists():
            require(sha(source)==sha(target),'existing_artifact_differs:'+str(target))
            return
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as handle:handle.write(source.read_bytes())
        require(sha(source)==sha(target),'artifact_copy_changed')

    def ledger_and_mirror(name, paths):
        # Bind only new evidence. Existing tracking and entrypoint files are not
        # overwritten in the user's separate editor while this worker publishes.
        value={'created_at':datetime.now(timezone.utc).isoformat(),
            'source_sha256':{p:sha(root/p) for p in paths},'automatic_continuation':True,
            'novel_method_claim':False,'general_quality_preservation_claim':False,
            'reserved_scenarios_read':0,'manuscript_changed':False}
        rel='reports/'+name+'.json'
        with (root/rel).open('x') as handle:json.dump(value,handle,ensure_ascii=False,indent=2);handle.write('\n')
        for p in [*paths,rel]:copy_new(root/p,editor/p)
        names=read(rt/'research_ledger_names.json')
        require(name not in names,'ledger_already_registered')
        for old in names:
            for p,digest in read(editor/'reports'/(old+'.json'))['source_sha256'].items():
                require(sha(editor/p)==digest,'prior_binding_changed:'+p)
        names.append(name)
        tmp=rt/'research_ledger_names.tmp';tmp.write_text(json.dumps(names,indent=2)+'\n')
        tmp.replace(rt/'research_ledger_names.json')
        return rel

    def tracking_update(note, link):
        import sync_tracking as tracking
        tasks=read(root/'tracking/tasks.json');require(len(tasks['tasks'])==120,'all_project_tasks_required')
        for task in tasks['tasks']:
            if task['id'] in ('R32','R33'):
                task['progress']=note+'\n'+link
        (root/'tracking/tasks.json').write_text(json.dumps(tasks,ensure_ascii=False,indent=2)+'\n')
        links=read(root/'tracking/github_links.json');tracking.render(tasks,links)
        try:tracking.publish({**tasks,'tasks':[t for t in tasks['tasks'] if t['id'] in ('R32','R33')]},links)
        finally:tracking.render(tasks,links)
        for rel in ('README.md','RESUME.md','docs/current_status.md','docs/next_actions.md'):
            path=root/rel;text=path.read_text()
            a=text.index('<!-- CURRENT_EVIDENCE_SNAPSHOT -->')+len('<!-- CURRENT_EVIDENCE_SNAPSHOT -->')
            b=text.index('<!-- END_CURRENT_EVIDENCE_SNAPSHOT -->',a)
            path.write_text(text[:a]+'\n'+note+' ['+'全件資料と判断'+']('+link+').\n'+text[b:])

    def ci_then_publish(branch,title,body,label):
        command(['git','add','--','README.md','RESUME.md','docs','reports','configs','materials','tracking'],label+'_stage')
        command(['git','diff','--cached','--check'],label+'_diffcheck')
        command(['git','commit','-m',title],label+'_commit')
        head=git('rev-parse','HEAD')
        command(['git','-c','credential.helper=','-c','credential.helper=!gh auth git-credential',
                 'push','-u','origin',branch],label+'_push',180)
        body_path=rt/(label+'_PR_body.md');body_path.write_text(body)
        url=command(['gh','pr','create','--repo',REPOSITORY,'--base','main','--head',branch,
            '--title',title,'--body-file',str(body_path)],label+'_PR',120).strip().splitlines()[-1]
        number=int(url.rsplit('/',1)[-1]);state[label+'_publication']={'head':head,'url':url};save('waiting_'+label+'_CI')
        deadline=time.monotonic()+1800
        from run_whole_task_rolling_checkpoint_pipeline import checked_ci
        while True:
            check_stop()
            payload=json.loads(subprocess.check_output(['gh','api','repos/'+REPOSITORY+
                '/actions/runs?head_sha='+head+'&per_page=30'],text=True,timeout=30))
            runs=[r for r in payload['workflow_runs'] if r['head_sha']==head and r['path']=='.github/workflows/checks.yml']
            require(not any(r['status']=='completed' and r['conclusion']!='success' for r in runs),'CI_failed_no_retry')
            if {r['event'] for r in runs}=={'push','pull_request'} and all(r['status']=='completed' for r in runs):
                ci=checked_ci(root,head);break
            if time.monotonic()>deadline:raise TimeoutError('exact_head_CI_deadline')
            time.sleep(10)
        state[label+'_publication']['ci']=ci;save()
        command(['gh','pr','merge',str(number),'--repo',REPOSITORY,'--merge','--match-head-commit',head],label+'_merge',120)
        merged=json.loads(subprocess.check_output(['gh','api',f'repos/{REPOSITORY}/pulls/{number}'],text=True,timeout=30))
        require(merged['merged'] and merged['head']['sha']==head,'expected_head_not_merged')
        state[label+'_publication'].update(merged=True,merge_commit=merged['merge_commit_sha']);save()
        return head

    try:
        require(root.resolve()==Path(__file__).resolve().parents[1], 'isolated_script_root_required')
        require(git('remote','get-url','origin') in ('https://github.com/'+REPOSITORY,'https://github.com/'+REPOSITORY+'.git'),
                'only_authorized_repository')
        require(git('rev-parse','HEAD')==expected_head and not git('status','--porcelain'),'clean_fixed_continuation_source_required')
        from run_whole_task_rolling_checkpoint_pipeline import checked_ci
        state['preparation_ci']=checked_ci(root,expected_head)
        state['P123_wrapper_sha256']=sha(rt/'run_close_p123_once.py')
        state['P123_collector_sha256']=sha(rt/'collect_p123_closed_once.py')
        save('waiting_P122_collector')
        deadline=time.monotonic()+67200
        while not (rt/'P122_report_collector_once_end.json').exists():
            check_stop()
            ended=rt/'P122_collection_wait_once_end.json'
            if ended.exists():
                require(read(ended)['status']=='complete_all_slots_collected_review_pending',
                        'P122_collection_stopped_no_retry')
            if time.monotonic()>deadline:raise TimeoutError('P122_collector_deadline')
            time.sleep(10)
        collected=read(rt/'P122_report_collector_once_end.json')
        require(collected['status']=='complete','P122_collection_not_complete')
        branch='research/p122-results-p123-fixed-20261025'
        command(['git','switch','-c',branch],'create_preparation_branch')
        for rel,digest in collected['copied_source_sha256'].items():
            require(sha(editor/rel)==digest,'collected_P122_artifact_changed')
            copy_new(editor/rel,root/rel)
        command([sys.executable,'scripts/prepare_rolling_checkpoint_followup.py','--repo-root',str(root),
                 '--storage-root',str(storage)],'review_and_bind',180)
        checked=read(root/'reports/P122_review_for_fixed_P123.json')
        evidence=[*collected['copied_source_sha256'],'reports/P122_review_for_fixed_P123.json','docs/P122_findings.md']
        allowed=checked['next_predeclared_comparison_may_be_bound']
        if allowed:
            plan=read(root/'configs/P123_whole_task_rolling_checkpoint_v01.json');validate_plan(plan)
            evidence.append('configs/P123_whole_task_rolling_checkpoint_v01.json')
        ledger_and_mirror('P122_results_P123_binding_provenance_20261025',evidence)
        note=('P122全24枠とserverを閉じて全件確認した. 反復採用基準は'+('達成' if checked['replication_gate_met'] else '未達')+
            '. 新規性、一般的品質維持、非劣性は未確立. '+('既定のP123 12条件を固定し、両CIと事前計数後に継続する.' if allowed else
            '未知使用量または未完了があるため次の生成は開始せず、全件を保存した.'))
        tracking_update(note,'https://github.com/'+REPOSITORY+'/blob/main/docs/P122_findings.md')
        head=ci_then_publish(branch,'Review all P122 results and bind the prespecified followup',note+
            '\n\n全24枠、全要求、全役割費用と記述統計を再計算済み. 次条件の選択は成否に依存せず、未見課題と原稿は変更しない.','P122_results')
        if not allowed:
            save('closed_results_need_research_review_no_P123_generation');return 2
        require(sha(rt/'run_close_p123_once.py')==state['P123_wrapper_sha256'],'P123_wrapper_changed')
        command(['git','worktree','add','--detach',str(rt/'worktrees/p123-run'),head],'create_P123_run_tree')
        state['P123_source_head']=head;save('starting_P123')
        for name in ('P122_pending_execution_handoff.json','checkpoint_letter_writing_handoff_20261025.json'):
            p=rt/name;h=read(p);h.update(current_phase='P123_starting',continuation_status=str(status_path),
                P123_source_head=head,P123_publication=state['P122_results_publication'],
                next_steps=['Do not duplicate the automatic P123 wrapper or collector.',
                    'Inspect operational status only while P123 is running; all-row review follows server closure.'])
            p.write_text(json.dumps(h,ensure_ascii=False,indent=2)+'\n')
        command([sys.executable,str(rt/'run_close_p123_once.py'),'--expected-head',head],'P123_execution_and_closure',34800)
        require(sha(rt/'collect_p123_closed_once.py')==state['P123_collector_sha256'],'P123_collector_changed')
        command([sys.executable,str(rt/'collect_p123_closed_once.py'),'--expected-head',head],'P123_collection',180)
        result=read(rt/'P123_report_collector_once_end.json')
        state['P123_closed_collection']=result
        save('P123_closed_collected_next_research_review')
        return 0
    except BaseException as error:
        state.update(error_type=type(error).__name__,error=str(error))
        save('stopped_preserve_records_no_retry')
        raise
    finally:
        state['finished_at']=datetime.now(timezone.utc).isoformat();save()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--expected-head',required=True);a=p.parse_args()
    raise SystemExit(run(Path(__file__).resolve().parents[1],a.storage_root.resolve(),a.expected_head))
