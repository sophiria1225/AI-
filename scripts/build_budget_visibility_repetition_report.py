"""Render all 24 P80/P81 rows after closure, including incomplete/unknown cells."""
import argparse
import csv
from datetime import datetime, timezone
import html
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from build_budget_visibility_report import TASKS, LABELS, cost, outcome, totals
from budget_observation import POLICIES
from budget_visibility_repetition import cell_id, run_order, summarize_repetitions, validate_plan
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_time_visibility_repetitions_20261024'
FILES = ('configs/P81_budget_visibility_repetition_v01.json', 'reports/P80_comparison.json',
         'reports/P81_repetitions.json', 'reports/P81_trajectory_stability.json',
         'reports/P81_server_session.json')


def validated():
    plan, anchor, report, stability, session = [read(ROOT / p) for p in FILES]
    validate_plan(plan)
    expected = [(cell_id(rep,n,p),rep,plan['known_tasks'][n-1]['task_id'],p) for rep,n,p in run_order()]
    if (report['batch_status'] not in ('complete','stopped') or report['audit_errors']
            or report['anchor_rows'] != anchor['rows'] or report['anchor_sha256'] != sha(ROOT / FILES[1])
            or report['plan_sha256'] != sha(ROOT / FILES[0])
            or [(r['run_id'],r['repetition'],r['task_id'],r['time_visibility']) for r in report['rows']] != expected
            or session['status'] != 'stopped' or not session['owned_processes_absent']
            or session['audit_source_sha256'] != sha(ROOT / FILES[2])
            or stability['comparison_sha256'] != sha(ROOT / FILES[2])
            or len(stability['pairs']) != 24 or len(stability['traces']) != 24):
        raise ValueError('closed_complete_planned_cohort_and_owned_server_required')
    for k,v in summarize_repetitions(anchor['rows'],report['rows'],report['audit_errors']).items():
        if report[k] != v: raise ValueError('repetition_summary_disagrees')
    return plan,report,stability,session


def table(headers, rows, cls=''):
    def cells(values, tag):
        return '<tr>'+''.join(f'<{tag}>'+html.escape(str(v))+f'</{tag}>' for v in values)+'</tr>'
    return f'<table class="{cls}">'+cells(headers,'th')+''.join(cells(r,'td') for r in rows)+'</table>'


def figure(output, plan, rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'Hiragino Sans','font.size':10,
                        'axes.spines.top':False,'axes.spines.right':False})
    folder=output/'figures';folder.mkdir(exist_ok=True)
    fig,axes=plt.subplots(2,2,figsize=(11,4),layout='constrained',facecolor='#f6f4ed')
    for n,(ax,item) in enumerate(zip(axes.flat,plan['known_tasks'],strict=True)):
        ax.set_facecolor('#f6f4ed');ax.set_title(TASKS[n],loc='left',fontsize=11)
        for j,policy in enumerate(POLICIES):
            color=('#7d8892','#177b79')[j]
            selected=sorted([r for r in rows if r['task_id']==item['task_id'] and r['time_visibility']==policy],key=lambda r:r['repetition'])
            for r in selected:
                x=r['repetition']+(-.06 if j==0 else .06)
                if r.get('known_total_tokens') is None:
                    ax.text(x,.05,'未計測',transform=ax.get_xaxis_transform(),ha='center',fontsize=8,color=color)
                    continue
                marker='^' if r['unknown_usage_calls'] else ('o','D')[j]
                ax.scatter(x,r['known_total_tokens']/1000,s=48,marker=marker,edgecolor=color,
                    facecolor=color if r['success'] is True else '#f6f4ed',lw=1.5)
            ax.plot([],[],color=color,marker=('o','D')[j],linestyle='',label=LABELS[j])
        ax.set_xticks([1,2,3],['P80','P81反復2','P81反復3']);ax.set_xlim(.6,3.4)
        ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.15);ax.set_ylabel('論理token（千）')
    axes[0,0].legend(loc='upper right',fontsize=8,frameon=False)
    for ext in ('svg','png','pdf'):fig.savefig(folder/('P81_repetition_costs.'+ext),dpi=180,facecolor='#f6f4ed')
    plt.close(fig)


def build(output):
    plan,report,stability,session=validated();output.mkdir(parents=True,exist_ok=True)
    rows=[{**r,'repetition':1} for r in report['anchor_rows']]+report['rows']
    fields=('run_id','repetition','task_id','time_visibility','record_status','success','stop_reason',
            'model_calls','known_total_tokens','unknown_usage_calls','input_tokens','cached_input_tokens',
            'output_tokens','api_requests','invocation_exceptions','wall_seconds','full_wall_seconds')
    for filename,data,columns in [('all_24_conditions.csv',rows,fields),
        ('all_24_dependent_pairs.csv',stability['pairs'],tuple(stability['pairs'][0])),
        ('all_8_repeated_conditions.csv',report['groups'],tuple(report['groups'][0]))]:
        with (output/filename).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(data)
    figure(output,plan,rows)
    slides=[]
    def add(title,body,takeaway,notes):slides.append(dict(title=title,body=body,takeaway=takeaway,notes=notes))
    aggregate=[totals(rows,p) for p in POLICIES]
    overview=table(('条件','成功／評価','既知全token','不明生成','実行済み／予定'),
        [(label,f'{r["successes"]}/{r["evaluated"]}',cost(r),r['unknown_usage_calls'],f'{r["measured"]}/{r["planned"]}')
         for label,r in zip(LABELS,aggregate,strict=True)])
    add('同じseedと初期状態で、全８条件を３回ずつ調べる',
        '<p class="body">既知４課題×残時間表示M／非表示H。P80の８行と、新しいP81の16行をすべて保持。</p>'+overview,
        '独立した課題は４つ。24行や24対を独立標本として扱わない。',
        'seed57＋呼出し番号、世界seed42。全推論保持・持続Python・実期限・計数を共通化。全体費用には失敗と不明試行も含める。P80欠測は反復で置き換えない。')
    for rep in (1,2,3):
        body=[]
        for n,item in enumerate(plan['known_tasks']):
            for j,policy in enumerate(POLICIES):
                r=next(r for r in rows if r['repetition']==rep and r['task_id']==item['task_id'] and r['time_visibility']==policy)
                body.append((TASKS[n],('M 表示','H 非表示')[j],outcome(r),cost(r),r.get('model_calls','—'),
                             r.get('api_requests','—'),f'{r["wall_seconds"]:.1f}' if r.get('wall_seconds') is not None else '—'))
        add(f'反復{rep}の全８条件'+('：P80の元記録' if rep==1 else '：P81の追加実行'),
            table(('課題','条件','成否','全仕事token','生成','API','作業秒'),body,'results'),
            '成功・未達・未評価・使用量不明を、同じ行に残す。',
            '各反復を別々に表示する。知られた費用だけの差を、完全な総費用差へ読み替えない。全入力はcache分を含み、金額ではない。')
    add('同じ条件の３回で、成否と費用はどの程度そろうか',
        '<img class="cost-figure" src="figures/P81_repetition_costs.svg" alt="全４課題・両条件・３回の論理費用">',
        '塗りは成功、白抜きは未達・未評価。上向き三角は既知費用＋不明使用量。',
        '全３回が評価済みで使用量既知の場合だけ範囲を計算。欠測を０にした平均や、成功例だけの平均は作らない。縦軸の尺度は課題ごとに異なる。')
    comparison=[]
    for n,item in enumerate(plan['known_tasks']):
        for j,policy in enumerate(POLICIES):
            pairs=[p for p in stability['pairs'] if p['task_id']==item['task_id'] and p['time_visibility']==policy]
            if len(pairs)!=3:raise ValueError('all_three_dependent_pairs_per_condition_required')
            complete=sum(p['both_known_complete'] for p in pairs)
            matched=lambda key: f'{sum(p[key] is True for p in pairs)}/{complete}' if complete else '未確定'
            comparison.append((TASKS[n],('M','H')[j],f'{complete}/3',
                matched('all_requests_equal'),matched('all_public_outputs_equal'),
                str(sum(p['first_request_difference_is_current_wall_only'] is True for p in pairs))+'対'))
    add('要求と公開出力の一致を全24対で照合する',
        table(('課題','条件','全使用量既知','全要求一致','全公開出力一致','最初の差が現在時計のみ'),comparison,'results'),
        '各条件３対は同じ３実行を共有する。入出力hashの照合は意味的な同値証明ではない。',
        '一致の比は一致対数／両方の使用量が既知の判定対数であり、生成数が異なる場合は不一致。使用量欠測は未確定。時計差は該当が観測された対数。現在通知だけをそろえた事後照合は、実際の入力を変更した実験ではない。推論文字列はhashだけ照合。')
    gates=table(('反復','採用基準','成功喪失','全費用差 H−M'),[
        (g['repetition'],'達成' if g['development_gate_met'] else '未達',g['paired_success_losses'] if g['paired_success_losses'] is not None else '未確定',
         f'{g["not_exposed_minus_measured_whole_task_tokens"]:+,}' if g['not_exposed_minus_measured_whole_task_tokens'] is not None else '未確定')
        for g in report['repetitions']])
    add('全体の採否とレターで主張できる範囲',gates+
        f'<p class="body">追加P81の推論器滞在 {session["wall_seconds"]:,.1f}秒、独立評価 {session["evaluation_wall_seconds"]:.2f}秒。<br>元のP80の費用・失敗・欠測は保持する。</p>',
        '新手法・一般的品質維持・母集団の平均削減を、この反復だけで確立したとはしない。',
        'P80の不明生成があるため全３反復の採用基準達成は元から不成立。反復の目的は安定性の確認。P80補助下限は別の事後解析で、終端使用量やこの表を書き換えない。各時間は重なるため足さない。同じホストで編集・読取解析・軽量検査も進めており、ホストの負荷を排他的に固定した実験ではない。')
    sections=[]
    for n,s in enumerate(slides,1):
        sections.append(f'<section class="slide"><div class="eyebrow">10月24日 残時間表示の反復 / {n:02d}</div><h2>{s["title"]}</h2>{s["body"]}<div class="takeaway">{s["takeaway"]}</div><div class="footer"><span>既知４課題・同一seed・全24行</span><span>{n}/{len(slides)}</span></div><div class="notes">{html.escape(s["notes"])}</div></section>')
    nav='<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css='h2{font-size:29px}table{font-size:18px}td{padding:9px 12px}.results td,.results th{font-size:16px;padding:8px 9px}.cost-figure{width:100%;height:365px;object-fit:contain}'
    (output/'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P81 時間通知の反復</title><style>'+STYLE+css+'</style></head><body>'+''.join(sections)+nav+'<script>'+SCRIPT+'</script></body></html>')
    write_json(output/'slides.json',slides)
    manifest={'pages':len(slides),'generated_at':datetime.now(timezone.utc).isoformat(),
        'source_sha256':{p:sha(ROOT/p) for p in FILES},'builder_sha256':sha(Path(__file__)),
        'all_planned_rows':len(rows),'dependent_pairwise_comparisons':24,'independent_tasks':4,
        'totals':aggregate,'visual_reviewed':False,'novel_method_claim':False,
        'general_quality_preservation_claim':False,'unknown_usage_imputed':False}
    write_json(output/'build_manifest.json',manifest)
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'materials/20261024_p81_results')
    p.add_argument('--pdf',action='store_true');args=p.parse_args()
    result=build(args.output);print({k:result[k] for k in ('pages','all_planned_rows','totals')})
    if args.pdf:build_budget_report.STEM=STEM;build_budget_report.export(args.output)
