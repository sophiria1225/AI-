"""Plot finished, audited native-memory runs from public aggregate reports."""
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
    parser.add_argument('--measurements', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--phase', required=True)
    args = parser.parse_args()
    measured = json.loads(args.measurements.read_text())
    runtime = {r['run_id']: r for r in json.loads(args.runtime.read_text())['trials']}
    rows, calls = [], []
    for i, row in enumerate(measured['trials'], 1):
        run = runtime[row['run_id']]
        if row['audit_errors'] or run['audit_errors'] or row['evaluation'] is None:
            raise ValueError('requires finished, audited trials')
        role = run['roles']['agent']
        rows.append({'task_number': i, 'run_id': row['run_id'],
                     'input_tokens': role['input_tokens'], 'output_tokens': role['output_tokens'],
                     'unknown_usage_calls': row['unknown_usage_calls'],
                     'model_calls': row['model_calls'], 'wall_seconds': row['wall_seconds'],
                     'success': row['evaluation']['official_success']})
        calls.extend({'task_number': i, 'call_number': j,
                      'input_tokens': c['input_tokens'], 'output_tokens': c['output_tokens'],
                      'processed_input_tokens': c.get('processed_input_tokens'),
                      'cached_input_tokens': c.get('cached_input_tokens')}
                     for j, c in enumerate(run['calls'], 1))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for filename, values in [('measurements.csv', rows), ('calls.csv', calls)]:
        with (args.output_dir / filename).open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(values[0]), lineterminator='\n')
            writer.writeheader(); writer.writerows(values)
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.3), layout='constrained')
    colors = ['#24688a', '#579277', '#b3772b', '#8d619e']
    for i, row in enumerate(rows):
        total = (row['input_tokens'] + row['output_tokens']) / 1000
        axes[0].barh(i, row['input_tokens'] / 1000, color=colors[i % 4])
        axes[0].barh(i, row['output_tokens'] / 1000, left=row['input_tokens'] / 1000,
                     color='#333333', label='生成出力' if i == 0 else None)
        status = '合格' if row['success'] else '未達'
        unknown = f"＋不明{row['unknown_usage_calls']}呼出" if row['unknown_usage_calls'] else ''
        axes[0].text(total + 2, i, f"{int(total * 1000):,}{unknown}\n{status}・{row['wall_seconds']/60:.2f}分",
                     va='center', fontsize=9)
        series = [c for c in calls if c['task_number'] == i + 1]
        axes[1].plot([c['call_number'] for c in series],
                     [(c['input_tokens'] or 0) / 1000 for c in series],
                     marker='o', ms=4, color=colors[i % 4], label=f"課題{i+1}")
    axes[0].set_yticks(range(len(rows)), [f"課題{r['task_number']}\n{r['model_calls']} LLM呼び出し" for r in rows])
    axes[0].invert_yaxis(); axes[0].set_xlabel('総入力＋出力（千トークン）')
    axes[0].set_xlim(0, max((r['input_tokens'] + r['output_tokens']) / 1000 for r in rows) * 1.38)
    axes[0].legend(loc='lower right', frameon=False)
    axes[1].set_xlabel('モデル呼び出し番号'); axes[1].set_ylabel('1回の入力（千トークン）')
    axes[1].set_ylim(bottom=0); axes[1].legend(frameon=False)
    axes[0].set_title('最終結果と全呼び出しの費用')
    axes[1].set_title('実際に入力が増えた経過')
    fig.suptitle(f'{args.phase}：追加4開発課題の全履歴基準', fontsize=16)
    fig.supxlabel('各1試行。API仕様と作業履歴を含む実入力。キャッシュ分も論理トークンへ算入。\n'
                  '短い導入観察であり、品質同等性・長期作業・新手法の有効性は未検証。', fontsize=10)
    for extension in ('png', 'pdf', 'svg'):
        fig.savefig(args.output_dir / ('native_series.' + extension), dpi=170,
                    metadata={'Creator': 'plot_native_series.py'})
    plt.close(fig)
    svg = args.output_dir / 'native_series.svg'
    svg.write_text('\n'.join(s.rstrip() for s in svg.read_text().splitlines()) + '\n')
    (args.output_dir / 'sources.json').write_text(json.dumps({
        'sources': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (args.measurements, args.runtime)},
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'trials': len(rows), 'repeats_per_condition': 1}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'plotted_trials': len(rows)}))
