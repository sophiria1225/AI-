"""Report all 36 P101 slots and 66 condition pairs after owned-server closure."""
import argparse
import csv
from datetime import datetime, timezone
import html
from pathlib import Path

import build_budget_report
from build_clock_notice_report import table
from build_morning_report import STYLE, SCRIPT
from choice_context_replay import (CASES, CHOICES, condition, conditions,
                                  equality_summary, input_comparisons, schedule, validate_plan)
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

STEM='AI_harness_choice_context_20261024'
FILES=('configs/P101_choice_context_v01.json','reports/P101_initial_checks.json',
       'reports/P101_choice_context.json')
CODES=dict(zip(CASES,('A','B','C','D','N','X')))
DESCRIPTIONS=('P80元入力','別反復の元入力','Aを表示前に統一','Bを表示前に統一',
              '構造上の参照だけ変更','診断文を加えた対照')


def validated(root=ROOT):
    plan,pre,report=[read(root/name) for name in FILES];validate_plan(plan)
    if (pre['status']!='complete' or report['audit_errors']
            or report['server']['status']!='stopped' or not report['owned_processes_absent']
            or report['preflight_sha256']!=sha(root/FILES[1])
            or report['source_sha256']!=pre['source_sha256']
            or report['source_request_sha256']!={c['id']:c['source_request_sha256'] for c in plan['cases']}
            or report['auditor_sha256']!=sha(root/'scripts/audit_choice_context.py')
            or len(report['rows'])!=36
            or any({k:row[k] for k in item}!=item for row,item in zip(report['rows'],schedule(),strict=True))
            or any(report[k] for k in ('environment_api_requests','generated_programs_executed',
                                      'evaluations','reserved_scenarios_read','task_quality_or_savings_measured'))):
        raise ValueError('closed_all_planned_P101_slots_required')
    for name,expected in pre['source_sha256'].items():
        if sha(root/name)!=expected:raise ValueError('frozen_P101_source_changed:'+name)
    attempted=report['model_calls_attempted'];rows=report['rows']
    if (type(attempted) is not int or not 0<=attempted<=36
            or any(r['record_status'] not in ('audited','unknown_usage','unknown_missing_terminal_record')
                   for r in rows[:attempted])
            or any(r['record_status']!='unattempted' for r in rows[attempted:])
            or equality_summary(rows[:attempted])!=report['equality_summary']
            or sum(r.get('known_total_tokens',0) for r in rows)!=report['known_total_tokens']
            or sum(r['record_status'].startswith('unknown_') for r in rows)!=report['unknown_usage_calls']
            or report['all_36_audited']!=(attempted==36 and all(r['record_status']=='audited' for r in rows))
            or input_comparisons(pre['rendered'])!=report['input_rendering_comparisons']
            or pre['counts']!=report['input_counts']):
        raise ValueError('P101_complete_cohort_aggregation_mismatch')
    return plan,pre,report,{name:sha(root/name) for name in FILES}


def cost_totals(rows,choice):
    group=[r for r in rows if r['tool_choice']==choice]
    known=[r for r in group if r['record_status']=='audited']
    return dict(tool_choice=choice,planned=len(group),attempted=sum(r['record_status']!='unattempted' for r in group),
        known=len(known),unknown=sum(r['record_status'].startswith('unknown_') for r in group),
        unattempted=sum(r['record_status']=='unattempted' for r in group),
        known_input_tokens=sum(r['input_tokens'] for r in known),
        known_output_tokens=sum(r['output_tokens'] for r in known),
        known_total_tokens=sum(r['known_total_tokens'] for r in known),
        complete_static_submissions=sum(r['complete_static_submission'] for r in known),
        no_structured_calls=sum(r['structure']['tool_calls']==0 for r in known),
        truncated=sum(r['done_reason']=='length' for r in known))


def terminal_label(row):
    if row['record_status']=='unattempted':return '未実行'
    if row['record_status'].startswith('unknown_'):return '使用量不明'
    if not row['complete_generation']:return '途中切れ'
    if row['structure']['tool_calls']==0:return '本文のみ'
    return '形式整合' if row['complete_static_submission'] else '形式不整合'


def flag(value):return '同じ' if value is True else '異なる' if value is False else '判定不可'


def match(metric):return f"{metric['equal']}/{metric['comparable']}"


def write_csv(path,rows):
    with path.open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def build(output,root=ROOT):
    plan,pre,report,hashes=validated(root);output.mkdir(parents=True,exist_ok=False)
    rows=report['rows'];summary=report['equality_summary']
    flat=[]
    for row in rows:
        flat.append({**{k:row.get(k) for k in ('id','case','tool_choice','repetition','record_status','status',
            'input_tokens','output_tokens','known_total_tokens','done_reason','wall_seconds',
            'complete_generation','complete_static_submission','public_output_sha256','opaque_message_sha256')},
            'structured_tool_calls':row['structure'].get('tool_calls'),
            'syntax_actions_sha256':row['structure'].get('syntax_actions_sha256'),
            'actual_execution_confirmed':False})
    write_csv(output/'all_36_generations.csv',flat)
    write_csv(output/'all_12_groups.csv',summary['groups'])
    write_csv(output/'all_66_input_pairs.csv',report['input_rendering_comparisons'])
    pairs=[]
    for pair in summary['structural_comparisons']['cross']:
        item={k:pair[k] for k in ('left','right','pairs','both_without_structured_calls')}
        for metric in ('public_output','content','tool_names','json_actions','syntax_actions'):
            item.update({metric+'_'+k:v for k,v in pair[metric].items()})
        pairs.append(item)
    write_csv(output/'all_66_output_pairs.csv',pairs)
    write_json(output/'all_output_comparisons.json',summary)
    totals=[cost_totals(rows,c) for c in CHOICES];write_json(output/'cost_totals.json',totals)
    slides=[]
    def add(title,body,takeaway,notes):slides.append(dict(title=title,body=body,takeaway=takeaway,notes=notes))
    add('保存６入力と提出設定を全36枠で比較する',
        table(('記号','保存文脈の表現'),[(CODES[c],DESCRIPTIONS[i]) for i,c in enumerate(CASES)])+
        '<p class="body">各入力をauto / requiredで３反復。seed 70、出力上限4,096、全要求cold。</p>',
        '既知CSVの保存１文脈。静的な提出形式を確認し、生成コードは実行しない。',
        'P83で事後選定した全６入力を保持。P99とは別の局所診断。cache_prompt=falseとtool_choice以外の保存要求欄は変更しない。36生成・105万論理token以内。失敗・未実行を補充しない。新手法・課題成功・全仕事削減の証明ではない。')
    panels=[]
    for choice in CHOICES:
        data=[]
        for case in CASES:
            value=pre['rendered'][condition(case,choice)]
            data.append((CODES[case],value['input_tokens'],value['tokens_sha256'][:10],value['session_controls_sha256'][:10]))
        panels.append('<div><h3>'+choice+'</h3>'+table(('入力','token','入力列hash','制約hash'),data)+'</div>')
    add('実入力のtoken列と生成制約を分ける','<div class="two">'+''.join(panels)+'</div>'+
        '<p class="body">全12入力を語彙専用描画とサーバ計数で照合。hashは表示用の先頭10桁。</p>',
        '同じ計数でも同じ入力とは限らない。照合は省略前の完全なhashで行う。',
        'prompt、token列、生成制約、その他の設定を別々に比較。語彙専用処理は推論contextを作らずdecode０。全66組の入力比較をCSVへ保存。requiredとautoの入力同一性を前提にしない。')
    panels=[]
    for repetition in (1,2,3):
        group=[r for r in rows if r['repetition']==repetition]
        data=[(CODES[r['case']]+'/'+('a' if r['tool_choice']=='auto' else 'r'),
               r['output_tokens'],terminal_label(r)) for r in group]
        panels.append(f'<div><h3>反復{repetition}</h3>'+table(('入力/設定','出力T','記録の状態'),data)+'</div>')
    add('全36枠の終端と提出形式を残す','<div class="three">'+''.join(panels)+'</div>',
        'a＝auto、r＝required。「形式整合」は静的確認で、実行成功ではない。',
        '固定順序の全枠。途中切れ、本文のみ、形式不整合、使用量不明、未実行を分ける。入力・出力・費用・hashは全36件CSVに保存。不明を０へ代入しない。既知の途中切れも費用へ含める。')
    panels=[]
    for choice in CHOICES:
        data=[]
        for group in summary['groups']:
            if group['tool_choice']!=choice:continue
            data.append((CODES[group['case']],flag(group['all_three_public_outputs_equal']),
                f"{group['complete_static_submissions']}/3",group['no_structured_calls'],group['unknown']))
        panels.append('<div><h3>'+choice+'</h3>'+table(('入力','公開出力','形式整合','本文のみ','不明'),data)+'</div>')
    add('出力一致と静的な提出形式は別に数える','<div class="two">'+''.join(panels)+'</div>',
        '３回の本文が同じでもツール提出がない場合を、良好な操作の再現と呼ばない。',
        '公開出力の同じ／異なるは３回とも既知・完全・非空の場合だけ。形式整合にはJSON、宣言インタフェース形、Python ASTの確認と非途中切れを要求する。span存在、Pythonの意味、外部作用、課題品質は未確認。')
    inputs={frozenset((p['left'],p['right'])):p for p in report['input_rendering_comparisons']}
    outputs={frozenset((p['left'],p['right'])):p for p in summary['structural_comparisons']['cross']}
    within=[];across=[]
    for choice in CHOICES:
        for a,b in ((CASES[0],CASES[1]),(CASES[2],CASES[3]),(CASES[0],CASES[4])):
            key=frozenset((condition(a,choice),condition(b,choice)));p=inputs[key];q=outputs[key]
            within.append((CODES[a]+'/'+CODES[b]+' '+('a' if choice=='auto' else 'r'),
                           flag(p['tokens_equal']),match(q['public_output']),match(q['syntax_actions'])))
    for case in CASES:
        key=frozenset(condition(case,c) for c in CHOICES);p=inputs[key];q=outputs[key]
        across.append((CODES[case],flag(p['tokens_equal']),flag(p['session_controls_equal']),match(q['public_output'])))
    add('固定した対照を、全66組の中で確認する',
        '<div class="two"><div><h3>設定内の元入力・同一入力対照</h3>'+table(('対照','入力列','公開一致','構文一致'),within)+
        '</div><div><h3>同じ入力のauto / required</h3>'+table(('入力','入力列','生成制約','公開一致'),across)+'</div></div>',
        '一致数／比較可能対数。全66組を保存し、組数を独立標本数へ読み替えない。',
        'ここは事前指定したA/B、C/D、A/Nと同一入力の設定間比較。その他を含む全66組と条件内全36対はJSON/CSVに保持。構文hashの比較と完全な静的提出の件数は別指標。空の行動同士を有効操作の一致に数えない。')
    server=report['server']
    cost=[(t['tool_choice'],t['attempted'],f"{t['known_total_tokens']:,}",t['unknown'],t['unattempted']) for t in totals]
    resources=[('所有サーバ秒',f"{server['wall_seconds']:.3f}"),('ロード秒',f"{server['load_wall_seconds']:.3f}"),
        ('全パイプライン秒',f"{report['pipeline_wall_seconds']:.3f}"),
        ('保存された生成秒の合計',f"{report['generation_wall_seconds']:.3f}"),
        ('sampled RSSピーク GiB',f"{server['sampled_peak_rss_bytes']/2**30:.2f}"),
        ('system swapピーク bytes',server['peak_system_swap_bytes'])]
    add('不明費用と生成以外の資源も残す',
        table(('設定','生成試行','既知の論理token','不明試行','未実行'),cost)+
        '<div class="two"><div>'+table(('資源・時間','記録値'),resources[:3])+'</div><div>'+table(('資源・時間','記録値'),resources[3:])+'</div></div>',
        '論理tokenはcached inputも含む。部分時間は重なりがあるため二重加算しない。',
        '生成の既知費用合計は使用量が判明した枠だけ。不明試行を別記し、設定間の正確な費用差を補完しない。サーバ滞在にはロード・描画・計数・生成・待機を含む。RSSは全ユニファイドGPU割当量ではない。編集等のホスト負荷は排他的に固定していない。')
    known=sum(r['record_status']=='audited' for r in rows);unknown=report['unknown_usage_calls'];unrun=36-report['model_calls_attempted']
    add('この診断から言える範囲を限定する',
        f'<p class="lead">全36枠：監査済み {known}、使用量不明 {unknown}、未実行 {unrun}。</p>'+
        table(('確認する段階','この診断の範囲'),[
            ('入力','実token列・生成制約を保存して照合'),
            ('次の出力','公開内容、JSON、インタフェースの形、Python構文'),
            ('実行と最終成果','生成コード・環境API・課題評価は実行しない'),
            ('一般性','事後に選んだ既知CSVの１文脈・１モデル環境')]),
        '新手法、一般品質維持、課題全体の費用削減を成立済みとは扱わない。',
        '同じseedでも数値実行、cache状態、ホスト負荷が同一とは限らない。cold要求は毎回のGPU再起動を意味しない。旧P84/P87の欠測・未実行を置き換えない。P99の全仕事比較、P98の24実行事後解析と区別して原稿へ接続する。')
    sections=[]
    for n,slide in enumerate(slides,1):
        sections.append(f'<section class="slide"><div class="eyebrow">P101 保存文脈と提出設定 / {n:02d}</div><h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div><div class="footer"><span>保存１文脈・全36枠／静的確認・生成コード実行なし</span><span>{n}/{len(slides)}</span></div><div class="notes">{html.escape(slide["notes"])}</div></section>')
    css='h2{font-size:30px}h3{font-size:20px;margin:8px 0}.results th,.results td{font-size:17px;line-height:1.2;padding:5px 8px}.body{font-size:21px;line-height:1.35;margin:12px 0}.lead{font-size:28px}.two,.three{display:grid;gap:20px}.two{grid-template-columns:1fr 1fr}.three{grid-template-columns:1fr 1fr 1fr}.two>div,.three>div{min-width:0}.two .results,.three .results{table-layout:fixed;width:100%}.two .results th,.two .results td{font-size:16px;padding:5px 4px}.three .results th,.three .results td{font-size:16px;line-height:1.15;padding:2px 4px}.takeaway{font-size:22px}'
    nav='<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    (output/'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P101 保存文脈と提出設定</title><style>'+STYLE+css+'</style></head><body>'+''.join(sections)+nav+'<script>'+SCRIPT+'</script></body></html>')
    write_json(output/'slides.json',slides)
    manifest=dict(pages=len(slides),generated_at=datetime.now(timezone.utc).isoformat(),source_sha256=hashes,
        builder_sha256=sha(Path(__file__)),visual_reviewed=False,all_planned_rows=36,all_cross_pairs=66,
        all_36_audited=report['all_36_audited'],model_attempts=report['model_calls_attempted'],
        known_total_tokens=report['known_total_tokens'],unknown_usage_calls=unknown,unattempted_slots=unrun,
        public_artifact_sha256={p.name:sha(p) for p in sorted(output.iterdir()) if p.is_file()},
        static_submission_is_not_execution=True,novel_method_claim=False,task_quality_or_savings_measured=False,
        report_build_model_calls=0,report_build_environment_API_requests=0,report_build_evaluations=0)
    write_json(output/'build_manifest.json',manifest);return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'materials/20261024_p101_results')
    parser.add_argument('--pdf',action='store_true');args=parser.parse_args()
    result=build(args.output);print({k:result[k] for k in ('pages','all_planned_rows','known_total_tokens','unknown_usage_calls')})
    if args.pdf:
        build_budget_report.STEM=STEM;build_budget_report.export(args.output)
