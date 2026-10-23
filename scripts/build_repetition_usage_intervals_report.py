"""Export the closed conditional intervals, with failure costs kept visible."""
import csv
from pathlib import Path

from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def run():
    report_path = ROOT / 'reports/P81_usage_intervals_20261024.json'
    report = read(report_path)
    for name, digest in report['source_sha256'].items():
        if sha(ROOT / name) != digest:
            raise ValueError('interval_source_changed')
    output = ROOT / 'materials/20261024_p81_usage_intervals'
    output.mkdir(exist_ok=True)
    partitions = []
    for label, groups in [*report['repetitions'].items(), ('combined', report['combined'])]:
        for category, data in groups.items():
            partitions.append(dict(repetition=label, category=category,
                M_lower=data['measured'][0], M_upper=data['measured'][1],
                H_lower=data['not_exposed'][0], H_upper=data['not_exposed'][1],
                H_minus_M_lower=data['H_minus_M'][0], H_minus_M_upper=data['H_minus_M'][1],
                original_unknown_usage_calls=data['original_unknown_usage_calls']))
    cells = []
    for run_id in dict.fromkeys(r['run_id'] for r in report['rows']):
        rows = [r for r in report['rows'] if r['run_id'] == run_id]
        cells.append(dict(run_id=run_id, **{k: rows[0][k] for k in
            ('repetition', 'task_id', 'time_visibility', 'success')},
            known_total_tokens=sum(r['logical_tokens_lower_bound'] for r in rows if r['complete_usage']),
            original_unknown_usage_calls=sum(not r['complete_usage'] for r in rows),
            conditional_lower=sum(r['logical_tokens_lower_bound'] for r in rows),
            conditional_upper=sum(r['logical_tokens_upper_bound'] for r in rows)))
    for name, rows in [('partitions.csv', partitions), ('all_24_conditions.csv', cells)]:
        with (output / name).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.8), layout='constrained')
    fig.get_layout_engine().set(h_pad=.12, w_pad=.10)
    colors = ['#336b87', '#b85f2a', '#253746']
    left, right = axes
    for y, rep in enumerate(('3', '2', '1')):
        lo, hi = [v / 1000 for v in report['repetitions'][rep]['total']['H_minus_M']]
        center = (lo + hi) / 2
        left.errorbar(center, y, xerr=[[center-lo], [hi-center]], fmt='o' if lo == hi else 'none', capsize=6,
                      color=colors[2], lw=2, markersize=6)
        text = f'{lo:+.1f}' if lo == hi else f'{lo:+.1f} ～ {hi:+.1f}'
        left.annotate(text, (center, y), xytext=(0, 14), textcoords='offset points',
                      ha='center', va='bottom')
    left.set(yticks=[0, 1, 2], yticklabels=['第３反復', '第２反復', '第１反復'],
             xlim=(-170, 105), ylim=(-.55, 2.65), title='各反復の全４課題：方向は一定しない')
    for y, category, color in [(2, 'both_success', colors[0]),
                                (1, 'both_failure', colors[1]), (0, 'total', colors[2])]:
        lo, hi = [v/1000 for v in report['combined'][category]['H_minus_M']]
        center = (lo+hi)/2
        guaranteed = hi if hi < 0 else lo if lo > 0 else 0
        right.barh(y, guaranteed, height=.22, color=color, alpha=.35)
        right.errorbar(center, y, xerr=[[center-lo], [hi-center]], fmt='o' if lo == hi else 'none',
                       color=color, lw=2, capsize=6, markersize=6)
        text = f'{lo:+.1f}' if lo == hi else f'{lo:+.1f} ～ {hi:+.1f}'
        right.annotate(text, (center, y), xytext=(0, 14), textcoords='offset points',
                       ha='center', va='bottom', color=color)
    right.set(yticks=[0, 1, 2], yticklabels=['全課題の合計', '両条件で失敗', '両条件で成功'],
              xlim=(-560, 550), ylim=(-.55, 2.65), title='３反復合計：成功課題の削減を失敗費用が相殺')
    for ax in axes:
        ax.axvline(0, color='#888888', lw=.8, ls='--')
        ax.set_xlabel('H − M の論理token（千token）\n負：非表示Hが少ない　正：非表示Hが多い')
        ax.grid(axis='x', alpha=.15)
    fig.suptitle('残時間の非表示による費用差：欠測を保持した条件付き区間', fontsize=14)
    fig.supxlabel('既知４課題を同一seedで３反復. 線は計数の前提に基づく上下限で, 統計的信頼区間ではない.', fontsize=9)
    for extension in ('png', 'svg', 'pdf'):
        fig.savefig(output / f'conditional_cost_intervals.{extension}', dpi=190)
    plt.close(fig)
    write_json(output / 'build_manifest.json', dict(
        report_sha256=sha(report_path), builder_sha256=sha(Path(__file__)),
        rows=len(report['rows']), conditions=len(cells), partition_rows=len(partitions),
        original_unknown_usage_calls=report['original_unknown_usage_preserved'],
        interpretation='Deterministic bounds conditional on backend and ordinal association, not statistical confidence intervals.',
        artifacts_sha256={p.name: sha(p) for p in sorted(output.iterdir())
                          if p.suffix in ('.csv', '.png', '.svg', '.pdf')}))
    print({'conditions': len(cells), 'partitions': len(partitions), 'output': str(output)})


if __name__ == '__main__':
    run()
