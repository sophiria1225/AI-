"""Present both P61 ordinary conditions and the common prefix cost."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_ordinary_continuation_20261023'
SOURCES = ('reports/P61_ordinary_continuation.json', 'reports/P61_ordinary_audit.json',
           'configs/P61_ordinary_continuation_v01.json')


def build(output):
    report, audit, plan = [read(ROOT / p) for p in SOURCES]
    if (audit['audit_errors'] or audit['source_report_sha256'] != sha(ROOT / SOURCES[0])
            or audit['plan_sha256'] != sha(ROOT / SOURCES[2]) or not audit['all_planned_rows_present']):
        raise ValueError('closed matching audit with all conditions required')
    table = []; notes = []
    for row in audit['rows']:
        label = '通常ツール' if row['arm'] == 'native' else '持続Python'
        if row['status'] == 'not_run':
            table.append(f'<tr><td>{label}</td><td>未実行</td><td>—</td><td>—</td><td>—</td><td>—</td></tr>')
            continue
        success = {True: '成功', False: '未達', None: '未評価'}[row['official_success']]
        tokens = f'{row["whole_task_known_tokens"]:,}'
        if row['unknown_usage_calls']: tokens += f'＋不明{row["unknown_usage_calls"]}'
        table.append(f'<tr><td>{label}</td><td>{success}</td><td>{row["model_calls"]}</td>'
            f'<td>{row["additional_contact_searches"]}</td><td>{row["continuation_api_requests"]}</td><td>{tokens}</td></tr>')
        notes.append(f'{label}の継続既知tokenは{row["known_continuation_tokens"]:,}、不明{row["unknown_usage_calls"]}。')
    python = audit['rows'][1]
    both_sufficient = all(r.get('official_success') is True and r.get('additional_contact_searches') == 0 for r in audit['rows'])
    ordinary_sufficient = python.get('official_success') is True and python.get('additional_contact_searches') == 0
    decision = ('両方式とも成功・追加検索０。所属キャッシュを加える根拠は弱い。' if both_sufficient else
                '持続Pythonで成功し、追加の連絡先検索は０。通常対照だけで処理できた。'
                if ordinary_sufficient else '通常対照でも成功・取得抑制がそろったとは限らず、失敗と費用を分けて点検する。')
    slides = [dict(cover=True, title='通常の計算能力で<br>取得と呼出しはどこまで減るか'),
        dict(cover=False, title='同じ取得済み情報から、２つの通常方式を再開',
             body='<p class="lead">既知の支払課題・第12応答後。前半は252,602 token・20 APIで共通。</p>'
             '<table><tr><th>両方で共通</th><th>変える能力</th></tr>'
             '<tr><td>元のタスク、全履歴、全公開APIの記録</td><td>通常ツール：元の関数呼出しで継続</td></tr>'
             '<tr><td>同じ公開スキーマ・同じ模擬世界の状態</td><td>持続Python：変数保持、集合演算、APIの一括処理</td></tr>'
             '<tr><td>８生成・197,398 token・900秒・残り60 API</td><td>具体的な照合式・対象・P60部品は渡さない</td></tr>'
             '<tr><td>初回cold、元モデルと温度、seed 54から</td><td>ツール定義の提示方法も変わる通常方式の比較</td></tr></table>',
             takeaway='同じ既知状態から各１回。新手法やキャッシュ単独の効果を測る比較ではない。',
             notes='P59で費用最大の既知課題を事後選定し、６検索前の境界を使った。各再開前に20返却、13保存DB、公開スキーマ集合を照合。過去のPython変数はなく、履歴のspanから通常の計算を行う。'),
        dict(cover=False, title='全２条件を、前半を含む仕事全体の費用で見る',
             body='<table><tr><th>条件</th><th>成否</th><th>継続生成</th><th>追加検索</th><th>継続API</th><th>前半込token</th></tr>'
             + ''.join(table) + '</table><p class="small">追加検索はphone.search_contacts。継続APIには書込み・完了通知も含む。<br>'
             + html.escape(' '.join(notes)) + '<br>前半252,602 tokenは両条件に計上。cache入力も論理tokenに含める。</p>',
             takeaway=decision,
             notes='１既知課題の２条件で、独立２課題や非劣性評価ではない。元P24の結果は保存し、再生成した通常対照を新しく測る。失敗、欠測、未実行はそのまま記録。'),
        dict(cover=False, title='追加する制御の価値を、通常対照の後で判断する',
             body='<table><tr><th>今回分かる範囲</th><th>研究としてまだ必要なこと</th></tr>'
             '<tr><td>同じ情報を通常の計算で使えるか</td><td>通常方式でも残る具体的な不要処理</td></tr>'
             '<tr><td>１課題での成否・取得数・総費用</td><td>必要な品質を保つ制御規則と追加価値</td></tr>'
             '<tr><td>全条件と不明を残す局所比較</td><td>未調整課題での評価と限界の明示</td></tr></table>'
             f'<p class="small">新しい生成{audit["model_calls"]}回、既知{audit["known_continuation_tokens"]:,} token＋不明{audit["unknown_usage_calls"]}。'
             f'<br>継続{audit["continuation_api_requests"]}＋復元{audit["replay_api_requests"]} API、評価{audit["evaluator_calls"]}回。'
             f'監査不一致０、推論器停止。保留群閲覧０。</p>',
             takeaway='必要な情報と最終品質を守り、制御・再取得・失敗を含む総費用を減らす。',
             notes='通常のインターフェース一式の比較で、コード化、ツール定義、提示、バッチ化を個別分離していない。中心的な新規性と投稿に足る一般的有効性は未確定。')]
    sections = []
    for i, slide in enumerate(slides, 1):
        if slide['cover']:
            sections.append(f'<section class="slide cover"><h1>{slide["title"]}</h1><div class="notes"></div></section>')
        else:
            sections.append(f'<section class="slide"><div class="eyebrow">10月23日 通常の実行能力 / {i-1:02d}</div>'
                f'<h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div>'
                '<div class="footer"><span class="sources"><a href="https://github.com/sophiria1225/AI-/blob/main/docs/P61_findings.md">全結果・解釈</a> / '
                '<a href="https://github.com/sophiria1225/AI-/blob/main/reports/P61_ordinary_audit.json">監査</a></span>'
                f'<span>{i}/4</span></div><div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css = 'h2{font-size:34px}table{font-size:18px}.lead{font-size:22px}.small{margin-top:18px;font-size:19px}td{padding:13px 14px}.takeaway{font-size:21px}'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P61 通常の実行能力</title><style>'
        + STYLE + css + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    (output / 'slides.json').write_text(json.dumps(slides, ensure_ascii=False, indent=2) + '\n')
    manifest = {'pages': 4, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': {p: sha(ROOT / p) for p in SOURCES}, 'builder_sha256': sha(Path(__file__)),
        'visual_reviewed': False, 'scope': 'Two ordinary interfaces at one known boundary; no new-method or generalization claim.'}
    (output / 'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, default=ROOT / 'materials/20261023_p61')
    p.add_argument('--pdf', action='store_true'); a = p.parse_args(); print(json.dumps(build(a.output)))
    if a.pdf:
        build_budget_report.STEM = STEM; build_budget_report.export(a.output)
