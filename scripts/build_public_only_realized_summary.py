"""Publish all P115 input slots and keep P111 references distinct from P114."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from build_realized_history_summary import csvfile
from measure_receipt_history import read, sha, write_new
from receipt_reasoning_history import require


def build(root):
    source = root/'reports/P115_realized_history_inputs.json'
    data = read(source)
    plan = read(root/'configs/P115_realized_history_inputs_v01.json')
    audit = read(root/'reports/P114_comparison.json')
    historical = read(root/'reports/P111_comparison.json')
    require(len(data['cells']) == 4 and {c['run_id'] for c in data['cells']} == set(plan['run_ids'])
            and len(data['rows']) == plan['planned_renderings']
            and data['source_audit_sha256'] == sha(root/'reports/P114_comparison.json')
            and data['historical_reference_audit_sha256'] == sha(root/'reports/P111_comparison.json')
            and len(historical['rows']) == 12, 'all_new_and_historical_conditions_required')
    by_id = {c['run_id']: c for c in data['cells']}
    cells = [by_id[rid] for rid in plan['run_ids']]
    folder = root/'materials/20261025_p115_results'
    folder.mkdir()
    inputs = []
    for row in data['rows']:
        projection = row.get('projection', {})
        inputs.append(dict(**row, removed_turns=json.dumps(projection.get('removed_reasoning_turns')),
            redisplayed_turns=json.dumps(projection.get('redisplayed_reasoning_turns'))))
    csvfile(folder/'all_inputs.csv', [
        'run_id', 'task_id', 'call_id', 'actual_policy', 'policy', 'status', 'input_tokens',
        'delta_from_full', 'delta_from_actual', 'actual_usage_status', 'actual_request_available',
        'actual_measured_input_tokens', 'actual_measured_output_tokens', 'actual_measured_cached_input_tokens',
        'actual_unknown_usage_not_imputed', 'removed_turns', 'redisplayed_turns',
        'input_and_max_output_fit_context', 'context_fit_is_not_total_budget_admission',
        'adjacent_input_common_prefix_tokens', 'common_prefix_is_not_measured_cache_usage',
        'prompt_sha256', 'token_sequence_sha256'], inputs)
    csvfile(folder/'all_new_conditions.csv', [
        'run_id', 'task_id', 'actual_policy', 'record_status', 'diagnosis_status', 'actual_success',
        'actual_model_attempts', 'actual_known_total_tokens', 'actual_unknown_usage_calls',
        'actual_full_logical_tokens', 'counted_actual_inputs', 'all_attempted_inputs_counted',
        'actual_policy_input_omission_on_realized_path', 'hypothetical_full_display_cost_on_same_outputs',
        'hypothetical_cost_is_not_an_observed_full_policy_run', 'terminal_unattempted_projections',
        'any_hypothetical_context_overflow'], cells)
    csvfile(folder/'all_historical_conditions.csv', [
        'run_id', 'task_id', 'reasoning_display_policy', 'record_status', 'success',
        'known_total_tokens', 'unknown_usage_calls', 'model_calls', 'api_requests', 'stop_reason'], historical['rows'])
    decompositions = data.get('accounting_decompositions', [])
    csvfile(folder/'all_decompositions.csv', [
        'task_id', 'actual_policy', 'actual_run_id', 'historical_full_run_id',
        'full_success', 'candidate_success', 'historical_full_unknown_usage_calls',
        'all_logical_usage_known', 'observed_cost_difference_from_full',
        'local_input_omission_on_candidate_path', 'remainder_after_adding_back_local_omission',
        'contemporaneous_comparison', 'remainder_is_not_a_causal_effect',
        'quality_preservation_or_savings_claim'], decompositions)
    summary = dict(status=data['status'], planned_inputs=len(data['rows']),
        counted_inputs=data['completed_renderings'], missing_request_slots=data['missing_request_slots'],
        errors=data['errors'], wall_seconds=data['wall_seconds'], conditions=cells,
        accounting_decompositions=decompositions, historical_P111_rows=historical['rows'],
        original_P111_development_gate_met=historical['development_gate_met'],
        original_P114_development_gate_met=audit['development_gate_met'],
        new_model_calls=0, new_API_requests=0, new_evaluations=0,
        contemporaneous_comparison=False, new_quality_measurement=False, causal_effect_estimate=None,
        new_method_claim=False, source_report_sha256=sha(source))
    write_new(folder/'summary.json', summary)
    lines = ['# P115: 非再入力の実軌跡における入力差の診断', '',
        f"P114の全４条件、予定{len(data['rows'])}入力のうち{data['completed_renderings']}計数. "
        f"状態は{data['status']}. 保存要求欠測は{data['missing_request_slots']}枠. 新規生成、API、評価は０.", '',
        '| 課題 | P114の成否 | 元の既知token | 元の不明使用量 | 同じ経路での表示省略量 D |',
        '|---|---|---:|---:|---:|']
    for cell in cells:
        success = '成功' if cell['actual_success'] is True else '未達' if cell['actual_success'] is False else cell['record_status']
        values = (cell['task_id'], success, cell['actual_known_total_tokens'],
                  cell['actual_unknown_usage_calls'], cell['actual_policy_input_omission_on_realized_path'])
        lines.append('| '+' | '.join(str(v) if v is not None else '不明' for v in values)+' |')
    lines += ['',
        '全保存要求をfull、recent、execution_gated、public_onlyで再構成した. '
        '元の実行はP114のpublic_onlyだけであり、仮想表示に成否を付与しない. '
        'Dは保存された同じ応答列と実際の残予算通知を固定した局所的入力差である.', '',
        '`C_public - C_historical_full = -D + (C_public + D - C_historical_full)`と整理する. '
        'fullの実測参照は過去のP111で、同時実行の対照ではない. '
        '残差を行動変化や推論品質など特定原因の因果効果とは呼ばない. '
        '不明使用量があれば実測差と残差をnullに保つ. 計数できても不明な実使用量は確定しない.', '',
        '仮想入力に4,096出力予約を加えた値が65,536 contextに収まるかを各行に記録する. '
        '収まっても仕事全体のtoken予算で送信できた保証はない. '
        '隣接仮想入力の共通prefixは実測cache使用量ではない. 全失敗、欠測、未実行を残す.', '',
        '[全入力](all_inputs.csv)／[全４新規条件](all_new_conditions.csv)／'
        '[全12過去条件](all_historical_conditions.csv)／[全会計分解](all_decompositions.csv)／'
        '[完全集約](summary.json)／[固定した範囲](../../docs/experiments/P115_realized_history_inputs.md).', '',
        'P111の採用基準未達とP114の通常対照としての範囲を維持する. '
        '新手法の新規性や一般的品質維持の証明ではない. 未見12課題と原稿保留を維持する.']
    (folder/'README.md').write_text('\n'.join(lines)+'\n')
    write_new(folder/'build_manifest.json', dict(created_at=datetime.now(timezone.utc).isoformat(),
        builder_sha256=sha(Path(__file__)), source_report_sha256=sha(source),
        artifacts={p.name: sha(p) for p in sorted(folder.iterdir())}))
    print({k: summary[k] for k in ('status', 'planned_inputs', 'counted_inputs', 'missing_request_slots')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, required=True)
    build(parser.parse_args().repo_root.resolve())
