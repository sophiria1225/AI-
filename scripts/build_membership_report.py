"""Present all six P60 component conditions without claiming task savings."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_membership_evidence_20261023'
SOURCES = ('reports/P60_membership_evidence.json', 'configs/P60_membership_evidence_v01.json')
LABELS = ('観測なし', '一方の関係だけ', '両関係・終端あり', '同じ行・終端証拠なし', '状態版の変更後', '別の利用主体')


def build(output):
    result, plan = [read(ROOT / p) for p in SOURCES]
    if (result['audit_errors'] or result['plan_sha256'] != sha(ROOT / SOURCES[1])
            or [r['condition'] for r in result['rows']] != plan['scenarios']
            or result['membership_requests'] != 156):
        raise ValueError('all fixed conditions and matching source required')
    table = ''.join(f'<tr><td>{label}</td><td>{r["positive"]}</td><td>{r["negative"]}</td><td>{r["unknown"]}</td></tr>'
                    for label, r in zip(LABELS, result['rows']))
    slides = [dict(cover=True, title='取得済みの証拠で<br>どこまで所属を判断できるか'),
        dict(cover=False, title='証拠が足りなければ「含まれない」と返さない',
             body='<p class="lead">既知１課題の26依頼。同じ行でも、終端を確認できるかで返せる答えが変わる。</p>'
             '<table><tr><th>証拠の条件</th><th>肯定</th><th>否定</th><th>不明</th></tr>' + table + '</table>',
             takeaway='両関係の全件で10／16へ分離。終端なしでは16件を不明に保つ。',
             notes='６条件を事前固定し各１回。全156は補助所属要求で、独立課題数ではない。一方の関係はroommateで、この26依頼には該当がない。肯定は有効な観測だけで返せる。通常集合照合との既知回答の不一致０。'),
        dict(cover=False, title='通常の再利用部品を、実行中の判断へつなぐ',
             body='<table><tr><th>今回実装・確認した範囲</th><th>次に必要な確認</th></tr>'
             '<tr><td>肯定・否定・不明を分ける所属判定</td><td>必要な出力の範囲を実行中に得る方法</td></tr>'
             '<tr><td>主体・状態・情報源・契約の一致</td><td>接続側が状態変更を検知する条件</td></tr>'
             '<tr><td>明示的な所属要求だけを処理</td><td>通常取得・再利用を含めた比較</td></tr>'
             '<tr><td>保存観測で全６条件を確認</td><td>最終品質と仕事全体の実測費用</td></tr></table>'
             '<p class="small">追加生成・環境API・評価０。全788検査合格。元の検索は省いていない。<br>通常の集合照合を部品化した段階で、新規性と総費用削減は未確立。</p>',
             takeaway='目標は、必要な情報と最終品質を保って、不要な取得・呼出しを減らすこと。',
             notes='要求解釈・関係名・キーは分析者指定。保存版の短い先頭ページを接続側で終端とした。外部の更新をこの部品単体で検知せず、完全な検索返却を置き換えない。通常対照として実装し、追加価値は未判定。')]
    sections = []
    for i, slide in enumerate(slides, 1):
        if slide['cover']:
            sections.append(f'<section class="slide cover"><h1>{slide["title"]}</h1><div class="notes"></div></section>')
        else:
            sections.append(f'<section class="slide"><div class="eyebrow">10月23日 所属判定の通常対照 / {i-1:02d}</div>'
                f'<h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div>'
                '<div class="footer"><span class="sources"><a href="https://github.com/sophiria1225/AI-/blob/main/docs/P60_findings.md">全結果・解釈</a> / '
                '<a href="https://github.com/sophiria1225/AI-/blob/main/reports/P60_membership_evidence.json">全６条件</a></span>'
                f'<span>{i}/3</span></div><div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css = 'h2{font-size:34px}table{font-size:19px}.lead{font-size:22px}.small{margin-top:16px}td{padding:10px 15px}.takeaway{font-size:21px}'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P60 所属判定の通常対照</title><style>'
        + STYLE + css + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    (output / 'slides.json').write_text(json.dumps(slides, ensure_ascii=False, indent=2) + '\n')
    manifest = {'pages': 3, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': {p: sha(ROOT / p) for p in SOURCES}, 'builder_sha256': sha(Path(__file__)),
        'visual_reviewed': False, 'scope': 'Ordinary three-valued membership baseline; no live task, savings or novelty claim.'}
    (output / 'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, default=ROOT / 'materials/20261023_p60')
    p.add_argument('--pdf', action='store_true'); args = p.parse_args()
    print(json.dumps(build(args.output)))
    if args.pdf:
        build_budget_report.STEM = STEM; build_budget_report.export(args.output)
