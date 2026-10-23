"""Export the entire closed P80 comparison, including failures and missing use."""
import argparse
import csv
from datetime import datetime, timezone
import html
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from budget_observation import POLICIES
from budget_visibility_comparison import cell_id, run_order, validate_plan
from audit_budget_visibility_comparison import development_gate
from run_handoff_factors import ROOT, read, sha
from run_context_comparison import write_json

STEM='AI_harness_budget_visibility_20261024'
TASKS=('写真移動','精算','返金','曲情報の書出し')
LABELS=('残時間を表示','残時間を非表示')
FILES=('configs/P80_budget_visibility_v01.json','reports/P80_comparison.json',
       'reports/P80_initial_checks.json','reports/P80_server_session.json')


def validated():
    plan,report,pre,session=[read(ROOT/name) for name in FILES]
    validate_plan(plan)
    expected=[(cell_id(n,p),plan['known_tasks'][n-1]['task_id'],p) for n,p in run_order()]
    if ([(r['run_id'],r['task_id'],r['time_visibility']) for r in report['rows']]!=expected
            or report['audit_errors'] or report['batch_status'] not in ('complete','stopped')
            or report['plan_sha256']!=sha(ROOT/FILES[0])
            or pre['status']!='complete' or not pre['all_eight_inputs_checked']
            or pre['git_commit']!='e23b74727f7c2ff0c881a487940a4b6dbf764fd1'
            or session['status']!='stopped' or not session['owned_processes_absent']
            or session['audit_source_sha256']!=sha(ROOT/FILES[1])):
        raise ValueError('closed_fixed_cohort_and_stopped_owned_server_required')
    for k,v in development_gate(report['rows'],report['audit_errors']).items():
        if report[k]!=v: raise ValueError('fixed_development_gate_disagrees')
    return plan,report,pre,session


def cost(row):
    if row.get('known_total_tokens') is None: return '未計測'
    missing=row.get('planned',0)-row.get('measured',0)
    return (f"{row['known_total_tokens']:,}"+(f"＋不明{row['unknown_usage_calls']}" if row['unknown_usage_calls'] else '')
            +(f'＋未計測{missing}条件' if missing else ''))


def outcome(row):
    if row['record_status']!='evaluated': return '未実行' if row['record_status']=='not_run' else '未評価'
    return '成功' if row['success'] else '未達'


def totals(rows,policy):
    cells=[r for r in rows if r['time_visibility']==policy]
    measured=[r for r in cells if r.get('known_total_tokens') is not None]
    return {'time_visibility':policy,'planned':len(cells),'measured':len(measured),
        'evaluated':sum(r['record_status']=='evaluated' for r in cells),
        'successes':sum(r['success'] is True for r in cells),
        **{k:sum(r.get(k,0) for r in measured) for k in
           ('model_calls','known_total_tokens','unknown_usage_calls','api_requests','invocation_exceptions','wall_seconds')}}


def figure(output,plan,report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'Hiragino Sans','font.size':10,
                        'axes.spines.top':False,'axes.spines.right':False})
    folder=output/'figures';folder.mkdir(exist_ok=True)
    fig,ax=plt.subplots(figsize=(11,3.5),layout='constrained',facecolor='#f6f4ed')
    ax.set_facecolor('#f6f4ed')
    for n,item in enumerate(plan['known_tasks']):
        cells={r['time_visibility']:r for r in report['rows'] if r['task_id']==item['task_id']}
        for j,policy in enumerate(POLICIES):
            row=cells[policy];color=('#7d8892','#177b79')[j];y=3-n+(-.13 if j==0 else .13)
            if row.get('known_total_tokens') is None:
                ax.text(.02,y,LABELS[j]+'：未計測',transform=ax.get_yaxis_transform(),va='center');continue
            value=row['known_total_tokens']/1000
            marker='>' if row['unknown_usage_calls'] else ('o','D')[j]
            ax.scatter(value,y,marker=marker,s=75,edgecolor=color,
                       facecolor=color if row['success'] is True else '#f6f4ed',lw=1.8)
            ax.annotate(f'{value:.1f}'+('＋不明' if row['unknown_usage_calls'] else ''),
                        (value,y),xytext=(7,0),textcoords='offset points',va='center',color=color)
    largest=max((r['known_total_tokens']/1000 for r in report['rows']
                 if r.get('known_total_tokens') is not None),default=1)
    ax.set_yticks(range(4),TASKS[::-1]);ax.set_ylim(-.6,3.6);ax.set_xlim(0,max(1,largest)*1.3)
    ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    ax.set_xlabel('初期からの論理入力＋出力token（千）／塗り：成功、白抜き：未達・未評価')
    for j,label in enumerate(LABELS):
        ax.plot([],[],color=('#7d8892','#177b79')[j],marker=('o','D')[j],linestyle='',label=label)
    ax.legend(loc='upper center',bbox_to_anchor=(.5,1.2),ncol=2,frameon=False)
    for ext in ('svg','png','pdf'):fig.savefig(folder/('P80_whole_task_costs.'+ext),dpi=180,facecolor='#f6f4ed')
    plt.close(fig)


def build(output):
    plan,report,pre,session=validated();output.mkdir(parents=True,exist_ok=True)
    fields=('run_id','task_id','time_visibility','record_status','success','stop_reason','model_calls',
        'known_total_tokens','unknown_usage_calls','input_tokens','cached_input_tokens','output_tokens',
        'api_requests','invocation_exceptions','setup_wall_seconds','wall_seconds','cleanup_wall_seconds','full_wall_seconds')
    for name,rows,columns in [('all_conditions.csv',report['rows'],fields),
            ('all_pairs.csv',report['paired_results'],list(report['paired_results'][0]))]:
        with (output/name).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    figure(output,plan,report)
    slides=[]
    def add(title,body,takeaway,notes):slides.append(dict(title=title,body=body,takeaway=takeaway,notes=notes))
    initial=''.join(f'<tr><td>{task}</td><td>{r["conditions"]["measured"]["input_tokens"]:,}</td><td>{r["conditions"]["not_exposed"]["input_tokens"]:,}</td></tr>' for task,r in zip(TASKS,pre['rows'],strict=True))
    add('実期限を守ったまま、残時間の表示を変える',
        '<p class="body">実測残時間を表示するMと、非表示と明示するHを、既知４課題の初期から比較。</p>'
        '<table><tr><th>課題</th><th>M 初期入力token</th><th>H 初期入力token</th></tr>'+initial+'</table>'
        '<p class="body">両側で通常Python例外・全推論履歴・持続Python・通信参照の正規化を共通化。</p>',
        '１秒差の局所診断P79から、課題全体の品質と費用の確認へ進む。',
        '全８条件各１回。seed57、実期限1800秒、80生成、450000token。Hの説明文の費用も含める。P78は歴史的結果で、新比較の因果対照ではない。')
    body=[]
    for n,task in enumerate(TASKS,1):
        for j,policy in enumerate(POLICIES):
            r=next(r for r in report['rows'] if r['run_id']==cell_id(n,policy))
            body.append('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in
                (task,('M 表示','H 非表示')[j],outcome(r),cost(r),r.get('model_calls','—'),r.get('api_requests','—'),
                 f'{r["wall_seconds"]:.1f}' if r.get('wall_seconds') is not None else '—'))+'</tr>')
    add('全８条件の成否と全仕事費用',
        '<table class="results"><tr><th>課題</th><th>条件</th><th>成否</th><th>全仕事token</th><th>生成</th><th>API</th><th>作業秒</th></tr>'+''.join(body)+'</table>',
        '失敗・制御・再取得・推論を含め、不明使用量を０で補完しない。',
        '各最終成否は独立評価器で１回判定。結果はモデルへ戻さない。保留12課題は未閲覧。')
    add('費用と成功を同じ課題で比較する',
        '<img class="cost-figure" src="figures/P80_whole_task_costs.svg" alt="全４課題の費用と成否">',
        '初期入力の長さや、早く失敗したことだけを効率化としない。',
        '横軸はcacheを含む全論理入出力で金額・時間とは別。使用量不明は既知部分の右向き三角で示す。')
    aggregate=[totals(report['rows'],p) for p in POLICIES]
    summary=''.join(f'<tr><td>{label}</td><td>{r["successes"]}/{r["evaluated"]}</td><td>{cost(r)}</td><td>{r["model_calls"]}</td><td>{r["wall_seconds"]:,.1f}</td></tr>' for label,r in zip(LABELS,aggregate,strict=True))
    delta=report['not_exposed_minus_measured_whole_task_tokens']
    difference=f'H−M：{delta:+,} token。' if delta is not None else '欠測または未計測があるため全費用差は未確定。'
    decision='開発上の採用基準を満たした。' if report['development_gate_met'] else '開発上の採用基準は未達。'
    add('通常設定の採否と、主張の限界',
        '<table><tr><th>条件</th><th>成功／評価</th><th>既知token合計</th><th>生成</th><th>作業秒</th></tr>'+summary+'</table>'
        '<p class="lead">'+difference+'</p>'
        f'<p class="body">所有推論器 {session["wall_seconds"]:,.1f}秒。独立評価 {session["evaluation_wall_seconds"]:.2f}秒。<br>'
        '全８評価・使用量既知・監査一致・課題ごとの成功喪失０・全費用減少で判定。</p>',
        decision+' 新規手法や一般的な品質維持を証明したものではない。',
        '全条件の実入力と実測／表示通知を照合。所有サーバー停止とPID不在を確認。時間通知と期限強制の分離には先行研究がある。準備・作業・評価等は滞在時間と重なるため加算しない。')
    sections=[]
    for n,s in enumerate(slides,1):
        sections.append(f'<section class="slide"><div class="eyebrow">10月24日 残時間表示の比較 / {n:02d}</div><h2>{s["title"]}</h2>{s["body"]}<div class="takeaway">{s["takeaway"]}</div><div class="footer"><span>既知４課題・固定８条件</span><span>{n}/{len(slides)}</span></div><div class="notes">{html.escape(s["notes"])}</div></section>')
    nav='<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css='h2{font-size:31px}table{font-size:18px}td{padding:9px 12px}.results td,.results th{font-size:17px;padding:8px 9px}.cost-figure{width:100%;height:350px;object-fit:contain}'
    (output/'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P80 残時間表示</title><style>'+STYLE+css+'</style></head><body>'+''.join(sections)+nav+'<script>'+SCRIPT+'</script></body></html>')
    write_json(output/'slides.json',slides)
    manifest={'pages':len(slides),'generated_at':datetime.now(timezone.utc).isoformat(),
        'source_sha256':{name:sha(ROOT/name) for name in FILES},'builder_sha256':sha(Path(__file__)),
        'visual_reviewed':False,'totals':aggregate,'development_gate_met':report['development_gate_met'],
        'csv_sha256':sha(output/'all_conditions.csv'),'paired_csv_sha256':sha(output/'all_pairs.csv'),
        'novel_method_claim':False,'general_quality_preservation_claim':False}
    write_json(output/'build_manifest.json',manifest);return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'materials/20261024_p80')
    p.add_argument('--pdf',action='store_true');args=p.parse_args()
    result=build(args.output);print({k:result[k] for k in ('pages','totals','development_gate_met')})
    if args.pdf:build_budget_report.STEM=STEM;build_budget_report.export(args.output)
