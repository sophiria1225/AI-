"""Render every fixed P66 outcome after whole-task and public-prefix auditing."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_ordinary_completion_20261023'
SOURCES = ('reports/P66_completion_audit.json', 'reports/P66_ordinary_completion.json',
    'configs/P66_ordinary_completion_v01.json', 'reports/P64_public_name_audit.json',
    'reports/P66_identity_differences.json')


def outcome(value):
    return '成功' if value is True else '未達' if value is False else '未評価'


def equality(value):
    return '一致' if value is True else '不一致' if value is False else '未確認'


def build(output):
    audit, report, plan, baseline, identity = [read(ROOT / p) for p in SOURCES]
    if (audit['audit_errors'] or not audit['server_stopped'] or audit['owned_server_processes_present']
            or audit['source_report_sha256'] != sha(ROOT / SOURCES[1])
            or audit['plan_sha256'] != sha(ROOT / SOURCES[2])
            or plan['reference_audit_sha256'] != sha(ROOT / SOURCES[3])
            or len(audit['rows']) != 2
            or [[r['task_id'],r['arm'],r['run_id']] for r in audit['rows']] != plan['run_order']
            or report['status'] not in ('complete','stopped')):
        raise ValueError('closed complete fixed population and reconciled sources required')
    if (identity['criterion_changed'] or identity['source_sha256'][SOURCES[0]] != sha(ROOT/SOURCES[0])
            or identity['inspector_sha256'] != sha(ROOT/'scripts/inspect_completion_identity_differences.py')
            or len(identity['rows']) != 2
            or any(r.get('request_other_differences', 0) or r.get('response_other_differences', 0) for r in identity['rows'])):
        raise ValueError('matching field-path diagnosis required for identifier-only description')
    comparisons=[]; scope=[]; completed=[]
    for row in audit['rows']:
        arm = '文書取得必須' if row['arm']=='documented' else '公開名アクセス'
        base=next(b for b in baseline['rows'] if b['task_id']==row['task_id'] and b['arm']==row['arm'])
        comparisons.append(f'<tr><td>{arm}</td><td>通常の継続</td><td>{outcome(base["official_success"])}</td>'
            f'<td>{base["known_total_tokens"]:,}</td><td>{base["model_calls"]}</td><td>{base["api_requests"]}</td></tr>')
        if row['status']=='not_run':
            comparisons.append(f'<tr><td>{arm}</td><td>終了制御</td><td colspan="4">未実行</td></tr>')
            scope.append(f'<tr><td>{arm}</td><td colspan="3">未実行</td></tr>');continue
        completed.append(row)
        tokens=f'{row["known_total_tokens"]:,}'+(' + ?' if row['unknown_usage_calls'] else '')
        comparisons.append(f'<tr><td>{arm}</td><td>終了制御</td><td>{outcome(row["official_success"])}</td>'
            f'<td>{tokens}</td><td>{row["model_calls"]}</td><td>{row["api_requests"]}</td></tr>')
        controller=row['controller'];pair=row['baseline_comparison']
        boundary=', '.join(controller['supported_boundaries']) or '支持なし'
        scope.append(f'<tr><td>{arm}</td><td>{boundary}</td><td>{equality(pair["same_entire_executed_model_prefix"])}</td>'
            f'<td>{equality(pair["non_supervisor_database_files_equal"])}</td></tr>')
    locally_lower=(len(completed)==2 and all(r['official_success'] is True and not r['unknown_usage_calls']
        and r['baseline_comparison']['logical_token_difference_new_minus_reference']<0 for r in completed))
    cost_message=('この既知１課題の両条件で、成功を保った全体tokenの減少を観測。' if locally_lower else
        '全条件の成否と費用を保持し、成功した条件だけで削減を主張しない。')
    totals=f'{audit.get("known_total_tokens",0):,}'+(' + 不明あり' if audit.get('unknown_usage_calls',0) else '')
    seconds=sum(r['controller']['wall_seconds'] for r in completed)
    checks=sum(r['controller']['checks'] for r in completed)
    attempts=sum(r['controller']['completion_attempts'] for r in completed)
    wall='／'.join(f'{r["full_wall_seconds"]:.3f}' for r in completed) or 'なし'
    slides=[
        dict(cover=True,title='公開記録による通常の終了制御を<br>仕事全体の費用で確かめる'),
        dict(cover=False,title='通常の継続と、全２条件の終了制御',
            body='<p class="lead">既知の写真１課題。各インターフェースで１回ずつ、新しい開始状態から実行。</p>'
            '<table><tr><th>通常Python</th><th>終了方法</th><th>公式成否</th><th>全体token</th><th>生成</th><th>API</th></tr>'
            +''.join(comparisons)+'</table><p class="small">全入力＋全出力。cached input、失敗、完了通知も含める。<br>通常の継続は閉じたP64、終了制御はP66。順序付き・各１回の開発比較。</p>',
            takeaway=cost_message,
            notes='両方とも同じ写真課題で、独立２課題ではない。P64/P65の結果後に選択した検証。P66では指示・初期状態・モデル・seed・予算を対応するP64とそろえる。使用量不明は０へ補完せず、未実行も保持する。'),
        dict(cover=False,title='前半の一致と、実作業の保存状態を照合',
            body='<p class="lead">時系列の公開応答だけで、全プログラム実行後・次の生成前に判定。</p>'
            '<table><tr><th>通常Python</th><th>支持された境界</th><th>実行した前半</th><th>作業アプリの最終DB</th></tr>'
            +''.join(scope)+'</table><p class="small">前半の全文一致は不成立。差分は外側のツール呼出しIDだった。<br>実APIの公開イベント・応答と、最終13 DBは両条件とも一致した。</p>',
            takeaway='事前の全文一致基準は変更しない。局所の観測差を一般的な因果効果へ広げない。',
            notes='同じseedだけで同じ生成になるとは仮定せず、終了後に全前半を比較した。差分診断では要求のID差156／132、モデルメッセージのID差13／12、その他の値の差０。これは判定基準を緩めた一致ではない。制御は未来の応答・元の解答・公式評価を使わない。生成内の途中では終了させない。'),
        dict(cover=False,title='判定と完了通知を含め、追加の費用も残す',
            body='<table><tr><th>全２予定条件の測定</th><th>今回の値</th></tr>'
            f'<tr><td>全入力＋全出力／生成／API／公式評価</td><td>{totals} token／{audit.get("model_calls",0)}／{audit.get("api_requests",0)}／{audit.get("evaluator_calls",0)}</td></tr>'
            f'<tr><td>判定＋digestの合計／判定回数／制御の通知試行</td><td>{seconds:.6f}秒／{checks}／{attempts}</td></tr>'
            f'<tr><td>実行済み各条件の初期化・片付け込み時間</td><td>{wall}秒</td></tr>'
            f'<tr><td>所有推論器／ロード／終了</td><td>{audit["server"]["wall_seconds"]:.3f}秒／{audit["server"]["load_wall_seconds"]:.3f}秒／停止確認</td></tr></table>'
            '<p class="small">判定の保存や完了APIも全体時間に含む。別プロセス評価・モデルロードは別記。<br>監査・資料作成はモデルや環境APIを呼ばない。保留群閲覧０。</p>',
            takeaway='局所的な論理tokenの減少率を、時間や金銭の削減率へ置き換えない。',
            notes='tokenはcached inputも含める。時間・資源は単位を分けて報告する。制御の失敗、不明使用量、未実行は計画に従い残す。判定時間はdigestと純粋なチェックの計測で、保存は条件の全時間に含む。'),
        dict(cover=False,title='通常の制御が成立する範囲と、残る研究判断',
            body='<table><tr><th>ここで扱った範囲</th><th>まだ成立していない主張</th></tr>'
            '<tr><td>分析者が解釈した既知の写真要求文型</td><td>任意の自然言語要求の自動解釈</td></tr>'
            '<tr><td>元集合・元日時・時計・移動・名前の公開根拠</td><td>任意の外部世界の真実・副作用の保証</td></tr>'
            '<tr><td>通常の保持と検査、支持時だけの完了通知</td><td>既存方式を超える新規性・独自中核</td></tr>'
            '<tr><td>同一既知課題・各条件１回の観測</td><td>独立課題での一般的な品質維持・平均効果</td></tr></table>',
            takeaway='必要な仕事と品質を残した全体費用削減という最終目標へ、根拠のある範囲で進む。',
            notes='この手書き検査を新手法へ昇格させない。原稿のP55/P56とは条件が異なり、結果を主表へ合算しない。10月23日に主張を絞り、25日まで不足確認、29〜30日原稿、31日投稿を目指す。中心貢献・公式様式・著者情報は別に解決が必要。')]
    sections=[]
    for n,s in enumerate(slides,1):
        if s['cover']:
            sections.append(f'<section class="slide cover"><h1>{s["title"]}</h1><div class="notes"></div></section>');continue
        sections.append(f'<section class="slide"><div class="eyebrow">10月23日 通常の終了制御 / {n-1:02d}</div><h2>{s["title"]}</h2>{s["body"]}'
            f'<div class="takeaway">{s["takeaway"]}</div><div class="footer"><span class="sources">'
            '<a href="https://github.com/sophiria1225/AI-/blob/main/docs/P66_findings.md">全結果・限界</a> / '
            '<a href="https://github.com/sophiria1225/AI-/blob/main/reports/P66_completion_audit.json">全監査</a></span>'
            f'<span>{n}/{len(slides)}</span></div><div class="notes">{html.escape(s["notes"])}</div></section>')
    nav='<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css='h2{font-size:34px}table{font-size:18px}.lead{font-size:21px}.small{margin-top:16px;font-size:18px}td{padding:11px 12px}.takeaway{font-size:20px}'
    output.mkdir(parents=True,exist_ok=True)
    (output/'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>通常の逐次終了制御</title><style>'+STYLE+css+'</style></head><body>'+''.join(sections)+nav+'<script>'+SCRIPT+'</script></body></html>')
    (output/'slides.json').write_text(json.dumps(slides,ensure_ascii=False,indent=2)+'\n')
    manifest={'pages':len(slides),'generated_at':datetime.now(timezone.utc).isoformat(),
        'source_sha256':{p:sha(ROOT/p) for p in SOURCES},'builder_sha256':sha(Path(__file__)),
        'visual_reviewed':False,'scope':'All two P66 ordinary controls on one known photo task; handwritten contract, no novel method claim.'}
    (output/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'materials/20261023_p66');p.add_argument('--pdf',action='store_true');a=p.parse_args()
    print(json.dumps(build(a.output)))
    if a.pdf:build_budget_report.STEM=STEM;build_budget_report.export(a.output)
