"""Draw sealed P16 review counts and complete accounting, without private text."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def architecture(output_dir):
    fig, ax = plt.subplots(figsize=(11.5, 6), layout='constrained')
    ax.set_xlim(0, 11.5)
    ax.set_ylim(0, 6)
    ax.axis('off')

    def box(x, y, w, h, title, color='#e9f0f3'):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=.08',
                                    facecolor=color, edgecolor='#406176', linewidth=1.3))
        ax.text(x + w / 2, y + h / 2, title, ha='center', va='center', fontsize=10)

    def arrow(start, end):
        ax.annotate('', xy=end, xytext=start,
                    arrowprops={'arrowstyle': '->', 'color': '#406176', 'lw': 1.5})

    ax.text(5.75, 5.85, 'P16の構成：変更するのは記憶役へ渡す表示',
            ha='center', fontsize=16, weight='bold')
    box(.2, 2.5, 2.1, 1.35, '固定した４課題の記録\n選んだ操作までの履歴\n公開の要求・API資料')
    box(3, 3.6, 2.3, 1.05, '記録通りの観測\n３表示の入力は同じ')
    box(3, 1.6, 2.3, 1.2, '送信前拒否の制御条件\n通常の引数検査を使用\n新たなAPI送信０', '#f4e8da')
    arrow((2.38, 3.55), (2.92, 4.1))
    arrow((2.38, 2.8), (2.92, 2.2))
    box(6, 2.45, 2.05, 1.4, '３つの表示\n元入力\n未送信の明記\n要求本文の退避', '#dbeaf1')
    arrow((5.38, 4.1), (5.92, 3.55))
    arrow((5.38, 2.2), (5.92, 2.8))
    box(8.8, 2.6, 2.3, 1.1, '同じM3で台帳を生成\n各条件の入力・出力\n費用と形式不備を保存')
    arrow((8.13, 3.15), (8.72, 3.15))
    box(7.1, .45, 4, 1.05, '全生成終了 → 項目判定 → ラベル固定\nその後に方式名と対応づけて集計', '#e4eddf')
    arrow((9.95, 2.52), (9.95, 1.58))
    ax.text(.2, .65, '元記録は変更しない。\n後続の完了宣言・最終評価は入力に使わない。\n修復と最終タスク成功は、この段階では測らない。',
            fontsize=10, va='center')
    for suffix in ('png', 'pdf', 'svg'):
        fig.savefig(output_dir / ('event_view_architecture.' + suffix), dpi=160)
    plt.close(fig)
    svg = output_dir / 'event_view_architecture.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--review', type=Path, required=True)
    p.add_argument('--structural', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    review, structural = read(args.review), read(args.structural)
    if (not review['review_complete'] or structural['audit_errors']
            or review['structural_audit_sha256'] != sha(args.structural)):
        raise ValueError('sealed review and passing structural audit must match')
    if review['known_total_tokens'] != structural['known_total_tokens']:
        raise ValueError('cost mismatch')
    variants = ['raw', 'execution_tag', 'quarantine']
    names = ['元入力', '未送信の明記', '要求の退避']
    conditions = ['recorded', 'rejected_before_dispatch']
    rows = []
    for condition in conditions:
        for variant in variants:
            g, = [g for g in review['groups']
                  if (g['condition'], g['variant']) == (condition, variant)]
            unsupported = g['outputs_with_unsupported_done_action']
            uncertain = g['outputs_with_unsupported_or_ambiguous_done'] - unsupported
            none = g['valid_reviewed_outputs'] - unsupported - uncertain
            invalid = g['reviewed_outputs'] - g['valid_reviewed_outputs']
            missing = 4 - g['reviewed_outputs']
            categories = [unsupported, uncertain, none, invalid, missing]
            if min(categories) < 0 or sum(categories) != 4:
                raise ValueError('four planned source outputs per group required')
            rows.append({'condition': condition, 'variant': variant,
                         'unsupported_completion': unsupported,
                         'ambiguous_without_detected_unsupported': uncertain,
                         'neither_detected': none, 'schema_invalid': invalid,
                         'no_reviewable_output': missing,
                         'known_tokens': g['known_tokens'],
                         'unknown_usage_calls': g['unknown_usage_calls']})

    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.8), layout='constrained',
                             gridspec_kw={'width_ratios': [1, 1, 1.4]})
    categories = [('unsupported_completion', '未支持の操作完了あり', '#b46c25'),
                  ('ambiguous_without_detected_unsupported', '未支持なし・曖昧項目あり', '#d8c9aa'),
                  ('neither_detected', '対象の未支持・曖昧項目を検出せず', '#306c87'),
                  ('schema_invalid', '形式不適合（意味を判定せず）', '#b6bdc1'),
                  ('no_reviewable_output', '未生成・応答なし', '#e5e7e9')]
    for ax, condition, title in zip(axes[:2], conditions,
                                     ['記録通りの結果：入力同一の対照', '人工的な送信前拒否']):
        subset = [r for r in rows if r['condition'] == condition]
        bottom = [0] * 3
        for key, label, color in categories:
            values = [r[key] for r in subset]
            ax.bar(range(3), values, bottom=bottom, label=label, color=color)
            for x, b, value in zip(range(3), bottom, values):
                if value:
                    ax.text(x, b + value / 2, str(value), ha='center', va='center')
            bottom = [a + b for a, b in zip(bottom, values)]
        ax.set_xticks(range(3), names, rotation=15)
        ax.set_yticks(range(5))
        ax.set_ylim(0, 4.35)
        ax.set_title(title, fontsize=11)
        ax.set_ylabel('出力数（４課題 × １ seed）')
    axes[0].legend(frameon=False, loc='upper left', bbox_to_anchor=(0, -.2), fontsize=8)
    xs = range(6)
    values = [r['known_tokens'] / 1000 for r in rows]
    axes[2].bar(xs, values, color=['#91b0be'] * 3 + ['#306c87'] * 3)
    for x, value, r in zip(xs, values, rows):
        suffix = f"\n＋不明{r['unknown_usage_calls']}回" if r['unknown_usage_calls'] else ''
        axes[2].text(x, value + max(values, default=1) * .015,
                     f"{r['known_tokens']:,}" + suffix, ha='center', fontsize=8)
    axes[2].set_xticks(xs, [s + '\n' + name for s in ('記録通り', '人工拒否') for name in names],
                       rotation=25, ha='right', fontsize=8)
    axes[2].set_ylabel('既知の入力＋出力（千トークン）')
    axes[2].set_ylim(0, max(values, default=1) * 1.25 or 1)
    axes[2].set_title('記憶生成の全費用：不適合出力も含む', fontsize=11)
    fig.suptitle('P16：実行記録の表示を変えた記憶生成の導入確認', fontsize=15)
    fig.supxlabel('助手１名の探索的判定。４開発課題で、対照の反復や項目数は独立課題数ではない。\n'
                  '未支持の完了がないことは、記憶全体の正しさ・修復・最終タスク成功を意味しない。', fontsize=9)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ('png', 'pdf', 'svg'):
        fig.savefig(args.output_dir / ('event_view_probe.' + suffix), dpi=160)
    plt.close(fig)
    svg = args.output_dir / 'event_view_probe.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
    architecture(args.output_dir)
    with (args.output_dir / 'counts_and_costs.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    (args.output_dir / 'sources.json').write_text(json.dumps({
        'source_sha256': {args.review.name: sha(args.review), args.structural.name: sha(args.structural)},
        'script_sha256': sha(Path(__file__)),
        'planned_outputs': 24, 'semantic_claim': 'Counts only; no general superiority or repair effect.'
    }, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'groups': len(rows), 'output_dir': str(args.output_dir)}))


if __name__ == '__main__':
    main()
