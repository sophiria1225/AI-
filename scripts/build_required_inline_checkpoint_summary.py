"""Publish all eight P120 slots and both roles; no model or private trace reads."""
import argparse
import csv
import json
from pathlib import Path

from receipt_reasoning_history import require
from run_handoff_factors import ROOT, read, sha
from whole_task_required_inline_checkpoint import cell_id, run_order


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
    target = root / 'materials/20261025_p120_results'
    require(not target.exists(), 'preserve_all_P120_materials')
    report = read(root / 'reports/P120_comparison.json')
    session = read(root / 'reports/P120_server_session.json')
    plan = read(root / 'configs/P120_whole_task_required_inline_checkpoint_v01.json')
    expected = [(cell_id(n, p), plan['known_tasks'][n - 1]['task_id'], p) for n, p in run_order()]
    require(report['phase'] == 'P120' and not report['audit_errors'] and report['owned_processes_absent'] and
            [(r['run_id'], r['task_id'], r['checkpoint_policy']) for r in report['rows']] == expected,
            'all_eight_audited_slots_required')
    require(session['phase'] == 'P120' and session['owned_processes_absent'] and
            session['audit_source_sha256'] == sha(root / 'reports/P120_comparison.json'),
            'closed_P120_session_required')
    target.mkdir(parents=True)
    fields = ['run_id', 'task_id', 'checkpoint_policy', 'record_status', 'success', 'stop_reason',
              'model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests',
              'input_tokens', 'output_tokens', 'cached_input_tokens', 'wall_seconds',
              'checkpoint_installed', 'checkpoint_opportunity']
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
        'API_requests', 'request_sha256', 'response_sha256'], calls)
    write_csv(target / 'all_controls.csv', ['run_id', 'task_id', 'checkpoint_policy',
        'after_model_calls', 'status', 'trigger_input_tokens', 'model_attempted', 'summary_calls',
        'summary_known_tokens', 'unknown_usage_calls', 'dispatched_without_terminal_usage',
        'ordinary_next_input_tokens', 'checkpoint_next_input_tokens', 'control_wall_seconds', 'split_status', 'accepted', 'reason',
        'ordinary_input_tokens', 'compacted_input_tokens', 'transport_metadata_hidden',
        'semantics_verified'], controls)
    write_csv(target / 'role_costs.csv', ['run_id', 'task_id', 'checkpoint_policy', 'role',
        'calls', 'unknown_usage', 'input_tokens', 'output_tokens'], roles)
    overview = {'phase': 'P120', **aggregate(report['rows']),
        'by_policy': {p: aggregate([r for r in report['rows'] if r['checkpoint_policy'] == p])
                      for p in ('single_checkpoint', 'inline_checkpoint')},
        'ordinary_control_criteria_met': report['development_gate_met'],
        'inline_checkpoint_offer_calls': report['inline_checkpoint_offer_calls'],
        'inline_checkpoint_installations': report['inline_checkpoint_installations'],
        'required_inline_control_exercised': report['required_inline_control_exercised'],
        'summary_cost_included': True, 'model_calls_in_materials': len(calls),
        'archive_and_summary_text_published': False, 'novel_method_claim': False,
        'general_quality_preservation_claim': False, 'manuscript_changed': False}
    (target / 'summary.json').write_text(json.dumps(overview, ensure_ascii=False, indent=2) + '\n')
    (target / 'README.md').write_text('''# P120: 通常の別呼出し要約と必須欄として同じ応答に含める要約の比較

既知４課題×２方式の全８枠、全モデル要求、制御判断、役割別費用を含む. 別呼出し要約と必須欄として同じ応答に含める要約を比較する. 追加する指示とschema、全出力、失敗、不採用、後続処理を共有する仕事予算へ計上する. 未知使用量は０や上限で補完せず、未実行・未評価も残す. 保存した推論、要約本文、課題データ、認証情報は公開しない.

これは通常対照の比較で、PAIRや初期台帳P14の再現、新提案の性能確認ではない. 要約は形式だけを検査し、元の意味の完全な保存を保証しない. ２方式は要約の時点、指示、schema、出力配分、後続行動も変わり得るため、差を要約用入力だけの削減へ帰属させない. 過去P111の採用基準未達と未知２件は変更しない. 原稿と未見12課題は保留する.

[全条件](all_conditions.csv)／[全モデル要求](all_model_calls.csv)／[制御判断](all_controls.csv)／[役割別費用](role_costs.csv)／[完全監査](../../reports/P120_comparison.json).
''')
    sources = ('reports/P120_comparison.json', 'reports/P120_server_session.json',
               'configs/P120_whole_task_required_inline_checkpoint_v01.json', 'scripts/build_required_inline_checkpoint_summary.py')
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
