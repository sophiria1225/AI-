"""Add a title-only cover and move the legend off the P82 data points."""
import argparse
import html
import shutil
from pathlib import Path

import build_budget_report
from build_late_clock_report_v02 import STEM, LABELS, POLICIES, TASKS, validated
from build_budget_visibility_repetition_report import table
from build_morning_report import STYLE, SCRIPT
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def figure(output, plan, rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(2, 2, figsize=(11, 4.3), facecolor='#f6f4ed')
    fig.subplots_adjust(left=.08, right=.99, top=.84, bottom=.12, wspace=.22, hspace=.58)
    for number, (ax, task) in enumerate(zip(axes.flat, plan['known_tasks'], strict=True)):
        ax.set_facecolor('#f6f4ed'); ax.set_title(TASKS[number], loc='left', fontsize=11)
        for j, policy in enumerate(POLICIES):
            color = ('#7d8892', '#177b79', '#bd683c')[j]
            for row in rows:
                if row['task_id'] != task['task_id'] or row['time_visibility'] != policy:
                    continue
                marker = '^' if row['unknown_usage_calls'] else ('o', 'D', 's')[j]
                ax.scatter(row['repetition'] + (j - 1) * .08, row['known_total_tokens'] / 1000,
                    s=48, marker=marker, edgecolor=color,
                    facecolor=color if row['success'] else '#f6f4ed', lw=1.5)
            ax.plot([], [], color=color, marker=('o', 'D', 's')[j], linestyle='', label=LABELS[j])
        largest = max(r['known_total_tokens'] / 1000 for r in rows if r['task_id'] == task['task_id'])
        ax.set_ylim(0, max(1, largest) * 1.15); ax.set_xlim(.65, 2.35)
        ax.set_xticks([1, 2], ['反復1', '反復2']); ax.grid(axis='y', alpha=.15)
        ax.set_ylabel('論理token（千）')
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', bbox_to_anchor=(.5, 1), ncol=3, frameon=False)
    for ext in ('svg', 'png', 'pdf'):
        fig.savefig(output / 'figures' / ('P82_whole_task_costs.' + ext), dpi=180, facecolor='#f6f4ed')
    plt.close(fig)


def run(source, output):
    plan, report, _, stability, _ = validated()
    if output.exists():
        raise FileExistsError('preserve_all_presentation_versions')
    if read(source / 'layout_checks.json')['errors']:
        raise ValueError('table_layout_must_already_be_fixed')
    manifest = read(source / 'build_manifest.json')
    original_csv = {p.name: sha(p) for p in source.glob('*.csv')}
    shutil.copytree(source, output)
    figure(output, plan, report['rows'])
    slides = read(source / 'slides.json')
    transitions = []
    for task, label in zip(plan['known_tasks'], TASKS, strict=True):
        positions = []
        for rep in (1, 2):
            row = next(r for r in report['rows'] if r['task_id'] == task['task_id']
                       and r['repetition'] == rep and r['time_visibility'] == 'late_half')
            pos = stability['traces'][row['run_id']]['first_measured_notice_call']
            positions.append('未到達' if pos is None else str(pos))
        transitions.append((label, *positions))
    slides[5]['body'] += table(('Lの表示開始生成', '反復1', '反復2'), transitions, 'transitions')
    cover = dict(title='残時間通知と全仕事費用の比較', body='', takeaway='', notes='', cover=True)
    slides.insert(0, cover)
    sections = ['<section class="slide cover"><h1>' + cover['title'] + '</h1></section>']
    for number, slide in enumerate(slides[1:], 2):
        sections.append(f'<section class="slide"><div class="eyebrow">10月24日 時間通知の３条件比較 / {number-1:02d}</div>'
            f'<h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div>'
            f'<div class="footer"><span>既知４課題・全24条件・２反復</span><span>{number}/{len(slides)}</span></div>'
            f'<div class="notes">{html.escape(slide["notes"])}</div></section>')
    css = ('h2{font-size:29px}table{font-size:18px}td{padding:9px 12px}'
           '.results td,.results th{font-size:14px;line-height:1.25;padding:3px 9px}'
           '.transitions{margin-top:10px}.transitions td,.transitions th{font-size:14px;line-height:1.2;padding:3px 9px}'
           '.cost-figure{width:100%;height:365px;object-fit:contain}')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P82 全件結果</title><style>'
        + STYLE + css + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    write_json(output / 'slides.json', slides)
    if any(sha(output / name) != expected for name, expected in original_csv.items()):
        raise ValueError('all_numerical_CSV_bytes_must_be_preserved')
    manifest.update(pages=len(slides), content_pages=7, title_only_cover=True,
        finalizer_sha256=sha(Path(__file__)), previous_manifest_sha256=sha(source / 'build_manifest.json'),
        csv_sha256=original_csv, html_sha256=sha(output / 'index.html'), slides_sha256=sha(output / 'slides.json'),
        presentation_revision='Shared legend outside all data axes; title-only cover; all eight L transition positions displayed.',
        visual_reviewed=False)
    write_json(output / 'build_manifest.json', manifest)
    build_budget_report.STEM = STEM
    build_budget_report.export(output)
    print({'pages': len(slides), 'CSV_bytes_unchanged': True, 'layout': read(output / 'layout_checks.json')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'materials/20261024_p82_results_v02')
    parser.add_argument('--output', type=Path, default=ROOT / 'materials/20261024_p82_results_final')
    args = parser.parse_args(); run(args.source, args.output)
