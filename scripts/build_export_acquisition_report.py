"""Render every fixed P69 record; opportunities are never measured savings."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_export_acquisition_scope_20261023'
SOURCES = ('reports/P69_export_acquisition_scope.json', 'configs/P69_export_acquisition_scope_v01.json')


def build(output):
    report, plan = [read(ROOT / p) for p in SOURCES]
    if (report['plan_sha256'] != sha(ROOT / SOURCES[1])
            or report['checker_sha256'] != sha(ROOT / 'scripts/export_acquisition_scope.py')
            or report['inspector_sha256'] != sha(ROOT / 'scripts/inspect_export_acquisition_scope.py')
            or [r['run_id'] for r in report['rows']] != plan['run_ids']
            or any(report[k] != 0 for k in ('model_generations', 'environment_api_requests', 'evaluator_calls',
                                          'task_databases_read', 'reserved_scenarios_read'))):
        raise ValueError('all five fixed records and unchanged read-only sources required')
    labels = ['P18 通常', 'P25 一般案内', 'P29 持続Python', 'P68 通常', 'P68 終了制御']
    rows = []
    for label, r in zip(labels, report['rows']):
        rows.append(f'<tr><td>{label}</td><td>{"成功" if r["original_official_success"] else "未達"}</td>'
            f'<td>{r["show_song_requests"]}</td><td>{r["task_fields_preknown_requests"]}</td>'
            f'<td>{r["same_request_response_preknown_requests"]}</td><td>{r["posthoc_prior_complete_object_equal"]}</td></tr>')
    covered = sum(sum(c['all_sent_requests_are_show_song_with_preknown_task_fields'] for c in r['model_boundaries']) for r in report['rows'])
    slides = [
        {'cover': True, 'title': 'CSVに必要な情報と<br>API応答全体の再利用範囲'},
        {'title': '全５記録：必要列が既知でも完全な応答とは違う',
         'body': '<p class="lead">同じ既知CSV課題の事後点検。元の成否を残し、成功記録も含める。</p>'
            '<table><tr><th>元記録</th><th>元成否</th><th>曲詳細要求</th><th>必要列が既知</th><th>同一要求を保持</th><th>既知全応答と一致</th></tr>'
            + ''.join(rows) + '</table><p class="small">既知＝要求直前。全応答一致＝返却後の照合。独立５課題の比較ではない。</p>',
         'take': 'P68の各９要求はCSVの列が既知だったが、詳細応答全体の代替は示せなかった。',
         'notes': 'P18/P25は必要列が既知だった曲への詳細要求０。P29は８、P68は各９。全５記録で同一要求の応答保持０、既知オブジェクトと完全一致０。過去と新しい条件の差を制御効果へ帰属しない。'},
        {'title': 'CSVの充足と、呼出し先の応答契約を分ける',
         'body': '<table><tr><th>確認した範囲</th><th>公開情報から分かること</th></tr>'
            '<tr><td>CSVで要求された列</td><td>Title と Artists。曲IDで対応させて照合。</td></tr>'
            '<tr><td>一覧から得る曲の情報</td><td>題名・アーティスト等と、一覧への追加日時。</td></tr>'
            '<tr><td>曲詳細APIの応答</td><td>ジャンル・評価・再生回数等も返る。全項目は一覧と異なる。</td></tr>'
            '<tr><td>同じ生成に混ざる要求</td><td>既知の列だけでなく、新しい情報の取得も含む。</td></tr></table>'
            f'<p class="small">送信が全て「必要列は既知の曲詳細」だった生成境界：{covered}。<br>候補API数を、削れる生成数やtokenへ換算しない。</p>',
         'take': '必要列を使い回すなら、その用途を明示する仕組みが必要になる。',
         'notes': 'API実装は固定した公開Spotifyコードで確認した。全応答のキャッシュとして部分的な一覧オブジェクトを返すと、元のAPI応答を保ったことにはならない。未知の値を埋めたり、未来の応答から事前可否を決めたりしない。'},
        {'title': '局所的な次の課題を残し、新手法とはしない',
         'body': '<table><tr><th>判断</th><th>今回の位置づけ</th></tr>'
            '<tr><td>通常の同一要求キャッシュ</td><td>この５記録の曲詳細要求には候補０。</td></tr>'
            '<tr><td>取得済みの必要列を利用する</td><td>対象はあるが、完全なAPI応答の代替や実測削減は未検証。</td></tr>'
            '<tr><td>強い通常対照</td><td>過去のP25は既知列の再取得０で成功。条件差は残る。</td></tr>'
            '<tr><td>方式の追加価値</td><td>通常の射影・差分取得・需要追跡との違いを先に照合する。</td></tr></table>'
            f'<p class="small">全点検 {report["wall_seconds"]:.6f} 秒。追加生成・API・評価・DB内容・保留群０。</p>',
         'take': '完全応答の意味を変えずに省ける範囲と、通常方式との差を具体化する。',
         'notes': '実装候補数や補助検査を新規性に転記しない。P68の条件を変えて成功まで再試行する比較ではない。P18の末尾のshow_fileとP18/P25の退会は本取得判定器の範囲外として残るが、全曲詳細要求より後であり候補数を変更しない。'}]
    sections = []
    for n, s in enumerate(slides, 1):
        if s.get('cover'):
            sections.append(f'<section class="slide cover"><h1>{s["title"]}</h1><div class="notes"></div></section>'); continue
        sections.append(f'<section class="slide"><div class="eyebrow">10月23日 CSVの取得範囲 / {n-1:02d}</div><h2>{s["title"]}</h2>{s["body"]}'
            f'<div class="takeaway">{s["take"]}</div><div class="footer"><span class="sources">'
            '<a href="https://github.com/sophiria1225/AI-/blob/main/docs/P69_findings.md">全結果・範囲</a> / '
            '<a href="https://github.com/sophiria1225/AI-/blob/main/reports/P69_export_acquisition_scope.json">全件集計</a></span>'
            f'<span>{n}/{len(slides)}</span></div><div class="notes">{html.escape(s["notes"])}</div></section>')
    nav='<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css='h2{font-size:33px}table{font-size:18px}.lead{font-size:21px}.small{margin-top:14px;font-size:18px}td{padding:9px 12px}.takeaway{font-size:20px}'
    output.mkdir(parents=True, exist_ok=True)
    (output/'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>CSVの取得範囲</title><style>'+STYLE+css+'</style></head><body>'+''.join(sections)+nav+'<script>'+SCRIPT+'</script></body></html>')
    (output/'slides.json').write_text(json.dumps(slides,ensure_ascii=False,indent=2)+'\n')
    manifest={'pages':len(slides),'generated_at':datetime.now(timezone.utc).isoformat(),
        'source_sha256':{p:sha(ROOT/p) for p in SOURCES},'builder_sha256':sha(Path(__file__)),
        'visual_reviewed':False,'scope':'All five posthoc known CSV records; no calls suppressed and no measured savings.'}
    (output/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'materials/20261023_p69');p.add_argument('--pdf',action='store_true');a=p.parse_args()
    print(json.dumps(build(a.output)))
    if a.pdf:build_budget_report.STEM=STEM;build_budget_report.export(a.output)
