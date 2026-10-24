"""Publish every closed P102 execution slot, pair denominator and incurred cost."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import html
from pathlib import Path

from audit_choice_action_execution import AUDIT, PLAN, REPORT, SOURCE, validate_closed
import build_budget_report
from build_choice_context_report import CODES, DESCRIPTIONS, write_csv
from build_clock_notice_report import table
from build_morning_report import STYLE, SCRIPT
from choice_context_replay import CASES, CHOICES, conditions, condition
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

STEM='AI_harness_choice_action_execution_20261024'
FILES=(PLAN,SOURCE,REPORT,AUDIT)


def label(key):
    case,choice=key.split('__');return CODES[case]+('/a' if choice=='auto' else '/r')


def value(x):return '—' if x is None else x


def validated(root=ROOT):
    plan,source,report,audit=[read(root/name) for name in FILES]
    validate_closed(plan,source,report)
    if (audit['status']!='complete' or audit['audit_errors'] or audit['checked_slots']!=36
            or audit['auditor_sha256']!=sha(root/'scripts/audit_choice_action_execution.py')
            or report['source_audit_sha256']!=sha(root/SOURCE)
            or report['plan_sha256']!=sha(root/PLAN)):
        raise ValueError('closed_all_slot_execution_record_audit_required')
    for name,expected in {**plan['source_sha256'],**audit['source_sha256']}.items():
        if sha(root/name)!=expected:raise ValueError('bound_reporting_source_changed:'+name)
    return plan,source,report,audit,{name:sha(root/name) for name in FILES}


def groups(report):
    result=[]
    for key in conditions():
        rows=[r for r in report['conditions'] if r['condition']==key]
        done=[r for r in rows if r['status']=='complete']
        result.append(dict(condition=key,planned_slots=3,source_available=sum(r['should_execute'] for r in rows),
            completed=len(done),source_unavailable=sum(r['status']=='source_unavailable' for r in rows),
            not_attempted=sum(r['status']=='not_attempted' for r in rows),
            stopped=sum(r['status'] in ('stopped','cleanup_or_accounting_failed') for r in rows),
            source_truncated=sum(r['source_complete_generation'] is False for r in rows),
            source_unknown=sum(r['source_record_status'].startswith('unknown_') for r in rows),
            source_unattempted=sum(r['source_record_status']=='unattempted' for r in rows),
            no_structured_submission=sum(r['structured_submissions']==0 for r in done),
            source_known_total_tokens=sum(r['source_known_total_tokens'] or 0 for r in rows),
            sent_API_requests=sum(r.get('typed_requests_started',0) for r in rows),
            recorded_prefix_API_requests=sum(r.get('prefix_api_requests',0) for r in rows),
            recorded_suffix_API_requests=sum(r.get('suffix_api_requests',0) for r in rows),
            saved_program_executions=sum(r.get('saved_program_executions',0) for r in rows),
            active_wall_seconds=sum(r.get('active_wall_seconds',0) for r in rows),
            cleanup_wall_seconds=sum(r.get('cleanup_wall_seconds',0) for r in rows),
            full_wall_seconds=sum(r.get('full_wall_seconds',0) for r in rows)))
    return result


def build(output,root=ROOT):
    plan,source,report,audit,hashes=validated(root);output.mkdir(parents=True,exist_ok=False)
    rows=report['conditions'];grouped=groups(report);comparison=report['execution_comparisons']
    flat=[]
    for row in rows:
        item={k:row.get(k) for k in ('id','case','tool_choice','condition','repetition','status',
            'source_record_status','source_complete_generation','source_static_submission',
            'source_known_total_tokens','public_prefix_matched','prefix_api_requests','suffix_api_requests',
            'typed_requests_started','structured_submissions','suffix_saved_programs','saved_program_executions',
            'suffix_request_sequence_sha256','suffix_execution_evidence_sha256',
            'active_wall_seconds','cleanup_wall_seconds','full_wall_seconds')}
        item['format_rejections']=sum(r['format_error_present'] for r in row.get('suffix_public_results',[]))
        item['Python_execution_errors']=sum(r.get('status')=='execution_error' for r in row.get('suffix_public_results',[]))
        flat.append(item)
    write_csv(output/'all_36_execution_slots.csv',flat)
    write_csv(output/'all_12_groups.csv',grouped)
    write_csv(output/'all_12_within_group_comparisons.csv',comparison['within'])
    write_csv(output/'all_66_cross_group_comparisons.csv',comparison['cross'])
    write_json(output/'all_execution_comparisons.json',comparison)
    costs=dict(P101_generation_attempts=source['model_calls_attempted'],
        P101_known_total_tokens=source['known_total_tokens'],P101_unknown_usage_calls=source['unknown_usage_calls'],
        P101_unattempted_slots=36-source['model_calls_attempted'],
        P102_environment_API_requests=report['environment_api_requests'],
        P102_saved_program_executions=report['saved_program_executions'],
        P102_wall_seconds=report['wall_seconds'],P102_record_audit_wall_seconds=audit['wall_seconds'],
        condition_active_wall_seconds=sum(g['active_wall_seconds'] for g in grouped),
        condition_cleanup_wall_seconds=sum(g['cleanup_wall_seconds'] for g in grouped),
        condition_full_wall_seconds=sum(g['full_wall_seconds'] for g in grouped),
        recorded_prefix_API_requests=sum(g['recorded_prefix_API_requests'] for g in grouped),
        recorded_suffix_API_requests=sum(g['recorded_suffix_API_requests'] for g in grouped),
        complete_task_cost_or_quality_comparison=False,overlapping_times_must_not_be_added=True)
    costs['API_requests_without_completed_prefix_or_suffix_partition']=(report['environment_api_requests']
        -costs['recorded_prefix_API_requests']-costs['recorded_suffix_API_requests'])
    write_json(output/'recorded_costs.json',costs)
    slides=[]
    def add(title,body,takeaway,notes):slides.append(dict(title=title,body=body,takeaway=takeaway,notes=notes))
    add('保存出力を実行し、提出形式と操作を分ける',
        table(('入力','保存文脈'),[(CODES[c],DESCRIPTIONS[i]) for i,c in enumerate(CASES)])+
        '<p class="body">各入力のauto / required × ３反復。全36枠を固定順序で確認。</p>',
        '追加生成０。既知の本文のみ・形式不整合・途中切れも選別せず通常実行口へ渡す。',
        'P101が閉鎖して所有推論器が終了した後だけ実行。既知CSVの保存１文脈。各既知出力に新しい環境を用い、先行12コード・28 APIの要求と公開応答を照合。元の全DB・乱数・Python状態を復元したとは扱わない。')
    statuses={'complete':'確認完了','source_unavailable':'元出力なし','not_attempted':'未実行',
              'stopped':'途中停止','cleanup_or_accounting_failed':'会計等の不整合'}
    panels=[]
    for rep in (1,2,3):
        data=[(label(r['condition']),statuses[r['status']],value(r.get('suffix_saved_programs')),
               value(r.get('suffix_api_requests'))) for r in rows if r['repetition']==rep]
        panels.append(f'<div><h3>反復{rep}</h3>'+table(('入力','記録','Python','API'),data)+'</div>')
    add('全36枠の実行記録を残す','<div class="three">'+''.join(panels)+'</div>',
        '「確認完了」は記録処理の完了。Pythonの正常終了や課題成功の意味ではない。',
        'Python・APIは保存出力からの後続部分だけ。先行再構成の費用は別表へ含める。—は値がない状態で０への代入ではない。途中停止以後の枠も残し、生成・実行を補充しない。a=auto、r=required。')
    panels=[]
    for choice in CHOICES:
        data=[]
        for g in grouped:
            if not g['condition'].endswith('__'+choice):continue
            selected=[r for r in flat if r['condition']==g['condition']]
            data.append((label(g['condition']),g['completed'],g['source_truncated'],
                sum(r['format_rejections'] for r in selected),sum(r['Python_execution_errors'] for r in selected),
                g['recorded_suffix_API_requests']))
        panels.append('<div><h3>'+choice+'</h3>'+table(('入力','完了','切れ','形式拒否','例外','API'),data)+'</div>')
    add('形式拒否・実行例外・送信APIを区別する','<div class="two">'+''.join(panels)+'</div>',
        '形式が整っていても処理結果は保証されず、既知の実行例外も実行記録へ残る。',
        '完了は各条件３枠中の確認完了。切れは元生成の途中切れ。形式拒否とPython例外は公開返却記録の件数で、独立した試行数ではない。APIは後続部分の送信試行の合計。未知作用では後続を止める。')
    lookup={frozenset((p['left'],p['right'])):p for p in comparison['cross']}
    contrasts=[]
    for choice in CHOICES:
        for a,b in ((CASES[0],CASES[1]),(CASES[2],CASES[3]),(CASES[0],CASES[4])):
            contrasts.append(lookup[frozenset((condition(a,choice),condition(b,choice)))])
    contrasts += [lookup[frozenset(condition(c,x) for x in CHOICES)] for c in CASES]
    def pair_table(pairs):
        return table(('条件対','API一致/非空対','実行一致/Python対','双方空','不可'),[
            (label(p['left'])+' '+label(p['right']),
             f"{p['nonempty_API_request_sequences_equal']}/{p['both_nonempty_API_sequences']}",
             f"{p['Python_execution_evidence_equal']}/{p['both_submitted_Python_executed']}",
             p['both_empty_API_sequences'],p['unavailable_pairs']) for p in pairs])
    add('事前に決めた対照の実際の操作を比較する',pair_table(contrasts),
        '空のAPI列同士は非空操作の一致に含めない。Pythonだけ動いた対も別の分母。',
        'A/B、C/D、A/Nの設定内対照と、全６入力の設定間対照。各条件対には３×３=９対があるが、独立９標本ではない。実行一致は保存された後続実行証拠の完全hash一致で、要求の正しさ・課題成功を意味しない。')
    for block in range(3):
        pairs=comparison['cross'][block*22:(block+1)*22]
        add(f'全66条件組を省略しない（{block+1}/3）',
            '<div class="two"><div>'+pair_table(pairs[:11])+'</div><div>'+pair_table(pairs[11:])+'</div></div>',
            '全66組・594対。条件内の12組・36対もCSVとJSONに保存。',
            '条件の選び直し、欠測補完、都合のよい対だけの採用をしない。双方空の列は独立表示し、片方だけ空の件数と途中切れを含む対数もCSVへ保存。API一致とPython実行証拠一致は、それぞれの比較可能分母で読む。')
    api_partition=costs['API_requests_without_completed_prefix_or_suffix_partition']
    add('再構成・失敗・後片付けの費用も含める',
        table(('区分','今回の記録'),[
            ('元生成の既知費用 / 不明試行',f"{source['known_total_tokens']:,} token / {source['unknown_usage_calls']}"),
            ('P102全API試行 / Python実行',f"{report['environment_api_requests']} / {report['saved_program_executions']}"),
            ('API：先行 / 後続 / 区分未確定',f"{costs['recorded_prefix_API_requests']} / {costs['recorded_suffix_API_requests']} / {api_partition}"),
            ('P102全体 / 記録監査',f"{report['wall_seconds']:.3f} 秒 / {audit['wall_seconds']:.3f} 秒"),
            ('各条件の処理 / 後片付け合計',f"{costs['condition_active_wall_seconds']:.3f} 秒 / {costs['condition_cleanup_wall_seconds']:.3f} 秒")]),
        '必要な最終成果の維持と、仕事全体の費用削減は、この１文脈の実行比較では未測定。',
        '１条件最大80 APIは先行28 APIを含む。全体最大2,880 API・1,800秒。追加モデル・評価器・予約評価群の参照は０。P101生成費用とP102費用は分け、重なる時間を足さない。これは新手法・一般品質・採択の証明ではない。')
    sections=[]
    for n,s in enumerate(slides,1):
        sections.append(f'<section class="slide"><div class="eyebrow">P102 保存出力の実行確認 / {n:02d}</div><h2>{s["title"]}</h2>{s["body"]}<div class="takeaway">{s["takeaway"]}</div><div class="footer"><span>保存１文脈・全36枠／追加モデル・課題評価０</span><span>{n}/{len(slides)}</span></div><div class="notes">{html.escape(s["notes"])}</div></section>')
    css='h2{font-size:30px}h3{font-size:19px;margin:6px 0}.results th,.results td{font-size:17px;line-height:1.15;padding:4px 7px}.body{font-size:20px;line-height:1.3}.two,.three{display:grid;gap:16px}.two{grid-template-columns:1fr 1fr}.three{grid-template-columns:1fr 1fr 1fr}.two>div,.three>div{min-width:0}.two .results,.three .results{table-layout:fixed;width:100%}.two .results th,.two .results td{font-size:14px;padding:3px 3px}.three .results th,.three .results td{font-size:15px;padding:2px 3px}.takeaway{font-size:22px}'
    nav='<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    (output/'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P102 保存出力の実行確認</title><style>'+STYLE+css+'</style></head><body>'+''.join(sections)+nav+'<script>'+SCRIPT+'</script></body></html>')
    write_json(output/'slides.json',slides)
    manifest=dict(pages=len(slides),generated_at=datetime.now(timezone.utc).isoformat(),source_sha256=hashes,
        builder_sha256=sha(Path(__file__)),visual_reviewed=False,all_planned_slots=36,all_cross_groups=66,
        completed_conditions=report['completed_conditions'],recorded_costs=costs,
        public_artifact_sha256={p.name:sha(p) for p in sorted(output.iterdir()) if p.is_file()},
        task_quality_measured=False,novel_method_claim=False,report_build_model_calls=0,
        report_build_environment_API_requests=0,report_build_evaluations=0)
    write_json(output/'build_manifest.json',manifest);return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'materials/20261024_p102_results')
    parser.add_argument('--pdf',action='store_true');args=parser.parse_args()
    result=build(args.output);print({k:result[k] for k in ('pages','all_planned_slots','completed_conditions')})
    if args.pdf:
        build_budget_report.STEM=STEM;build_budget_report.export(args.output)
