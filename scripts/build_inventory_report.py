"""Build six slides from the complete P55 audit, including missing outcomes."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from inventory_display import ARMS
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_inventory_comparison_20261023'
TASKS = [('34d9492_1', '写真整理'), ('3c13f5a_1', '電気代精算'),
         ('60d0b5b_1', '返金'), ('6104387_1', '曲一覧の書出')]
LABELS = ('F 全表示', 'D 詳細を省略', 'B 詳細＋一覧を省略')
LINK = 'https://github.com/sophiria1225/AI-/blob/main/'


def outcome(row):
    if row['record_status'] == 'not_run_after_stop': return '未実行'
    if row['record_status'] != 'evaluated': return '未評価'
    return '成功' if row['success'] else '未達'


def cost(row):
    if row['record_status'] == 'not_run_after_stop': return '—'
    return f"{row['logical_task_known_total_tokens']:,}" + (
        '＋不明' if row['logical_task_unknown_usage_calls'] else '')


def plot(report, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    font = FontProperties(fname='/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
    fig, ax = plt.subplots(figsize=(11.3, 3.1), layout='constrained', facecolor='#f6f4ed')
    ax.set_facecolor('#f6f4ed')
    maximum = max((r['logical_task_known_total_tokens'] for r in report['rows']), default=1)
    colors = ('#657685', '#177b79', '#b95d39')
    for index, (arm, label, color) in enumerate(zip(ARMS, LABELS, colors, strict=True)):
        for position, (task, _) in enumerate(TASKS):
            row = next(r for r in report['rows'] if r['task_id'] == task and r['arm'] == arm)
            x = position + (index - 1) * .25
            if row['record_status'] == 'not_run_after_stop':
                ax.text(x, maximum * .035, '未実行', ha='center', rotation=90, fontproperties=font, fontsize=10)
                continue
            unknown = row['logical_task_unknown_usage_calls'] > 0
            ax.bar(x, row['logical_task_known_total_tokens'], width=.23, color=color,
                   hatch='//' if unknown else None, label=label if position == 0 else None)
            annotation = outcome(row) + ('・費用不明' if unknown else '')
            ax.text(x, row['logical_task_known_total_tokens'] + maximum * .025,
                    annotation, ha='center', fontproperties=font, fontsize=10,
                    rotation=25 if unknown else 0)
    ax.set_xticks(range(4), [label for _, label in TASKS], fontproperties=font, fontsize=12)
    ax.set_ylabel('共通前半＋継続の総 token', fontproperties=font, fontsize=12)
    ax.set_ylim(0, maximum * 1.35)
    ax.ticklabel_format(axis='y', style='plain')
    ax.legend(prop=font, frameon=False, ncol=3, loc='upper center')
    ax.spines[['top', 'right']].set_visible(False)
    for ext in ('svg', 'png', 'pdf'): fig.savefig(output / ('work_tokens.' + ext), dpi=180)
    plt.close(fig)


def build(root, output):
    source_paths = ('reports/P55_comparison.json', 'reports/P55_prefix_checks.json',
                    'reports/P55_initial_inventory_visibility.json',
                    'reports/P55_full_control_variation.json', 'reports/P55_server_session.json')
    report, pre, visibility, variation, server = [read(root / p) for p in source_paths]
    if (report['audit_errors'] or not report['all_planned_cells_accounted'] or len(report['rows']) != 12
            or server['status'] != 'stopped' or pre['status'] != 'complete'):
        raise ValueError('closed and audited whole-cohort evidence required')
    output.mkdir(parents=True, exist_ok=True)
    plot(report, output)
    slides = [{'title': '必要な情報を残すハーネス制御<br>API一覧と詳細の表示比較', 'cover': True}]
    def add(title, body, takeaway, refs, notes):
        slides.append(dict(title=title, body=body, takeaway=takeaway, refs=refs, notes=notes, cover=False))
    add('一覧を残すことが、品質と総費用にどう響くか',
        '<p class="lead">最終目標：必要な情報・処理と最終品質を守り、仕事全体の費用を減らす。</p>'
        '<table><tr><th>条件</th><th>古い詳細</th><th>API一覧・説明</th></tr>'
        '<tr><td>F 全表示</td><td>保持</td><td>保持</td></tr>'
        '<tr><td>D 詳細を省略</td><td>由来が一致する区間を省略</td><td>保持</td></tr>'
        '<tr><td>B 詳細＋一覧を省略</td><td>Dと同じ区間を省略</td><td>由来が一致する区間を省略</td></tr></table>'
        '<p class="small">Python状態・公開スキーマ・原文への参照・契約返信・予算を共通にする。</p>',
        '既知４課題の同じ８応答後、各３条件を一度ずつ。通常方式の開発比較。',
        [('固定計画', 'docs/experiments/P55_inventory_comparison.md')],
        '各16生成・継続120,000 token・480秒。省略は境界で一度だけ。最新応答、操作、リテラル、混合出力を保持。初回cache_prompt=false。未閲覧12課題は使用していない。')

    table = []
    for task, label in TASKS:
        cells = [next(r for r in report['rows'] if r['task_id'] == task and r['arm'] == arm) for arm in ARMS]
        table.append('<tr><td>' + label + '</td>' + ''.join(
            f'<td>{outcome(r)}<br><span class="metric">{cost(r)}</span></td>' for r in cells) + '</tr>')
    counts = report['record_status_counts']
    add('全12予定条件を、成否と仕事全体の費用で見る',
        '<table class="results"><tr><th>課題</th><th>F 全表示</th><th>D 詳細を省略</th><th>B 詳細＋一覧を省略</th></tr>'
        + ''.join(table) + '</table><p class="small">数値：共通前半＋継続の全入力出力 token。'
        f'評価済み{counts.get("evaluated", 0)}、未評価{counts.get("attempted_unevaluated", 0)}、'
        f'未実行{counts.get("not_run_after_stop", 0)}。</p>',
        '不明費用と未実行をゼロで埋めず、失敗して安く終了した条件を改善に数えない。',
        [('全件監査', 'reports/P55_comparison.json')],
        '成否は独立評価器。モデル使用量不明でも、作用と片付けが既知の場合だけ最終状態を評価する事前規則。全12条件の費用が確定しなければ総費用の採用基準は未達。')

    add('初回の入力短縮と、終了までの総費用を分ける',
        '<img class="chart" src="work_tokens.svg" alt="全４課題・３条件の仕事全体tokenと最終成否"/>'
        '<p class="small">Dの初回削減：' + ' ／ '.join(f'{n:,}' for n in pre['detail_control_allocation_gate']['removed_tokens'])
        + ' token。最終費用とは別の指標。</p>',
        '棒は共通前半と継続の既知費用。斜線がある場合は、さらに不明費用が存在する。',
        [('初回計数', 'reports/P55_prefix_checks.json'), ('総費用', 'reports/P55_comparison.json')],
        'キャッシュした入力も論理tokenへ含む。処理入力・出力・モデル呼出し・API・時間は別集計。縦軸は０から。失敗条件や未実行を除外しない。')

    totals = [report['totals'][a] for a in ARMS]
    metric_rows = []
    for label, key in [('AI呼出し', 'model_calls'), ('継続API', 'api_requests'),
                       ('復元API', 'setup_api_requests'), ('使用量不明の呼出し', 'unknown_usage_calls')]:
        metric_rows.append('<tr><td>' + label + '</td>' + ''.join(f'<td>{t[key]:,}</td>' for t in totals) + '</tr>')
    metric_rows.append('<tr><td>継続実時間（秒）</td>' + ''.join(
        f'<td>{t["continuation_wall_seconds"]:,.1f}</td>' for t in totals) + '</tr>')
    add('取得・実行・失敗・推論器の稼働も記録する',
        '<table><tr><th>全４課題の合計</th><th>F</th><th>D</th><th>B</th></tr>' + ''.join(metric_rows) + '</table>'
        f'<p class="small">推論器：ロード{server["load_wall_seconds"]:.1f}秒、常駐{server["wall_seconds"]:,.1f}秒。'
        '比較終了後に停止済み。</p>',
        'APIが少ないことだけでは、要求を満たす仕事が効率化されたとは判断しない。',
        [('費用監査', 'reports/P55_comparison.json'), ('推論器記録', 'reports/P55_server_session.json')],
        '実験用の状態復元・評価と運用時の継続を区別。全条件共通の前半モデル費用を足すが、同じ元実行を実際に何度も生成したという意味ではない。')

    gate = '達成' if report['development_gate_met'] else '未達'
    advantage = '支持条件を満たす' if report['inventory_advantage_supported'] else '支持条件を満たさない'
    add('投稿の中心へ使える範囲を限定する',
        f'<p class="lead">固定した開発上の採用基準：{gate}<br>一覧保持の追加価値：{advantage}</p>'
        '<table><tr><th>制約</th><th>解釈</th></tr>'
        '<tr><td>既知４課題、各１回</td><td>一般的な性能維持・非劣性の証明ではない</td></tr>'
        '<tr><td>返金はD/Bの基礎入力が同じ</td><td>その差を一覧の効果と呼ばない</td></tr>'
        '<tr><td>API名・状態・原文が別経路に残る</td><td>完全な情報消去の実験ではない</td></tr>'
        '<tr><td>段階的な開示には先行方式がある</td><td>通常方式を独自アルゴリズムにしない</td></tr></table>',
        '10月23日：主張・主要結果・概要を絞る。10月31日：レター投稿完了を目指す。',
        [('採録見込みの評価', 'docs/letter_assessment_20261023.md'),
         ('近接研究', 'docs/inventory_retention_overlap_20261023.md')],
        '採用条件は全12件評価・使用量既知・監査合格、DがF/Bの成功を失わず総tokenがFより少なくB以下。'
        '一覧の効果を支持するには入力が異なる課題でD成功/B失敗も必要。中心的な新規性や一般的な品質維持が自動的に成立するわけではない。')

    sections = []
    for number, slide in enumerate(slides, 1):
        if slide['cover']:
            sections.append(f'<section class="slide cover"><h1>{slide["title"]}</h1><div class="notes"></div></section>')
            continue
        refs = ' / '.join(f'<a href="{LINK + path}">{html.escape(label)}</a>' for label, path in slide['refs'])
        sections.append(f'<section class="slide"><div class="eyebrow">10月23日 API表示の比較 / {number-1:02d}</div>'
            f'<h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div>'
            f'<div class="footer"><span class="sources">{refs}</span><span>{number}/{len(slides)}</span></div>'
            f'<div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    extra = '.chart{display:block;width:1120px;height:325px;object-fit:contain}table{font-size:20px}h2{font-size:35px}.small{margin-top:18px}.results td{padding:10px 16px}.metric{font-size:19px;font-variant-numeric:tabular-nums}'
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P55 API一覧と詳細</title><style>'
        + STYLE + extra + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    write = lambda path, value: path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    write(output / 'slides.json', slides)
    manifest = {'generated_at': datetime.now(timezone.utc).isoformat(), 'pages': len(slides),
        'source_sha256': {p: sha(root / p) for p in source_paths}, 'builder_sha256': sha(Path(__file__)),
        'visual_reviewed': False, 'scope': 'Known-cohort development comparison; no general quality or novel method claim.'}
    write(output / 'build_manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, default=ROOT / 'materials/20261023_p55')
    p.add_argument('--pdf', action='store_true'); args = p.parse_args()
    print(json.dumps(build(ROOT, args.output)))
    if args.pdf:
        build_budget_report.STEM = STEM; build_budget_report.export(args.output)
