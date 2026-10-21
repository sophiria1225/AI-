"""One bounded local job for the explicitly requested 2026-10-22 07:00 JST deck.

The process performs no model inference. It takes the latest committed aggregate
reports from the sole authorized repository at 06:40, renders and checks them,
then publishes a dedicated branch/PR. Waiting before 06:40 is in 30-second steps.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO='sophiria1225/AI-'
BRANCH='report/morning-20261022-0700'
DUE=dt.datetime(2026,10,21,21,40,tzinfo=dt.timezone.utc)
DEADLINE=dt.datetime(2026,10,21,22,0,tzinfo=dt.timezone.utc)
STORAGE=Path('/Users/tp26013/AI-')
WORKTREE=STORAGE/'.runtime/worktrees/morning-delivery'
LOCAL=STORAGE/'.runtime/morning-report-20261022'
STATE=STORAGE/'.runtime/morning_delivery_status.json'
PY=STORAGE/'.runtime/p3_ci_venv/bin/python'
REPORT_PY=STORAGE/'.runtime/reporting-venv/bin/python'
GIT=['git','-c','credential.helper=','-c','credential.helper=!gh auth git-credential']


def now():return dt.datetime.now(dt.timezone.utc)
def write(state):
    state['updated_at']=now().isoformat()
    temporary=STATE.with_suffix('.tmp');temporary.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(STATE)


def run(args,cwd,timeout=90,allow_failure=False):
    p=subprocess.run([str(a) for a in args],cwd=cwd,capture_output=True,text=True,timeout=timeout)
    if p.returncode and not allow_failure:raise RuntimeError(f'command failed: {args[0]} ({p.returncode}): {p.stderr[-800:]}')
    return p


def authorized(cwd):
    url=run(['git','remote','get-url','origin'],cwd).stdout.strip().removesuffix('.git')
    if url not in ('https://github.com/'+REPO,'git@github.com:'+REPO):
        raise ValueError('refusing any other repository')


def generate(state):
    authorized(STORAGE)
    run(GIT+['fetch','origin','main'],STORAGE)
    if WORKTREE.exists():
        authorized(WORKTREE)
        if run(['git','status','--porcelain'],WORKTREE).stdout.strip():raise ValueError('delivery worktree has edits')
        if run(['git','branch','--show-current'],WORKTREE).stdout.strip()!=BRANCH:raise ValueError('unexpected delivery branch')
        run(['git','merge','--ff-only','origin/main'],WORKTREE)
    else:run(['git','worktree','add','-b',BRANCH,WORKTREE,'origin/main'],STORAGE)
    state.update(status='rendering',source_commit=run(['git','rev-parse','HEAD'],WORKTREE).stdout.strip());write(state)
    build=WORKTREE/'scripts/build_morning_report.py'
    if not build.exists():raise ValueError('committed report builder not available')
    LOCAL.mkdir(parents=True,exist_ok=True)
    run([PY,build,'--output',LOCAL,'--pdf'],WORKTREE,timeout=140)
    run([REPORT_PY,WORKTREE/'scripts/review_morning_report.py','--folder',LOCAL],WORKTREE,timeout=45)
    manifest=json.loads((LOCAL/'build_manifest.json').read_text())
    state.update(status='local_ready',local_html=str(LOCAL/'index.html'),local_pdf=str(LOCAL/'AI_harness_progress_20261022.pdf'),pages=manifest['pages'],p27_included=manifest['p27_included']);write(state)
    return manifest


def publish(state,manifest):
    target=WORKTREE/'materials/20261022_morning';target.mkdir(parents=True,exist_ok=True)
    for p in LOCAL.rglob('*'):
        if p.is_file() and p.suffix in ('.html','.pdf','.svg','.csv','.md','.json') and 'review' not in p.relative_to(LOCAL).parts:
            dst=target/p.relative_to(LOCAL);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
    manifest['artifacts']={str(p.relative_to(target)):hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in target.rglob('*') if p.is_file() and p.name!='build_manifest.json'}
    (target/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (target/'README.md').write_text('# 10月22日 朝７時の進捗報告\n\n'
        '[HTMLスライド](index.html) / [PDF](AI_harness_progress_20261022.pdf) / [説明メモ](speaker_notes.md)\n\n'
        'HTMLはダウンロードしてブラウザーで開くと、矢印で移動、Oで一覧、Nで説明メモを表示できます。外部通信は不要です。\n\n'
        f'生成：{manifest["generated_at"]}。全{manifest["pages"]}枚。確定した公開集計だけを使用し、未監査の途中結果は成績へ入れません。最終生成には自動の文字・はみ出し検査を実行しています。全最終ページの目視確認は別記録で示します。\n\n'
        '新規性は未確立。既存技術の接続・校正と、今後の研究上の差を区別します。\n')
    run(['git','add','materials/20261022_morning'],WORKTREE)
    run(['git','commit','-m','Publish 07:00 progress report from latest audited results'],WORKTREE)
    head=run(['git','rev-parse','HEAD'],WORKTREE).stdout.strip()
    run(GIT+['push','-u','origin',BRANCH],WORKTREE,timeout=90)
    body=LOCAL/'pr_body.txt';body.write_text('10月22日朝7時の進捗報告資料。6時40分以降に、その時点で監査済みの集計からHTML・PDF・図表・説明メモを生成した。\n\n題名、社会・技術背景、目的、提案の現在地、既存との差、実験、結果、考察、限界、投稿までの予定を収録。新規性が未確定であることと、通常機能の校正を区別する。自動レイアウト検査・PDF検査合格。最終生成の全ページ目視は別記録で示し、この自動処理では実施済みと主張しない。\n\nRefs #130\n')
    pr=run(['gh','pr','create','--repo',REPO,'--base','main','--head',BRANCH,'--title','朝7時の進捗報告：目的・差分・実験・限界を図で整理','--body-file',body],WORKTREE).stdout.strip()
    state.update(status='published_branch',branch=BRANCH,commit=head,pr_url=pr);write(state)
    # A deterministic publication may wait for exact-head checks, never bypass them.
    until=min(now()+dt.timedelta(minutes=8),DEADLINE-dt.timedelta(minutes=2))
    while now()<until:
        checks=json.loads(run(['gh','api',f'repos/{REPO}/commits/{head}/check-runs'],WORKTREE).stdout)['check_runs']
        if checks and all(c['status']=='completed' and c['conclusion']=='success' for c in checks):
            run(['gh','pr','merge',pr,'--repo',REPO,'--merge','--match-head-commit',head],WORKTREE)
            state.update(status='published_main',html_url=f'https://github.com/{REPO}/blob/main/materials/20261022_morning/index.html',pdf_url=f'https://github.com/{REPO}/blob/main/materials/20261022_morning/AI_harness_progress_20261022.pdf');write(state);break
        if any(c['status']=='completed' and c['conclusion'] not in ('success','skipped') for c in checks):break
        time.sleep(20)
    note=LOCAL/'issue_comment.txt';note.write_text(f'朝の進捗資料を生成しました。全{manifest["pages"]}枚、生成時刻 {manifest["generated_at"]}。\n\n'
        f'[資料のPR]({pr}) / [PDF](https://github.com/{REPO}/blob/{BRANCH}/materials/20261022_morning/AI_harness_progress_20261022.pdf) / [HTML](https://github.com/{REPO}/blob/{BRANCH}/materials/20261022_morning/index.html)\n\n'
        f'ローカルHTML: `{LOCAL}/index.html`。完成集計のみ使用。新規性・有効性の未確定部分と日程のリスクも明記しています。最終生成の自動文字・境界検査は合格。全ページ目視確認はこの自動処理では実施していません。\n')
    run(['gh','issue','comment','130','--repo',REPO,'--body-file',note],WORKTREE)


def main():
    p=argparse.ArgumentParser();p.add_argument('--publish',action='store_true');p.add_argument('--check-only',action='store_true')
    a=p.parse_args();authorized(STORAGE)
    if a.check_only:
        print(json.dumps(dict(due=DUE.isoformat(),deadline=DEADLINE.isoformat(),repo=REPO,storage_exists=STORAGE.exists(),report_python=REPORT_PY.exists(),future=DUE>now())));return
    if STATE.exists() and json.loads(STATE.read_text()).get('status') in ('published_main','published_branch','complete_local'):
        raise ValueError('delivery already completed; no duplicate publication')
    state=dict(status='waiting',pid=os.getpid(),due_at=DUE.isoformat(),deadline=DEADLINE.isoformat(),model_calls=0,repository=REPO,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest());write(state)
    try:
        while now()<DUE:
            time.sleep(min(30,max(1,(DUE-now()).total_seconds())));write(state)
        if now()>DEADLINE+dt.timedelta(hours=1):raise ValueError('scheduled day has passed')
        manifest=generate(state)
        if a.publish:publish(state,manifest)
        else:state['status']='complete_local';write(state)
    except Exception as exc:
        state.update(status='failed',error_type=type(exc).__name__,error=str(exc));write(state);raise


if __name__=='__main__':main()
