"""Report every P82 condition and fixed comparison after the owned run closes."""
import argparse
import csv
from datetime import datetime, timezone
import html
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from build_budget_visibility_report import TASKS, cost, outcome, totals
from build_budget_visibility_repetition_report import table
from late_clock_comparison import POLICIES, cell_id, run_order, summarize, validate_plan
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

STEM = 'AI_harness_late_clock_comparison_20261024'
LABELS = ('M 毎回表示', 'H 非表示', 'L 後半表示')
FILES = ('configs/P82_late_clock_comparison_v01.json', 'reports/P82_comparison.json',
         'reports/P82_server_session.json', 'reports/P82_trajectory_stability.json',
         'reports/P82_call_profile.json')


def validated():
    plan, report, session, stability, profile = [read(ROOT / p) for p in FILES]
    validate_plan(plan)
    expected = [(cell_id(rep,n,p), rep, plan['known_tasks'][n-1]['task_id'], p)
                for rep,n,p in run_order()]
    if (report['batch_status'] not in ('complete','stopped') or report['audit_errors']
            or report['plan_sha256'] != sha(ROOT / FILES[0])
            or [(r['run_id'],r['repetition'],r['task_id'],r['time_visibility']) for r in report['rows']] != expected
            or session['status'] != 'stopped' or not session['owned_processes_absent']
            or session['audit_source_sha256'] != sha(ROOT / FILES[1])
            or stability['comparison_sha256'] != sha(ROOT / FILES[1])
            or profile['comparison_sha256'] != sha(ROOT / FILES[1])
            or len(stability['pairs']) != 36 or len(stability['traces']) != 24):
        raise ValueError('all_fixed_conditions_closed_and_audited_required')
    for k,v in summarize(report['rows'],report['audit_errors']).items():
        if report[k] != v: raise ValueError('fixed_gate_summary_disagrees')
    return plan, report, session, stability, profile


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
            color=('#7d8892','#177b79','#bd683c')[j]
            for r in rows:
                if r['task_id']!=item['task_id'] or r['time_visibility']!=policy:continue
                x=r['repetition']+(j-1)*.08
                if r.get('known_total_tokens') is None:
                    ax.text(x,.05,'未計測',transform=ax.get_xaxis_transform(),ha='center',fontsize=8,color=color)
                    continue
                marker='^' if r['unknown_usage_calls'] else ('o','D','s')[j]
                ax.scatter(x,r['known_total_tokens']/1000,s=48,marker=marker,edgecolor=color,
                    facecolor=color if r['success'] is True else '#f6f4ed',lw=1.5)
            ax.plot([],[],color=color,marker=('o','D','s')[j],linestyle='',label=LABELS[j])
        ax.set_xticks([1,2],['反復1','反復2']);ax.set_xlim(.65,2.35)
        ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.15);ax.set_ylabel('論理token（千）')
    axes[0,0].legend(loc='upper right',fontsize=8,frameon=False)
    for ext in ('svg','png','pdf'):fig.savefig(folder/('P82_whole_task_costs.'+ext),dpi=180,facecolor='#f6f4ed')
    plt.close(fig)


def build(output):
    plan,report,session,stability,profile=validated()
    output.mkdir(parents=True,exist_ok=True);rows=report['rows']
    fields=('run_id','repetition','task_id','time_visibility','record_status','success','stop_reason',
        'model_calls','known_total_tokens','unknown_usage_calls','input_tokens','cached_input_tokens',
        'output_tokens','api_requests','invocation_exceptions','setup_wall_seconds','wall_seconds',
        'cleanup_wall_seconds','full_wall_seconds')
    for filename,data,columns in [('all_24_conditions.csv',rows,fields),
        ('all_36_dependent_pairs.csv',stability['pairs'],tuple(stability['pairs'][0]))]:
        with (output/filename).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(data)
    figure(output,plan,rows);slides=[]
    def add(title,body,takeaway,notes):slides.append(dict(title=title,body=body,takeaway=takeaway,notes=notes))
    aggregate=[totals(rows,p) for p in POLICIES]
    add('残時間を知らせる時機を３条件で比べる',
        '<p class="body">既知４課題×毎回表示M／非表示H／後半表示L×２反復。実期限と参照整形は共通。</p>'+
        table(('条件','成功／評価','全仕事token','不明生成','実行済み／予定'),
            [(label,f'{r["successes"]}/{r["evaluated"]}',cost(r),r['unknown_usage_calls'],f'{r["measured"]}/{r["planned"]}')
             for label,r in zip(LABELS,aggregate,strict=True)]),
        '各仕事を初期状態から実行。P80/P81の結果を新しい対照へ流用しない。',
        '各条件は80生成、450000論理token、作業1800秒。Lは生成直前の整数残秒900以下から表示。長い生成中には通知できない。既知課題による開発比較であり、閾値・seed探索と保留課題閲覧は行わない。')
    for rep in (1,2):
        body=[]
        for n,item in enumerate(plan['known_tasks']):
            for j,p in enumerate(POLICIES):
                r=next(r for r in rows if r['repetition']==rep and r['task_id']==item['task_id'] and r['time_visibility']==p)
                body.append((TASKS[n],LABELS[j][0],outcome(r),cost(r),r.get('model_calls','—'),
                    r.get('api_requests','—'),f'{r["wall_seconds"]:.1f}' if r.get('wall_seconds') is not None else '—'))
        add(f'反復{rep}：全12条件の成果と費用',table(('課題','条件','成否','全仕事token','生成','API','作業秒'),body,'results'),
            '未達・未評価・使用量不明も保持する。成功例だけで総費用を判断しない。',
            '論理入力はcache再利用分も含む。未知使用量を０で補完しない。各最終状態を独立評価し、その正解や追加評価をモデルへ返さない。')
    add('同じ課題の３条件を両反復で見る',
        '<img class="cost-figure" src="figures/P82_whole_task_costs.svg" alt="全24条件の論理費用">',
        '塗りは成功、白抜きは未達・未評価。三角は既知費用に不明使用量が残る条件。',
        '独立課題は４つ。同じ課題・seedの反復を別の課題として数えない。縦軸は課題ごとに異なる。')
    gates=[]
    signed=lambda v:'未確定' if v is None else f'{v:+,}'
    for rep in report['repetitions']:
        for c in rep['comparisons']:
            key='late_half_minus_'+c['baseline']+'_whole_task_tokens'
            gates.append((rep['repetition'],'M' if c['baseline']=='measured' else 'H',
                '達成' if c['development_gate_met'] else '未達',c['paired_success_losses'],signed(c[key]),
                signed(c['paired_successful_token_difference']),signed(c['both_failed_token_difference'])))
    add('Lは両対照に対し、両反復で基準を満たしたか',
        table(('反復','対照','採用基準','成功喪失','全課題 L−対照','両側成功分','両側未達分'),gates,'results'),
        '全４比較の基準：'+('達成' if report['all_repetition_gates_met'] else '未達')+'。一般的な品質維持や新規性の認定とは別。',
        '全件評価・使用量既知・監査一致、課題ごとの成功喪失０、共通成功課題１以上、全４課題の論理費用減少を要求する。両側未達を安く終えた分と、共通成功課題の差を分ける。')
    comparison=[]
    for policy,label in zip(POLICIES,LABELS,strict=True):
        selected=[p for p in stability['pairs'] if p['relation']=='same_policy_repetition' and p['policies'][0]==policy]
        complete=sum(p['both_known_complete'] for p in selected)
        matched=lambda key:f'{sum(p[key] is True for p in selected)}/{complete}' if complete else '未確定'
        comparison.append((label,f'{complete}/4',matched('all_requests_equal'),matched('all_public_outputs_equal')))
    add('反復間の一致と、時間表示を始めた位置を残す',
        table(('条件','全使用量既知の対','全要求一致','全公開出力一致'),comparison)+
        '<p class="body">反復間12対と反復内24対の全36対を保存。最初の入力差と最初の実測時間通知を記録。</p>',
        '現在の通知をそろえた補助照合は、過去の履歴差や全仕事の因果効果を消去しない。',
        '比は一致対数／全使用量が既知の判定対数。使用量欠測時は未確定。保存JSONと出力hashの比較であり、モデルtoken列や数値状態の同一性は証明しない。36対は独立標本ではない。')
    add('推論器と全実行を含む費用の記録',
        table(('計測対象','実測値'),[
            ('新規生成',len(profile['calls'])),('推論器滞在秒',f'{session["wall_seconds"]:,.2f}'),
            ('初期化・作業・後片付け秒',f'{session["cell_full_wall_seconds"]:,.2f}'),
            ('評価秒（滞在時間に含む）',f'{session["evaluation_wall_seconds"]:,.2f}'),
            ('推論器の最大実測RSS GiB',f'{session["sampled_peak_rss_bytes"]/2**30:,.2f}')]),
        '論理token、cache、API、実時間は別の指標。重なる時間を加算しない。',
        '通知構築・入力計数・失敗・再取得は仕事時間に含む。旧P80/P81は別セッション。ホストでは編集や軽量解析も進めており排他的な負荷条件ではない。自動再試行は行わない。')
    sections=[]
    for n,s in enumerate(slides,1):
        sections.append(f'<section class="slide"><div class="eyebrow">10月24日 時間通知の３条件比較 / {n:02d}</div><h2>{s["title"]}</h2>{s["body"]}<div class="takeaway">{s["takeaway"]}</div><div class="footer"><span>既知４課題・全24条件・２反復</span><span>{n}/{len(slides)}</span></div><div class="notes">{html.escape(s["notes"])}</div></section>')
    nav='<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css='h2{font-size:29px}table{font-size:18px}td{padding:9px 12px}.results td,.results th{font-size:15px;padding:5px 9px}.cost-figure{width:100%;height:365px;object-fit:contain}'
    (output/'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P82 時間通知の３条件比較</title><style>'+STYLE+css+'</style></head><body>'+''.join(sections)+nav+'<script>'+SCRIPT+'</script></body></html>')
    write_json(output/'slides.json',slides)
    manifest={'pages':len(slides),'generated_at':datetime.now(timezone.utc).isoformat(),
        'source_sha256':{p:sha(ROOT/p) for p in FILES},'builder_sha256':sha(Path(__file__)),
        'all_planned_rows':24,'dependent_pairwise_comparisons':36,'independent_tasks':4,
        'totals':aggregate,'all_repetition_gates_met':report['all_repetition_gates_met'],
        'visual_reviewed':False,'novel_method_claim':False,'general_quality_preservation_claim':False,
        'unknown_usage_imputed':False}
    write_json(output/'build_manifest.json',manifest);return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'materials/20261024_p82_results')
    p.add_argument('--pdf',action='store_true');a=p.parse_args();r=build(a.output)
    print({k:r[k] for k in ('pages','all_planned_rows','all_repetition_gates_met')})
    if a.pdf:build_budget_report.STEM=STEM;build_budget_report.export(a.output)
