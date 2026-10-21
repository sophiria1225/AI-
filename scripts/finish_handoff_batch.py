"""Complete a frozen batch and publish only its audited aggregate report.

Allows a running experiment to leave a reviewable result if the interactive
session reaches its quota. This is deterministic execution, not unattended AI.
"""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

REPOSITORY='sophiria1225/AI-'


def run(root,storage,phase='P31'):
    if phase not in ('P31','P32'):raise ValueError('unknown phase')
    slug=phase.lower()
    state_path=storage/f'.runtime/{slug}_pipeline_status.json'
    def status(**values):
        values['updated_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        state_path.write_text(json.dumps(values,ensure_ascii=False,indent=2)+'\n')
    def command(args,**kwargs):
        result=subprocess.run(args,cwd=root,text=True,capture_output=True,**kwargs)
        if result.returncode:raise RuntimeError(result.stderr[-2000:])
        return result.stdout.strip()
    origin=command(['git','remote','get-url','origin'])
    if origin not in ('https://github.com/sophiria1225/AI-','https://github.com/sophiria1225/AI-.git'):
        raise ValueError('wrong repository')
    branch=command(['git','branch','--show-current'])
    if branch!=f'research/{slug}-run-20261022' or command(['git','status','--porcelain']):
        raise ValueError('require clean dedicated fixed run branch')
    status(status='running_batch',branch=branch)
    log=storage/f'.runtime/{slug}_pipeline.log'
    with log.open('w') as stream:
        completed=subprocess.run([sys.executable,str(root/'scripts/run_handoff_factors.py'),
            '--storage-root',str(storage),'--repo-root',str(root),'--phase',phase,'--publish'],cwd=root,
            stdout=stream,stderr=subprocess.STDOUT)
        if completed.returncode:
            status(status='batch_stopped',exit_code=completed.returncode);return completed.returncode
        status(status='auditing_complete_cohort',branch=branch)
        analyzed=subprocess.run([sys.executable,str(root/'scripts/analyze_handoff_factors.py'),
            '--storage-root',str(storage),'--repo-root',str(root),'--phase',phase],cwd=root,
            stdout=stream,stderr=subprocess.STDOUT)
        if analyzed.returncode:
            status(status='audit_failed',exit_code=analyzed.returncode);return analyzed.returncode
    report_name=f'reports/{phase}_comparison.json'
    report=json.loads((root/report_name).read_text())
    if not report['all_sixteen_reviewed'] or report['audit_errors']:
        raise ValueError('incomplete audit')
    command(['git','add',report_name])
    command(['git','commit','-m',f'Record all sixteen {phase} fixed-prefix handoff continuations'])
    head=command(['git','rev-parse','HEAD'])
    command(['git','-c','credential.helper=','-c','credential.helper=!gh auth git-credential',
             'push','-u','origin',branch])
    lines=['全16分岐の実行・独立評価・費用監査が終了したため、公開可能な集計だけを保存する。',
           '', '| 条件 | 成功 | 既知token | 不明呼出 | 後続API |','|---|---:|---:|---:|---:|']
    for arm,row in report['totals'].items():
        lines.append(f"| {arm} | {row['successes']}/4 | {row['known_total_tokens']:,} | {row['unknown_usage_calls']} | {row['api_requests']} |")
    boundary=report.get('boundary_after_model_calls',4)
    lines+=['',f'同じ{boundary}応答後・既知４課題・１seedの探索比較。復元と共通前半の費用は別に記録。',
            '新方式・完全プロセス同一性・再編の有効性を証明したものではない。機構の考察は別途行う。',
            '固定した処理による自動集計・公開。モデルが条件を変更したり次の研究を選んだものではない。']
    body=storage/f'.runtime/{slug}_results_pr.txt';body.write_text('\n'.join(lines)+'\n')
    url=command(['gh','pr','create','--repo',REPOSITORY,'--base','main','--head',branch,
                 '--title',f'Record the complete {phase} fixed-prefix handoff comparison','--body-file',str(body)])
    status(status='published_waiting_ci',branch=branch,head=head,pull_request=url)
    deadline=time.monotonic()+1200
    while time.monotonic()<deadline:
        data=json.loads(command(['gh','pr','view',url,'--repo',REPOSITORY,'--json','headRefOid,statusCheckRollup']))
        checks=data['statusCheckRollup']
        if data['headRefOid']!=head:raise ValueError('published branch changed')
        if len(checks)>=2 and all(c.get('status')=='COMPLETED' for c in checks):
            if all(c.get('conclusion')=='SUCCESS' for c in checks):
                command(['gh','pr','merge',url,'--repo',REPOSITORY,'--merge','--match-head-commit',head])
                status(status='merged',head=head,pull_request=url)
                return 0
            status(status='ci_failed',head=head,pull_request=url);return 1
        time.sleep(15)
    status(status='ci_wait_timeout_branch_published',head=head,pull_request=url);return 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--repo-root',type=Path,required=True)
    parser.add_argument('--storage-root',type=Path,required=True)
    parser.add_argument('--phase',choices=('P31','P32'),default='P31');a=parser.parse_args()
    try:raise SystemExit(run(a.repo_root,a.storage_root,a.phase))
    except Exception as exc:
        (a.storage_root/f'.runtime/{a.phase.lower()}_pipeline_error.txt').write_text(type(exc).__name__+': '+str(exc)+'\n')
        raise
