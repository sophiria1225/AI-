"""Frozen eight-cell budget-awareness baseline, on known development prefixes."""
import argparse
import datetime as dt
import json
from pathlib import Path
import signal
import subprocess

from budget_signal import ARMS, add_notification, digest, snapshot
from code_agent_interface import CODE_TOOLS
from handoff_factors import handoff_conversation
from later_handoff_sources import prepare_later_sources
from local_llama import count_input
from probe_inference_cache import live_identity
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha, run_branch


def sources(storage, root):
    prior, original, tools, schemas, prepared = prepare_later_sources(storage, root)
    plan = read(root / 'configs/P40_budget_notification_v01.json')
    if plan['phase'] != 'P40' or plan['arms'] != list(ARMS):
        raise ValueError('outside the fixed two-condition budget baseline')
    for key in ('source_plan', 'source_runs', 'boundary_after_model_calls', 'max_calls',
                'max_total_tokens', 'max_wall_seconds', 'max_setup_seconds', 'recent_complete_turns'):
        if plan[key] != prior[key]:
            raise ValueError('original sources or budgets changed: ' + key)
    calibration = read(root / 'reports/P39_calibration_audit.json')
    if (not calibration['all_six_validated'] or calibration['unknown_usage_calls']
            or calibration['source_report_sha256'] != sha(root / 'reports/P39_inference_cache_v02.json')):
        raise ValueError('P39 calibration is not closed and audited')
    previous = read(root / 'reports/P33_prefix_checks.json')
    if (not previous['all_four_attempted'] or not previous['all_observable_prefixes_match']
            or [r['boundary_manifest_sha256'] for r in previous['rows']] !=
               [p['boundary_manifest_sha256'] for p in prepared]):
        raise ValueError('common restoration evidence does not cover these exact boundaries')
    return plan, original, tools, schemas, prepared


def frozen_hashes(root):
    paths = list((root / 'scripts').glob('*.py'))
    paths += [root / p for p in ('configs/P40_budget_notification_v01.json',
        'configs/P29_stateful_code_v01.json', 'configs/python_export_image_v01.json',
        'docs/experiments/P40_budget_notification.md', 'reports/P39_calibration_audit.json',
        'reports/P39_inference_cache_v02.json', 'reports/P33_prefix_checks.json',
        'reports/P40_budget_visibility.json', 'tests/test_budget_signal.py',
        'tests/test_budget_visibility.py', 'tests/test_budget_notification_plan.py')]
    return {str(p.relative_to(root)): sha(p) for p in sorted(paths)}


def run_order(prepared):
    return [(number, item, arm) for number, item in enumerate(prepared, 1)
            for arm in (ARMS if number % 2 else ARMS[::-1])]


def preflight(storage, root):
    plan, original, _, _, prepared = sources(storage, root)
    identity, end = live_identity(storage, original, 120)
    output = storage / 'records/context_pilot/P40_preflight_v01'
    target = root / 'reports/P40_prefix_checks.json'
    if output.exists() or target.exists():
        raise FileExistsError('preserve preflight records')
    output.mkdir(); rows = []
    for item in prepared:
        prefix = item['prefix']
        view, _ = handoff_conversation(prefix['conversation_private'], prefix['public_task'], 'full_keep', 8)
        base, _ = view.for_model(original['observation_page_characters'])
        config = {**original, **{k: plan[k] for k in ('max_calls', 'max_total_tokens', 'max_wall_seconds')},
                  'max_api_requests': original['api_budget_by_task'][item['task_id']]}
        state = snapshot(config, [], prefix['manifest']['state']['api_requests'], 0, 0)
        cell = {'source_run': item['source_run'], 'boundary_manifest_sha256': item['boundary_manifest_sha256'],
                'base_messages_sha256': digest(base), 'conditions': {}}
        for arm in ARMS:
            messages = add_notification(base, state, arm)
            if arm == 'budget_keep' and messages[:-1] != base:
                raise ValueError('notification changed existing input')
            cfg = {**original['model'], 'temperature': original['agent_temperature'],
                   'seed': original['seed'] + 8, 'num_predict': original['max_output_tokens'],
                   'cache_prompt': False}
            count = count_input(cfg, messages, CODE_TOOLS)
            if count['input_tokens'] + cfg['num_predict'] > min(cfg['num_ctx'], plan['max_total_tokens']):
                raise ValueError('input does not fit the unchanged resource limit')
            p = output / (item['source_run'] + '_' + arm + '_private.json')
            write_json(p, messages)
            cell['conditions'][arm] = {'input_tokens': count['input_tokens'],
                'input_sha256': sha(p), 'notification_characters': len(messages[-1]['content']) if arm == 'budget_keep' else 0}
        cell['notification_input_token_increment'] = (cell['conditions']['budget_keep']['input_tokens'] -
                                                       cell['conditions']['plain_keep']['input_tokens'])
        rows.append(cell)
    result = {'phase': 'P40_preflight', 'all_eight_inputs_checked': len(rows) == 4,
              'rows': rows, 'model_identity': identity, 'server_lease_end': end,
              'prepared_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'source_hashes': frozen_hashes(root), 'model_calls': 0, 'environment_api_requests': 0,
              'evaluator_calls': 0, 'input_count_requests': 8,
              'restoration_evidence_reused': 'reports/P33_prefix_checks.json',
              'restoration_rechecked_before_each_generation': True}
    write_json(output / 'summary.json', result); write_json(target, result)
    print(json.dumps({k: result[k] for k in ('all_eight_inputs_checked', 'input_count_requests', 'model_calls')}))


def activate(root):
    target = root / 'reports/P40_activation_v01.json'
    if target.exists(): raise FileExistsError('preserve activation')
    pre = read(root / 'reports/P40_prefix_checks.json')
    if not pre['all_eight_inputs_checked'] or pre['source_hashes'] != frozen_hashes(root):
        raise ValueError('preparation is stale')
    write_json(target, {'phase': 'P40', 'source_hashes': pre['source_hashes'],
        'preflight_sha256': sha(root / 'reports/P40_prefix_checks.json'),
        'source_boundaries': [r['boundary_manifest_sha256'] for r in pre['rows']],
        'all_eight_conditions_frozen_before_inference': True})


def publish_status(status, output):
    from watch_pro_comparison import gh_api
    marker = '<!-- harness-budget-awareness:P40_batch_v01 -->'
    issue = 191
    active = status.get('active') if status['status'] == 'running' else None
    lines = [marker, 'P40：予算通知の有無を比べる既存方式の対照実験',
        f"状態：{status['status']}／評価済 {len(status['completed'])}/8／実行中 {active or 'なし'}", '',
        '| 課題 | 条件 | 成功 | AI呼出し | 既知token | 使用量不明 | 後続API |', '|---|---|---:|---:|---:|---:|---:|']
    for r in status['rows']:
        lines.append(f"| {r['task_id']} | {r['arm']} | {r.get('success','未評価')} | {r['model_calls']} | {r['known_total_tokens']:,} | {r.get('unknown_usage_calls',0)} | {r['api_requests']} |")
    if status['status'] == 'stopped':
        lines += ['', f"事前規則でバッチ停止。未実行は {8 - len(status['rows'])} 条件。",
                  '使用量不明分は既知tokenへの追加であり、０として計上していません。４課題の比較は未完遂です。',
                  '置換試行や予算延長はせず、評価済み・未評価・未実行を分けて終了監査します。']
    lines += ['', '同じ４既知課題の８応答後から、全履歴・Python状態を維持。残予算通知だけを変更。',
        '初回は両方式とも推論キャッシュ再利用なし。通知と復元の費用、失敗も記録する。',
        '全件終了前に優劣を確定しない。予算通知自体は先行研究があり、新規性の主張はしない。']
    body = '\n'.join(lines); (output / 'progress.md').write_text(body + '\n')
    try:
        if status.get('comment_id'):
            endpoint = f"repos/sophiria1225/AI-/issues/comments/{int(status['comment_id'])}"
            old = gh_api(endpoint)
            if (not old.get('body', '').startswith(marker) or
                    old.get('issue_url') != f'https://api.github.com/repos/sophiria1225/AI-/issues/{issue}'):
                raise ValueError('progress target differs')
            result = gh_api(endpoint, method='PATCH', payload={'body': body})
        else:
            old = gh_api(f'repos/sophiria1225/AI-/issues/{issue}')
            if not old.get('body', '').startswith('<!-- harness-task:R65 -->'):
                raise ValueError('task issue differs')
            result = gh_api(f'repos/sophiria1225/AI-/issues/{issue}/comments', method='POST', payload={'body': body})
        status.update(comment_id=result['id'], comment_url=result['html_url'])
        status.pop('publish_error', None)
    except Exception as error:
        status['publish_error'] = type(error).__name__


def run(storage, root, publish=False):
    plan, original, tools, schemas, prepared = sources(storage, root)
    freeze = read(root / 'reports/P40_activation_v01.json')
    preflight_record = read(root / 'reports/P40_prefix_checks.json')
    if (freeze['source_hashes'] != frozen_hashes(root)
            or freeze['preflight_sha256'] != sha(root / 'reports/P40_prefix_checks.json')
            or freeze['source_boundaries'] != [p['boundary_manifest_sha256'] for p in prepared]):
        raise ValueError('frozen experiment changed')
    order = run_order(prepared)
    max_cell_seconds = plan['max_setup_seconds'] + plan['max_wall_seconds'] + 180 + 60
    identity, end = live_identity(storage, original, len(order) * max_cell_seconds)
    if identity != preflight_record['model_identity']:
        raise ValueError('prepared server identity changed')
    folder = storage / 'records/context_pilot' / plan['batch_id']
    folder.mkdir(exist_ok=False)
    write_json(folder / 'frozen_plan.json', plan); write_json(folder / 'activation.json', freeze)
    state = {'phase': 'P40', 'status': 'running', 'rows': [], 'completed': [], 'active': None,
             'started_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'model_identity': identity,
             'server_lease_end': end,
             'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()}
    def save():
        state['updated_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        if publish: publish_status(state, folder)
        write_json(folder / 'status.json', state)
    try:
        for number, item, arm in order:
            if (storage / '.runtime/P40.stop').exists():
                raise InterruptedError('user stop requested')
            current, _ = live_identity(storage, original, max_cell_seconds)
            if current != identity:
                raise ValueError('same idle inference runtime required')
            rid = f'P40_{number:02d}_{arm.upper()}'
            state['active'] = rid; save()
            result = run_branch(storage, root, plan, original, tools, schemas, item, arm, rid)
            row = {k: result[k] for k in ('run_id', 'task_id', 'arm', 'stop_reason', 'model_calls',
                'known_total_tokens', 'unknown_usage_calls', 'api_requests', 'prefix_api_requests', 'wall_seconds')}
            state['rows'].append(row)
            if (result['setup']['status'] != 'matched_observable_prefix'
                    or result['unknown_usage_calls'] or result['unknown_effect_requests']
                    or result['stop_reason'] in ('runtime_error', 'cleanup_error', 'setup_failure')):
                raise ValueError('cell ended with unknown usage/effects, restoration or runtime failure')
            evaluated = subprocess.run([str(storage / '.runtime/appworld/venv/bin/python'),
                str(root / 'scripts/evaluate_context_trial.py'), '--appworld-root',
                str(storage / '.runtime/appworld/r18_probe_01'), '--trial',
                str(storage / 'records/context_pilot' / rid)], capture_output=True, text=True, timeout=180)
            (folder / (rid + '_evaluation.log')).write_text(evaluated.stdout + evaluated.stderr)
            if evaluated.returncode:
                raise ValueError('independent evaluation failed')
            row['success'] = read(storage / 'records/context_pilot' / rid / 'evaluation.json')['official_success']
            state['completed'].append(rid); save(); print(json.dumps(row), flush=True)
        state.update(status='complete', active=None, finished_at=dt.datetime.now(dt.timezone.utc).isoformat())
    except Exception as error:
        state.update(status='stopped', error_type=type(error).__name__)
        (folder / 'error_private.txt').write_text(str(error))
    finally:
        save()
    return 0 if state['status'] == 'complete' else 1


def timeout(*_): raise TimeoutError('bounded research execution interrupted')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT); p.add_argument('--publish', action='store_true')
    modes = p.add_mutually_exclusive_group()
    modes.add_argument('--preflight', action='store_true'); modes.add_argument('--activate', action='store_true')
    a = p.parse_args(); signal.signal(signal.SIGALRM, timeout); signal.signal(signal.SIGTERM, timeout)
    if a.preflight: preflight(a.storage_root, a.repo_root)
    elif a.activate: activate(a.repo_root)
    else: raise SystemExit(run(a.storage_root, a.repo_root, a.publish))
