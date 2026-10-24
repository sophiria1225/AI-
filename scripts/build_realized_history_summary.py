"""Publish every P112 input and original condition without exposing saved text."""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from measure_receipt_history import read, sha, write_new
from receipt_reasoning_history import require


def csvfile(path, fields, rows):
    with path.open('x') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fields})


def build(root):
    source = root/'reports/P112_realized_history_inputs.json'
    data = read(source)
    plan = read(root/'configs/P112_realized_history_inputs_v01.json')
    audit = read(root/'reports/P111_comparison.json')
    require(len(data['cells']) == 12 and {c['run_id'] for c in data['cells']} == set(plan['run_ids'])
            and len(data['rows']) == plan['planned_renderings']
            and data['source_audit_sha256'] == sha(root/'reports/P111_comparison.json'),
            'all_original_conditions_and_input_slots_required')
    by_id = {c['run_id']: c for c in data['cells']}
    cells = [by_id[rid] for rid in plan['run_ids']]
    folder = root/'materials/20261025_p112_results'
    folder.mkdir()
    inputs = []
    for row in data['rows']:
        projection = row.get('projection', {})
        inputs.append(dict(**row, removed_turns=json.dumps(projection.get('removed_reasoning_turns')),
            redisplayed_turns=json.dumps(projection.get('redisplayed_reasoning_turns')),
            signature_unbound_turns=json.dumps(projection.get('signature_unbound_turns'))))
    csvfile(folder/'all_inputs.csv', [
        'run_id', 'task_id', 'call_id', 'actual_policy', 'policy', 'status', 'input_tokens',
        'delta_from_full', 'delta_from_actual', 'actual_usage_status', 'actual_request_available',
        'actual_measured_input_tokens', 'actual_measured_output_tokens', 'actual_measured_cached_input_tokens',
        'actual_unknown_usage_not_imputed', 'removed_turns', 'redisplayed_turns', 'signature_unbound_turns',
        'adjacent_input_common_prefix_tokens', 'common_prefix_is_not_measured_cache_usage',
        'prompt_sha256', 'token_sequence_sha256'], inputs)
    csvfile(folder/'all_conditions.csv', [
        'run_id', 'task_id', 'actual_policy', 'record_status', 'diagnosis_status', 'actual_success',
        'actual_model_attempts', 'actual_known_total_tokens', 'actual_unknown_usage_calls',
        'actual_full_logical_tokens', 'counted_actual_inputs', 'all_attempted_inputs_counted',
        'actual_policy_input_omission_on_realized_path', 'hypothetical_full_display_cost_on_same_outputs',
        'hypothetical_cost_is_not_an_observed_full_policy_run', 'terminal_unattempted_projections'], cells)
    decompositions = data.get('accounting_decompositions', [])
    csvfile(folder/'all_decompositions.csv', [
        'task_id', 'actual_policy', 'full_success', 'candidate_success', 'all_logical_usage_known',
        'observed_cost_difference_from_full', 'local_input_omission_on_candidate_path',
        'remainder_after_adding_back_local_omission', 'remainder_is_not_a_causal_effect',
        'quality_preservation_or_savings_claim'], decompositions)
    summary = dict(status=data['status'], planned_inputs=len(data['rows']),
        counted_inputs=data['completed_renderings'], missing_request_slots=data['missing_request_slots'],
        errors=data['errors'], wall_seconds=data['wall_seconds'], conditions=cells,
        accounting_decompositions=decompositions,
        original_P111_development_gate_met=audit['development_gate_met'],
        new_model_calls=0, new_API_requests=0, new_evaluations=0,
        new_quality_measurement=False, causal_effect_estimate=None,
        new_method_claim=False, source_report_sha256=sha(source))
    write_new(folder/'summary.json', summary)
    lines = ['# P112: 実軌跡での表示差と全仕事費用の診断', '',
        f"全12条件、予定{len(data['rows'])}入力のうち{data['completed_renderings']}計数. "
        f"状態は{data['status']}. 保存要求が欠測の枠は{data['missing_request_slots']}件. 新規生成、API、評価は０.", '',
        '| 課題 | 実際の表示方式 | 元の成否 | 元の既知token | 元の不明使用量 | 同じ経路での表示省略量 D |',
        '|---|---|---|---:|---:|---:|']
    for cell in cells:
        success = '成功' if cell['actual_success'] is True else '未達' if cell['actual_success'] is False else cell['record_status']
        values = (cell['task_id'], cell['actual_policy'], success, cell['actual_known_total_tokens'],
            cell['actual_unknown_usage_calls'], cell['actual_policy_input_omission_on_realized_path'])
        lines.append('| '+' | '.join(str(v) if v is not None else '不明' for v in values)+' |')
    lines += ['',
        'Dは各実軌跡の入力をfull表示へ戻した場合の局所差であり、実測の仕事全体の削減ではない. '
        '元の成否はP111の独立評価を参照し、仮想入力の成績へ転記しない.', '',
        '`C_p - C_full = -D_p + (C_p + D_p - C_full)`という恒等式で比較する. '
        '括弧内の残差を、再試行や推論品質など特定の原因の因果効果とは呼ばない. '
        '同じ応答列の仮定と実際の残予算を固定した診断であり、別方式で同じ応答や予算内完了が得られる保証はない.', '',
        '使用量不明があれば総費用と残差はnullに保つ. 元の失敗、未実行、欠測を除外しない. '
        '入力を計数できても、元の不明使用量は確定しない. 隣接入力の共通prefixは実測cache使用量ではない.', '',
        '[全入力枠](all_inputs.csv)／[全12条件](all_conditions.csv)／[全会計分解](all_decompositions.csv)／'
        '[完全集約](summary.json)／[固定した診断](../../docs/experiments/P112_realized_history_inputs.md).', '',
        '全仕事の採用判断は[P111](../20261025_p111_results/README.md)の固定基準を用いる. '
        '生の推論と完全要求は非公開保存先に留める. 未見12課題と原稿保留を維持する.']
    (folder/'README.md').write_text('\n'.join(lines)+'\n')
    write_new(folder/'build_manifest.json', dict(created_at=datetime.now(timezone.utc).isoformat(),
        builder_sha256=sha(Path(__file__)), source_report_sha256=sha(source),
        artifacts={p.name: sha(p) for p in sorted(folder.iterdir())}))
    print({k: summary[k] for k in ('status', 'planned_inputs', 'counted_inputs', 'missing_request_slots')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, required=True)
    build(parser.parse_args().repo_root.resolve())
