"""Compare finished development baselines from public, audited aggregates."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--p6', type=Path, required=True)
    parser.add_argument('--p8', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    reports = [json.loads(p.read_text()) for p in (args.p6, args.p8)]
    wanted = [('P6_01_FULL_V02', 1, 'P6 全履歴'), ('P8_01_NATIVE', 1, 'P8 公開API'),
              ('P6_02_FULL_V03', 2, 'P6 全履歴'), ('P8_02_NATIVE', 2, 'P8 公開API')]
    source = {r['run_id']: r for report in reports for r in report['trials']}
    rows = []
    for name, task, label in wanted:
        row = source[name]
        if row['audit_errors'] or row['evaluation'] is None:
            raise ValueError('only completed and audited trials are supported')
        rows.append({'run_id': name, 'task': task, 'label': label,
                     'known_total_tokens': row['known_total_tokens'],
                     'unknown_usage_calls': row['unknown_usage_calls'],
                     'model_calls': row['model_calls'], 'wall_seconds': row['wall_seconds'],
                     'official_success': row['evaluation']['official_success']})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / 'measurements.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), layout='constrained')
    labels = [f"課題{r['task']}  {r['label']}\n{r['model_calls']} LLM呼び出し" for r in rows]
    colors = ['#286488' if r['official_success'] else '#9a6b32' for r in rows]
    for ax, key, divisor, xlabel in [(axes[0], 'known_total_tokens', 1000, '既知の総入力＋出力（千トークン）'),
                                    (axes[1], 'wall_seconds', 60, '実行時間（分）')]:
        values = [r[key] / divisor for r in rows]
        ax.barh(range(4), values, color=colors)
        ax.set_yticks(range(4), labels); ax.invert_yaxis()
        ax.set_xlim(0, max(values) * 1.55); ax.set_xlabel(xlabel)
        ax.axhline(1.5, color='#cccccc', lw=0.8)
        for index, row in enumerate(rows):
            text = f"{row[key]:,}" if key == 'known_total_tokens' else f"{values[index]:.2f}分"
            if key == 'known_total_tokens' and row['unknown_usage_calls']:
                text += ' ＋不明1呼出'
            state = '最終評価 合格' if row['official_success'] else '最終評価 未達'
            ax.text(values[index] + max(values) * 0.025, index, text + '\n' + state,
                    va='center', fontsize=9)
    axes[0].set_title('呼び出しが減っても総トークンは減るとは限らない')
    axes[1].set_title('終了までの費用と時間を別々に測る')
    fig.suptitle('P8：記憶を圧縮しない全履歴基準の接続校正', fontsize=16)
    fig.supxlabel('開発2課題・各方式1回。P8はAPIスキーマ・複数操作・指示を同時に変更。\n'
                  '少数の観察で、単一要因の因果効果・品質維持・一般的な削減率は未確定。', fontsize=10)
    for extension in ('png', 'pdf', 'svg'):
        fig.savefig(args.output_dir / ('native_baseline.' + extension), dpi=170,
                    metadata={'Creator': 'plot_native_baseline.py'})
    plt.close(fig)
    svg = args.output_dir / 'native_baseline.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
    (args.output_dir / 'sources.json').write_text(json.dumps({
        'sources': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.p6, args.p8)},
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'unknown_usage_policy': 'Known count is a lower bound; no imputation of the missing call.',
        'trials': len(rows), 'independent_tasks': 2, 'repeats_per_condition': 1,
    }, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'plotted_finished_trials': len(rows)}))


if __name__ == '__main__':
    main()
