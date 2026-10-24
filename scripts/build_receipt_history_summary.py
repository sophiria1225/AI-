"""Publish all P110 slots, including uncounted inputs; never expose reasoning."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def write_csv(path, fields, rows):
    with path.open('x') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})


def build(root):
    source = root / 'reports/P110_receipt_history_inputs.json'
    data = json.loads(source.read_text())
    plan = json.loads((root / 'configs/P110_receipt_history_inputs_v01.json').read_text())
    audit = json.loads((root / plan['source_audit']).read_text())
    assert len(data['rows']) == 444 and len(data['cells']) == 8
    folder = root / 'materials/20261025_p110_results'
    folder.mkdir()
    inputs = []
    for row in data['rows']:
        projection = row.get('projection', {})
        inputs.append(dict(**row, **{key: projection.get(key) for key in (
            'latest_execution_eligible', 'removed_reasoning_characters',
            'supplied_reasoning_characters', 'original_reasoning_characters')},
            removed_turns=json.dumps(projection.get('removed_reasoning_turns')),
            redisplayed_turns=json.dumps(projection.get('redisplayed_reasoning_turns')),
            unbound_turns=json.dumps(projection.get('signature_unbound_turns'))))
    write_csv(folder / 'all_inputs.csv', [
        'run_id', 'call_id', 'policy', 'status', 'input_tokens', 'delta_from_full',
        'original_usage_status', 'original_measured_input_tokens',
        'original_measured_output_tokens', 'original_measured_cached_input_tokens',
        'original_unknown_usage_not_imputed', 'adjacent_input_common_prefix_tokens',
        'common_prefix_is_not_measured_cache_usage', 'latest_execution_eligible',
        'removed_turns', 'redisplayed_turns', 'unbound_turns',
        'removed_reasoning_characters', 'supplied_reasoning_characters',
        'original_reasoning_characters', 'prompt_sha256', 'token_sequence_sha256'], inputs)
    conditions = []
    for original in audit['rows']:
        for policy in plan['policies']:
            selected = [r for r in data['rows'] if r['run_id'] == original['run_id'] and r['policy'] == policy]
            counted = [r for r in selected if r['status'] == 'counted']
            complete = len(counted) == len(selected) == original['model_calls']
            conditions.append(dict(run_id=original['run_id'], task_id=original['task_id'],
                original_tool_choice=original['tool_choice_policy'], policy=policy,
                original_success=original['success'], original_model_calls=original['model_calls'],
                original_known_total_tokens=original['known_total_tokens'],
                original_unknown_usage_calls=original['unknown_usage_calls'],
                planned_inputs=len(selected), counted_inputs=len(counted),
                hypothetical_input_sum=sum(r['input_tokens'] for r in counted) if complete else None,
                hypothetical_delta_sum=sum(r['delta_from_full'] for r in counted) if complete else None,
                changed_inputs=sum(r['delta_from_full'] != 0 for r in counted),
                inputs_redisplaying_reasoning=sum(bool(r['projection']['redisplayed_reasoning_turns']) for r in counted),
                new_task_quality_measured=False, measured_whole_task_savings=None))
    write_csv(folder / 'all_conditions.csv', list(conditions[0]), conditions)
    evidence = []
    for cell in data['cells']:
        for i, entry in enumerate(cell.get('prior_turn_evidence', []), 1):
            evidence.append(dict(run_id=cell['run_id'], turn=i, **entry,
                reason_labels='|'.join(entry['reasons'])))
    write_csv(folder / 'all_evidence.csv', ['run_id', 'turn', 'eligible', 'reason_labels',
        'outer_records', 'API_records', 'actual_API_requests', 'pending_reads',
        'semantic_redundancy_certified', 'public_function_signature_sha256', 'trusted_record_sha256'], evidence)
    summary = dict(status=data['status'], original_cells=len(audit['rows']),
        original_attempts=sum(r['model_calls'] for r in audit['rows']),
        original_unknown_usage_calls=sum(r['unknown_usage_calls'] for r in audit['rows']),
        planned_inputs=len(data['rows']), counted_inputs=data['completed_renderings'],
        original_successes=sum(r['success'] is True for r in audit['rows']),
        original_failures=sum(r['success'] is False for r in audit['rows']),
        eligible_prior_turns=sum(e['eligible'] for e in evidence),
        inspected_prior_turns=len(evidence), conditions=conditions,
        measured_whole_task_savings=None, new_task_quality_measured=False,
        errors=data['errors'], wall_seconds=data['wall_seconds'])
    with (folder / 'summary.json').open('x') as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2, allow_nan=False); stream.write('\n')
    (folder / 'README.md').write_text(
        '# P110: 実行記録に応じた推論履歴の表示\n\n'
        f"保存済み全{summary['original_cells']}実行・{summary['original_attempts']}要求から、"
        f"３表示・予定{summary['planned_inputs']}入力のうち{summary['counted_inputs']}入力を計数した. "
        f"状態は{summary['status']}. 元の使用量不明{summary['original_unknown_usage_calls']}件は不明のまま残す.\n\n"
        'fullは全推論、recentは直近だけ、execution_gatedは型付き実行記録に応じて古い推論を非表示にし、'
        '直近が不確かなら原文を再表示する. 実行正常は意味的な不要性の保証ではない. '
        'コード、API結果、指示、要求設定は維持した.\n\n'
        '[全444枠](all_inputs.csv)、[全８実行×３表示](all_conditions.csv)、'
        '[全手順の適格理由](all_evidence.csv)、[集約](summary.json)を保持する. '
        '元の失敗を含め、一部の成功例に絞っていない.\n\n'
        '**固定済み軌跡上の仮想入力であり、新方針の全仕事費用ではない.** '
        'hypothetical_input_sumとhypothetical_delta_sumは計数用の集約であり、'
        '変更後の生成回数、出力、回復、品質は未測定. 共通接頭辞は実測cache使用量ではない. '
        '原文を再表示する負担も各入力に含めたが、新しい実軌跡の復旧費ではない.\n\n'
        '[固定計画](../../docs/experiments/P110_receipt_history_inputs.md)／'
        '[全結果](../../reports/P110_receipt_history_inputs.json). '
        '追加モデル生成、API送信、生成コード実行、評価、DB読取、未見課題読取は０. 原稿は保留.\n')
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}
    with (folder / 'build_manifest.json').open('x') as stream:
        json.dump(dict(created_at=datetime.now(timezone.utc).isoformat(),
            builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            source_report_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            files=files), stream, indent=2); stream.write('\n')
    print(json.dumps({k: summary[k] for k in ('status','planned_inputs','counted_inputs','eligible_prior_turns')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--repo-root', type=Path, required=True)
    build(parser.parse_args().repo_root.resolve())
