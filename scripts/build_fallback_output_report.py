"""Show all eighteen P84 slots and all fifteen case contrasts after closure."""
import argparse
import csv
from datetime import datetime, timezone
import html
from itertools import combinations
from pathlib import Path

import build_budget_report
from build_clock_notice_report import table
from build_morning_report import STYLE, SCRIPT
from fallback_output_replay import CASES, equality_summary, schedule, validate_plan
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_fallback_output_20261024'
FILES = ('configs/P84_fallback_output_v01.json', 'reports/P84_initial_checks.json',
         'reports/P84_fallback_output_replay.json')
CODES = dict(zip(CASES, ('A', 'B', 'C', 'D', 'N', 'X')))
LABELS = ('P80元入力', '第２反復元入力', 'P80表示前統一', '第２反復表示前統一',
          'native参照変更', '内容変更対照')


def validated(root=ROOT):
    plan, pre, report = [read(root / name) for name in FILES]
    validate_plan(plan)
    if (pre['status'] not in ('complete', 'stopped') or report['audit_errors']
            or report['server']['status'] != 'stopped' or not report['owned_processes_absent']
            or report['preflight_sha256'] != sha(root / FILES[1])
            or report['source_sha256'] != pre['source_sha256']
            or report['source_request_sha256'] != {c['id']: c['source_request_sha256'] for c in plan['cases']}
            or report['auditor_sha256'] != sha(root / 'scripts/audit_fallback_output.py')
            or len(report['rows']) != 18
            or any({k: r[k] for k in item} != item for r, item in zip(report['rows'], schedule(), strict=True))
            or any(report[k] for k in ('environment_api_requests', 'generated_programs_executed',
                                       'evaluations', 'reserved_scenarios_read', 'task_quality_or_savings_measured'))):
        raise ValueError('closed_complete_planned_P84_table_required')
    for name, expected in pre['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('frozen_P84_source_changed:' + name)
    attempted = report['model_calls_attempted']
    if (not 0 <= attempted <= 18 or (pre['status'] != 'complete' and attempted)
            or any(r['record_status'] not in ('audited', 'unknown_usage', 'unknown_missing_terminal_record')
                   for r in report['rows'][:attempted])
            or any(r['record_status'] != 'unattempted' for r in report['rows'][attempted:])
            or equality_summary(report['rows'][:attempted]) != report['equality_summary']
            or sum(r.get('known_total_tokens', 0) for r in report['rows']) != report['known_total_tokens']
            or sum(r['record_status'].startswith('unknown_') for r in report['rows']) != report['unknown_usage_calls']
            or report['all_eighteen_audited'] != (attempted == 18 and all(
                r['record_status'] == 'audited' for r in report['rows']))):
        raise ValueError('P84_full_cohort_aggregation_mismatch')
    usable = report['all_eighteen_audited'] and report['equality_summary']['stable_complete_public_outputs_and_equivalent_input_controls'] is True
    effect = report['equality_summary']['original_fallback_ID_pair_public_outputs_differ'] if usable else None
    if report['diagnostic_usable'] != usable or report['local_public_output_difference_identified'] != effect:
        raise ValueError('diagnostic_conclusion_exceeds_audit')
    return plan, pre, report, {name: sha(root / name) for name in FILES}


def comparison_matrix(summary, field):
    cross = {(p['left'], p['right']): p for p in summary['cross']}
    if set(cross) != set(combinations(CASES, 2)):
        raise ValueError('all_fifteen_contrasts_required')
    matrix = []
    for i, left in enumerate(CASES):
        cells = [CODES[left]]
        for j, right in enumerate(CASES):
            if i > j:
                cells.append('')
            else:
                pair = summary['within'][left] if i == j else cross[left, right]
                cells.append(f"{pair[field]}/{pair['compared_pairs']}")
        matrix.append(cells)
    return table(('入力', *CODES.values()), matrix)


def outcome(report):
    if not report['diagnostic_usable']:
        return '完全な反復と同値入力の対照がそろわず、ID差だけの効果として結論しない。'
    if report['local_public_output_difference_identified']:
        return 'この保存文脈では元のID一対で公開出力が異なり、同値入力の対照は一致した。'
    return 'この保存文脈では、元のID一対に対する公開出力も一致した。'


def build(output, root=ROOT):
    plan, pre, report, source_hashes = validated(root)
    output.mkdir(parents=True, exist_ok=True)
    rows, summary = report['rows'], report['equality_summary']
    fields = ('id', 'case', 'repetition', 'record_status', 'status', 'input_tokens', 'output_tokens',
        'known_total_tokens', 'done_reason', 'has_public_output', 'complete_generation', 'wall_seconds',
        'cached_input_tokens', 'processed_input_tokens', 'public_output_sha256', 'opaque_message_sha256')
    with (output / 'all_eighteen_generations.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore'); writer.writeheader()
        for row in rows:
            writer.writerow({**row, 'cached_input_tokens': row.get('cache', {}).get('cached_tokens'),
                             'processed_input_tokens': row.get('cache', {}).get('processed_tokens')})
    write_json(output / 'all_output_comparisons.json', summary)
    slides = [dict(title='参照IDの表現差と<br>次のモデル出力', cover=True, body='', takeaway='',
                   notes='P84。既知CSV課題の事後選定した保存文脈の診断。課題の実行・品質評価は行わない。')]
    def add(title, body, takeaway, notes):
        slides.append(dict(title=title, body=body, takeaway=takeaway, notes=notes))
    methods = [(CODES[c['id']], LABELS[i], c['expected_input_tokens']) for i, c in enumerate(plan['cases'])]
    add('保存した６入力を各３回、生成だけ比較する',
        table(('記号', '保存入力と対照', '入力token'), methods) +
        '<p class="body">全18予定生成。seed 70、出力上限4,096、全要求で入力cacheを無効化。</p>',
        'P83の入力列の観測を次の出力まで調べる。元のwarm状態や課題全体を再現しない。',
        '元の一対はP80/P81の既知課題を見た後に選ばれた。６入力は６独立課題ではない。元要求のcache_promptだけを全条件でFalseにする。P82とは別の有限な所有推論器で実行する。')
    panels = []
    for repetition in (1, 2, 3):
        cells = []
        for row in rows:
            if row['repetition'] != repetition:
                continue
            status = {'audited': {'stop': '完了', 'tool_calls': '呼出し', 'length': '途中切れ'}.get(row.get('done_reason'), '不明'),
                      'unattempted': '未実行', 'unknown_usage': '使用量不明',
                      'unknown_missing_terminal_record': '記録不明'}.get(row['record_status'], row['record_status'])
            cells.append((CODES[row['case']], row['input_tokens'], row['output_tokens'], status))
        panels.append(f'<div><h3>反復{repetition}</h3>' + table(('入力', '入力T', '出力T', '終端'), cells) + '</div>')
    add('全18枠を、失敗・途中切れ・未実行も含めて示す',
        '<div class="three">' + ''.join(panels) + '</div>',
        '使用量不明を０に置換しない。上限で切れた応答も費用へ含める。',
        '各表はその反復の固定実行順。A/B/C/D/N/Xは前頁の入力。呼出しはモデルが呼出しを生成した意味であり、実際のプログラムやAPIは実行していない。完全・非空の公開出力が３回そろう条件は次頁と最終判定で別に確認する。')
    add('入力内の全３対と、入力間の全15組を照合する',
        '<div class="two"><div><h3>公開内容・関数・引数の一致</h3>' + comparison_matrix(summary, 'equal_public_pairs') +
        '</div><div><h3>全messageのhash一致</h3>' + comparison_matrix(summary, 'equal_opaque_pairs') + '</div></div>' +
        '<p class="body">一致数／使用量が既知の比較可能対数。対角は同入力内、上三角は入力間。</p>',
        outcome(report),
        '下三角は重複なので空欄。入力内は最大３対、入力間は最大９対で、共有する反復から作るため独立標本ではない。途中切れや空出力のhash一致も生の照合数には残し、完全・非空の３反復と同値入力対照が成立しなければ局所効果を結論しない。推論の意味内容は読まない。')
    known = [r for r in rows if r['record_status'] == 'audited']
    total = f'{report["known_total_tokens"]:,}' + (f'＋不明{report["unknown_usage_calls"]}生成' if report['unknown_usage_calls'] else '')
    resource_rows = [
        ('試行／計画', f'{report["model_calls_attempted"]}/18'), ('論理入力＋出力token', total),
        ('入力計数要求', pre['input_count_requests']),
        ('既知生成の実処理／cache入力token', f'{sum(r["cache"]["processed_tokens"] for r in known):,} / {sum(r["cache"]["cached_tokens"] for r in known):,}'),
        ('全推論器稼働 秒', f'{report["server"]["wall_seconds"]:,.3f}'),
        ('内・ロード 秒', f'{report["server"]["load_wall_seconds"]:,.3f}'),
        ('保存済み生成応答時間の合計 秒', f'{report["generation_wall_seconds"]:,.3f}')]
    add('診断の全費用を残し、元の課題結果へ広げない',
        table(('測定', '値'), resource_rows) +
        '<p class="body">環境API、生成コード実行、課題評価、保留課題の閲覧は０。</p>',
        '所有推論器は停止済み。局所診断であり、新規手法・課題成功・全仕事削減の証明ではない。',
        '推論器滞在にはロード・計数・生成・待機が含まれ、部分時間と二重加算しない。未知費用を既知分へ補完しない。cache内訳は使用量が既知の生成だけ、応答時間は保存済み記録だけの合計。ホストで軽量編集や集計も行うため負荷を排他的に固定した比較ではない。元のP80/P81の未達と欠測、P82の採用基準を変更しない。')
    sections = []
    for n, slide in enumerate(slides, 1):
        if slide.get('cover'):
            sections.append(f'<section class="slide dark cover"><h1>{slide["title"]}</h1><div class="notes">{html.escape(slide["notes"])}</div></section>')
        else:
            sections.append(f'<section class="slide"><div class="eyebrow">10月24日 保存入力の診断 / {n:02d}</div><h2>{slide["title"]}</h2>{slide["body"]}'
                f'<div class="takeaway">{slide["takeaway"]}</div><div class="footer"><span>既知CSV保存文脈・全18予定生成／課題実行なし</span><span>{n}/{len(slides)}</span></div>'
                f'<div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav = '<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css = 'h2{font-size:30px}h3{font-size:22px}.results th,.results td{font-size:17px;line-height:1.3;padding:4px 9px}.body{font-size:22px;line-height:1.45}.two,.three{display:grid;gap:20px}.two{grid-template-columns:1fr 1fr}.three{grid-template-columns:1fr 1fr 1fr}.two>div,.three>div{min-width:0}.two .results,.three .results{table-layout:fixed;width:100%}.two .results th,.two .results td{padding:4px 5px}.three .results th,.three .results td{font-size:16px;padding:5px 5px}'
    (output / 'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P84 参照IDと次の生成</title><style>' + STYLE + css + '</style></head><body>' + ''.join(sections) + nav + '<script>' + SCRIPT + '</script></body></html>')
    write_json(output / 'slides.json', slides)
    manifest = dict(pages=len(slides), generated_at=datetime.now(timezone.utc).isoformat(),
        source_sha256=source_hashes, builder_sha256=sha(Path(__file__)), visual_reviewed=False,
        csv_sha256=sha(output / 'all_eighteen_generations.csv'), comparisons_sha256=sha(output / 'all_output_comparisons.json'),
        html_sha256=sha(output / 'index.html'), slides_sha256=sha(output / 'slides.json'),
        all_eighteen_audited=report['all_eighteen_audited'], diagnostic_usable=report['diagnostic_usable'],
        local_public_output_difference_identified=report['local_public_output_difference_identified'],
        known_total_tokens=report['known_total_tokens'], unknown_usage_calls=report['unknown_usage_calls'],
        novel_method_claim=False, task_quality_or_savings_measured=False,
        report_build_model_calls=0, report_build_environment_api_requests=0, report_build_evaluations=0)
    write_json(output / 'build_manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'materials/20261024_p84_results')
    parser.add_argument('--pdf', action='store_true')
    args = parser.parse_args(); result = build(args.output)
    print({k: result[k] for k in ('pages', 'all_eighteen_audited', 'known_total_tokens', 'unknown_usage_calls')})
    if args.pdf:
        build_budget_report.STEM = STEM
        build_budget_report.export(args.output)
