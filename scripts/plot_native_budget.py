"""Plot every completed native trial, including failures and unknown usage."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--summary', type=Path, required=True)
    p.add_argument('--budget', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    summary = json.loads(args.summary.read_text())
    budget = json.loads(args.budget.read_text())
    if summary['pending'] or summary['audit_errors']:
        raise ValueError('all trials must be complete and audited')
    if summary['plan_sha256'] != budget['plan_sha256']:
        raise ValueError('plan hashes differ')
    outcomes = summary['trials']
    measured = budget['trials']
    if [r['run_id'] for r in outcomes] != [r['run_id'] for r in measured]:
        raise ValueError('trial cohorts differ')
    rows = []
    for index, (outcome, record) in enumerate(zip(outcomes, measured, strict=True), 1):
        if outcome['audit_errors'] or outcome['evaluation'] is None:
            raise ValueError('missing audited evaluation')
        for key in ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'wall_seconds'):
            if outcome[key] != record[key]:
                raise ValueError('aggregate mismatch: ' + key)
        rows.append({'task_number': index, 'run_id': record['run_id'],
                     'success': outcome['evaluation']['official_success'],
                     'stop_reason': record['stop_reason'],
                     **{k: record[k] for k in ('model_calls', 'api_requests', 'known_total_tokens',
                                               'unknown_usage_calls', 'wall_seconds')},
                     **record['limits']})
    if not rows:
        raise ValueError('empty cohort')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir/'native_budget.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.8), layout='constrained')
    colors = ['#276B8C' if r['success'] else '#A66A32' for r in rows]
    labels = [f"課題{r['task_number']}  {'成功' if r['success'] else '未達'}\n"
              f"{r['model_calls']} LLM生成" for r in rows]
    panels = [('known_total_tokens', 'max_total_tokens', 1000, '総入力＋出力（千トークン）'),
              ('api_requests', 'max_api_requests', 1, '実際に送信したAPI要求'),
              ('wall_seconds', 'max_wall_seconds', 60, '実行時間（分）')]
    for ax, (key, cap, unit, xlabel) in zip(axes, panels, strict=True):
        values = [r[key]/unit for r in rows]
        ax.barh(range(len(rows)), values, color=colors)
        ax.set_yticks(range(len(rows)), labels if ax is axes[0] else [])
        ax.invert_yaxis()
        maximum = max(max(values), max(r[cap]/unit for r in rows))
        ax.set_xlim(0, maximum*1.25)
        caps = {r[cap]/unit for r in rows}
        if len(caps) == 1:
            ax.axvline(next(iter(caps)), ls='--', color='#8A9199', lw=1)
        for i, (r, value) in enumerate(zip(rows, values, strict=True)):
            label = str(r[key]) if key == 'api_requests' else f'{value:.1f}'
            if key == 'known_total_tokens' and r['unknown_usage_calls']:
                label += f" + 不明{r['unknown_usage_calls']}"
            ax.text(value+maximum*.015, i, label, va='center', fontsize=10)
        ax.set_xlabel(xlabel)
        ax.grid(axis='x', alpha=.15)
        ax.set_axisbelow(True)
    fig.suptitle(f"{budget['phase']}：全履歴基準の全{len(rows)}課題・失敗も含む費用", fontsize=16)
    fig.supxlabel('破線は各上限。各課題１試行。API上限・トークン予約・時間制限を区別する。\n'
                  '新方式との比較ではなく、自然な実行上の制約を調べる開発実験。', fontsize=10)
    for extension in ('png', 'pdf', 'svg'):
        fig.savefig(args.output_dir/('native_budget.'+extension), dpi=180,
                    metadata={'Creator': 'plot_native_budget.py'})
    plt.close(fig)
    svg = args.output_dir/'native_budget.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    sources = {'source_sha256': {str(path): digest(path) for path in (args.summary, args.budget)},
               'script_sha256': digest(Path(__file__)), 'trials': len(rows),
               'unknown_usage_policy': 'Known tokens remain a lower bound where usage is unknown.'}
    (args.output_dir/'sources.json').write_text(json.dumps(sources, indent=2)+'\n')
    print(json.dumps({'plotted_finished_trials': len(rows)}))


if __name__ == '__main__':
    main()
