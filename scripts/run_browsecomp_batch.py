"""Frozen two-question integration batch, serialized after P14, with aggregate progress."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

from browsecomp_terminal import digest, load_terminal
from run_context_comparison import write_json
from watch_pro_comparison import gh_api

ROOT = Path(__file__).resolve().parents[1]
MARKER = '<!-- harness-browsecomp:P15_batch_v01 -->'
REPOSITORY = 'sophiria1225/AI-'


def check_plan(plan, frozen, plan_path):
    if (plan['phase'] != 'P15' or plan['batch_id'] != 'P15_batch_v01'
            or list(plan['run_ids']) != plan['selected_ids'][:2]
            or list(plan['run_ids'].values()) != ['P15_01_FULL', 'P15_02_FULL']
            or digest(plan_path) != frozen['plan_sha256']):
        raise ValueError('integration schedule differs from the precommitted first two questions')
    for name, expected in frozen['source_hashes'].items():
        path = (ROOT / name).resolve()
        if (ROOT / name).is_symlink() or not path.is_relative_to(ROOT.resolve()) or digest(path) != expected:
            raise ValueError('frozen source changed')


def collect(storage, plan):
    rows = []
    for query_id, run_id in plan['run_ids'].items():
        trial = storage / 'records/browsecomp_pilot' / run_id
        row = {'query_id': query_id, 'run_id': run_id, 'state': 'pending',
               'calls': 0, 'known_tokens': 0, 'unknown_usage_calls': 0, 'submitted': None}
        if trial.exists():
            row['state'] = 'running'
        if (trial / 'usage.json').exists():
            usage = json.loads((trial / 'usage.json').read_text())
            row.update(calls=len(usage), known_tokens=sum(
                c['input_tokens'] + c['output_tokens'] for c in usage if c['status'] == 'ok'),
                unknown_usage_calls=sum(c['status'] != 'ok' for c in usage))
        if (trial / 'terminal_manifest.json').exists():
            summary = json.loads((trial / 'summary.json').read_text())
            row.update(state='generation_ended', submitted=summary['submitted'],
                       stop_reason=summary['stop_reason'])
        rows.append(row)
    return rows


def body(state):
    lines = [MARKER, 'P15：全100195文書を使う全履歴基準・先頭２問の接続確認', '',
             '| 順 | 状態 | 呼出 | 既知トークン | 不明呼出 | 提出 |',
             '|---|---|---:|---:|---:|---|']
    for i, row in enumerate(state['rows'], 1):
        status = {'pending': '待機', 'running': '生成中', 'generation_ended': '生成終了'}[row['state']]
        submitted = '未確定' if row['submitted'] is None else ('あり' if row['submitted'] else 'なし')
        lines.append(f"| {i} | {status} | {row['calls']} | {row['known_tokens']:,} | "
                     f"{row['unknown_usage_calls']} | {submitted} |")
    lines += ['', 'バッチ状態：' + state['status'],
              '各80モデル呼出・80ツール要求・45万総トークン・生成1800秒。検索起動は別途計測。',
              '回答生成と正解判定は別です。この表は成功率ではありません。正解は生成側へ返しません。',
              '事前選定12問の先頭２問のみ、全コーパスは維持。本文や成績による課題の入替えはしません。',
              '[固定条件](https://github.com/sophiria1225/AI-/blob/main/docs/experiments/P15_browsecomp_baseline.md)']
    return '\n'.join(lines) + '\n'


def publish(state, issue):
    endpoint = f'repos/{REPOSITORY}/issues/{issue}'
    text = body(state)
    if state.get('comment_id'):
        comment = f'repos/{REPOSITORY}/issues/comments/{int(state["comment_id"])}'
        previous = gh_api(comment)
        if (previous.get('issue_url') != 'https://api.github.com/' + endpoint
                or not previous.get('body', '').startswith(MARKER)):
            raise ValueError('progress destination changed')
        value = gh_api(comment, method='PATCH', payload={'body': text})
    else:
        previous = gh_api(endpoint)
        if previous.get('html_url') != f'https://github.com/{REPOSITORY}/issues/{issue}':
            raise ValueError('unexpected progress Issue')
        value = gh_api(endpoint + '/comments', method='POST', payload={'body': text})
    state.update(comment_id=value['id'], comment_url=value['html_url'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--freeze-record', type=Path, required=True)
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    plan, frozen = json.loads(args.plan.read_text()), json.loads(args.freeze_record.read_text())
    storage = args.storage_root.resolve()
    check_plan(plan, frozen, args.plan)
    prior = json.loads((storage / 'records/context_pilot/P14_batch_v01/status.json').read_text())
    if prior['status'] != 'complete':
        raise ValueError('P14 must finish before BrowseComp model generation')
    left = (datetime.datetime.fromisoformat(plan['server_lease_end_utc']) -
            datetime.datetime.now(datetime.timezone.utc)).total_seconds()
    if left < 2 * (plan['max_wall_seconds'] + 240) + 300:
        raise ValueError('server lease too short for both questions and setup')
    out = storage / 'records/browsecomp_pilot' / plan['batch_id']
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / 'plan.json', plan); write_json(out / 'freeze_record.json', frozen)
    state = {'status': 'running', 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'active': None, 'process_wall_seconds': {}, 'completed': []}
    last_publish = 0
    def update(force=False):
        nonlocal last_publish
        state['rows'] = collect(storage, plan)
        state['updated_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if args.publish and (force or time.monotonic() - last_publish >= 300):
            try:
                publish(state, plan['progress_issue'])
                state.pop('publish_error', None)
            except Exception as error:
                state['publish_error'] = type(error).__name__
            last_publish = time.monotonic()
        write_json(out / 'status.json', state)
    process = None
    try:
        for query_id, run_id in plan['run_ids'].items():
            check_plan(plan, frozen, args.plan)
            state['active'] = run_id; update(True)
            started = time.monotonic()
            with (out / (run_id + '.log')).open('x') as log:
                process = subprocess.Popen([sys.executable, str(ROOT / 'scripts/run_browsecomp_baseline.py'),
                    '--plan', str(args.plan.resolve()), '--storage-root', str(storage),
                    '--query-id', query_id, '--run-id', run_id], stdout=log, stderr=subprocess.STDOUT)
                while process.poll() is None:
                    update()
                    if time.monotonic() - started > plan['max_wall_seconds'] + 240:
                        raise TimeoutError('trial process exceeded setup plus execution allowance')
                    time.sleep(15)
            state['process_wall_seconds'][run_id] = time.monotonic() - started
            if process.returncode:
                raise RuntimeError('trial process failed; no automatic retry or replacement')
            summary, _ = load_terminal(storage / 'records/browsecomp_pilot' / run_id)
            state['completed'].append(run_id)
            state.setdefault('terminal_manifest_sha256', {})[run_id] = digest(
                storage / 'records/browsecomp_pilot' / run_id / 'terminal_manifest.json')
            update(True)
        state.update(status='generation_complete_evaluation_pending', active=None)
    except BaseException as error:
        state.update(status='runtime_error', error_type=type(error).__name__)
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=10)
        raise
    finally:
        state['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        update(True)


if __name__ == '__main__':
    main()
