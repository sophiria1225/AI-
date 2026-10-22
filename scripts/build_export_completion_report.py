"""Render all fixed P68 conditions after execution and independent accounting."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from build_completion_control_report import outcome, equality
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_export_completion_20261023'
SOURCES = ('reports/P68_completion_audit.json', 'reports/P68_export_completion.json',
           'configs/P68_export_completion_v01.json', 'reports/P67_public_export_scope.json')


def build(output):
    audit, report, plan, _ = [read(ROOT / p) for p in SOURCES]
    if (audit['audit_errors'] or not audit['server_stopped'] or audit['owned_server_processes_present']
            or audit['source_report_sha256'] != sha(ROOT / SOURCES[1])
            or audit['plan_sha256'] != sha(ROOT / SOURCES[2])
            or plan['public_scope_sha256'] != sha(ROOT / SOURCES[3])
            or [[r['task_id'], r['arm'], r['run_id']] for r in audit['rows']] != plan['run_order']
            or report['status'] not in ('complete', 'stopped')):
        raise ValueError('closed, reconciled, complete scheduled population required')
    labels = {'native': '通常native', 'controlled': '同じnative＋終了制御'}
    comparisons = []; evidence = []; executed = []
    for row in audit['rows']:
        label = labels[row['arm']]
        if row['status'] == 'not_run':
            comparisons.append(f'<tr><td>{label}</td><td colspan="5">未実行</td></tr>')
            evidence.append(f'<tr><td>{label}</td><td colspan="3">未実行</td></tr>'); continue
        executed.append(row)
        tokens = f'{row["known_total_tokens"]:,}' + (' + ?' if row['unknown_usage_calls'] else '')
        comparisons.append(f'<tr><td>{label}</td><td>{outcome(row["official_success"])}</td><td>{tokens}</td>'
            f'<td>{row["model_calls"]}</td><td>{row["api_requests"]}</td><td>{row["unknown_usage_calls"]}</td></tr>')
        c = row['controller']; boundary = ', '.join(c['supported_boundaries']) or ('監視なし' if row['arm'] == 'native' else '支持なし')
        evidence.append(f'<tr><td>{label}</td><td>{boundary}</td><td>{c["checks"]}</td><td>{c["completion_attempts"]}</td></tr>')
    pair = audit['comparison']; complete = pair['both_evaluated']
    state_equal = (not pair['changed_final_database_files'] and pair['final_database_file_counts'] == [13, 13]) if complete else None
    delta = f'{pair["logical_token_difference_controlled_minus_native"]:+,}' if complete and pair['difference_is_exact'] else '確定差は算出しない'
    gate = audit['local_adoption_gate_met']
    conclusion = ('既知１課題で、同じ最終状態・公式成功を保った全体tokenの減少を観測。' if gate else
                  '両成功・同じ最終状態・全体token減という局所採用条件は満たしていない。')
    totals = f'{audit.get("known_total_tokens", 0):,}' + (' + ?' if audit.get('unknown_usage_calls', 0) else '')
    seconds = sum(r['controller']['wall_seconds'] for r in executed)
    walls = '／'.join(f'{r["full_wall_seconds"]:.3f}' for r in executed) or 'なし'
    strict = equality(pair.get('same_entire_executed_model_prefix'))
    events = equality(pair.get('same_prefix_events')); spans = equality(pair.get('same_prefix_spans'))
    slides = [
        dict(cover=True, title='CSV書出し課題の通常終了制御を<br>同じ条件の仕事全体で比較する'),
        dict(cover=False, title='新しい通常対照と終了制御：全２条件',
            body='<p class="lead">既知CSV１課題・各１回。初期状態、案内、ツール、予算、モデルをそろえる。</p>'
            '<table><tr><th>条件</th><th>公式成否</th><th>全体token</th><th>生成</th><th>API</th><th>使用量不明</th></tr>'
            + ''.join(comparisons) + f'</table><p class="small">制御あり−通常の全体token差：{delta}。<br>全入力＋全出力、cached inputを含む。未達・未評価・未実行も保持。</p>',
            takeaway=conclusion,
            notes='P25との歴史的な差ではなく、P68の２条件を比較する。P67で既知の成功・失敗を読んだ後に選択した通常制御の開発点検で、独立確認ではない。'),
        dict(cover=False, title='書出しの内容と、その後の退会を要求',
            body='<p class="lead">各応答の全操作後に確認。制御が送れるのは通常の完了通知だけ。</p>'
            '<table><tr><th>条件</th><th>支持境界</th><th>検査回数</th><th>制御の通知試行</th></tr>'
            + ''.join(evidence) + '</table><p class="small">終端ページ→元ID集合→メタデータ→正しいCSV→退会の順序を確認。<br>不明・矛盾なら追加案内なしで継続。退会そのものはモデルが実行。</p>',
            takeaway='書出しだけで終わらせず、未来の情報で不足していた証拠を埋めない。',
            notes='P67の手書き文型と検査器を変更せず使う。同じ応答内で後続の未対応変更があれば支持しない。完了通知の失敗・作用不明時には再試行しない。'),
        dict(cover=False, title='実行した前半・最終状態・費用を照合',
            body='<table><tr><th>全件監査の指標</th><th>観測値</th></tr>'
            f'<tr><td>実行した前半の要求・モデル応答全文</td><td>{strict}</td></tr>'
            f'<tr><td>公開イベント／公開応答／最終13 DB</td><td>{events}／{spans}／{equality(state_equal)}</td></tr>'
            f'<tr><td>全token／生成／API／評価</td><td>{totals}／{audit.get("model_calls",0)}／{audit.get("api_requests",0)}／{audit.get("evaluator_calls",0)}</td></tr>'
            f'<tr><td>検査＋digestの合計／各条件の全時間</td><td>{seconds:.6f}秒／{walls}秒</td></tr>'
            f'<tr><td>所有推論器／ロード／終了</td><td>{audit["server"]["wall_seconds"]:.3f}秒／{audit["server"]["load_wall_seconds"]:.3f}秒／停止確認</td></tr></table>',
            takeaway='判定・保存・通知を含む全費用を残し、論理tokenの率を時間や金銭へ移さない。',
            notes='全文の不一致はそのまま残す。IDだけの差とそれ以外の差は全監査のフィールド経路へ記録する。各条件の時間には初期化・片付けが入り、評価器と推論器は別記。'),
        dict(cover=False, title='局所的な採否と、レターで使える範囲',
            body='<table><tr><th>確認すること</th><th>拡大しない主張</th></tr>'
            '<tr><td>同じ既知CSV課題の２実行</td><td>独立課題の成功率・反復された平均効果</td></tr>'
            '<tr><td>宣言した公開API意味・手書き要求の支持</td><td>任意の自然言語要求や外界の品質保証</td></tr>'
            '<tr><td>通常の保持・内容検査・終了通知</td><td>証拠付き終了そのものの新規性</td></tr>'
            '<tr><td>失敗・未知費用・未実行を含む全条件</td><td>有利な実行だけを選んだ費用削減</td></tr></table>',
            takeaway=conclusion,
            notes='写真P66とは別の既知文型の結果として扱い、P55の表示比較へ合算しない。保留12シナリオは未閲覧。10月31日の投稿目標へ、必要処理と品質を保った仕事全体の費用削減という目的を維持する。')]
    sections = []
    for n, s in enumerate(slides, 1):
        if s['cover']:
            sections.append(f'<section class="slide cover"><h1>{s["title"]}</h1><div class="notes"></div></section>'); continue
        sections.append(f'<section class="slide"><div class="eyebrow">10月23日 CSVの通常終了制御 / {n-1:02d}</div><h2>{s["title"]}</h2>{s["body"]}'
            f'<div class="takeaway">{s["takeaway"]}</div><div class="footer"><span class="sources">'
            '<a href="https://github.com/sophiria1225/AI-/blob/main/docs/P68_findings.md">全結果・限界</a> / '
            '<a href="https://github.com/sophiria1225/AI-/blob/main/reports/P68_completion_audit.json">全監査</a></span>'
            f'<span>{n}/{len(slides)}</span></div><div class="notes">{html.escape(s["notes"])}</div></section>')
    nav='<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css='h2{font-size:34px}table{font-size:18px}.lead{font-size:21px}.small{margin-top:16px;font-size:18px}td{padding:11px 12px}.takeaway{font-size:20px}'
    output.mkdir(parents=True, exist_ok=True)
    (output/'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>CSVの通常終了制御</title><style>'+STYLE+css+'</style></head><body>'+''.join(sections)+nav+'<script>'+SCRIPT+'</script></body></html>')
    (output/'slides.json').write_text(json.dumps(slides,ensure_ascii=False,indent=2)+'\n')
    manifest={'pages':len(slides),'generated_at':datetime.now(timezone.utc).isoformat(),
        'source_sha256':{p:sha(ROOT/p) for p in SOURCES},'builder_sha256':sha(Path(__file__)),
        'visual_reviewed':False,'scope':'All two P68 fresh native conditions on one known export task; ordinary hand-authored control.'}
    (output/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'materials/20261023_p68');p.add_argument('--pdf',action='store_true');a=p.parse_args()
    print(json.dumps(build(a.output)))
    if a.pdf:build_budget_report.STEM=STEM;build_budget_report.export(a.output)
