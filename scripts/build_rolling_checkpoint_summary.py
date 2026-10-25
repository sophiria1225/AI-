"""Publish all twelve P123 slots and both roles; no model or private trace reads."""
import argparse
import csv
import json
from pathlib import Path

from receipt_reasoning_history import require
from run_handoff_factors import ROOT, read, sha
from whole_task_rolling_checkpoint import POLICIES, cell_id, run_order


def aggregate(rows):
    accounted = [r for r in rows if type(r.get('known_total_tokens')) is int]
    all_accounted = len(accounted) == len(rows)
    unknown = sum(r['unknown_usage_calls'] for r in accounted)
    return {'planned_conditions': len(rows), 'accounted_conditions': len(accounted),
            'evaluated_conditions': sum(type(r.get('success')) is bool for r in rows),
            'successful_conditions': sum(r.get('success') is True for r in rows),
            'recorded_known_tokens': sum(r['known_total_tokens'] for r in accounted),
            'recorded_unknown_usage_calls': unknown,
            'exact_all_condition_tokens': sum(r['known_total_tokens'] for r in rows)
                if all_accounted and unknown == 0 else None,
            'all_conditions_accounted': all_accounted,
            'unknown_usage_is_not_zero': True}


def write_csv(path, fields, rows):
    with path.open('x', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def build(root):
    target = root / 'materials/20261025_p123_results'
    require(not target.exists(), 'preserve_all_P123_materials')
    report = read(root / 'reports/P123_comparison.json')
    session = read(root / 'reports/P123_server_session.json')
    plan = read(root / 'configs/P123_whole_task_rolling_checkpoint_v01.json')
    expected = [(cell_id(n, p), plan['known_tasks'][n - 1]['task_id'], p) for n, p in run_order()]
    require(report['phase'] == 'P123' and not report['audit_errors'] and report['owned_processes_absent'] and
            [(r['run_id'], r['task_id'], r['checkpoint_policy']) for r in report['rows']] == expected,
            'all_twelve_audited_slots_required')
    require(session['phase'] == 'P123' and session['owned_processes_absent'] and
            session['audit_source_sha256'] == sha(root / 'reports/P123_comparison.json'),
            'closed_P123_session_required')
    target.mkdir(parents=True)
    fields = ['run_id', 'task_id', 'checkpoint_policy', 'record_status', 'success', 'stop_reason',
              'model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests',
              'input_tokens', 'output_tokens', 'cached_input_tokens', 'wall_seconds',
              'checkpoint_installed', 'checkpoint_installations', 'checkpoint_opportunity']
    write_csv(target / 'all_conditions.csv', fields, report['rows'])
    calls, controls, roles = [], [], []
    for row in report['rows']:
        identity = {k: row[k] for k in ('run_id', 'task_id', 'checkpoint_policy')}
        calls += [{**identity, **call} for call in row.get('request_checks', [])]
        controls += [{**identity, **event} for event in row.get('checkpoint_controls', [])]
        for role, usage in row.get('usage_by_role', {}).items():
            roles.append({**identity, 'role': role, **usage})
    write_csv(target / 'all_model_calls.csv', ['run_id', 'task_id', 'checkpoint_policy', 'call_id',
        'role', 'status', 'input_tokens', 'output_tokens', 'cached_input_tokens', 'finish_reason',
        'API_requests', 'inline_offered', 'request_sha256', 'response_sha256'], calls)
    write_csv(target / 'all_controls.csv', ['run_id', 'task_id', 'checkpoint_policy',
        'after_model_calls', 'opportunity_index', 'mode', 'revision', 'cutoff', 'status', 'trigger_input_tokens', 'model_attempted', 'summary_calls',
        'summary_known_tokens', 'unknown_usage_calls', 'dispatched_without_terminal_usage',
        'ordinary_next_input_tokens', 'checkpoint_next_input_tokens', 'control_wall_seconds', 'split_status', 'accepted', 'reason',
        'ordinary_input_tokens', 'compacted_input_tokens', 'transport_metadata_hidden',
        'semantics_verified'], controls)
    write_csv(target / 'role_costs.csv', ['run_id', 'task_id', 'checkpoint_policy', 'role',
        'calls', 'unknown_usage', 'input_tokens', 'output_tokens'], roles)
    overview = {'phase': 'P123', **aggregate(report['rows']),
        'by_policy': {p: aggregate([r for r in report['rows'] if r['checkpoint_policy'] == p])
                      for p in POLICIES},
        'ordinary_control_criteria_met': report['development_gate_met'],
        'repeated_control_exercised': report['repeated_control_exercised'],
        'common_success_tasks': report['common_success_tasks'],
        'comparisons': report['comparisons'],
        'summary_cost_included': True, 'model_calls_in_materials': len(calls),
        'archive_and_summary_text_published': False, 'novel_method_claim': False,
        'general_quality_preservation_claim': False, 'manuscript_changed': False}
    (target / 'summary.json').write_text(json.dumps(overview, ensure_ascii=False, indent=2) + '\n')
    pairs = [pair for comparison in report['comparisons'] for pair in comparison['paired_results']]
    write_csv(target / 'all_pairs.csv', ['task_id', 'baseline', 'baseline_success',
        'rolling_inline_success', 'success_lost', 'both_successful',
        'rolling_inline_minus_baseline_tokens'], pairs)
    (target / 'README.md').write_text('# P123: 再要約を含む３方式の仕事全体比較\n\n既知４課題×３方式の全12枠を残す. 単発の別呼出し要約、最大３回の別呼出し要約、最大３回の同時要約を比較する. 各枠は同じ80呼出し、450000入力＋出力トークン、1800作業秒の上限を共有し、追加要約、失敗、制御、後続処理をすべて計上する. 未知使用量を０や上限で補完せず、未実行と未評価も残す.\n\n同時要約は２種類の対照それぞれで成功していた課題を落とさず、４課題合計と３方式すべてで成功した課題の合計で、双方より低い総トークンが必要である. 両方の反復方式で２回以上の採用を実際に確認する. この基準は既知課題の開発判断であり、一般的な品質維持、意味保存、非劣性や新規性を証明しない. 要約の時点、指示、schema、出力配分、後続行動も変わり得る.\n\n[全条件](all_conditions.csv)／[全モデル要求](all_model_calls.csv)／[全制御判断](all_controls.csv)／[役割別費用](role_costs.csv)／[２対照との全組比較](all_pairs.csv)／[完全監査](../../reports/P123_comparison.json).\n\n課題本文、生成推論、要約本文、APIの実データは公開しない. 全条件とサーバが閉じてから生成した資料である. 過去の失敗と未知使用量、未達の採用基準は変更しない.\n')
    sources = ('reports/P123_comparison.json', 'reports/P123_server_session.json',
               'configs/P123_whole_task_rolling_checkpoint_v01.json', 'scripts/build_rolling_checkpoint_summary.py')
    manifest = {'source_sha256': {p: sha(root / p) for p in sources},
                'artifact_sha256': {p.name: sha(p) for p in sorted(target.iterdir()) if p.is_file()},
                'new_model_calls': 0, 'new_API_requests': 0, 'new_evaluations': 0}
    (target / 'build_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return overview


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(build(args.repo_root)))
