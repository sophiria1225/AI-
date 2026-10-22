"""Six-slide decision brief from closed, audited October 22 observations."""
import argparse
import datetime as dt
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from run_handoff_factors import read, sha

ROOT = Path(__file__).resolve().parents[1]
STEM = 'AI_harness_evening_decisions_20261022'
LINK = 'https://github.com/sophiria1225/AI-/blob/main/'


def plot_counts(report, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    font = FontProperties(fname='/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
    fig, ax = plt.subplots(figsize=(11.3, 3.05), layout='constrained', facecolor='#f6f4ed')
    ax.set_facecolor('#f6f4ed')
    labels = ['写真整理', '電気代精算', '返金', '曲一覧の書出']
    modes = [('all_documented_details', '一覧を残し詳細を省略', '#657685'),
             ('used_since_document', '使用後だけ省略', '#177b79'),
             ('all_parameters_observed', '全引数名の観測後だけ省略', '#b95d39')]
    for index, (mode, label, color) in enumerate(modes):
        bars = ax.bar([i + (index - 1) * .24 for i in range(4)],
                      [row['tokens_removed'][mode] for row in report['rows']],
                      width=.22, label=label, color=color)
        ax.bar_label(bars, padding=3, fontsize=10)
    ax.axhline(1000, color='#8a6460', linestyle='--', linewidth=1.2)
    ax.text(3.48, 1035, '1,000', ha='right', color='#8a6460', fontsize=10)
    ax.set_xticks(range(4), labels, fontproperties=font, fontsize=13)
    ax.set_ylabel('初回入力の削減 token', fontproperties=font, fontsize=12)
    ax.set_ylim(0, 2050)
    ax.legend(prop=font, ncol=3, loc='upper center', frameon=False, fontsize=11)
    ax.spines[['top', 'right']].set_visible(False)
    for extension in ('svg', 'png', 'pdf'):
        fig.savefig(output / f'initial_token_reduction.{extension}', dpi=180)
    plt.close(fig)


def build(root, output):
    source_paths = ('reports/P47_comparison.json', 'reports/P51_stream_receipts_v02.json',
                    'reports/P51_stream_receipts_v02_audit.json',
                    'reports/P51_stream_receipts_v01_failure.json',
                    'reports/P52_contract_use_retention.json',
                    'reports/P53_contract_retention_counts.json',
                    'reports/P53_contract_retention_audit.json',
                    'reports/goal_alignment_20261022.json')
    p47, p51, a51, fail51, p52, p53, a53, goal = [read(root / p) for p in source_paths]
    if (p47['audit_errors'] or a51['audit_errors'] or a53['audit_errors']
            or len(p47['rows']) != 12 or p53['count_requests_completed'] != 16
            or p53['model_generations'] != 0 or p51['server_shutdown_record_pending']
            or p53['server_shutdown_record_pending'] or goal['pages_read'] != list(range(1, 29))):
        raise ValueError('closed evidence requirements not met')
    output.mkdir(parents=True, exist_ok=True)
    plot_counts(p53, output)
    slides = [dict(title='必要な処理を残すハーネス制御<br>10月23日の判断に向けた進捗', cover=True)]

    def add(title, body, takeaway, refs, notes):
        slides.append(dict(title=title, body=body, takeaway=takeaway, refs=refs,
                           notes=notes, cover=False))

    add('最終品質を守り、仕事全体の費用を減らす',
        '<p class="lead">不要な情報取得・共有・AI呼出し・実行・検証を、ハーネスで減らす。</p>'
        '<div class="two"><div class="col"><h3>守るもの</h3><p class="body">必要な情報と処理<br>要求を満たす最終成果</p></div>'
        '<div class="col"><h3>評価する費用</h3><p class="body">全AI入力＋出力 token<br>制御・再取得・失敗を含む</p></div></div>'
        '<p class="small subtle">10月23日：主張・主要結果・あらまし　／　10月31日：レター投稿完了</p>',
        '局所比較を最終目標へつなぐ。単一作業役の結果から、多担当の削減効果は主張しない。',
        [('研究目的', 'docs/research_objective_20261022.md'), ('金曜の判断', 'docs/letter_friday_decisions_20261022.md')],
        'API件数・時間・推論器の稼働も併記する。現在の局所比較だけで独自方式や品質維持は確定していない。')

    task_ids = list(dict.fromkeys(r['task_id'] for r in p47['rows']))
    labels = ['写真整理', '電気代精算', '返金', '曲一覧の書出']
    table = []
    for task, label in zip(task_ids, labels):
        cells = []
        for r in [r for r in p47['rows'] if r['task_id'] == task]:
            value = ('成功' if r['success'] else '未達') if r['record_status'] == 'evaluated' else (
                '未評価' if r['record_status'] == 'attempted_unevaluated' else '未実行')
            cells.append('<td>' + value + '</td>')
        table.append('<tr><td>' + label + '</td>' + ''.join(cells) + '</tr>')
    add('選択表示は写真の成功を失い、採用を見送った',
        '<table><tr><th>P47・４既知課題</th><th>全表示</th><th>選択＋名前返信</th><th>選択＋契約返信</th></tr>'
        + ''.join(table) + '</table>'
        '<p class="small">９評価・１未評価・２未実行。既知834,705 token＋使用量不明１呼出し。<br>'
        'P49／P50の局所修復候補も限定的で、通常の決定的な対応付けを先に対照へ置く。</p>',
        '未評価・未実行を埋めず、返金の費用増も含めて、全12予定条件を保存した。',
        [('P47全結果', 'docs/P47_findings.md'), ('P49', 'docs/P49_findings.md'), ('P50', 'docs/P50_findings.md')],
        '同じ４課題・各１回の開発比較。選択条件には省略したAPI名／契約の拒否時返信がある。写真の選択＋契約には対象拒否がなく返信０。返金は全表示32,145、名前63,118、契約47,185 token。４課題の完全比較は成立していない。')

    stream_rows = []
    for label, row in zip(['通常応答', 'ストリーム完了', '意図した切断'], p51['rows']):
        exact = '不明' if row['input_tokens'] is None else f"{row['input_tokens']} ＋ {row['output_tokens']}"
        observed = '出力４以上／途中メッセージ不使用' if row['input_tokens'] is None else '確定した使用量を保存'
        stream_rows.append(f'<tr><td>{label}</td><td>{exact}</td><td>{observed}</td></tr>')
    add('途中の観測値と、確定した使用量を分けた',
        '<table><tr><th>P51・合成３生成</th><th>入力＋出力 token</th><th>記録の扱い</th></tr>'
        + ''.join(stream_rows) + '</table>'
        f'<p class="body">既知{p51["known_total_tokens"]:,} token＋不明１呼出し。52監査の不一致０。</p>'
        f'<p class="small">推論器の稼働 {p51["server_closure"]["wall_seconds"]:.3f}秒。'
        f'初期版の生成前失敗も別に保存（稼働{fail51["server_session"]["wall_seconds"]:.3f}秒）。</p>',
        '計測校正は終了。過去の欠測を推定で埋めず、タスク性能の結果とは区別する。',
        [('P51結果と失敗', 'docs/P51_findings.md'), ('計測補足', 'materials/20261022_letter_review/measurement_addendum.md')],
        '意図した切断は出力４ tokenを観測した時点で終了。正確な最終使用量は不明。実際の自然タイムアウトや停電耐性は測っていない。確定した２応答のメッセージは一致したが、一般的再現性の保証ではない。')

    add('使用済みの説明だけを省く２候補は、配分基準未達',
        '<p class="small intro">P52の候補をP53で実計数：４境界 × ４入力、生成０。基準は「２課題で1,000 token以上」。</p>'
        '<img class="chart" src="initial_token_reduction.svg" alt="初回入力の削減。単純対照だけが２課題で1000以上。"/>'
        '<p class="small chart-caption">全４課題の削減合計：単純対照3,976 ／ 使用後1,975 ／ 全引数名観測後982 token</p>',
        '２候補の継続生成は見送る。単純対照の基準達成も、品質・総費用・新規性の証明ではない。',
        [('P52構築', 'docs/P52_findings.md'), ('P53全16計数', 'docs/P53_findings.md')],
        f'入力一覧、未使用の契約、最新ターン等を保持する使用履歴候補。過去使用は将来不要の証明ではない。計数全体{p53["wall_seconds"]:.3f}秒、推論器稼働{p53["server_closure"]["wall_seconds"]:.3f}秒。計数後の待機も隠さず記録。86監査は入力再構築と保存計数の整合確認で、再計数ではない。')

    add('金曜は、具体的な規則と主張を一つに絞る',
        '<table><tr><th>残る判断</th><th>次にそろえる根拠</th></tr>'
        '<tr><td>減らせる不要処理</td><td>取得・呼出しそのものを省ける公開の条件</td></tr>'
        '<tr><td>必要処理の保持</td><td>適用外・有害条件と、通常方式へ戻る条件</td></tr>'
        '<tr><td>追加価値</td><td>強い単純対照との、最終品質・総費用の比較</td></tr>'
        '<tr><td>投稿物</td><td>検討用４ページは作成済み。中心主張・公式様式・著者情報は未完了</td></tr></table>'
        '<p class="small">未閲覧12シナリオは方式選びに使わない。Project #70・#71・#72と資料を同期する。</p>',
        '10月23日：主張・結果・あらまし → 25日：追加確認 → 29〜30日：原稿 → 31日：投稿',
        [('金曜の判断', 'docs/letter_friday_decisions_20261022.md'), ('検討用原稿', 'materials/20261022_letter_review/README.md')],
        '独自の中核と品質を保った総費用削減は未確立。次の案は公開契約と強い対照を確認してから有限計画にする。計測・実装件数を主張の代わりにはしない。検討用４ページは一般jsarticleであり、公式様式の４ページ確認ではない。')

    sections = []
    for i, slide in enumerate(slides, 1):
        if slide['cover']:
            sections.append(f'<section class="slide cover"><h1>{slide["title"]}</h1><div class="notes"></div></section>')
            continue
        refs = ' / '.join(f'<a href="{LINK+p}">{html.escape(label)}</a>' for label, p in slide['refs'])
        sections.append(f'<section class="slide"><div class="eyebrow">10月22日 夜の判断資料 / {i-1:02d}</div>'
                        f'<h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div>'
                        f'<div class="footer"><span class="sources">{refs}</span><span>{i}/{len(slides)}</span></div>'
                        f'<div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    extra = '.chart{display:block;width:1120px;height:302px;object-fit:contain;margin-top:4px}.intro{margin-top:12px}.chart-caption{margin-top:0;font-size:17px}table{font-size:20px}h2{font-size:36px}.small{margin-top:20px}.intro.small{margin-top:12px}.chart-caption.small{margin-top:0}'
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>10月22日 夜の判断資料</title><style>' + STYLE + extra + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    (output / 'slides.json').write_text(json.dumps(slides, ensure_ascii=False, indent=2) + '\n')
    manifest = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'pages': len(slides),
                'source_sha256': {p: sha(root / p) for p in source_paths},
                'builder_sha256': sha(Path(__file__)), 'visual_reviewed': False,
                'scope': 'Closed development observations; no novel method, quality preservation or end-to-end savings claim'}
    (output / 'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, default=ROOT / 'materials/20261022_evening')
    parser.add_argument('--pdf', action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(args.repo_root, args.output)))
    if args.pdf:
        build_budget_report.STEM = STEM
        build_budget_report.export(args.output)
