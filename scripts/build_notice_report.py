"""Present all four P58 generation-only cells from the closed audit."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_notice_calibration_20261023'
SOURCES = ('reports/P58_notice_calibration.json', 'reports/P58_notice_audit.json',
           'configs/P58_notice_calibration_v01.json')


def build(output):
    report, audit, plan = [read(ROOT / name) for name in SOURCES]
    if (audit['audit_errors'] or not audit['all_four_planned_rows_accounted']
            or audit['source_report_sha256'] != sha(ROOT / SOURCES[0])
            or audit['source_plan_sha256'] != sha(ROOT / SOURCES[2])
            or report['status'] not in ('complete', 'stopped')):
        raise ValueError('closed audit with every planned condition required')
    labels = {}; table = []
    for row in audit['rows']:
        fingerprint = row.get('message_sha256')
        if fingerprint is not None:
            labels.setdefault(fingerprint, chr(65 + len(labels)))
        result = labels.get(fingerprint, '未実行' if not row['model_request_started'] else '不明')
        tokens = (f"{row['input_tokens'] + row['output_tokens']:,}" if row['status'] == 'ok' else '—')
        cache = str(row['cached_input_tokens']) if row['status'] == 'ok' else '—'
        table.append(f'<tr><td>{row["label"][-1]}回目</td><td>{row["wall_snapshot_seconds"]}秒</td>'
                     f'<td>{tokens}</td><td>{cache}</td><td>{result}</td></tr>')
    comparison = audit['comparison']
    if comparison['local_sensitivity_observed'] is True:
        finding = '同じ通知の２回は一致し、335秒と336秒の間で生成メッセージが異なった。'
    elif comparison['local_sensitivity_observed'] is False:
        finding = '同じ通知の２回も、335秒と336秒の間も、生成メッセージは一致した。'
    elif comparison['all_four_confirmed']:
        finding = '同じ通知の反復にも揺れがあり、通知差だけへの帰属はできなかった。'
    else:
        finding = '４回の比較は未完了。実行済み・不明・未実行を区別して残した。'
    costs = f"{audit['known_total_tokens']:,} token"
    if audit['unknown_usage_calls']: costs += f"＋不明{audit['unknown_usage_calls']}生成"
    server = audit['server']
    slides = [dict(cover=True, title='残時間通知１か所と生成の揺れ<br>固定４回の局所確認'),
        dict(cover=False, title='通知以外を共通にし、同じ条件も２回ずつ調べる',
             body='<p class="lead">同じ既知入力・seed 51・出力上限4,096。全回、初回入力キャッシュを使わない。</p>'
             '<table><tr><th>固定順序</th><th>残時間の表示</th><th>全入力＋出力</th><th>cache入力</th><th>全文一致群</th></tr>'
             + ''.join(table) + '</table><p class="small">一致群は配送IDだけを除く全文の一致。推論文・コードも含む。生成した操作は実行していない。</p>',
             takeaway=finding,
             notes='元の返金D/B第２要求は、配送IDを除くと残時間335/336の１か所だけ異なる。新しい４要求はDのIDまで共通化し、335/336/336/335の順序を固定した。'),
        dict(cover=False, title='この確認で分かる範囲を、課題の改善と分ける',
             body='<table><tr><th>今回の確認</th><th>ここからは言えないこと</th></tr>'
             '<tr><td>既知１入力・２通知・各２回</td><td>独立４課題や分散の推定</td></tr>'
             '<tr><td>全回coldでそろえた局所比較</td><td>元P55のwarm条件の原因同定</td></tr>'
             '<tr><td>生成メッセージの全文一致</td><td>実行した行動や最終品質の差</td></tr>'
             '<tr><td>新しい校正費用も記録</td><td>省費用の新手法の成立</td></tr></table>'
             f'<p class="small">生成{audit["model_calls_attempted"]}回、{costs}、計数{audit["input_count_requests"]}回。環境API・評価０。<br>'
             f'実行{audit["worker_wall_seconds"]:.1f}秒、推論器{server["wall_seconds"]:.1f}秒で停止（ロード{server["load_wall_seconds"]:.1f}秒を含む）。</p>',
             takeaway='方式の差・通知入力の差・実行の揺れを区別し、品質と仕事全体の費用で判断する。',
             notes='これだけで時計を隠す制御を採用しない。研究目標は必要な情報と処理を保ち、不要な取得・共有・呼出し・実行・検証を減らすこと。中心的新規性と月末投稿の科学的な十分性は未確定。')]
    sections = []
    for i, slide in enumerate(slides, 1):
        if slide['cover']:
            sections.append(f'<section class="slide cover"><h1>{slide["title"]}</h1><div class="notes"></div></section>')
        else:
            sections.append(f'<section class="slide"><div class="eyebrow">10月23日 通知の生成感度 / {i-1:02d}</div>'
                f'<h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div>'
                '<div class="footer"><span class="sources"><a href="https://github.com/sophiria1225/AI-/blob/main/docs/P58_findings.md">全結果・解釈</a> / '
                '<a href="https://github.com/sophiria1225/AI-/blob/main/reports/P58_notice_audit.json">監査</a></span>'
                f'<span>{i}/3</span></div><div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    output.mkdir(parents=True, exist_ok=True)
    css = 'h2{font-size:34px}table{font-size:19px}.lead{font-size:22px}.small{margin-top:16px}td{padding:12px 15px}.takeaway{font-size:21px}'
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P58 通知の生成感度</title><style>'
        + STYLE + css + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    (output / 'slides.json').write_text(json.dumps(slides, ensure_ascii=False, indent=2) + '\n')
    manifest = {'pages': 3, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': {name: sha(ROOT / name) for name in SOURCES}, 'builder_sha256': sha(Path(__file__)),
        'visual_reviewed': False, 'scope': 'One-field generation calibration, not task quality or a new method.'}
    (output / 'build_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, default=ROOT / 'materials/20261023_p58')
    p.add_argument('--pdf', action='store_true'); args = p.parse_args()
    print(json.dumps(build(args.output)))
    if args.pdf:
        build_budget_report.STEM = STEM; build_budget_report.export(args.output)
