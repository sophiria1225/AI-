"""Publish all 24 P122 conditions and descriptive paired differences."""
import argparse
import json
from pathlib import Path

from build_required_inline_checkpoint_summary import aggregate, write_csv
from receipt_reasoning_history import require
from run_handoff_factors import ROOT, read, sha
from whole_task_checkpoint_replication import POLICIES, SEEDS, TASKS, cell_id, run_order


def build(root):
    target = root / 'materials/20261025_p122_results'
    require(not target.exists(), 'preserve_all_P122_materials')
    report = read(root / 'reports/P122_comparison.json')
    session = read(root / 'reports/P122_server_session.json')
    prior = read(root / 'reports/P120_comparison.json')
    expected = [(cell_id(rep, n, p), rep, SEEDS[rep - 1], TASKS[n - 1], p)
                for rep, n, p in run_order()]
    require(report['phase'] == 'P122' and not report['audit_errors'] and report['owned_processes_absent']
            and [(r['run_id'], r['repetition'], r['model_seed'], r['task_id'], r['checkpoint_policy'])
                 for r in report['rows']] == expected, 'all_24_audited_slots_required')
    require(session['phase'] == 'P122' and session['owned_processes_absent']
            and session['audit_source_sha256'] == sha(root / 'reports/P122_comparison.json'),
            'closed_P122_session_required')
    target.mkdir(parents=True)
    identity_fields = ['run_id', 'repetition', 'model_seed', 'task_id', 'checkpoint_policy']
    fields = identity_fields + ['record_status', 'success', 'stop_reason', 'model_calls',
        'known_total_tokens', 'unknown_usage_calls', 'api_requests', 'input_tokens',
        'output_tokens', 'cached_input_tokens', 'wall_seconds', 'checkpoint_installed', 'checkpoint_opportunity']
    write_csv(target / 'all_conditions.csv', fields, report['rows'])
    calls, controls, roles, pairs = [], [], [], []
    for row in report['rows']:
        identity = {k: row[k] for k in identity_fields}
        calls += [{**identity, **call} for call in row.get('request_checks', [])]
        controls += [{**identity, **event} for event in row.get('checkpoint_controls', [])]
        roles += [{**identity, 'role': role, **usage} for role, usage in row.get('usage_by_role', {}).items()]
    for task in report['task_summaries']:
        pairs += [{'task_id': task['task_id'], **pair} for pair in task['pairs']]
    write_csv(target / 'all_model_calls.csv', identity_fields + ['call_id', 'role', 'status',
        'input_tokens', 'output_tokens', 'cached_input_tokens', 'finish_reason', 'API_requests',
        'request_sha256', 'response_sha256'], calls)
    write_csv(target / 'all_controls.csv', identity_fields + ['after_model_calls', 'status',
        'trigger_input_tokens', 'model_attempted', 'summary_calls', 'summary_known_tokens',
        'unknown_usage_calls', 'dispatched_without_terminal_usage', 'ordinary_next_input_tokens',
        'checkpoint_next_input_tokens', 'control_wall_seconds', 'split_status', 'accepted',
        'reason', 'ordinary_input_tokens', 'compacted_input_tokens',
        'transport_metadata_hidden', 'semantics_verified'], controls)
    write_csv(target / 'role_costs.csv', identity_fields + ['role', 'calls', 'unknown_usage',
        'input_tokens', 'output_tokens'], roles)
    write_csv(target / 'all_pairs.csv', ['task_id', 'repetition', 'model_seed',
        'both_evaluated', 'both_usage_known', 'separate_success', 'inline_success',
        'both_successful', 'success_lost', 'difference_tokens',
        'difference_percent_of_separate', 'separate_installed', 'inline_installed'], pairs)
    old_index = {(r['task_id'], r['checkpoint_policy']): r for r in prior['rows']}
    same_seed = []
    for row in report['rows']:
        if row['repetition'] != 1:
            continue
        old = old_index[row['task_id'], row['checkpoint_policy']]
        exact = all(type(r.get('known_total_tokens')) is int and r.get('unknown_usage_calls') == 0
                    for r in (row, old))
        same_seed.append({k: row[k] for k in identity_fields} | {
            'prior_run_id': old['run_id'], 'prior_success': old.get('success'),
            'new_success': row.get('success'), 'both_usage_known': exact,
            'new_minus_prior_tokens': row['known_total_tokens'] - old['known_total_tokens'] if exact else None,
            'prior_model_calls': old.get('model_calls'), 'new_model_calls': row.get('model_calls'),
            'prior_API_requests': old.get('api_requests'), 'new_API_requests': row.get('api_requests'),
            'identical_trajectory_claim': False, 'pooled_into_primary_analysis': False})
    write_csv(target / 'same_seed_prior_comparison.csv', identity_fields + ['prior_run_id',
        'prior_success', 'new_success', 'both_usage_known', 'new_minus_prior_tokens',
        'prior_model_calls', 'new_model_calls', 'prior_API_requests', 'new_API_requests',
        'identical_trajectory_claim', 'pooled_into_primary_analysis'], same_seed)
    overview = {'phase': 'P122', **aggregate(report['rows']),
        'by_policy': {p: aggregate([r for r in report['rows'] if r['checkpoint_policy'] == p]) for p in POLICIES},
        'by_repetition': {str(rep): aggregate([r for r in report['rows'] if r['repetition'] == rep]) for rep in range(1, 4)},
        'task_summaries': report['task_summaries'], 'repetition_summaries': report['repetition_summaries'],
        'replication_gate_met': report['replication_gate_met'],
        'photo_reduction_repeated_with_success': report['photo_reduction_repeated_with_success'],
        'model_seeds': list(SEEDS), 'unique_known_tasks': 4,
        'all_model_and_summary_costs_included': True,
        'model_calls_in_materials': len(calls), 'paired_comparisons': len(pairs),
        'prior_P120_pooled_into_primary_analysis': False, 'novel_method_claim': False,
        'statistical_significance_claim': False, 'inferential_noninferiority_claim': False,
        'general_quality_preservation_claim': False, 'confidence_intervals_reported': False,
        'new_model_API_evaluation_or_tokenizer_calls': 0}
    (target / 'summary.json').write_text(json.dumps(overview, ensure_ascii=False, indent=2) + '\n')
    (target / 'README.md').write_text('''# P122: 同時要約のばらつきを全４課題・固定３設定で確認

同じ既知４課題×２方式×３設定の全24枠を含む. モデルseedは57、157、257で、world seed42、要約方法、指示、予算はP120と同じ. 中央の反復で方式順を反転した. 追加モデル生成は終了した実記録のみにあり、この資料builderは生成、API、評価、token計数を行わない.

各課題の３対を別々に示し、全３対の費用が既知の場合だけ平均、中央値、最小、最大、標本標準偏差を出す. 全３対の成否も併記する. 失敗して安く終わった差を品質維持の削減としない. 一部の費用が不明な場合、既知分は部分集合として残し、全３対の統計量を補完しない.

これは少数の固定seedによる記述的確認で、統計的有意差や非劣性、未見課題への一般化を示す試験ではない. 24実行を独立24課題とは数えない. 要約未起動の成功を要約の追加成功例へ数えず、P120の元の7.50%や失敗と合算して主解析を作らない. 同じseed57の以前との差は別の参考表で、数値一致だけから軌跡の完全一致は主張しない.

[全条件](all_conditions.csv)／[全12対](all_pairs.csv)／[全モデル要求](all_model_calls.csv)／[制御判断](all_controls.csv)／[役割別費用](role_costs.csv)／[同じseedの以前との差](same_seed_prior_comparison.csv)／[集計](summary.json)／[固定計画](../../docs/experiments/P122_checkpoint_replication.md).
''')
    sources = ('reports/P122_comparison.json', 'reports/P122_server_session.json',
        'reports/P120_comparison.json', 'configs/P122_checkpoint_replication_v01.json',
        'scripts/build_checkpoint_replication_summary.py', 'scripts/build_required_inline_checkpoint_summary.py')
    manifest = {'source_sha256': {p: sha(root / p) for p in sources},
        'artifact_sha256': {p.name: sha(p) for p in sorted(target.iterdir()) if p.is_file()},
        'new_model_calls': 0, 'new_API_requests': 0, 'new_evaluations': 0, 'new_tokenizer_counts': 0}
    (target / 'build_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return overview


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    args = parser.parse_args()
    result = build(args.repo_root)
    print(json.dumps({k: result[k] for k in ('planned_conditions', 'evaluated_conditions', 'replication_gate_met')}))
