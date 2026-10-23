"""Render all twelve audited P79 generation slots, without exposing model text."""
import argparse
import csv
from datetime import datetime, timezone
import html
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from clock_notice_replay import LEVELS, equality_summary, schedule
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_clock_notice_replay_20261023'
FILES = ('configs/P79_clock_notice_replay_v01.json', 'reports/P79_initial_checks.json',
         'reports/P79_clock_notice_replay.json')
TASKS = ('返金', '曲情報の書出し')


def validated():
    plan, pre, report = [read(ROOT / p) for p in FILES]
    if (pre['status'] != 'complete' or pre['git_commit'] != '1365919664d33fe6b883232151f6e36043ada5d5'
            or report['audit_errors'] or report['server']['status'] != 'stopped'
            or not report['owned_processes_absent'] or report['preflight_sha256'] != sha(ROOT / FILES[1])
            or report['source_sha256'] != pre['source_sha256']
            or len(report['rows']) != 12
            or any({k: r[k] for k in s} != s for r, s in zip(report['rows'], schedule(), strict=True))
            or any(report[k] for k in ('environment_api_requests', 'generated_programs_executed',
                                       'evaluations', 'reserved_scenarios_read', 'task_quality_or_savings_measured'))):
        raise ValueError('closed_all_slot_P79_audit_required')
    for p, expected in pre['source_sha256'].items():
        if sha(ROOT / p) != expected: raise ValueError('frozen_P79_source_changed:' + p)
    n = report['model_calls_attempted']
    if (equality_summary(report['rows'][:n]) != report['equality_summary']
            or sum(r.get('known_total_tokens', 0) for r in report['rows']) != report['known_total_tokens']):
        raise ValueError('P79_aggregation_mismatch')
    return plan, pre, report, {p: sha(ROOT / p) for p in FILES}


def display(value):
    return '—' if value is None else f'{value:,}' if type(value) is int else str(value)


def table(headers, rows):
    return '<table class="results"><tr>' + ''.join('<th>' + html.escape(str(h)) + '</th>' for h in headers) + '</tr>' + ''.join(
        '<tr>' + ''.join('<td>' + html.escape(display(v)) + '</td>' for v in row) + '</tr>' for row in rows) + '</table>'


def build(output):
    plan, pre, report, source_hashes = validated()
    output.mkdir(parents=True, exist_ok=True)
    rows = report['rows']
    fields = ('id', 'task_id', 'case_index', 'level', 'replicate', 'record_status', 'status', 'input_tokens',
        'output_tokens', 'known_total_tokens', 'done_reason', 'has_public_output', 'complete_generation',
        'wall_seconds', 'cached_input_tokens', 'processed_input_tokens', 'public_output_sha256', 'opaque_message_sha256')
    with (output / 'all_twelve_generations.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore'); writer.writeheader()
        for row in rows:
            writer.writerow({**row, 'cached_input_tokens': row.get('cache', {}).get('cached_tokens'),
                             'processed_input_tokens': row.get('cache', {}).get('processed_tokens')})
    summary = report['equality_summary']
    write_json(output / 'all_output_comparisons.json', summary)
    slides = [{'title': '残時間通知と<br>生成の再現性', 'cover': True, 'body': '', 'takeaway': '',
               'notes': 'P79。既知２入力の有限診断。表紙は題名のみ。'}]
    def add(title, body, takeaway, notes):
        slides.append({'title': title, 'body': body, 'takeaway': takeaway, 'notes': notes})
    methods = [(TASKS[i], c['source_call'], c['original_wall_seconds'], c['original_wall_seconds'] + 1,
                c['expected_input_tokens']) for i, c in enumerate(plan['cases'])]
    add('同じ入力の反復と、通知１秒差を分ける',
        table(('既知入力', '元の生成', '元の通知 秒', '＋１秒', '入力token'), methods) +
        '<p class="body">各通知３回、計12生成。履歴・通信ID・ツール・seed56・最大4096出力を共通化。</p>'
        '<p class="body">全要求で入力再利用を無効にし、実測cache_n=0を確認する。</p>',
        '元P78のタスクや推論状態を再現せず、保存入力に対する単発生成を診断する。',
        'P78の全４対から、実API例外前の最初の内容差が残時間だけだった全２対を選んだ。元の継続はキャッシュあり。保存された通知は実時間ではなく固定した刺激である。')
    rendered = []
    for i, r in enumerate(rows, 1):
        label = {'audited': {'tool_calls': 'ツール生成', 'stop': '停止', 'length': '上限'}.get(r.get('done_reason'), '不明'),
                 'unattempted': '未実行', 'unknown_usage': '使用量不明', 'unknown_missing_terminal_record': '記録不明'}.get(r['record_status'], r['record_status'])
        rendered.append((i, ('返金', '書出し')[r['case_index']], '元' if r['level'] == 'original' else '＋１',
            r['replicate'], r['input_tokens'], r['output_tokens'], label,
            f'{r["wall_seconds"]:.3f}' if r.get('wall_seconds') is not None else None))
    add('固定した全12生成を、そのまま残す',
        table(('順', '入力', '通知', '反復', '入力token', '出力token', '終了', '生成 秒'), rendered),
        '未実行や不明使用量を補充しない。生成したプログラムは実行しない。',
        '入力は全履歴を含む論理tokenで、内部推論も出力tokenへ計上する。生成時間には推論器全体のロードや待機は含まれない。生成した内容や認証値は公開せず、ハッシュだけ保存する。')
    within, cross = [], []
    for item in summary:
        for level in LEVELS:
            s = item['within'][level]
            verdict = {True: '一致', False: '異なる', None: '未確定'}[s['all_three_public_outputs_equal']]
            within.append((TASKS[item['case_index']], '元' if level == 'original' else '＋１',
                f'{s["known"]}/{s["attempted"]}', f'{s["equal_public_pairs"]}/{s["compared_pairs"]}',
                f'{s["equal_opaque_pairs"]}/{s["compared_pairs"]}', verdict))
        s = item['cross']
        cross.append((TASKS[item['case_index']], f'{s["equal_public_pairs"]}/{s["compared_pairs"]}',
                      f'{s["equal_opaque_pairs"]}/{s["compared_pairs"]}'))
    add('同一通知の３反復を、条件間の差より先に確認する',
        table(('入力', '通知', '既知／試行', '公開出力一致／組', '全メッセージ一致／組', '３回判定'), within) +
        '<p class="body">公開出力は文・関数名・引数・終了理由をそのまま照合。生成された通信IDだけを除く。</p>',
        '打切りや空の公開出力、未完了の群を、同じ行動の再現とは判定しない。',
        '全メッセージには推論フィールドも含めるが、内容を解釈せずハッシュで比較する。同じ入力からの組合せは独立標本ではない。未知の結果を一致に置き換えない。')
    conclusions = []
    for item in summary:
        same = [item['within'][level]['all_three_public_outputs_equal'] for level in LEVELS]
        equal, compared = item['cross']['equal_public_pairs'], item['cross']['compared_pairs']
        if None in same: text = '未完了・打切り等があり、通知差の解釈を確定しない。'
        elif not all(same): text = '同じ通知でも出力が異なり、１秒差だけで説明しない。'
        elif compared == 9 and equal == 0: text = '同一通知内は一致し、２通知の公開出力は全９組で異なった。'
        elif compared == 9 and equal == 9: text = '今回の再利用なし条件では、２通知の公開出力は全９組で一致した。'
        else: text = '条件内と条件間の組合せを併記し、単純な通知効果にまとめない。'
        conclusions.append('<p class="body"><strong>' + TASKS[item['case_index']] + '</strong>：' + text + '</p>')
    add('１秒差の全９組を、入力ごとに読む',
        table(('入力', '公開出力一致／組', '全メッセージ一致／組'), cross) + ''.join(conclusions),
        'この固定入力の感度と、元タスクの成功・費用への効果は別である。',
        '一方の通知の３回と他方の３回の総当たり９組。独立９標本やp値にはしない。キャッシュありのP78、将来の入力、課題品質への一般化は行わない。')
    known = [r for r in rows if r['record_status'] == 'audited']
    total = f'{report["known_total_tokens"]:,}' + (f'＋不明{report["unknown_usage_calls"]}生成' if report['unknown_usage_calls'] else '')
    resources = [('試行／計画', f'{report["model_calls_attempted"]}/12'), ('論理入力＋出力token', total),
        ('実処理入力token', sum(r['cache']['processed_tokens'] for r in known)),
        ('キャッシュ入力token', sum(r['cache']['cached_tokens'] for r in known)),
        ('全推論器稼働 秒', f'{report["server"]["wall_seconds"]:,.3f}'),
        ('ロード 秒', f'{report["server"]["load_wall_seconds"]:.3f}'),
        ('生成時間合計 秒', f'{report["generation_wall_seconds"]:,.3f}')]
    add('診断自身の費用を記録し、所有推論器を終了する',
        table(('測定', '値'), resources) + '<p class="body">入力計数４回。環境API・生成コード実行・評価器・保留群は０。</p>',
        '全結果の監査と所有プロセスの不在を確認。新手法や全仕事費用の削減は未実証。',
        '全推論器時間はロード・計数・生成・待機を含むため、各部分と足し合わせない。不明使用量は既知分へ補完しない。この診断結果は次の比較の入力条件へ戻し、元P78の成否と採否を変更しない。')
    sections = []
    for number, slide in enumerate(slides, 1):
        if slide.get('cover'):
            sections.append(f'<section class="slide dark cover"><h1>{slide["title"]}</h1><div class="notes">{html.escape(slide["notes"])}</div></section>')
        else:
            sections.append(f'<section class="slide"><div class="eyebrow">10月23日 残時間通知の診断 / {number:02d}</div>'
                f'<h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div>'
                f'<div class="footer"><span>既知２入力・固定12生成／タスク実行なし</span><span>{number}/{len(slides)}</span></div>'
                f'<div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css = 'h2{font-size:30px}table{font-size:18px}.results th,.results td{font-size:17px;line-height:1.3;padding:4px 10px}.body{font-size:23px;line-height:1.5}'
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P79 残時間通知と生成の再現性</title><style>' +
        STYLE + css + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    write_json(output / 'slides.json', slides)
    manifest = {'pages': len(slides), 'generated_at': datetime.now(timezone.utc).isoformat(),
        'builder_sha256': sha(Path(__file__)), 'source_sha256': source_hashes,
        'visual_reviewed': False, 'csv_sha256': sha(output / 'all_twelve_generations.csv'),
        'comparisons_sha256': sha(output / 'all_output_comparisons.json'),
        'all_twelve_audited': report['all_twelve_audited'], 'novel_method_claim': False,
        'task_quality_or_savings_measured': False, 'known_total_tokens': report['known_total_tokens'],
        'unknown_usage_calls': report['unknown_usage_calls'], 'report_build_model_calls': 0,
        'report_build_environment_api_requests': 0, 'report_build_evaluations': 0}
    write_json(output / 'build_manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, default=ROOT / 'materials/20261023_p79')
    p.add_argument('--pdf', action='store_true'); a = p.parse_args(); result = build(a.output)
    print({k: result[k] for k in ('pages', 'all_twelve_audited', 'known_total_tokens', 'unknown_usage_calls')})
    if a.pdf:
        build_budget_report.STEM = STEM; build_budget_report.export(a.output)
