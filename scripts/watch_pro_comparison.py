"""Observe this bounded batch and update its one authorized GitHub progress comment.

No model calls, experiment retries, configuration changes, or Git commits.
The Issue stays open: result interpretation remains a separate research step.
"""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import time

from summarize_pro_comparison import build_report

REPOSITORY = 'sophiria1225/AI-'
AUTHORIZED_BATCH = 'P5_01'
AUTHORIZED_ISSUE = 24
STAGES = {
    'not_started': '未開始', 'initializing': '準備中', 'running': '実行中',
    'awaiting_evaluation': '独立評価待ち', 'evaluated': '独立評価完了',
    'execution_error': '実行要確認', 'evaluation_error': '評価要確認',
    'audit_error': '記録要確認', 'record_error': '記録読取要確認',
}


def public_body(report, *, observer_finished=False):
    """Allowlist summary fields; never serialize tool outputs or model text."""
    if report['batch_id'] != AUTHORIZED_BATCH:
        raise ValueError('Progress publishing is restricted to P5_01')
    rows = [
        '<!-- harness-batch:P5_01 -->',
        'P5自動進捗（記録の観察のみ）',
        '',
        '更新時刻（UTC）：' + report['at'],
        '',
        '| 方式 | 状態 | 記録済み呼び出し | 記録済み入力＋出力 | 最終結果 |',
        '|---|---|---:|---:|---|',
    ]
    for row in report['runs']:
        strategy = {'fixed_pair': '固定2担当', 'single': '単一'}[row['strategy']]
        calls = str(int(row['recorded_calls'])) if 'recorded_calls' in row else '—'
        tokens = f"{int(row['recorded_tokens']):,}" if 'recorded_tokens' in row else '—'
        outcome = '未確定'
        if row['stage'] == 'evaluated':
            value = row['result']['measurements']['evaluation']['resolved']
            if type(value) is not bool:
                raise ValueError('Final resolution must be Boolean')
            outcome = '解決' if value else '未解決'
        rows.append(f"| {strategy} | {STAGES[row['stage']]} | {calls} | {tokens} | {outcome} |")
    rows += [
        '',
        '両方式は60呼び出し・60万トークン・最大120分。未開始や実行中は失敗に数えません。',
        '計画に固定した順に各1回実行し、基盤異常時の自動再試行は行いません。',
        '1課題・各1回の開発観察です。品質維持・一般的な費用削減・再編効果は、この表だけでは確定しません。',
        '完了してもIssueは閉じず、公開操作の分析と考察を別に記録します。',
        '',
        '[固定計画・選択理由](https://github.com/sophiria1225/AI-/blob/research/pro-fixed-pair-observation/docs/experiments/P5_pro_comparison.md)',
        '[研究説明資料（P4終了時点）](https://github.com/sophiria1225/AI-/tree/main/materials/20261020)',
    ]
    if observer_finished:
        rows += ['', 'このバッチの自動進捗監視を終了しました。上の状態が未完了の場合、完了とは扱いません。']
    return '\n'.join(rows) + '\n'


def gh_api(endpoint, *, method='GET', payload=None):
    allowed = f'repos/{REPOSITORY}/issues/'
    if not endpoint.startswith(allowed):
        raise ValueError('GitHub endpoint outside the authorized repository')
    command = ['gh', 'api', endpoint, '--method', method]
    if payload is not None:
        command += ['--input', '-']
    result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                            text=True, capture_output=True, timeout=45, check=False)
    if result.returncode:
        raise RuntimeError('GitHub progress request failed with exit ' + str(result.returncode))
    return json.loads(result.stdout)


def publish(body, state):
    issue_endpoint = f'repos/{REPOSITORY}/issues/{AUTHORIZED_ISSUE}'
    if state.get('comment_id'):
        endpoint = f'repos/{REPOSITORY}/issues/comments/{int(state["comment_id"])}'
        existing = gh_api(endpoint)
        expected_issue = f'https://api.github.com/repos/{REPOSITORY}/issues/{AUTHORIZED_ISSUE}'
        if existing.get('issue_url') != expected_issue:
            raise ValueError('Saved comment belongs to another Issue')
        if not existing.get('body', '').startswith('<!-- harness-batch:P5_01 -->'):
            raise ValueError('Saved comment marker differs')
        result = gh_api(endpoint, method='PATCH', payload={'body': body})
    else:
        issue = gh_api(issue_endpoint)
        if issue.get('html_url') != f'https://github.com/{REPOSITORY}/issues/{AUTHORIZED_ISSUE}':
            raise ValueError('Unexpected Issue identity')
        result = gh_api(issue_endpoint + '/comments', method='POST', payload={'body': body})
    state.update(comment_id=result['id'], comment_url=result['html_url'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--max-seconds', type=int, default=21600)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.max_seconds <= 21600:
        raise ValueError('Observer must be bounded to at most six hours')
    storage = args.storage_root.resolve()
    directory = storage/'records/pro_batches'/AUTHORIZED_BATCH/'observer'
    directory.mkdir(exist_ok=False)
    state = {'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'max_seconds': args.max_seconds, 'publish': args.publish, 'status': 'running'}
    path = directory/'summary.json'
    started, last_published, signature = time.monotonic(), None, None
    transient_errors = 0
    try:
        while True:
            try:
                report = build_report(storage, AUTHORIZED_BATCH)
                transient_errors = 0
            except (OSError, ValueError, KeyError):
                transient_errors += 1
                if transient_errors >= 3:
                    raise
                time.sleep(1)
                continue
            current = [(r['trial_id'], r['stage']) for r in report['runs']]
            terminal = report['batch_status'] in ('completed', 'error')
            timeout = time.monotonic() - started >= args.max_seconds
            finished = terminal or timeout
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            state.update(last_checked_at=now, batch_status=report['batch_status'],
                         comparison_status=report['comparison_status'],
                         trials=current, recorded_tokens=report['recorded_tokens_so_far'])
            (directory/'latest_measurements.json').write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            body = public_body(report, observer_finished=finished)
            (directory/'progress.md').write_text(body)
            due = (last_published is None or current != signature
                   or time.monotonic() - last_published >= 600 or finished)
            if args.publish and due:
                try:
                    publish(body, state)
                    state['last_published_at'] = now
                    state.pop('publish_error', None)
                except (ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
                    state['publish_error'] = type(error).__name__
                last_published, signature = time.monotonic(), current
            if finished:
                state['status'] = 'batch_terminal' if terminal else 'observer_timeout'
            path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
            if finished:
                break
            time.sleep(30)
    except Exception as error:
        state.update(status='observer_error', error_type=type(error).__name__)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
        raise
    print(json.dumps(state), flush=True)


if __name__ == '__main__':
    main()
