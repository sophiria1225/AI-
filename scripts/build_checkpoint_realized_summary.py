"""Keep every source condition and input pair in P121's public diagnosis."""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from build_realized_history_summary import csvfile
from checkpoint_realized_inputs import PHASES
from measure_receipt_history import read, sha, write_new
from receipt_reasoning_history import require


def build(root):
    source = root / 'reports/P121_checkpoint_inputs.json'
    data = read(source)
    plan = read(root / 'configs/P121_checkpoint_inputs_v01.json')
    require(len(data['cells']) == len(plan['run_ids']) == 24
            and {c['run_id'] for c in data['cells']} == set(plan['run_ids'])
            and len(data['rows']) == plan['planned_renderings']
            and data['plan_sha256'] == sha(root / 'configs/P121_checkpoint_inputs_v01.json'),
            'all_twenty_four_conditions_and_attempt_pairs_required')
    audits = {p: read(root / f'reports/{p}_comparison.json') for p in PHASES}
    require(all(data['source_audit_sha256'][p] == sha(root / f'reports/{p}_comparison.json') for p in PHASES),
            'original_source_audits_required')
    by_id = {c['run_id']: c for c in data['cells']}
    cells = [by_id[rid] for rid in plan['run_ids']]
    folder = root / 'materials/20261025_p121_results'
    folder.mkdir()
    csvfile(folder / 'all_inputs.csv', [
        'source_phase', 'run_id', 'task_id', 'call_id', 'role', 'display', 'status', 'checkpoint_active',
        'input_tokens', 'restoration_input_difference', 'actual_usage_status', 'actual_request_available',
        'actual_measured_input_tokens', 'actual_measured_output_tokens', 'actual_output_cap',
        'input_and_actual_output_cap_fit_context', 'actual_unknown_usage_not_imputed',
        'request_private_sha256', 'prompt_sha256', 'token_sequence_sha256'], data['rows'])
    csvfile(folder / 'all_conditions.csv', [
        'source_phase', 'run_id', 'task_id', 'checkpoint_policy', 'record_status', 'diagnosis_status',
        'actual_success', 'actual_model_attempts', 'actual_known_total_tokens', 'actual_unknown_usage_calls',
        'all_attempted_inputs_counted', 'counted_actual_inputs', 'direct_input_difference_on_realized_path',
        'separate_summary_exact_tokens', 'direct_input_difference_minus_separate_summary_cost',
        'hypothetical_restore_cost_on_same_outputs', 'hypothetical_restore_cost_exceeds_task_token_budget',
        'any_restored_context_overflow', 'actual_unknown_usage_not_imputed', 'whole_task_savings_claim'], cells)
    timeline = []
    for cell in cells:
        identity = {k: cell[k] for k in ('source_phase', 'run_id', 'task_id', 'checkpoint_policy')}
        timeline += [{**identity, **row} for row in cell['active_replacement_input_timeline']]
    csvfile(folder / 'all_amortization.csv', [
        'source_phase', 'run_id', 'task_id', 'checkpoint_policy', 'call_id', 'actual_usage_status',
        'input_difference', 'cumulative_input_difference', 'minus_separate_summary_cost'], timeline)
    summary = dict(status=data['status'], planned_inputs=len(data['rows']),
        counted_inputs=data['completed_renderings'], missing_request_slots=data['missing_request_slots'],
        errors=data['errors'], wall_seconds=data['wall_seconds'], conditions=cells,
        original_gate_decisions={p: audits[p]['development_gate_met'] for p in PHASES},
        new_model_calls=0, new_API_requests=0, new_evaluations=0, new_quality_measurement=False,
        causal_effect_estimate=None, new_method_claim=False, source_report_sha256=sha(source))
    write_new(folder / 'summary.json', summary)
    lines = ['# P121: 要約後の入力短縮と費用回収の診断', '',
        f"P118、P119、P120の全24枠. 予定{len(data['rows'])}入力のうち{data['completed_renderings']}計数、"
        f"保存要求欠測は{data['missing_request_slots']}枠. 状態は{data['status']}. 新規生成、API、評価は０.", '',
        '| 実験 | 課題 | 元の方式 | 元の成否 | 同じ行動列での入力差 D | 別要約の費用 C | D − C（別要約のみ） |',
        '|---|---|---|---|---:|---:|---:|']
    for cell in cells:
        outcome = '成功' if cell['actual_success'] is True else '未達' if cell['actual_success'] is False else cell['record_status']
        values = (cell['source_phase'], cell['task_id'], cell['checkpoint_policy'], outcome,
                  cell['direct_input_difference_on_realized_path'], cell['separate_summary_exact_tokens'],
                  cell['direct_input_difference_minus_separate_summary_cost'])
        lines.append('| ' + ' | '.join(str(v) if v is not None else '不明／対象外' for v in values) + ' |')
    lines += ['',
        '各保存要求について、実際の入力と、実際に置換された古い履歴だけを戻した入力を数えた. '
        '要約が未採用なら両入力は同一. 同時出力のmetadata非再入力、必須欄の指示とschema、'
        '実際の残予算通知、出力上限、seedなどは両入力で維持する. 別要約の要求と費用も保持する.', '',
        'Dは後続の全保存要求における入力差の合計. Cは別呼出し要約の実測入力と出力の合計. '
        'D − Cは同じ行動列と実際の予算通知を固定した費用回収の算術であり、'
        '別要約をしなかった場合の実行結果や総節約の実績ではない. '
        '同時出力の要約本文だけの生成tokenは分離計測していないため、独自のCを推定しない.', '',
        '元の使用量不明は、入力の計数ができても不明のまま残す. '
        '既知小計へDを足した仮想値が仕事予算を超える場合や、復元した入力と実際の出力予約がcontextを超える場合を明示する. '
        '予算内でも別方式の行動や成功を保証しない. 成功例だけを選ばず、全失敗、欠測、未実行枠を含める.', '',
        '[全入力](all_inputs.csv)／[全24条件](all_conditions.csv)／[各呼出しでの回収額](all_amortization.csv)／'
        '[完全な集約](summary.json)／[事前固定した範囲](../../docs/experiments/P121_checkpoint_inputs.md).', '',
        '元の採用基準の判断と未知を変更しない. この分析は新しい方式の性能試験ではない. '
        '新規性、一般的品質維持、因果効果を主張せず、原稿と未見12課題は保留する.']
    (folder / 'README.md').write_text('\n'.join(lines) + '\n')
    write_new(folder / 'build_manifest.json', dict(created_at=datetime.now(timezone.utc).isoformat(),
        builder_sha256=sha(Path(__file__)), source_report_sha256=sha(source),
        artifacts={p.name: sha(p) for p in sorted(folder.iterdir())}))
    print({k: summary[k] for k in ('status', 'planned_inputs', 'counted_inputs', 'missing_request_slots')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, required=True)
    build(parser.parse_args().repo_root.resolve())
