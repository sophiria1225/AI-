"""Plot P7's bound qualitative review and all known generation costs."""
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
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--conformance', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    review, audit = [json.loads(p.read_text()) for p in (args.review, args.conformance)]
    if audit['audit_errors'] or review['source_request_sha256'] != audit['source_request_sha256']:
        raise ValueError('source mismatch or conformance failure')
    costs = {r['call_id']: r for r in audit['calls']}
    rows = []
    for r in review['calls']:
        c = costs[r['call_id']]
        if r['request_sha256'] != c['request_sha256'] or r['response_sha256'] != c['response_sha256']:
            raise ValueError('review and accounting refer to different output')
        label = ('invalid' if not r['semantic_measurement_available'] else
                 'unsupported' if r['unsupported_operation_done'] else
                 'ambiguous' if r['ambiguous_done_items'] else 'none_detected')
        rows.append({k: r[k] for k in ('call_id', 'variant', 'seed', 'reviewed_done_items',
                                      'unsupported_operation_done', 'ambiguous_done_items')} |
                    {'classification': label, 'input_tokens': c['input_tokens'],
                     'output_tokens': c['output_tokens']})
    variants = ['raw', 'quarantine', 'execution_tag']
    labels = ['原入力', '未実行文を退避', '未実行記録を追加']
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), layout='constrained')
    base = [0, 0, 0]
    groups = [('unsupported', '未支持の操作完了あり', '#b16c21'),
              ('ambiguous', '未支持の操作完了なし・曖昧項目あり', '#d8c9aa'),
              ('none_detected', '未支持の操作完了・曖昧項目なし', '#246185'),
              ('invalid', '形式不適合：意味を測れず', '#b9bfc4')]
    for key, label, color in groups:
        values = [sum(r['variant'] == v and r['classification'] == key for r in rows) for v in variants]
        axes[0].bar(range(3), values, bottom=base, color=color, label=label)
        base = [b + n for b, n in zip(base, values)]
    axes[0].set_xticks(range(3), labels)
    axes[0].set_yticks([0, 1, 2, 3])
    axes[0].set_ylabel('生成された台帳の数（各条件3回）')
    axes[0].set_title('公開の実行記録に基づく完了項目の確認')
    axes[0].legend(frameon=False, fontsize=9, loc='upper center', bbox_to_anchor=(.5, -.1))
    inputs = [sum(r['input_tokens'] or 0 for r in rows if r['variant'] == v) / 1000 for v in variants]
    outputs = [sum(r['output_tokens'] or 0 for r in rows if r['variant'] == v) / 1000 for v in variants]
    axes[1].bar(range(3), inputs, color='#246185', label='入力')
    axes[1].bar(range(3), outputs, bottom=inputs, color='#71a7bc', label='出力')
    for i, (a, b) in enumerate(zip(inputs, outputs)):
        unknown = sum(c['variant'] == variants[i] and c['status'] != 'ok' for c in costs.values())
        suffix = f'＋不明{unknown}回' if unknown else ''
        axes[1].text(i, a+b+.5, f'{int(round((a+b)*1000)):,}' + suffix, ha='center', fontsize=10)
    axes[1].set_ylim(0, max(a+b for a, b in zip(inputs, outputs)) * 1.18)
    axes[1].set_xticks(range(3), labels)
    axes[1].set_ylabel('既知の入力＋出力（千トークン、3回合計）')
    axes[1].set_title('記憶生成の全費用')
    axes[1].legend(frameon=False)
    fig.suptitle('P7：同じ保存入力の表現を変えた9回の記憶生成', fontsize=15)
    fig.supxlabel('助手1者の非盲検・探索的確認。1選択状態の3種反復。未支持の完了がないことは、課題成功の証明ではない。', fontsize=9)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ('png', 'pdf', 'svg'):
        fig.savefig(args.output_dir / ('memory_probe.' + suffix), dpi=160,
                    metadata={'Creator': 'plot_memory_probe.py'})
    svg = args.output_dir / 'memory_probe.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
    plt.close(fig)
    with (args.output_dir / 'calls.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    (args.output_dir / 'sources.json').write_text(json.dumps({
        'sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (args.review, args.conformance)},
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, indent=2) + '\n')
    print(json.dumps({'calls': len(rows), 'output_dir': str(args.output_dir)}))


if __name__ == '__main__':
    main()
