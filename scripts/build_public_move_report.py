"""Render the bounded P62 receipt-support inspection without task relabelling."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_public_completion_scope_20261023'
SOURCE = 'reports/P62_public_move_scope.json'


def build(output):
    report = read(ROOT / SOURCE)
    if (len(report['rows']) != 3 or report['source_audit_sha256'] != sha(ROOT / 'reports/P55_comparison.json')
            or report['checker_sha256'] != sha(ROOT / 'scripts/public_move_evidence.py')
            or report['inspector_sha256'] != sha(ROOT / 'scripts/inspect_public_move_scope.py')):
        raise ValueError('closed three-condition report and matching code required')
    table = []
    for label, row in zip(('F 全表示', 'D 詳細省略', 'B 詳細＋一覧省略'), report['rows'], strict=True):
        final = row['final']
        outcome = '成功' if row['original_official_success'] else '未達'
        table.append(f'<tr><td>{label}</td><td>{final["metadata_files"]}</td><td>{final["unique_moved_sources"]}</td>'
            f'<td>{row["public_clock_requests_sent"]}</td><td>{outcome}</td></tr>')
    slides = [dict(cover=True, title='移動が済んだことと<br>終了条件の根拠を分ける'),
        dict(cover=False, title='対象と名前はそろっても、日時の根拠は別に必要',
             body='<p class="lead">既知の写真整理３条件。依頼は「今年の２月・３月」と、その他の写真を分ける。</p>'
             '<table><tr><th>条件</th><th>元の日時取得</th><th>元集合の移動</th><th>時刻API送信</th><th>元の成否</th></tr>'
             + ''.join(table) + '</table><p class="small">F/Dは42件全て名前を保持。時刻APIの要求は公開集合への未登録で拒否。<br>'
             '現在年を仮に2023とすると移動先は一致するが、その年を観測した証拠にはならない。</p>',
             takeaway='公式成否は維持する。公開記録の支持範囲と、実際の成否を付け替えない。',
             notes='全生成境界を順番に点検。Fは第７、Dは第４の継続生成で元集合42件の移動がそろった。Bは移動０。時計の未送信拒否は１／１／２件。原典と公開APIの意味に基づく分析者指定の検査であり、自律的な要求解釈ではない。'),
        dict(cover=False, title='安全に省ける後続処理は、まだ確定していない',
             body='<table><tr><th>照合したこと</th><th>この結果では未確定のこと</th></tr>'
             '<tr><td>完全な元集合と、移動前の日時</td><td>公開観測のない現在年</td></tr>'
             '<tr><td>成功した移動先と元のファイル名</td><td>任意の依頼を正しく検査へ変換する方法</td></tr>'
             '<tr><td>欠落・重複・上書き・返却不一致</td><td>通常の事前確認を超える追加価値</td></tr></table>'
             '<p class="small">移動APIは既定で日時を変えるため、元の条件に使う日時は移動前に保持。<br>'
             '読取0.028秒。追加生成・環境API・評価・DB読取・保留群閲覧０。</p>',
             takeaway='必要な情報と最終品質を守って、仕事全体の費用を減らす目標を維持する。',
             notes='通常の条件付き証拠検査で、新手法・節約額・自動完了器の成立ではない。元の時刻を新たに取得したり、完了APIを追加したりしていない。検査器をオンライン制御へ接続する新実験は配分しない。')]
    sections = []
    for number, slide in enumerate(slides, 1):
        if slide['cover']:
            sections.append(f'<section class="slide cover"><h1>{slide["title"]}</h1><div class="notes"></div></section>')
            continue
        sections.append(f'<section class="slide"><div class="eyebrow">10月23日 公開の終了根拠 / {number-1:02d}</div>'
            f'<h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div>'
            '<div class="footer"><span class="sources"><a href="https://github.com/sophiria1225/AI-/blob/main/docs/P62_findings.md">全結果・限界</a> / '
            '<a href="https://github.com/sophiria1225/AI-/blob/main/reports/P62_public_move_scope.json">全境界の記録</a></span>'
            f'<span>{number}/3</span></div><div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css = 'h2{font-size:34px}table{font-size:20px}.lead{font-size:22px}.small{margin-top:22px;font-size:20px}td{padding:18px 16px}.takeaway{font-size:21px}'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P62 公開の終了根拠</title><style>'
        + STYLE + css + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    (output / 'slides.json').write_text(json.dumps(slides, ensure_ascii=False, indent=2) + '\n')
    manifest = {'pages': 3, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': {SOURCE: sha(ROOT / SOURCE)}, 'builder_sha256': sha(Path(__file__)),
        'visual_reviewed': False, 'scope': 'Three known conditions; declared receipt support, not task relabelling or autonomous completion.'}
    (output / 'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'materials/20261023_p62')
    parser.add_argument('--pdf', action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(args.output)))
    if args.pdf:
        build_budget_report.STEM = STEM
        build_budget_report.export(args.output)
