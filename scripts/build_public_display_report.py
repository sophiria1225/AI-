"""Render every P71 cell and its fixed decision; never select successful runs."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path

import build_budget_report
from build_inventory_report import ARMS, TASKS, LABELS, cost, outcome, plot
from build_morning_report import STYLE, SCRIPT
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_public_display_20261023'
LINK = 'https://github.com/sophiria1225/AI-/blob/main/'


def build(root, output):
    sources = ('reports/P71_comparison.json', 'reports/P71_prefix_checks.json',
               'reports/P71_server_session.json', 'reports/P55_comparison.json')
    report, pre, server, historical = [read(root / name) for name in sources]
    if (report['phase'] != 'P71' or report['catalog_policy'] != 'public_names'
            or report['audit_errors'] or not report['all_planned_cells_accounted']
            or len(report['rows']) != 12 or pre['status'] != 'complete'
            or server['status'] != 'stopped' or not server['owned_processes_absent']):
        raise ValueError('closed, audited P71 cohort and owned server required')
    if {(r['task_id'], r['arm']) for r in report['rows']} != {(t, a) for t, _ in TASKS for a in ARMS}:
        raise ValueError('every fixed task and display condition must be retained')
    output.mkdir(parents=True, exist_ok=True)
    plot(report, output)
    slides = [dict(title='公開API名を使える条件で<br>説明省略の総費用を検証', cover=True)]

    def add(title, body, takeaway, refs, notes):
        slides.append(dict(title=title, body=body, takeaway=takeaway, refs=refs, notes=notes, cover=False))

    add('呼出し制約をそろえて、表示の比較を繰り返す',
        '<p class="lead">必要な情報・処理と最終品質を保ち、仕事全体の費用を減らす。</p>'
        '<table><tr><th>表示</th><th>保持するもの</th><th>公開APIの呼出し</th></tr>'
        '<tr><td>F 全表示</td><td>詳細・一覧</td><td rowspan="3">全条件で同じ<br>登録公開名を説明閲覧前から使える</td></tr>'
        '<tr><td>D 詳細を省略</td><td>一覧</td></tr>'
        '<tr><td>B 詳細＋一覧を省略</td><td>操作・新しい出力・不確かな出力</td></tr></table>'
        '<p class="small">P55と同じ４既知課題・８応答後。Python状態・アーカイブ・公開契約返信・予算は共通。</p>',
        '説明閲覧を必須にしない通常接続で、表示省略の適用範囲を確かめる。',
        [('固定条件', 'docs/experiments/P71_public_display.md')],
        '能力説明とrun_pythonの案内も全条件で共通修正。元の履歴・行動・応答は維持。'
        '各16生成・120,000継続token・480秒、FDB/DBF/BFD/FBDの順に１回ずつ。新手法の主張ではない。')

    rows = []
    for tid, label in TASKS:
        cells = [next(r for r in report['rows'] if r['task_id'] == tid and r['arm'] == arm) for arm in ARMS]
        rows.append('<tr><td>' + label + '</td>' + ''.join(
            f'<td>{outcome(r)}<br><span class="metric">{cost(r)}</span></td>' for r in cells) + '</tr>')
    counts = report['record_status_counts']
    add('全12条件の成否と、仕事全体の費用',
        '<table class="results"><tr><th>課題</th><th>F 全表示</th><th>D 詳細を省略</th><th>B 詳細＋一覧を省略</th></tr>'
        + ''.join(rows) + '</table><p class="small">数値は共通前半＋全継続の入力出力token。'
        f'評価{counts.get("evaluated", 0)}、未評価{counts.get("attempted_unevaluated", 0)}、'
        f'未実行{counts.get("not_run_after_stop", 0)}。</p>',
        '不明使用量・未評価・未実行を補完せず、未達で早く止まった条件も残す。',
        [('全件監査', 'reports/P71_comparison.json')],
        'キャッシュ入力も論理費用へ含む。使用量不明は追加費用として明記し、その生成を再試行しない。'
        '効果・片付け・idleが確認できる場合に限り最終状態を評価して次の固定条件へ進む。')

    add('初回入力の短縮と、最後までの費用は別に測る',
        '<img class="chart" src="work_tokens.svg" alt="全４課題３条件の総費用と成否"/>'
        '<p class="small">Dの初回短縮：' + ' ／ '.join(
            f'{n:,}' for n in pre['detail_control_allocation_gate']['removed_tokens']) + ' token。</p>',
        '棒は前半＋継続の既知費用。不明がある棒には斜線を付ける。',
        [('入力計数', 'reports/P71_prefix_checks.json'), ('総費用', 'reports/P71_comparison.json')],
        '縦軸は０始まり。省略処理・通知・計数・契約返信の費用も継続に含める。'
        '返金D/Bは基礎入力が同じで、残時間通知と数値の揺らぎは残る。そこでの行動差を一覧の効果としない。')

    totals = [report['totals'][a] for a in ARMS]
    metrics = []
    for label, key in [('成功数', 'successes'), ('継続AI呼出し', 'model_calls'),
                       ('継続API', 'api_requests'), ('復元API', 'setup_api_requests'),
                       ('使用量不明の呼出し', 'unknown_usage_calls')]:
        metrics.append('<tr><td>' + label + '</td>' + ''.join(f'<td>{t[key]:,}</td>' for t in totals) + '</tr>')
    unseen = [sum(sum(r.get('access_audit', {}).get('sent_before_documentation_exposure', {}).values())
                  for r in report['rows'] if r['arm'] == arm) for arm in ARMS]
    metrics.append('<tr><td>説明公開前のAPI送信</td>' + ''.join(f'<td>{n}</td>' for n in unseen) + '</tr>')
    add('呼出し・復元・推論器の費用を残す',
        '<table class="metrics"><tr><th>４課題合計</th><th>F</th><th>D</th><th>B</th></tr>'
        + ''.join(metrics) + '</table><p class="small">推論器ロード'
        f'{server["load_wall_seconds"]:.1f}秒、常駐{server["wall_seconds"]:,.1f}秒。終了とプロセス消滅を確認。</p>',
        '説明なしの公開名呼出しも、通常のAPI送信として予算と監査の対象にする。',
        [('全件監査', 'reports/P71_comparison.json'), ('推論器費用', 'reports/P71_server_session.json')],
        '未登録API、不正引数、完了後、作用不明後の送信を監査。公開スキーマが増える契機も記録から照合する。'
        '復元は実験の費用として別記。評価単独の時間は分離計測していないので０としない。')

    decision = '達成' if report['development_gate_met'] else '未達'
    advantage = '支持条件を満たす' if report['inventory_advantage_supported'] else '支持条件を満たさない'
    add('この既知群から主張できる範囲',
        f'<p class="lead">固定した採用基準：{decision}<br>一覧保持の追加価値：{advantage}</p>'
        '<table><tr><th>比較の範囲</th><th>原稿での扱い</th></tr>'
        '<tr><td>P71内のF/D/B</td><td>同じ公開名接続・能力説明での比較</td></tr>'
        '<tr><td>旧P55との違い</td><td>時点・案内文も違う。接続制約だけの因果効果としない</td></tr>'
        '<tr><td>既知４課題を各１回</td><td>一般品質維持・統計的非劣性・新手法の証明ではない</td></tr></table>',
        '元P55も全結果を保持し、都合のよい条件だけを原稿へ残さない。',
        [('P71固定条件', 'docs/experiments/P71_public_display.md'), ('元のP55', 'docs/P55_findings.md')],
        '採用条件は全12評価・全使用量既知・監査不一致０、DがF/Bの対の成功を失わず、総費用がFより少なくB以下。'
        '一覧の利点には、実際に一覧入力が違う課題でD成功/B失敗も必要。未閲覧12シナリオを使っていない。')

    sections = []
    for number, slide in enumerate(slides, 1):
        if slide['cover']:
            sections.append(f'<section class="slide cover"><h1>{slide["title"]}</h1><div class="notes"></div></section>')
            continue
        refs = ' / '.join(f'<a href="{LINK + path}">{html.escape(label)}</a>' for label, path in slide['refs'])
        sections.append(f'<section class="slide"><div class="eyebrow">10月23日 公開名接続と説明表示 / {number-1:02d}</div>'
            f'<h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div>'
            f'<div class="footer"><span class="sources">{refs}</span><span>{number}/{len(slides)}</span></div>'
            f'<div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    extra = '.chart{display:block;width:1120px;height:325px;object-fit:contain}table{font-size:20px}h2{font-size:35px}.small{margin-top:14px}.results td{padding:6px 16px}.metrics td{padding:6px 16px}.metric{font-size:19px;font-variant-numeric:tabular-nums}'
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P71 公開名接続での表示比較</title><style>'
        + STYLE + extra + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    write = lambda path, value: path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    write(output / 'slides.json', slides)
    manifest = {'generated_at': datetime.now(timezone.utc).isoformat(), 'pages': len(slides),
        'source_sha256': {p: sha(root / p) for p in sources}, 'builder_sha256': sha(Path(__file__)),
        'shared_rendering_sha256': {name: sha(root / 'scripts' / name) for name in (
            'build_inventory_report.py', 'build_morning_report.py', 'build_budget_report.py')},
        'visual_reviewed': False, 'scope': 'All four known tasks and all three displays under public-name admission.'}
    write(output / 'build_manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'materials/20261023_p71')
    parser.add_argument('--pdf', action='store_true'); args = parser.parse_args()
    print(json.dumps(build(ROOT, args.output)))
    if args.pdf:
        build_budget_report.STEM = STEM; build_budget_report.export(args.output)
