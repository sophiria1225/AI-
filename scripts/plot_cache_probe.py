"""Draw the individual target-call measurements, keeping logical tokens explicit."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.report.read_text())
    if data['status'] != 'complete' or data['audit_errors']:
        raise ValueError('a completed, audited report is required')
    rows = [r for r in data['calls'] if r['stage'] == 'target']
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / 'all_calls.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data['calls'][0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(data['calls'])
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False})
    figure, axes = plt.subplots(1, 2, figsize=(12, 5.7), layout='constrained')
    labels = [f"組{r['pair']}・" + ('元配置' if r['variant'] == 'original' else '一覧を後置') for r in rows]
    cached = [r['cached_input_tokens'] for r in rows]
    processed = [r['processed_input_tokens'] for r in rows]
    axes[0].barh(range(4), cached, color='#bdcbd5', label='キャッシュを再利用')
    axes[0].barh(range(4), processed, left=cached, color='#285f83', label='再処理した入力')
    axes[0].set_xlim(0, max(r['input_tokens'] for r in rows) * 1.35)
    axes[0].set_title('総入力は全て17,682トークンで同じ')
    axes[0].set_xlabel('入力トークン'); axes[0].legend(loc='upper right', fontsize=9, frameon=False)
    seconds = [r['prompt_seconds'] for r in rows]
    axes[1].barh(range(4), seconds, color=['#996b38' if r['variant'] == 'original' else '#285f83' for r in rows])
    axes[1].set_xlim(0, max(seconds) * 1.22)
    axes[1].set_title('同じ次入力を処理する時間')
    axes[1].set_xlabel('入力処理秒')
    for index, row in enumerate(rows):
        axes[0].text(row['input_tokens'] + 300, index, f"再処理 {row['processed_input_tokens']:,}", va='center', fontsize=9)
        axes[1].text(row['prompt_seconds'] + 3, index, f"{row['prompt_seconds']:.3f}秒", va='center', fontsize=10)
    for ax in axes:
        ax.set_yticks(range(4), labels); ax.set_ylim(3.6, -1.05)
    figure.suptitle('P9：履歴一覧の配置によるキャッシュ再利用の校正', fontsize=16)
    figure.supxlabel('各組の先頭入力はキャッシュ無効で処理してから、次入力を計測。固定8呼び出しの全費用も保存。\n'
                      '同じ隣接2入力・各配置2回・生成は各1トークン。課題品質や総トークン削減の結果ではない。', fontsize=10)
    for extension in ('png', 'pdf', 'svg'):
        figure.savefig(args.output_dir / ('cache_probe.' + extension), dpi=170,
                       metadata={'Creator': 'plot_cache_probe.py'})
    plt.close(figure)
    svg = args.output_dir / 'cache_probe.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
    (args.output_dir / 'sources.json').write_text(json.dumps({
        'report_sha256': hashlib.sha256(args.report.read_bytes()).hexdigest(),
        'plot_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'individual_target_measurements': len(rows), 'scope': data['scope'],
    }, ensure_ascii=False, indent=2) + '\n')
