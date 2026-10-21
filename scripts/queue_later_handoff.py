"""Run the prespecified P32 batch after the complete P31 audit is published.

Deterministic dependency handling only: no task selection, condition changes,
model reasoning or semantic interpretation of partial outcomes.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

from handoff_factors import ARMS
from run_event_view_probe import lease_remaining

REPO='sophiria1225/AI-'
BRANCH='research/p32-run-20261022'
PREFIX='https://github.com/'+REPO+'/pull/'
MINI_COMMIT='04d809ceab9df28f9adaed044884180159172930'


def prepare_vendor(root,storage):
    """Connect the same ignored, pinned test dependency used by other worktrees."""
    source=storage/'vendor/mini-swe-agent'
    head=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if head!=MINI_COMMIT:raise ValueError('test dependency revision differs')
    subprocess.run(['git','-C',str(source),'diff','--exit-code','HEAD','--','src'],check=True,capture_output=True)
    target=root/'vendor/mini-swe-agent'
    if target.exists() or target.is_symlink():
        if target.resolve()!=source.resolve():raise ValueError('preserve a different existing dependency')
    else:
        target.parent.mkdir(parents=True,exist_ok=True)
        target.symlink_to(source,target_is_directory=True)


def validate_resume(head,branch,dirty,base_commit):
    if head!=base_commit or branch!=BRANCH:
        raise ValueError('prepared worktree identity differs')
    if dirty not in ('','?? reports/P31_comparison.json'):
        raise ValueError('preserve modified prepared worktree')


def validate_prior(status, report):
    if status.get('status')!='merged' or not re.fullmatch(PREFIX+r'[0-9]+',status.get('pull_request','')):
        raise ValueError('prior audit must be merged into the authorized repository')
    if not re.fullmatch(r'[0-9a-f]{40}',status.get('head','')):
        raise ValueError('prior result must have an exact commit')
    if report.get('phase')!='P31' or not report.get('all_sixteen_reviewed') or report.get('audit_errors'):
        raise ValueError('prior whole-cohort audit did not pass')
    rows=report.get('rows',[])
    tasks={r['task_id'] for r in rows}
    if len(tasks)!=4 or len(rows)!=16 or {(r['task_id'],r['arm']) for r in rows}!={(t,a) for t in tasks for a in ARMS}:
        raise ValueError('prior report does not cover every cell once')


def validate_slots(slots):
    if len(slots)!=1 or slots[0].get('is_processing') is not False:
        raise ValueError('require one idle inference slot')


def run(storage,base_commit,wait_seconds,resume_prepared=False):
    if not re.fullmatch(r'[0-9a-f]{40}',base_commit):raise ValueError('pin the prepared implementation')
    state_path=storage/'.runtime/p32_queue_status.json'
    def status(**values):
        values.update(at=dt.datetime.now(dt.timezone.utc).isoformat(),base_commit=base_commit,
                      repository=REPO,automatic_condition_selection=False)
        tmp=state_path.with_suffix('.tmp');tmp.write_text(json.dumps(values,indent=2)+'\n');tmp.replace(state_path)
    def command(args,cwd=storage):
        result=subprocess.run(args,cwd=cwd,text=True,capture_output=True)
        if result.returncode:raise RuntimeError(result.stderr[-1600:])
        return result.stdout.strip()
    origin=command(['git','remote','get-url','origin'])
    if origin not in ('https://github.com/'+REPO,'https://github.com/'+REPO+'.git'):
        raise ValueError('wrong repository')
    deadline=time.monotonic()+wait_seconds
    prior=None
    while time.monotonic()<deadline:
        path=storage/'.runtime/p31_pipeline_status.json'
        if path.exists():
            try:prior=json.loads(path.read_text())
            except json.JSONDecodeError:prior=None
        if prior and prior.get('status')=='merged':break
        if prior and prior.get('status') in ('batch_stopped','audit_failed','ci_failed','ci_wait_timeout_branch_published'):
            raise ValueError('prior batch stopped; no automatic alternative')
        status(status='waiting_for_complete_prior_audit')
        time.sleep(30)
    else:raise TimeoutError('prior audit waiting deadline')
    if not re.fullmatch(PREFIX+r'[0-9]+',prior.get('pull_request','')):
        raise ValueError('unexpected prior pull request')
    if not re.fullmatch(r'[0-9a-f]{40}',prior.get('head','')):raise ValueError('invalid prior commit')
    remote=json.loads(command(['gh','pr','view',prior['pull_request'],'--repo',REPO,'--json','state,headRefOid']))
    if remote!={'headRefOid':prior['head'],'state':'MERGED'}:raise ValueError('prior remote identity differs')
    prior_text=command(['git','show',prior['head']+':reports/P31_comparison.json'])
    report=json.loads(prior_text);validate_prior(prior,report)
    root=storage/'.runtime/worktrees/p32-run'
    if root.exists():
        if not resume_prepared:raise FileExistsError('preserve existing run tree')
        validate_resume(command(['git','rev-parse','HEAD'],cwd=root),
                        command(['git','branch','--show-current'],cwd=root),
                        command(['git','status','--porcelain'],cwd=root),base_commit)
        cached=root/'reports/P31_comparison.json'
        if cached.exists() and cached.read_text().strip()!=prior_text:
            raise ValueError('preserve a different prior report')
    else:
        command(['git','worktree','add','-b',BRANCH,str(root),base_commit])
    sys.path.insert(0,str(root/'scripts'))
    # Validate through the pinned implementation, in a separate interpreter.
    checked=json.loads((root/'reports/P32_prefix_checks.json').read_text())
    for name,digest in checked['source_hashes'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('prepared source changed')
    if not checked['all_four_attempted'] or not checked['all_observable_prefixes_match']:
        raise ValueError('later prefixes did not all pass')
    (root/'reports/P31_comparison.json').write_text(prior_text+'\n')
    status(status='preparing_fixed_activation',prior_result_commit=prior['head'])
    prepare_vendor(root,storage)
    test=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-q'],cwd=root,text=True,capture_output=True)
    (storage/'.runtime/p32_activation_tests.log').write_text(test.stdout+test.stderr)
    if test.returncode:raise ValueError('activation tests failed')
    command([sys.executable,'-m','compileall','-q','scripts','tests'],cwd=root)
    names=command(['git','ls-files','configs','scripts','reports','tests'],cwd=root).splitlines()
    names=sorted(set(names+['reports/P31_comparison.json']))
    plan=json.loads((root/'configs/P32_handoff_factors_v01.json').read_text())
    def check_runtime():
        runtime=json.loads((storage/'.runtime/model_server.json').read_text())
        process=command(['ps','-p',str(runtime['supervisor_pid']),'-o','command='])
        remaining,end=lease_remaining(runtime,process,dt.datetime.now(dt.timezone.utc))
        required=16*(plan['max_setup_seconds']+plan['max_wall_seconds']+180)+600
        if remaining<required:raise ValueError('insufficient server lease for the conservative batch bound')
        source_plan=json.loads((root/plan['source_plan']).read_text())
        with urllib.request.urlopen(source_plan['model']['base_url']+'/slots',timeout=10) as r:slots=json.load(r)
        validate_slots(slots)
        return {'remaining_seconds':remaining,'required_seconds':required,'ends_at':end,'one_slot_idle':True}
    live=check_runtime()
    activation={'phase':'P32','at':dt.datetime.now(dt.timezone.utc).isoformat(),
        'decision':'run_all_sixteen_prespecified_eighth_boundary_cells_after_complete_prior_audit',
        'why':'Fixed before complete P31 outcomes because early runtime states had few user bindings. No success-based checkpoint selection.',
        'alternatives':['Do not modify the four conditions or continuation budgets based on P31 outcomes.',
                        'Do not replace an ineligible prefix or use the twelve unviewed scenarios.',
                        'Do not call this an independent task cohort, novel algorithm or exact process restore.'],
        'selection_rule_commit':'fb134e98ee310263e823a0fd61774782af001db4',
        'source_boundaries':[r['boundary_manifest_sha256'] for r in checked['rows']],
        'prior_result_commit':prior['head'],'prior_review':'complete mechanical cohort audit; not an automated scientific interpretation',
        'unittest_discovery_passed':True,'compileall_passed':True,'model_calls_before_activation':0,
        'controller_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'resumed_prepared_worktree':resume_prepared,'test_dependency_commit':MINI_COMMIT,
        'runtime_check':live,
        'source_hashes':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}}
    (root/'reports/P32_activation_v01.json').write_text(json.dumps(activation,ensure_ascii=False,indent=2)+'\n')
    command(['git','add','reports/P31_comparison.json','reports/P32_activation_v01.json'],cwd=root)
    command(['git','commit','-m','Freeze the prespecified later-boundary continuation batch'],cwd=root)
    head=command(['git','rev-parse','HEAD'],cwd=root)
    command(['git','-c','credential.helper=','-c','credential.helper=!gh auth git-credential','push','-u','origin',BRANCH],cwd=root)
    body=storage/'.runtime/p32_activation_pr.txt'
    body.write_text('P31全16件の集計・機械監査・公開後、事前に用意したP32を固定する。\n\n'
        '元の全４軌跡の８応答後、同じ四条件・後続予算。前半のAPI返却・保存DB・Pythonの照合済み。'
        '地点や条件をP31の勝ち負けで変更していない。準備済み実装、出典、サーバー期限を照合した。\n\n'
        'unittest全件とcompileallが合格。同じheadのCI２件合格後だけ16分岐を開始する。'
        '科学的な結論を自動選択する処理ではなく、結果に新規性を付与しない。\n')
    url=command(['gh','pr','create','--repo',REPO,'--base','main','--head',BRANCH,
                 '--title','Freeze the prespecified later-boundary continuation batch','--body-file',str(body)],cwd=root)
    status(status='activation_waiting_ci',head=head,pull_request=url)
    ci_deadline=time.monotonic()+900
    while time.monotonic()<ci_deadline:
        data=json.loads(command(['gh','pr','view',url,'--repo',REPO,'--json','headRefOid,statusCheckRollup']))
        if data['headRefOid']!=head:raise ValueError('activation head changed')
        checks=data['statusCheckRollup']
        if len(checks)>=2 and all(c.get('status')=='COMPLETED' for c in checks):
            if not all(c.get('conclusion')=='SUCCESS' for c in checks):raise ValueError('activation CI failed')
            command(['gh','pr','merge',url,'--repo',REPO,'--merge','--match-head-commit',head]);break
        time.sleep(15)
    else:raise TimeoutError('activation CI deadline')
    check_runtime()
    status(status='running_fixed_followup',head=head,pull_request=url)
    result=subprocess.run([sys.executable,str(root/'scripts/finish_handoff_batch.py'),'--repo-root',str(root),
                           '--storage-root',str(storage),'--phase','P32'],cwd=root)
    status(status='followup_process_ended',returncode=result.returncode,head=head,pull_request=url)
    return result.returncode


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True)
    p.add_argument('--base-commit',required=True);p.add_argument('--wait-seconds',type=int,default=10800)
    p.add_argument('--resume-prepared',action='store_true');a=p.parse_args()
    try:raise SystemExit(run(a.storage_root,a.base_commit,a.wait_seconds,a.resume_prepared))
    except Exception as exc:
        (a.storage_root/'.runtime/p32_queue_error.txt').write_text(type(exc).__name__+': '+str(exc)+'\n')
        (a.storage_root/'.runtime/p32_queue_status.json').write_text(json.dumps({
            'status':'stopped','error_type':type(exc).__name__,'at':dt.datetime.now(dt.timezone.utc).isoformat(),
            'repository':REPO,'base_commit':a.base_commit,'automatic_alternative':False},indent=2)+'\n')
        raise
