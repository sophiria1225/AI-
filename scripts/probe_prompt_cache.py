"""Bounded input-order timing control; never executes generated tools or grades tasks."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time
import urllib.request

from audit_context_costs import archive_last
from local_llama import count_input, model_call, payload_for
from model_provenance import check_live_model
from run_context_comparison import write_json
from watch_pro_comparison import gh_api

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'sophiria1225/AI-'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_frozen(frozen):
    for name, value in frozen['source_hashes'].items():
        if digest(ROOT / name) != value:
            raise RuntimeError('frozen cache probe changed')


def payload_config(plan, source, stage):
    config = dict(plan['model'], seed=source['seed'], temperature=source['temperature'],
                  num_predict=1, cache_prompt=stage == 'target')
    expected = dict(source, max_tokens=1, cache_prompt=stage == 'target')
    if payload_for(config, source['messages'], source['tools']) != expected:
        raise ValueError('source sampling or tool settings would change')
    return config


def public_body(state):
    # Explicit numeric whitelist: no model output or source input can be posted.
    lines = ['<!-- harness-cache-probe:P9_01 -->', 'P9：履歴の並び順と入力再処理の校正', '',
             '| 組 | 配置 | 段階 | 入力 | キャッシュ | 再処理 | 入力処理秒 |',
             '|---:|---|---|---:|---:|---:|---:|']
    for row in state['rows']:
        if row['variant'] not in ('original', 'archive_last') or row['stage'] not in ('warm', 'target'):
            raise ValueError('invalid public probe category')
        values = [str(int(row[key])) if row.get(key) is not None else '—'
                  for key in ('input_tokens', 'cached_input_tokens', 'processed_input_tokens')]
        seconds = f"{float(row['prompt_seconds']):.3f}" if row.get('prompt_seconds') is not None else '—'
        lines.append(f"| {int(row['pair'])} | {row['variant']} | {row['stage']} | "
                     f"{' | '.join(values)} | {seconds} |")
    labels = {'waiting': 'P8終了待ち', 'running': '計測中', 'complete': '固定8呼び出し終了',
              'prerequisite_failed': '前段要確認のため未開始',
              'lease_too_short': 'サーバー残時間不足のため未開始',
              'runtime_error': '異常または使用量不明で停止', 'budget_stop': '予算上限で停止'}
    lines += ['', labels[state['status']],
              f"既知 {int(state['known_total_tokens']):,} トークン、不明 {int(state['unknown_usage_calls'])} 呼び出し。",
              '保存した同じ隣接2入力を使用。生成は各1トークン、環境操作・最終評価は0回。',
              '入力再処理を測る校正で、タスク成功・品質維持・新手法の検証ではありません。',
              '組の先頭はcache_prompt=false、次はtrue。順序は原配置→変更→変更→原配置。']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--freeze-record', type=Path, required=True)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    storage = args.storage_root.resolve()
    plan = json.loads(args.plan.read_text())
    frozen = json.loads(args.freeze_record.read_text())
    if (plan['run_id'] != 'P9_01' or plan['order'] != [
            'original', 'archive_last', 'archive_last', 'original'] or plan['max_calls'] != 8):
        raise ValueError('outside the fixed eight-call control')
    check_frozen(frozen)
    out = storage / 'records/cache_probe' / plan['run_id']
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / 'plan.json', plan)
    write_json(out / 'freeze_record.json', frozen)
    for name in frozen['source_hashes']:
        target = out / 'source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    state = dict(status='waiting', rows=[], known_total_tokens=0, unknown_usage_calls=0,
                 started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 git_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip())
    last_publish = 0

    def update(force=False):
        nonlocal last_publish
        body = public_body(state)
        (out / 'progress.md').write_text(body)
        if args.publish and (force or time.monotonic() - last_publish >= 300):
            try:
                issue = int(plan['progress_issue'])
                endpoint = f'repos/{REPOSITORY}/issues/{issue}'
                if state.get('comment_id'):
                    endpoint = f'repos/{REPOSITORY}/issues/comments/{int(state["comment_id"])}'
                    previous = gh_api(endpoint)
                    if (previous['issue_url'] != f'https://api.github.com/repos/{REPOSITORY}/issues/{issue}'
                            or not previous['body'].startswith('<!-- harness-cache-probe:P9_01 -->')):
                        raise ValueError('unexpected progress destination')
                    value = gh_api(endpoint, method='PATCH', payload={'body': body})
                else:
                    if gh_api(endpoint)['html_url'] != f'https://github.com/{REPOSITORY}/issues/{issue}':
                        raise ValueError('unexpected Issue')
                    value = gh_api(endpoint + '/comments', method='POST', payload={'body': body})
                state.update(comment_id=value['id'], comment_url=value['html_url'])
                state.pop('publish_error', None)
            except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
                state['publish_error'] = type(exc).__name__
            last_publish = time.monotonic()
        state['updated_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_json(out / 'status.json', state)

    def timeout(_signum, _frame):
        raise TimeoutError('local inference deadline')
    signal.signal(signal.SIGALRM, timeout)
    update(True)
    waiting = time.monotonic()
    while True:
        prerequisite = json.loads((storage / 'records/context_pilot' / plan['wait_for_batch'] / 'status.json').read_text())
        if prerequisite['status'] == 'complete':
            break
        if (prerequisite['status'] not in ('waiting', 'running')
                or time.monotonic() - waiting > plan['max_wait_seconds']):
            state['status'] = 'prerequisite_failed'
            update(True)
            return 1
        update()
        time.sleep(30)
    remaining = (datetime.datetime.fromisoformat(plan['server_lease_end_utc'])
                 - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
    if remaining < plan['max_wall_seconds'] + 120:
        state['status'] = 'lease_too_short'
        update(True)
        return 1
    started = time.monotonic()
    try:
        check_frozen(frozen)
        runtime = json.loads((storage / '.runtime/model_server.json').read_text())
        with urllib.request.urlopen(plan['model']['base_url'] + '/props', timeout=10) as response:
            props = json.load(response)
        check_live_model(plan['model_selection'], runtime, props, root=storage,
                         expected_ctx=plan['model']['num_ctx'], expected_cache=('q8_0', 'q8_0'))
        write_json(out / 'provenance.json', {'runtime': runtime, 'props': props})
        sources = []
        for item in plan['sources']:
            path = storage / 'records/context_pilot' / plan['source_run_id'] / item['call_id'] / 'request.json'
            if digest(path) != item['sha256']:
                raise RuntimeError('frozen source request changed')
            sources.append(json.loads(path.read_text()))
        if len(sources) != 2:
            raise ValueError('exactly two adjacent saved requests required')
        state['status'] = 'running'
        state['inference_started_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        update(True)
        for pair, variant in enumerate(plan['order'], 1):
            for stage, source in zip(('warm', 'target'), sources, strict=True):
                check_frozen(frozen)
                request = archive_last(source) if variant == 'archive_last' else source
                cfg = payload_config(plan, request, stage)
                left = plan['max_wall_seconds'] - (time.monotonic() - started)
                if left <= 0:
                    state['status'] = 'budget_stop'
                    return 1
                predicted = count_input(cfg, request['messages'], request['tools'], timeout=min(60, left))['input_tokens']
                if (state['known_total_tokens'] + predicted + 1 > plan['max_total_tokens']
                        or predicted + 1 > cfg['num_ctx']):
                    state['status'] = 'budget_stop'
                    return 1
                left = plan['max_wall_seconds'] - (time.monotonic() - started)
                if left <= 0:
                    state['status'] = 'budget_stop'
                    return 1
                call_id = f"call_{len(state['rows']) + 1:03d}"
                path = out / call_id
                path.mkdir()
                result = model_call(cfg, request['messages'], path, left, request['tools'])
                timing = result.get('timings') or {}
                row = {'id': call_id, 'pair': pair, 'variant': variant, 'stage': stage,
                       'status': result['status'], 'input_tokens': result['input_tokens'],
                       'output_tokens': result['output_tokens'],
                       'predicted_input_tokens': predicted,
                       'cached_input_tokens': result.get('cached_input_tokens'),
                       'processed_input_tokens': timing.get('prompt_n'),
                       'prompt_seconds': timing['prompt_ms'] / 1000 if 'prompt_ms' in timing else None,
                       'decode_seconds': timing['predicted_ms'] / 1000 if 'predicted_ms' in timing else None,
                       'wall_seconds': result['wall_seconds'],
                       'request_sha256': digest(path / 'request.json'),
                       'response_sha256': digest(path / 'response.json')}
                state['rows'].append(row)
                if result['status'] != 'ok':
                    state['unknown_usage_calls'] += 1
                    raise RuntimeError('unknown terminal usage; no retry')
                state['known_total_tokens'] += result['input_tokens'] + result['output_tokens']
                if (result['input_tokens'] != predicted or result['output_tokens'] > 1
                        or timing.get('cache_n', -1) + timing.get('prompt_n', -1) != predicted):
                    raise RuntimeError('terminal timing or input count mismatch')
                if stage == 'warm' and result['cached_input_tokens'] != 0:
                    raise RuntimeError('cold prefix not isolated; stop without repeating')
                update(True)
        state['status'] = 'complete'
    except Exception as exc:
        state.update(status='runtime_error', error_type=type(exc).__name__)
        write_json(out / 'error_private.json', {'type': type(exc).__name__, 'message': str(exc)})
    finally:
        state.update(finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     probe_wall_seconds=time.monotonic() - started)
        update(True)
    return 0 if state['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
