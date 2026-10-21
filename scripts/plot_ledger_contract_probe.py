"""Draw P17 from the sealed semantic review and independently audited costs."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Rectangle


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--structural', type=Path, required=True)
    p.add_argument('--review', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    audit, review = read(args.structural), read(args.review)
    if (audit['run_id'] != 'P17_01' or audit['status'] != 'complete'
            or audit['audit_errors'] or not review['review_complete']
            or review['structural_audit_sha256'] != sha(args.structural)
            or audit['known_total_tokens'] != review['known_total_tokens']):
        raise ValueError('complete passing P17 audit and sealed matching review required')
    calls = {row['call_id']: row for row in audit['rows']}
    cases = sorted({row['case_id'] for row in audit['rows']})
    seeds = sorted({row['seed'] for row in audit['rows']})
    variants, names = ['legacy', 'aligned'], ['旧定義', '宣言・受取の整合版']
    if len(cases) != 4 or len(seeds) != 2 or len(calls) != 16:
        raise ValueError('expected four inputs, two seeds and two interfaces')
    categories = {
        'unsupported': ('未支持の操作完了あり', '#b76d31'),
        'ambiguous': ('未支持なし・曖昧な完了あり', '#d8c8a3'),
        'neither': ('対象の未支持・曖昧完了を検出せず', '#7297aa'),
        'invalid': ('形式不適合：意味判定対象外', '#c7cbce'),
    }
    rows = []
    for variant in variants:
        for case in cases:
            for seed in seeds:
                row, = [r for r in review['outputs']
                        if (r['variant'], r['case_id'], r['seed']) == (variant, case, seed)]
                kind = ('invalid' if not row['schema_valid'] else
                        'unsupported' if row['unsupported_done_action'] else
                        'ambiguous' if row['ambiguous_done'] else 'neither')
                call = calls[row['call_id']]
                rows.append({'case_id': case, 'seed': seed, 'variant': variant,
                             'category': kind, 'items': row['items'],
                             'done_items': row['done_items'],
                             'unsupported_done_action_items': row['unsupported_done_action'],
                             'ambiguous_done_items': row['ambiguous_done'],
                             'input_tokens': call['input_tokens'], 'output_tokens': call['output_tokens'],
                             'wall_seconds': call['wall_seconds']})
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.7), layout='constrained',
                             gridspec_kw={'width_ratios': [1.5, 1, 1]})
    ax = axes[0]
    for row in rows:
        x = variants.index(row['variant'])
        y = cases.index(row['case_id']) * 2 + seeds.index(row['seed'])
        ax.add_patch(Rectangle((x, y), 1, 1, facecolor=categories[row['category']][1],
                               edgecolor='white', linewidth=2))
        text = '形式不適合' if row['category'] == 'invalid' else f"done {row['done_items']}項目"
        ax.text(x + .5, y + .5, text, ha='center', va='center', fontsize=9)
    ax.set_xlim(0, 2); ax.set_ylim(8, 0)
    ax.set_xticks([.5, 1.5], names)
    ax.set_yticks([i+.5 for i in range(8)],
                  [f'入力{i+1}・seed {seed}' for i in range(4) for seed in seeds])
    ax.set_title('全16出力：形式と対象の意味判定')
    ax.legend(handles=[Patch(facecolor=color, label=label) for label, color in categories.values()],
              frameon=False, loc='upper left', bbox_to_anchor=(-.1, -.12), fontsize=8)
    totals = []
    for variant in variants:
        subset = [r for r in rows if r['variant'] == variant]
        totals.append({key: sum(r[key] for r in subset)
                       for key in ('input_tokens', 'output_tokens', 'wall_seconds')})
    for key, label, color in [('input_tokens', '入力', '#7297aa'),
                              ('output_tokens', '出力', '#d8c8a3')]:
        bottoms = [0, 0] if key == 'input_tokens' else [r['input_tokens']/1000 for r in totals]
        axes[1].bar(range(2), [r[key]/1000 for r in totals], bottom=bottoms, label=label, color=color)
    for i, total in enumerate(totals):
        tokens = total['input_tokens'] + total['output_tokens']
        axes[1].text(i, tokens/1000, f'{tokens:,}', ha='center', va='bottom')
    axes[1].set_xticks(range(2), names, rotation=10)
    axes[1].set_ylabel('全入力＋出力（千トークン）')
    axes[1].set_ylim(0, max((r['input_tokens']+r['output_tokens'])/1000 for r in totals)*1.15)
    axes[1].legend(frameon=False, ncol=2, fontsize=9, loc='upper left')
    axes[1].set_title('不適合も含む全費用')
    axes[2].bar(range(2), [r['wall_seconds']/60 for r in totals], color='#7297aa')
    for i, total in enumerate(totals):
        axes[2].text(i, total['wall_seconds']/60, f"{total['wall_seconds']/60:.1f}分",
                     ha='center', va='bottom')
    axes[2].set_xticks(range(2), names, rotation=10)
    axes[2].set_ylabel('モデル呼び出し時間の合計（分）')
    axes[2].set_ylim(0, max(r['wall_seconds']/60 for r in totals)*1.15)
    axes[2].set_title('同じモデル・入力群での校正')
    fig.suptitle('P17：台帳インターフェースの整合性を校正', fontsize=15)
    fig.supxlabel('既知の４開発入力・２seed。反復や項目数は独立課題数ではない。\n'
                  '助手１名の探索的判定。形式適合・対象誤りの不検出は、台帳全体の正しさや最終成功を保証しない。', fontsize=9)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    for suffix in ('png', 'pdf', 'svg'):
        fig.savefig(args.output_dir/('ledger_contract.'+suffix), dpi=160)
    plt.close(fig)
    svg = args.output_dir/'ledger_contract.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    with (args.output_dir/'counts_and_costs.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    (args.output_dir/'sources.json').write_text(json.dumps({
        'source_sha256': {args.review.name: sha(args.review), args.structural.name: sha(args.structural)},
        'script_sha256': sha(Path(__file__)), 'planned_outputs': 16,
        'scope': 'Baseline interface calibration, not a novel-method efficacy result.'
    }, indent=2)+'\n')
    print(json.dumps({'outputs': len(rows), 'output_dir': str(args.output_dir)}))


if __name__ == '__main__':
    main()
