"""Present the four audited P56 interventions without relabelling P55."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_completion_scope_20261023'
SOURCES = ('reports/P56_completion_scope.json', 'reports/P56_completion_audit.json',
           'reports/P55_comparison.json', 'reports/P55_outcome_scope.json')


def build(output):
    report, audit, _, _ = [read(ROOT / name) for name in SOURCES]
    if (report['status'] != 'complete' or audit['audit_errors'] or not audit['all_four_evaluated']
            or audit['source_report_sha256'] != sha(ROOT / SOURCES[0]) or len(audit['rows']) != 4):
        raise ValueError('complete audited four-case evidence required')
    expected = [('P55_01_FULL_KEEP', 'no_completion', False),
                ('P55_01_FULL_KEEP', 'append_completion', True),
                ('P55_01_DETAILS_AND_LISTINGS_OMITTED_KEEP', 'no_completion', False),
                ('P55_01_DETAILS_AND_LISTINGS_OMITTED_KEEP', 'append_completion', False)]
    observed = [(r['source_run'], r['arm'], r['official_success']) for r in audit['rows']]
    if (observed != expected or not audit['rows'][1]['final_world_equals_original_D']
            or any(r['database_files'] != 13 or not r['non_supervisor_files_unchanged']
                   for r in audit['rows'])):
        raise ValueError('observations changed; review the narrative before generating it')
    output.mkdir(parents=True, exist_ok=True)
    table, texrows = [], []
    for row in audit['rows']:
        source = 'F 全表示' if row['source_run'] == 'P55_01_FULL_KEEP' else 'B 詳細＋一覧省略'
        arm = 'なし' if row['arm'] == 'no_completion' else '空引数で１回追加'
        success = '成功' if row['official_success'] else '未達'
        table.append(f'<tr><td>{source}</td><td>{arm}</td><td>{success}</td><td>全返却・13 DB一致</td></tr>')
        texrows.append(('F' if source.startswith('F') else 'B') + ' & ' +
                       ('なし' if row['arm'] == 'no_completion' else '１回追加') + ' & ' + success + r'\\')
    replay = sum(r['replay_api_requests'] for r in audit['rows'])
    intervention = sum(r['intervention_api_requests'] for r in audit['rows'])
    evaluation = sum(r['evaluation_wall_seconds'] for r in audit['rows'])
    slides = [dict(title='作業状態と完了通知を分ける<br>保存状態を使った４条件の確認', cover=True),
        dict(title='作業状態を固定し、最後の通知だけを変える', cover=False,
             body='<p class="lead">P55写真の全表示と詳細省略は、非supervisorの保存状態が同じだった。</p>'
             '<table><tr><th>再現する元状態</th><th>追加する完了API</th><th>独立評価</th><th>介入前の照合</th></tr>'
             + ''.join(table) + '</table><p class="small">別の模擬環境で公開APIを再現。介入で変わったアプリはsupervisorだけ。</p>',
             takeaway='Fは完了通知１回で未達→成功。Bは通知を加えても未達。',
             notes='全４条件を事前固定。FとBのなし対照は元の未達を再現した。Fへ通知を加えた後は13保存ファイルが元Dと一致。隠れたテストは読まず、原状態のP55結果も変えていない。'),
        dict(title='局所的な原因確認を、過大な有効性へ広げない', cover=False,
             body='<table><tr><th>今回確認できたこと</th><th>解釈の範囲</th></tr>'
             '<tr><td>Fの成否は通知だけで変わった</td><td>写真整理そのものの改善とは区別する</td></tr>'
             '<tr><td>Bは通知を加えても未達</td><td>完了宣言だけで要求達成にはならない</td></tr>'
             '<tr><td>既知１課題・４つの再現</td><td>新しい自律エージェントの成功率に足さない</td></tr>'
             '<tr><td>P55の元結果・費用を維持</td><td>未知tokenの補完や費用不採用の撤回はしない</td></tr></table>'
             f'<p class="small">再現{replay}＋介入{intervention}＝{report["total_api_requests"]} API、独立評価４回。'
             f'全体{report["wall_seconds"]:.3f}秒（評価{evaluation:.3f}秒を含む）、モデル生成０。</p>',
             takeaway='最終品質と仕事全体の費用を守るため、終了手続きと実作業を分けて評価する。',
             notes='自動で完了を宣言してよい条件を学習・検証したわけではない。通常の完了APIを新方式と呼ばない。未閲覧12シナリオは保持。次の主張と主要実験を10月23日に絞り、10月31日の投稿を目指す。')]
    sections = []
    for index, slide in enumerate(slides, 1):
        if slide['cover']:
            sections.append(f'<section class="slide cover"><h1>{slide["title"]}</h1><div class="notes"></div></section>')
        else:
            sections.append(f'<section class="slide"><div class="eyebrow">10月23日 完了通知の局所確認 / {index-1:02d}</div>'
                f'<h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div>'
                f'<div class="footer"><span class="sources"><a href="https://github.com/sophiria1225/AI-/blob/main/docs/P56_findings.md">全結果と解釈</a> / '
                '<a href="https://github.com/sophiria1225/AI-/blob/main/reports/P56_completion_audit.json">全件監査</a></span>'
                f'<span>{index}/{len(slides)}</span></div><div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css = 'h2{font-size:36px}table{font-size:20px}.lead{font-size:23px}.small{margin-top:17px}td{padding:13px 15px}'
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P56 作業状態と完了通知</title><style>'
        + STYLE + css + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    (output / 'slides.json').write_text(json.dumps(slides, ensure_ascii=False, indent=2) + '\n')
    manifest = {'pages': len(slides), 'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': {name: sha(ROOT / name) for name in SOURCES}, 'builder_sha256': sha(Path(__file__)),
        'visual_reviewed': False, 'scope': 'Post-hoc terminal intervention; original agent outcomes remain unchanged.'}
    (output / 'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    component = (r'\par\smallskip\noindent\textbf{完了通知だけを変えた追加診断．}' + '\n'
        '上の保存状態照合後，F/Bの２状態を新しい模擬環境で再現し，完了APIのなし／１回追加を固定４条件で比較した．'
        '送信済みの公開APIの返却と介入前13保存ファイルを全て照合し，既存Dと同じ空引数の通知だけを加えた．'
        '表4のとおりFは未達から成功へ変わり，その最終保存ファイルは元Dと全て一致した．Bは通知後も未達だった．'
        '非supervisorの保存ファイルは全条件で介入前後不変だった．\n'
        r'\begin{center}\small 表4\quad 別環境の再現における終了手続きの介入\par\smallskip' + '\n'
        r'\begin{tabular}{lll}\hline 元状態 & 完了API追加 & 公式成否\\\hline' + '\n'
        + '\n'.join(texrows) + '\n' + r'\hline\end{tabular}\end{center}' + '\n'
        f'再現{replay}と介入{intervention}の計{report["total_api_requests"]} API，独立評価４回，生成０で，'
        f'全体{report["wall_seconds"]:.3f}秒（評価{evaluation:.3f}秒を含む）だった．'
        'これは既知１課題の事後診断であり，元のP55成否・未知費用は変更しない．'
        '自動で完了を宣言してよい条件や，新たな自律エージェントの成功率は検証していない．\n')
    (ROOT / 'papers/202610_letter/completion_diagnostic.tex').write_text(component)
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, default=ROOT / 'materials/20261023_p56')
    p.add_argument('--pdf', action='store_true'); args = p.parse_args()
    print(json.dumps(build(args.output)))
    if args.pdf:
        build_budget_report.STEM = STEM; build_budget_report.export(args.output)
