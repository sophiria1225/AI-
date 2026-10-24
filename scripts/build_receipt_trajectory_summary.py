"""Publish all P113 calls and comparisons using hashes, never source text."""
import argparse
import csv
import json
from pathlib import Path

from inspect_receipt_history_trajectories import read, write_new
from inspect_recorded_action_agreement import sha
from receipt_reasoning_history import require


def csvfile(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('x') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        writer.writerows(rows)


def build(root):
    path = root/'reports/P113_receipt_history_trajectories.json'
    data = read(path); plan = read(root/'configs/P113_receipt_history_trajectories_v01.json')
    require(data['status'] == 'complete' and not data['errors'] and len(data['runs']) == len(data['pairs']) == 12
            and [r['run_id'] for r in data['runs']] == plan['run_ids'] and data['plan_sha256'] == sha(root/'configs/P113_receipt_history_trajectories_v01.json'),
            'complete_bound_all_condition_diagnosis_required')
    folder = root/'materials/20261025_p113_results'; folder.mkdir()
    calls = []
    for run in data['runs']:
        for call in run['calls']:
            row = {k:v for k,v in call.items() if not isinstance(v, (dict,list))}
            for nested in ('input', 'response', 'components'):
                row.update({nested+'_'+k:v for k,v in call[nested].items()})
            row.update(run_id=run['run_id'], task_id=run['task_id'], policy=run['reasoning_display_policy'],
                original_success=run['success'], execution_kinds=json.dumps(call['execution_kinds'], sort_keys=True),
                history_removed_turns=json.dumps(call['history_removed_turns']),
                history_redisplayed_turns=json.dumps(call['history_redisplayed_turns']))
            calls.append(row)
    positions = [dict(task_id=p['task_id'], left=p['left'], right=p['right'], **r) for p in data['pairs'] for r in p['rows']]
    firsts = []
    for pair in data['pairs']:
        firsts.extend(dict(task_id=pair['task_id'], left=pair['left'], right=pair['right'],
                          field=field, **v) for field,v in pair['equality'].items())
    require(len(calls) == 204 and len(positions) == 219, 'all_calls_and_union_positions_required')
    csvfile(folder/'all_calls.csv', calls); csvfile(folder/'all_pair_positions.csv', positions)
    csvfile(folder/'all_first_differences.csv', firsts)
    summary = {k:v for k,v in data.items() if k not in ('runs','pairs','source_sha256','private_source_sha256','absent_private_sources')}
    summary['source_report_sha256'] = sha(path)
    write_new(folder/'summary.json', summary)
    lines = ['# P113: 履歴選別後の実行内容の全件診断', '',
        '全12条件、204モデル要求、12方式対の219対応位置を保存した. 同じ生成順の対応であり、意味的に同じ処理段階を整列したものではない.', '',
        '| 課題 | 比較 | 初めて入力が異なる位置 | 初めてPython構文が異なる位置 | 初めてAPI要求列が異なる位置 |',
        '|---|---|---:|---:|---:|']
    for p in data['pairs']:
        values = [p['task_id'], p['left_policy']+' / '+p['right_policy']]
        values += [p['equality'][field]['first_observed_difference'] for field in
                   ('request_equal','Python_AST_equal','API_sequence_including_empty_equal')]
        lines.append('| '+' | '.join(str(v) if v is not None else '観測なし' for v in values)+' |')
    lines += ['', '「観測なし」は全位置の一致を意味しない. 未知応答、ASTのない出力、先に終わった条件は比較不能として全表に残す. '
        'API要求列が一致してもPython状態や出力観測の一致は保証されない. 空のAPI列の一致を取得処理の一致として数えない.', '',
        '全要求の指紋は予算通知、引数、transport ID、seedを保持する. 推論だけを除いた指紋は別に記録し、元の完全要求を変更しない. '
        'Python構文の照合では変数名と定数、処理順を保持し、ソース位置だけを除く. 生の推論と要求は公開しない.', '',
        '新しいモデル生成、API、コード実行、評価、DB閲覧、未見12課題の閲覧は０. 因果効果や状態の意味的同値性、新規手法の証明ではない.', '',
        '[全204要求](all_calls.csv)／[全219対応位置](all_pair_positions.csv)／[全指標の最初の差と欠測](all_first_differences.csv)／[完全集約](summary.json).']
    (folder/'README.md').write_text('\n'.join(lines)+'\n')
    write_new(folder/'build_manifest.json', dict(builder_sha256=sha(Path(__file__)), source_report_sha256=sha(path),
        artifacts={p.name:sha(p) for p in sorted(folder.iterdir())}))
    print(json.dumps(dict(calls=len(calls), comparisons=len(data['pairs']), aligned_positions=len(positions))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--repo-root', type=Path, required=True)
    build(parser.parse_args().repo_root.resolve())
