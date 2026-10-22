"""Render every closed P64 condition from the audited whole-task measurements."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_public_name_comparison_20261023'
SOURCE = 'reports/P64_public_name_audit.json'


def build(output):
    audit = read(ROOT / SOURCE); report = read(ROOT / 'reports/P64_public_name_comparison.json')
    plan = read(ROOT / 'configs/P64_public_name_comparison_v01.json')
    scope = read(ROOT / 'reports/P65_public_move_scope.json')
    if (audit['audit_errors'] or len(audit['rows']) != 4 or not audit['server_stopped']
            or audit['owned_server_processes_present'] or audit['source_report_sha256'] != sha(ROOT / 'reports/P64_public_name_comparison.json')
            or audit['plan_sha256'] != sha(ROOT / 'configs/P64_public_name_comparison_v01.json')
            or report['status'] not in ('complete', 'stopped')
            or [[r['task_id'], r['arm'], r['run_id']] for r in audit['rows']] != plan['run_order']):
        raise ValueError('all fixed conditions, closed server and reconciled sources required')
    if (scope['source_report_sha256']['P64'] != sha(ROOT / SOURCE) or len(scope['rows']) != 2
            or any(r['differences'] for r in scope['old_parity_controls'])
            or scope['inspector_sha256'] != sha(ROOT / 'scripts/inspect_new_move_scope.py')):
        raise ValueError('matching passive scope analysis and original parity controls required')
    for row in scope['rows']:
        final = row['final']; tail = row['observed_cost_after_first_supported_boundary']
        if (final['trace_support'] != 'supported' or not final['current_year_observed']
                or any(final[k] != 42 for k in ('inventory_files', 'metadata_files', 'successful_move_receipts', 'filename_preserved_moves'))
                or tail is None or tail['later_model_calls'] != 2 or tail['later_unknown_usage_calls']):
            raise ValueError('this presentation requires both complete, clock-supported photo traces and two measured later calls')
    table = []; details = []
    for row in audit['rows']:
        task = '写真整理' if row['task_id'] == '34d9492_1' else '電気代精算'
        arm = '文書取得必須' if row['arm'] == 'documented' else '公開名アクセス'
        if row['status'] == 'not_run':
            table.append(f'<tr><td>{task}</td><td>{arm}</td><td colspan="4">未実行</td></tr>'); continue
        success = row['official_success']
        outcome = '成功' if success is True else '未達' if success is False else '未評価'
        tokens = f'{row["known_total_tokens"]:,}' + (' + ?' if row['unknown_usage_calls'] else '')
        table.append(f'<tr><td>{task}</td><td>{arm}</td><td>{outcome}</td><td>{tokens}</td>'
            f'<td>{row["model_calls"]}</td><td>{row["api_requests"]}</td></tr>')
        details.append(f'<tr><td>{task}・{arm}</td><td>{len(row["clock_receipts_with_date_and_time"])}</td>'
            f'<td>{row["undispatched_clock_requests"]}</td><td>{row["full_wall_seconds"]:.1f}</td></tr>')
    total = f'{audit.get("known_total_tokens", 0):,}' + (' + 使用量不明あり' if audit.get('unknown_usage_calls', 0) else '')
    server = audit['server']
    slides = [dict(cover=True, title='公開名で呼べる通常基準を<br>課題の開始から確かめる'),
        dict(cover=False, title='全４条件の成否と仕事全体の費用',
            body='<p class="lead">既知２課題を各条件１回。公開課題・初期DB・予算をそろえた。</p>'
            '<table><tr><th>課題</th><th>通常Pythonの条件</th><th>成否</th><th>全体token</th><th>生成</th><th>API</th></tr>'
            + ''.join(table) + '</table><p class="small">全入力＋全出力。cached inputも含む。文書取得・失敗・完了通知も計上。<br>'
            '公開名条件では、説明を見ていなくても正確な登録名で呼べる。能力の案内も合わせて変更。</p>',
            takeaway='呼出し受付と正確な案内をまとめた通常基準の比較。新手法の効果とはしない。',
            notes='P63で時刻要求の受付が変わると確認した２既知課題の事後選択。単一モデル・seed42。写真は従来→公開名、精算は公開名→従来。初回cached inputは０、後続キャッシュも全入力費用へ含める。未達で早く止まった条件を高効率の成功とは数えない。'),
        dict(cover=False, title='時計の返却・拒否と、完了までの時間も残す',
            body='<table><tr><th>条件</th><th>日時入り返却</th><th>未送信の時計要求</th><th>全経過秒</th></tr>'
            + ''.join(details) + '</table><p class="small">全条件合計：' + total + ' token、'
            f'{audit.get("model_calls", 0)}生成、{audit.get("api_requests", 0)} API、{audit.get("evaluator_calls", 0)}評価。<br>'
            f'所有推論器 {server["wall_seconds"]:.1f}秒、ロード {server["load_wall_seconds"]:.1f}秒。終了を確認。</p>',
            takeaway='２課題の観測を保持し、旧実験の結果は変更しない。保留群の閲覧は０。',
            notes='日時入り返却はdate/time文字列を含む公開clock API応答の数で、要求全体の品質保証ではない。未送信は受付で拒否・停止された要求を含む。全経過秒は初期化と片付けを含み、別プロセス評価・モデルのロードは含まない。API・時間・tokenを一つの金額へ換算しない。'),
        dict(cover=False, title='主張を強める前に、通常基準の条件をそろえる',
            body='<table><tr><th>今回の証拠</th><th>残る研究判断</th></tr>'
            '<tr><td>正確な公開名の受付と、初期文書表示を分離</td><td>通常基準を超える独自の制御は未確定</td></tr>'
            '<tr><td>全条件・失敗・不明使用量を同じ規則で集計</td><td>２既知課題・各１回を一般化しない</td></tr>'
            '<tr><td>公開応答と独立の公式成否を分離</td><td>必要情報・品質・総費用を一緒に評価</td></tr></table>'
            '<p class="small">P55/P56の原稿は、そのときの追加制約の下で得た局所診断として保持。<br>'
            '10月31日の投稿へ向け、実証的な主張の根拠と限界を更新する。</p>',
            takeaway='最終目標は、必要な仕事と品質を保ち、制御・失敗込みの仕事全体費用を減らすこと。',
            notes='公開名アクセスは普通の実行能力をそろえる比較であり、独自方式の採用ではない。受付と能力説明が一緒に変わるため、受付コードだけの因果効果も主張しない。公式様式と著者情報、採録に足る中心貢献は未確定。')]
    scope_table = []
    for row in scope['rows']:
        arm = '文書取得必須' if row['arm'] == 'documented' else '公開名アクセス'
        if row['status'] == 'not_run':
            scope_table.append(f'<tr><td>{arm}</td><td colspan="3">未実行</td></tr>'); continue
        supported = row['final']['trace_support']
        tail = row['observed_cost_after_first_supported_boundary']
        status = {'supported': '宣言した条件を支持', 'contradicted': '矛盾', 'unknown': '不明'}[supported]
        boundary = tail['first_supported_boundary'] if tail else 'なし'
        cost = f'{tail["later_known_tokens"]:,}' + (' + ?' if tail['later_unknown_usage_calls'] else '') if tail else '対象なし'
        scope_table.append(f'<tr><td>{arm}</td><td>{status}</td><td>{boundary}</td><td>{cost}</td></tr>')
    slides.insert(-1, dict(cover=False, title='写真２条件では、公開時計を含む根拠がそろった',
        body='<p class="lead">P65の読取分析。元集合・移動前の日時・42件の移動・名前保持を照合。</p>'
        '<table><tr><th>通常条件</th><th>公開記録の支持範囲</th><th>最初の境界</th><th>その後のtoken</th></tr>'
        + ''.join(scope_table) + '</table><p class="small">両条件とも、その後に２生成。後続費用は実測節約額ではない。<br>'
        '同じ既知要求文型の通常検査。旧３条件との一致を確認し、公式成否を維持。</p>',
        takeaway='公開根拠がそろう条件を確認した。自動終了による品質・費用はまだ測っていない。',
        notes='P62の厳しい正規化を新しい２記録へ適用。新しい独立２課題ではなく同じ写真課題の２条件。後続の公開一覧確認と完了通知が不要だったとは断定しない。読取0.030秒、追加生成・API・評価・DB内容・保留群０。事前のJSONキー表現の比較失敗も別記録へ保存。'))
    sections = []
    for number, slide in enumerate(slides, 1):
        if slide['cover']:
            sections.append(f'<section class="slide cover"><h1>{slide["title"]}</h1><div class="notes"></div></section>'); continue
        sections.append(f'<section class="slide"><div class="eyebrow">10月23日 通常基準の条件 / {number-1:02d}</div>'
            f'<h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div>'
            '<div class="footer"><span class="sources"><a href="https://github.com/sophiria1225/AI-/blob/main/docs/P64_findings.md">全結果・限界</a> / '
            '<a href="https://github.com/sophiria1225/AI-/blob/main/reports/P64_public_name_audit.json">全条件の照合</a></span>'
            f'<span>{number}/{len(slides)}</span></div><div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css = 'h2{font-size:34px}table{font-size:19px}.lead{font-size:22px}.small{margin-top:16px;font-size:18px}td{padding:12px 14px}.takeaway{font-size:20px}'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P64 公開名アクセスの通常基準</title><style>'
        + STYLE + css + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    (output / 'slides.json').write_text(json.dumps(slides, ensure_ascii=False, indent=2) + '\n')
    manifest = {'pages': len(slides), 'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': {p: sha(ROOT / p) for p in (SOURCE, 'reports/P64_public_name_comparison.json', 'configs/P64_public_name_comparison_v01.json', 'reports/P65_public_move_scope.json')},
        'builder_sha256': sha(Path(__file__)), 'visual_reviewed': False,
        'scope': 'All four scheduled conditions on two known development tasks; ordinary interface package, no novel method.'}
    (output / 'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, default=ROOT / 'materials/20261023_p64')
    p.add_argument('--pdf', action='store_true'); a = p.parse_args()
    print(json.dumps(build(a.output)))
    if a.pdf:
        build_budget_report.STEM = STEM; build_budget_report.export(a.output)
