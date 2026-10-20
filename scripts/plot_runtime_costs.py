"""Render numeric P6 runtime diagnostics without loading any private task data."""
import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--costs', type=Path, required=True)
    parser.add_argument('--memory-sizes', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    trials = json.loads(args.costs.read_text())['trials']
    updates = json.loads(args.memory_sizes.read_text())['trials'][0]['updates']
    args.output_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    figure, axes = plt.subplots(1, 3, figsize=(16, 5.4), layout='constrained')
    columns = [('作業役・入力処理', '#246185', lambda row: row['roles']['agent']['prompt_seconds']),
               ('作業役・出力生成', '#71a7bc', lambda row: row['roles']['agent']['decode_seconds']),
               ('台帳・入力処理', '#b16c21', lambda row: row['roles'].get('ledger', {}).get('prompt_seconds', 0)),
               ('台帳・出力生成', '#e4ad64', lambda row: row['roles'].get('ledger', {}).get('decode_seconds', 0))]
    bases = [0.0] * len(trials)
    for label, color, extract in columns:
        values = [extract(row) / 60 for row in trials]
        axes[0].bar(range(len(trials)), values, bottom=bases, color=color, label=label)
        bases = [b + v for b, v in zip(bases, values)]
    other = [row['wall_seconds'] / 60 - b for row, b in zip(trials, bases)]
    axes[0].bar(range(len(trials)), other, bottom=bases, color='#dedede',
                label='中断呼出・他（内訳不明を含む）')
    axes[0].set_xticks(range(len(trials)), ['全履歴', '対象台帳'])
    axes[0].set_ylabel('経過時間（分）')
    axes[0].set_title('両方式とも30分で未達')
    axes[0].legend(frameon=False, fontsize=8, loc='upper center', bbox_to_anchor=(0.5, -0.1))
    full = next(row for row in trials if row['arm'] == 'full')
    calls = [row for row in full['calls'] if row['status'] == 'ok'
             and row['original_previous_input_prefix_tokens'] is not None]
    for variant, label, color in [('original', '原配置', '#246185'),
                                   ('archive_last', '一覧を後置した入力列', '#b16c21')]:
        axes[1].plot([int(row['id'].split('_')[1]) for row in calls],
                     [row[variant + '_previous_input_prefix_tokens'] / 1000 for row in calls],
                     label=label, color=color)
    axes[1].set_xlabel('全履歴方式の呼び出し番号')
    axes[1].set_ylabel('隣接入力で同じ先頭部分（千トークン）')
    axes[1].set_title('値を変えずJSONキーの順序だけ変更')
    axes[1].legend(frameon=False, fontsize=8)
    axes[1].text(0.02, 0.96, '変更後の速度・品質は未測定', transform=axes[1].transAxes,
                 va='top', fontsize=9)
    ids = list(range(1, len(updates) + 1))
    axes[2].plot(ids, [u['before_memory_tokens'] / 1000 for u in updates], 'o-', label='更新前', color='#246185')
    axes[2].plot(ids, [u['after_memory_tokens'] / 1000 for u in updates], 'o-', label='更新直後', color='#b16c21')
    axes[2].axhline(4.096, color='#666666', linestyle='--', label='更新を始める基準')
    axes[2].set_xlabel('台帳更新の番号')
    axes[2].set_ylabel('作業用の記憶（千トークン）')
    axes[2].set_xticks(ids)
    axes[2].set_title('3回は更新直後も基準を超える')
    axes[2].legend(frameon=False, fontsize=8)
    figure.suptitle('P6第2課題：情報保持の問題と実行基盤の費用を分ける', fontsize=15)
    figure.supxlabel('開発1課題・各方式1回。費用不明を0にせず、元の実行条件を維持。新手法や品質維持の証明ではない。', fontsize=9)
    for suffix in ('png', 'svg', 'pdf'):
        figure.savefig(args.output_dir / ('runtime_diagnosis.' + suffix), dpi=160,
                       metadata={'Creator': 'plot_runtime_costs.py'})
    svg = args.output_dir / 'runtime_diagnosis.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
    plt.close(figure)
    with (args.output_dir / 'call_input_prefixes.csv').open('w') as stream:
        fields = ['id', 'input_tokens', 'original_previous_input_prefix_tokens',
                  'archive_last_previous_input_prefix_tokens', 'prompt_seconds']
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows({key: row[key] for key in fields} for row in calls)


if __name__ == '__main__':
    main()
