"""Plot all matched development outcomes, including failures and all role costs."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch


def load_rows(paths, labels):
    if len(paths) != len(labels):
        raise ValueError('one label per measurement file is required')
    rows, expected = [], None
    for path, label in zip(paths, labels, strict=True):
        measured = json.loads(path.read_text())
        if measured['pending'] or measured['audit_errors']:
            raise ValueError('requires finished, audited measurements')
        ids = [r['task_id'] for r in measured['trials']]
        if expected is not None and ids != expected:
            raise ValueError('task order and identities must match')
        expected = ids
        for i, row in enumerate(measured['trials'], 1):
            if row['evaluation'] is None or row['audit_errors'] or row['unknown_usage_calls']:
                raise ValueError('unknown usage or evaluation cannot be plotted as complete costs')
            role_costs = {name: role['input_tokens'] + role['output_tokens']
                          for name, role in row['usage_by_role'].items()}
            if sum(role_costs.values()) != row['known_total_tokens']:
                raise ValueError('role costs disagree with totals')
            rows.append({'task_number': i, 'condition': label, 'run_id': row['run_id'],
                         'success': row['evaluation']['official_success'],
                         'total_tokens': row['known_total_tokens'],
                         'agent_tokens': role_costs.get('agent', 0),
                         'memory_tokens': sum(v for k, v in role_costs.items() if k != 'agent'),
                         'model_calls': row['model_calls'], 'wall_seconds': row['wall_seconds'],
                         'stop_reason': row['stop_reason']})
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--measurements', type=Path, nargs='+', required=True)
    parser.add_argument('--labels', nargs='+', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--title', required=True)
    args = parser.parse_args()
    rows = load_rows(args.measurements, args.labels)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / 'comparison.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 6.4), layout='constrained')
    colors = ['#286b8a', '#bd732a', '#6c8d55', '#865b95']
    width = 0.74 / len(args.labels)
    for c, label in enumerate(args.labels):
        subset = [r for r in rows if r['condition'] == label]
        for row in subset:
            y = row['task_number'] - 1 + (c - (len(args.labels) - 1) / 2) * width
            hatch = None if row['success'] else '///'
            for ax, value in zip(axes, [row['total_tokens']/1000, row['wall_seconds']/60]):
                ax.barh(y, value, height=width*.88, color=colors[c % len(colors)],
                        hatch=hatch, edgecolor='#555555', linewidth=.4)
                text = f"{row['total_tokens']:,}" if ax is axes[0] else f"{value:.2f}分"
                ax.text(value + (3 if ax is axes[0] else .16), y,
                        text + ('  未達' if not row['success'] else ''),
                        va='center', fontsize=9)
    task_count = max(r['task_number'] for r in rows)
    for ax, key, scale in [(axes[0], 'total_tokens', 1000), (axes[1], 'wall_seconds', 60)]:
        ax.set_yticks(range(task_count), [f'課題{i+1}' for i in range(task_count)])
        ax.invert_yaxis(); ax.set_xlim(0, max(r[key] / scale for r in rows) * 1.27)
        ax.grid(axis='x', alpha=.15); ax.set_axisbelow(True)
    axes[0].set_xlabel('全役割の入力＋出力（千トークン）')
    axes[1].set_xlabel('課題の実行時間（分、独立評価を除く）')
    axes[0].set_title('失敗した試行の費用も含む')
    axes[1].set_title('計数・保持更新・環境操作を含む')
    handles = [Patch(facecolor=colors[i % len(colors)], label=label)
               for i, label in enumerate(args.labels)]
    handles.append(Patch(facecolor='white', edgecolor='#555555', hatch='///', label='独立評価で未達'))
    axes[1].legend(handles=handles, loc='lower right', frameon=False, fontsize=9)
    fig.suptitle(args.title, fontsize=16)
    fig.supxlabel('同じ4開発課題・各1試行。固定seedでも軌跡の同一性は保証しない。\n'
                  '品質同等性・統計的優位・大規模長期作業への有効性は未検証。', fontsize=10)
    for ext in ('png', 'pdf', 'svg'):
        fig.savefig(args.output_dir / ('comparison.' + ext), dpi=170,
                    metadata={'Creator': 'plot_native_comparison.py'})
    plt.close(fig)
    svg = args.output_dir / 'comparison.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
    (args.output_dir / 'sources.json').write_text(json.dumps({
        'sources': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in args.measurements},
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'conditions': args.labels, 'repeats_per_condition': 1,
        'unknown_usage_calls': 0, 'failed_trials_included': True}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'plotted_trials': len(rows)}))
