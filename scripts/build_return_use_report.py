"""Source-linked P70 slides, keeping all twelve syntax-only records."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_return_use_scope_20261023'
SOURCES = ('reports/P70_return_use_scope.json', 'configs/P70_return_use_scope_v01.json')


def build(output):
    report, plan = [read(ROOT / p) for p in SOURCES]
    if (report['plan_sha256'] != sha(ROOT / SOURCES[1])
            or report['checker_sha256'] != sha(ROOT / 'scripts/return_use_scope.py')
            or report['inspector_sha256'] != sha(ROOT / 'scripts/inspect_return_use_scope.py')
            or report['helper_contract_sha256'] != sha(ROOT / 'scripts/field_read_contract.py')
            or [r['run_id'] for r in report['rows']] != [r['run_id'] for r in plan['rows']]
            or report['program_occurrences'] != 181 or report['unique_input_files'] != 117):
        raise ValueError('unchanged all-twelve sources required')
    for key in ('model_generations', 'environment_api_requests', 'evaluator_calls',
                'task_databases_read', 'reserved_scenarios_read', 'saved_code_executions'):
        if report[key] != 0: raise ValueError('read-only result required')
    slides = [{'cover': True, 'title': 'API返却を後で使う可能性と<br>直接項目読取の適用範囲'}]
    tasks = ['写真', '共有・請求', '返金', 'CSV']
    arms = {'full_keep': '全履歴', 'stdout_mask_keep': '出力省略', 'stdout_mask_index_keep': '一覧追加'}
    for offset in (0, 6):
        rows = []
        for index, r in enumerate(report['rows'][offset:offset+6], offset):
            c = r['agent_use_counts']
            rows.append(f'<tr><td>{tasks[index//3]}</td><td>{arms[r["arm"]]}</td><td>{r["program_occurrences"]}</td>'
                f'<td>{c.get("name_binding",0)}</td><td>{c.get("whole_value_argument",0)}</td>'
                f'<td>{r["direct_field_helper_syntax_candidates"]}</td></tr>')
        slides.append({'title': f'全12条件の構文点検（{1 if offset == 0 else 2}/2）',
            'body': '<p class="lead">コード上の箇所数。ループの実API回数やtoken数とは異なる。</p>'
                '<table><tr><th>課題</th><th>元の条件</th><th>プログラム</th><th>根を名前へ</th><th>根を全体の引数へ</th><th>直接項目候補</th></tr>'
                + ''.join(rows) + '</table>',
            'take': '名前への保存・全体引渡しから、必要なのは一部の項目だけだとは推定しない。',
            'notes': '前半８プログラムは各課題３条件で重複。全体引数の分類は実際に全フィールドを参照したという意味ではない。全12条件を残し、構文解析不能０。'})
    slides.extend([
        {'title': '今の生成内で読まなくても、次の生成から使える',
         'body': '<table><tr><th>一般例（保存コードの引用ではない）</th><th>意味</th></tr>'
            '<tr><td>song = call_api(...)<br>title = song["title"]</td><td>返却の根が名前空間へ残る。</td></tr>'
            '<tr><td>次の生成：song["rating"]</td><td>別項目の利用が後から追加され得る。</td></tr>'
            '<tr><td>title = call_api(...)["title"]</td><td>根を直接項目へ絞る候補。この記録群では０。</td></tr></table>'
            '<p class="small">181出現＝前半96＋後続81＋制御４。固有入力117、既知４課題。</p>',
         'take': '将来のコードを先読みして、過去の要求で不要だったことにはしない。',
         'notes': '直接項目候補があっても、APIの純粋性・鮮度・例外・応答契約・品質を証明するわけではない。現在のAPI呼出しを抑制したり原コードを実行したりしていない。'},
        {'title': '自動射影の拡張を見送り、中心結果の適用範囲を確かめる',
         'body': '<table><tr><th>得たこと</th><th>今回の判断</th></tr>'
            '<tr><td>既存の項目読取</td><td>P37/P38を維持。新機能として作り直さない。</td></tr>'
            '<tr><td>今回の自動変換候補</td><td>全12条件で０。ランタイムへ接続しない。</td></tr>'
            '<tr><td>既存研究との関係</td><td>需要追跡・射影・再利用自体を新規性にしない。</td></tr>'
            '<tr><td>次の確認</td><td>追加の接続制約を外しても、表示比較の傾向が残るか。</td></tr></table>'
            f'<p class="small">読取 {report["wall_seconds"]:.6f} 秒。追加生成・API・評価・記録コード実行０。</p>',
         'take': '新規性を無理に付けず、原稿を支える比較と適用条件を具体化する。',
         'notes': '原稿のP55には説明取得前の公開API名を拒否する制約がある。通常の公開名接続を全表示条件へそろえた比較を別に固定する段階。新しい比較はまだ実行していない。'}])
    sections = []
    for n, s in enumerate(slides, 1):
        if s.get('cover'):
            sections.append(f'<section class="slide cover"><h1>{s["title"]}</h1><div class="notes"></div></section>');continue
        sections.append(f'<section class="slide"><div class="eyebrow">10月23日 返却の利用範囲 / {n-1:02d}</div><h2>{s["title"]}</h2>{s["body"]}'
            f'<div class="takeaway">{s["take"]}</div><div class="footer"><span class="sources">'
            '<a href="https://github.com/sophiria1225/AI-/blob/main/docs/P70_findings.md">全結果・限界</a> / '
            '<a href="https://github.com/sophiria1225/AI-/blob/main/docs/field_demand_review_20261023.md">既存実装と原典</a></span>'
            f'<span>{n}/{len(slides)}</span></div><div class="notes">{html.escape(s["notes"])}</div></section>')
    nav='<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css='h2{font-size:30px}table{font-size:18px}.lead{font-size:21px}.small{margin-top:14px;font-size:18px}td{padding:9px 12px}.takeaway{font-size:20px}'
    output.mkdir(parents=True,exist_ok=True)
    (output/'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>返却の利用範囲</title><style>'+STYLE+css+'</style></head><body>'+''.join(sections)+nav+'<script>'+SCRIPT+'</script></body></html>')
    (output/'slides.json').write_text(json.dumps(slides,ensure_ascii=False,indent=2)+'\n')
    m={'pages':len(slides),'generated_at':datetime.now(timezone.utc).isoformat(),
       'source_sha256':{p:sha(ROOT/p) for p in SOURCES},'builder_sha256':sha(Path(__file__)),
       'visual_reviewed':False,'scope':'All twelve P33 cells, syntax inventory only; no code replay or measured savings.'}
    (output/'build_manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
    return m


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'materials/20261023_p70');p.add_argument('--pdf',action='store_true');a=p.parse_args()
    print(json.dumps(build(a.output)))
    if a.pdf:build_budget_report.STEM=STEM;build_budget_report.export(a.output)
