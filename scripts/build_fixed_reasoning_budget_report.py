"""Show all eight P87 slots and structural completion only, after closure."""
import argparse
import csv
from datetime import datetime, timezone
import html
from itertools import combinations
from pathlib import Path

import build_budget_report
from build_clock_notice_report import table
from build_morning_report import STYLE, SCRIPT
from fixed_reasoning_budget_replay import CASES, equality_summary, schedule, validate_plan
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_fixed_reasoning_budget_20261024'
FILES = ('configs/P87_fixed_reasoning_budget_v01.json', 'reports/P87_initial_checks.json',
         'reports/P87_fixed_reasoning_budget_replay.json')
CODES = dict(zip(CASES, ('A-U', 'A-H', 'B-U', 'B-H')))
LABELS = ('途中切れ・上限なし', '途中切れ・半分', '操作なし・上限なし', '操作なし・半分')


def validated(root=ROOT):
    plan, pre, report = [read(root / name) for name in FILES]
    validate_plan(plan)
    if (pre['status'] not in ('complete', 'stopped') or report['audit_errors']
            or report['server']['status'] != 'stopped' or not report['owned_processes_absent']
            or report['preflight_sha256'] != sha(root / FILES[1])
            or report['source_sha256'] != pre['source_sha256']
            or report['source_request_sha256'] != {c['id']: c['source_request_sha256'] for c in plan['cases']}
            or report['auditor_sha256'] != sha(root / 'scripts/audit_fixed_reasoning_budget.py')
            or len(report['rows']) != 8
            or any({k: r[k] for k in item} != item for r, item in zip(report['rows'], schedule(), strict=True))
            or any(report[k] for k in ('environment_api_requests', 'generated_programs_executed',
                                       'evaluations', 'reserved_scenarios_read', 'task_quality_or_savings_measured'))):
        raise ValueError('closed_complete_planned_P87_table_required')
    for name, expected in pre['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('frozen_P87_source_changed:' + name)
    attempted = report['model_calls_attempted']
    if (not 0 <= attempted <= 8 or (pre['status'] != 'complete' and attempted)
            or any(r['record_status'] not in ('audited', 'unknown_usage', 'unknown_missing_terminal_record')
                   for r in report['rows'][:attempted])
            or any(r['record_status'] != 'unattempted' for r in report['rows'][attempted:])
            or equality_summary(report['rows'][:attempted]) != report['equality_summary']
            or sum(r.get('known_total_tokens', 0) for r in report['rows']) != report['known_total_tokens']
            or sum(r['record_status'].startswith('unknown_') for r in report['rows']) != report['unknown_usage_calls']
            or report['all_eight_audited'] != (attempted == 8 and all(
                r['record_status'] == 'audited' for r in report['rows']))):
        raise ValueError('P87_full_cohort_aggregation_mismatch')
    usable = report['all_eight_audited']
    effect = report['equality_summary']['both_contexts_local_completion_improved'] if usable else None
    if report['diagnostic_usable'] != usable or report['local_code_completion_improvement_identified'] != effect:
        raise ValueError('diagnostic_conclusion_exceeds_audit')
    return plan, pre, report, {name: sha(root / name) for name in FILES}


def outcome(report):
    if not report['diagnostic_usable']:
        return '全８生成の終端使用量と監査が揃わず、固定した改善条件を判定しない。'
    if report['local_code_completion_improvement_identified']:
        return '２保存文脈で、通常の予算指定によりコード提出の完成が０/２から２/２へ変わった。'
    return '両文脈で０/２から２/２へ改善するという固定した局所条件は満たさなかった。'


def completion_label(row):
    if row['record_status'] == 'unattempted': return '未実行'
    if row['record_status'].startswith('unknown_'): return '不明'
    for key,label in (('malformed_json_calls','JSON不正'),('shape_invalid_calls','引数不正'),
                      ('syntax_invalid_calls','構文不正'),('other_tool_calls','別ツール')):
        if row.get(key): return label
    if not row.get('tool_calls'): return '操作なし'
    if row['complete_code_submission']: return '完成'
    return '途中終了'


def build(output, root=ROOT):
    plan, pre, report, source_hashes = validated(root)
    output.mkdir(parents=True, exist_ok=False)
    rows, summary = report['rows'], report['equality_summary']
    fields = ('id','case','source_context','repetition','record_status','status','input_tokens',
        'output_tokens','known_total_tokens','done_reason','tool_calls','python_calls',
        'malformed_json_calls','shape_invalid_calls','syntax_invalid_calls','other_tool_calls',
        'complete_code_submission','wall_seconds','cached_input_tokens','processed_input_tokens',
        'public_output_sha256','opaque_message_sha256')
    with (output/'all_eight_generations.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader()
        for row in rows:
            writer.writerow({**row,'cached_input_tokens':row.get('cache',{}).get('cached_tokens'),
                'processed_input_tokens':row.get('cache',{}).get('processed_tokens')})
    write_json(output/'all_comparisons.json',summary)
    slides=[dict(title='普通の推論予算で<br>コード提出は完成するか',cover=True,body='',takeaway='',
        notes='P87。同じ既知CSV課題の２保存文脈を用いた通常対照の局所診断。新手法でも課題品質の評価でもない。')]
    def add(title,body,takeaway,notes):
        slides.append(dict(title=title,body=body,takeaway=takeaway,notes=notes))
    add('２保存文脈 × 通常２条件 × ２反復の８生成',
        table(('文脈','元入力token','元seed','推論ブロック上限'),[
            ('A：引数途中切れ',17696,69,'なし／2,048'),
            ('B：公開操作なし',31211,74,'なし／2,048')])+
        '<p class="body">全出力は4,096のまま。条件間の要求差は予算フィールドだけ。<br>全件でcacheを無効化し、各反復で条件順を逆にする。</p>',
        '対象は同じ既知CSV課題の１課題。元のwarm状態や課題全体を再現しない。',
        'P86を見た後に、元の時系列で最初の引数途中切れと最初の公開操作なしを選んだ。独立課題数は１。推論予算はブロック単位であり、終了タグや再開の可能性もあるため、残り半分を操作へ保証する仕組みではない。上限値・seedの探索はしない。')
    cells=[]
    for row in rows:
        cells.append((CODES[row['case']],row['repetition'],row['input_tokens'],row['output_tokens'],
            row.get('done_reason'),completion_label(row)))
    add('全８予定枠を欠測・未実行も含めて示す',
        table(('条件','反復','入力T','出力T','終端','コード提出'),cells),
        'Uは推論ブロック上限なし、Hは2,048。完成したコードも実行していない。',
        '上限途中終了ではなく、全呼出しがrun_pythonで、公開仕様のcode・span_idsと非空Python ASTを満たした場合だけ完成とする。理由欄はJSON、引数形状、Python構文、他ツールの順で表示し、全ての数はCSVへ残す。spanの実在、API前提、意図、実行効果は未検証。')
    groups=[]
    for case in CASES:
        g=summary['groups'][case]
        equal={True:'一致',False:'不一致',None:'不明'}[g['public_outputs_equal']]
        groups.append((CODES[case],f"{g['complete_code_submissions']}/{g['known']}",
            2-g['known'],g['known_output_tokens'],equal))
    add('構文の完成と課題達成を分けて判断する',
        table(('条件','完成／既知生成','不明・未実行','既知出力T','反復の公開出力'),groups)+
        '<p class="body">固定した条件：両文脈でUが完成０/２、Hが完成２/２。<br>全８使用量が既知で監査一致の場合だけ判定する。</p>',
        outcome(report),
        '完成率の分母は観測できた生成数であり、欠測や未実行を成功・失敗へ補完しない。反復は独立課題ではなく、比較を母集団の推定や品質保証へ広げない。公開出力の一致は機械的なhash比較であり、内部推論の意味内容は読んでいない。通常手法による局所の形式改善が得られても新規性・全仕事削減の証明ではない。')
    known=[r for r in rows if r['record_status']=='audited']
    resource=[('試行／計画',f"{report['model_calls_attempted']}/8"),
        ('既知の入力＋出力token',f"{report['known_total_tokens']:,}"),
        ('終端使用量不明',report['unknown_usage_calls']),('入力計数要求',pre['input_count_requests']),
        ('実処理／cache入力token',f"{sum(r['cache']['processed_tokens'] for r in known):,} / {sum(r['cache']['cached_tokens'] for r in known):,}"),
        ('推論器稼働 秒',f"{report['server']['wall_seconds']:,.3f}"),
        ('内・ロード／生成応答の合計 秒',f"{report['server']['load_wall_seconds']:,.3f} / {report['generation_wall_seconds']:,.3f}")]
    add('通常対照の診断費用を全て残す',table(('測定','値'),resource),
        '所有推論器は停止済み。コード実行・環境API・課題評価・未見課題読取は０。',
        '推論器稼働にはロード・計数・生成・待機を含み、部分時間と二重加算しない。既知小計は使用量不明の費用を含まない。ホストで軽量な編集・資料準備も行うため排他的な速度ベンチマークではない。全時間・メモリ・hashは監査JSONへ保存する。元課題の未達やP82/P84の採否を変更しない。')
    sections=[]
    for n,slide in enumerate(slides,1):
        if slide.get('cover'):
            sections.append(f'<section class="slide dark cover"><h1>{slide["title"]}</h1><div class="notes">{html.escape(slide["notes"])}</div></section>')
        else:
            sections.append(f'<section class="slide"><div class="eyebrow">10月24日 通常予算の局所診断 / {n:02d}</div><h2>{slide["title"]}</h2>{slide["body"]}'
                f'<div class="takeaway">{slide["takeaway"]}</div><div class="footer"><span>既知CSV課題・２保存文脈・全８予定生成／コード実行なし</span><span>{n}/{len(slides)}</span></div>'
                f'<div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav='<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css='h2{font-size:30px}.results th,.results td{font-size:18px;line-height:1.3;padding:5px 9px}.body{font-size:23px;line-height:1.5}'
    (output/'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P87 通常の推論予算</title><style>'+STYLE+css+'</style></head><body>'+''.join(sections)+nav+'<script>'+SCRIPT+'</script></body></html>')
    write_json(output/'slides.json',slides)
    manifest=dict(pages=len(slides),generated_at=datetime.now(timezone.utc).isoformat(),source_sha256=source_hashes,
        builder_sha256=sha(Path(__file__)),visual_reviewed=False,
        csv_sha256=sha(output/'all_eight_generations.csv'),comparisons_sha256=sha(output/'all_comparisons.json'),
        html_sha256=sha(output/'index.html'),slides_sha256=sha(output/'slides.json'),
        all_eight_audited=report['all_eight_audited'],diagnostic_usable=report['diagnostic_usable'],
        local_code_completion_improvement_identified=report['local_code_completion_improvement_identified'],
        known_total_tokens=report['known_total_tokens'],unknown_usage_calls=report['unknown_usage_calls'],
        novel_method_claim=False,task_quality_or_savings_measured=False,
        report_build_model_calls=0,report_build_environment_api_requests=0,report_build_evaluations=0)
    write_json(output/'build_manifest.json',manifest)
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'materials/20261024_p87_results')
    p.add_argument('--pdf',action='store_true');a=p.parse_args();result=build(a.output)
    print({k:result[k] for k in ('pages','all_eight_audited','known_total_tokens','unknown_usage_calls')})
    if a.pdf:
        build_budget_report.STEM=STEM;build_budget_report.export(a.output)


