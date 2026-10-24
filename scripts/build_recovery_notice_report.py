"""P97 whole-cohort report. Missing and failed cells remain visible."""
import argparse
import csv
from datetime import datetime, timezone
import html
from pathlib import Path

import build_budget_report
from build_morning_report import STYLE, SCRIPT
from build_budget_visibility_report import TASKS, outcome
from build_budget_visibility_repetition_report import table
from recovery_notice_comparison import POLICIES, cell_id, run_order, summarize, validate_plan
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

EXECUTED_HEAD = '46dcfd3f3d2b79214b8601618f40ee6083e67452'
STEM = 'AI_harness_recovery_notices_20261024'
LABELS = {'none':'N 通知なし', 'generic':'G 一般通知', 'factual':'F 事実通知'}
FILES = ('configs/P97_recovery_notice_comparison_v01.json', 'reports/P97_comparison.json',
         'reports/P97_initial_checks.json', 'reports/P97_activation_v01.json',
         'reports/P97_server_session.json', 'reports/P97_notice_ledger.json')


def validated(root):
    plan, report, pre, activation, session, notices = [read(root / name) for name in FILES]
    validate_plan(plan)
    expected = [(cell_id(n,p), plan['known_tasks'][n-1]['task_id'], p) for n,p in run_order()]
    if ([(r['run_id'],r['task_id'],r['notice_policy']) for r in report['rows']] != expected
            or report['audit_errors'] or report['batch_status'] not in ('complete','stopped')
            or report['plan_sha256'] != sha(root / FILES[0])
            or report['activation_sha256'] != sha(root / FILES[3])
            or not report['owned_processes_absent']
            or pre['status'] != 'complete' or not pre['all_twelve_inputs_checked']
            or pre['input_count_requests'] != 12 or pre['failed_input_count_requests']
            or pre['git_commit'] != EXECUTED_HEAD
            or activation['preflight_sha256'] != sha(root / FILES[2])
            or activation['source_hashes'] != pre['source_hashes']
            or not activation['all_twelve_conditions_frozen_before_generation']
            or session['status'] != 'stopped' or not session['owned_processes_absent']
            or session['audit_source_sha256'] != sha(root / FILES[1])
            or session['pipeline_source_sha256'] != report['pipeline_status_sha256']
            or notices['status'] != 'complete' or notices['audit_source_sha256'] != sha(root / FILES[1])
            or [r['run_id'] for r in notices['rows']] != [r[0] for r in expected]):
        raise ValueError('closed_fixed_P97_whole_cohort_required')
    for name, expected_hash in pre['source_hashes'].items():
        if sha(root / name) != expected_hash:
            raise ValueError('frozen_executed_source_changed:' + name)
    for key,value in summarize(report['rows'],report['audit_errors']).items():
        if report[key] != value:raise ValueError('fixed_gate_differs:' + key)
    for row in report['rows']:
        if (row['record_status']=='evaluated') != (type(row['success']) is bool):
            raise ValueError('only_evaluated_cells_have_boolean_success')
    return plan, report, pre, activation, session, notices


def totals(rows, policy):
    cells=[r for r in rows if r['notice_policy']==policy]
    measured=[r for r in cells if type(r.get('known_total_tokens')) is int]
    out=dict(notice_policy=policy,planned=len(cells),measured=len(measured),unmeasured=len(cells)-len(measured),
        evaluated=sum(r['record_status']=='evaluated' for r in cells),
        successes=sum(r['success'] is True for r in cells),
        failures=sum(r['record_status']=='evaluated' and r['success'] is False for r in cells))
    for key in ('model_calls','known_total_tokens','unknown_usage_calls','input_tokens','output_tokens',
                'cached_input_tokens','api_requests','invocation_exceptions','setup_wall_seconds',
                'wall_seconds','cleanup_wall_seconds','full_wall_seconds'):
        out[key]=sum(r[key] for r in measured) if measured and all(r.get(key) is not None for r in measured) else None
    out['full_logical_tokens']=out['known_total_tokens'] if measured and len(measured)==len(cells) and out['unknown_usage_calls']==0 else None
    out['known_uncached_input_tokens']=(out['input_tokens']-out['cached_input_tokens']
        if out['input_tokens'] is not None and out['cached_input_tokens'] is not None else None)
    return out


def contributions(report):
    out=[]
    for pair in report['pairs']:
        groups={g:[] for g in ('both_successful','both_failed','discordant','unevaluated')}
        for row in pair['tasks']:
            a,b=row['left_success'],row['right_success']
            group=('unevaluated' if type(a) is not bool or type(b) is not bool else
                   'both_successful' if a and b else 'both_failed' if not a and not b else 'discordant')
            groups[group].append(row)
        for key,rows in groups.items():
            out.append(dict(left=pair['left'],right=pair['right'],group=key,task_count=len(rows),
                right_minus_left_tokens=sum(r['right_minus_left_tokens'] for r in rows)
                if report['all_twelve_evaluated_with_known_usage'] else None))
    return out


def number(value, decimals=0):
    return '未計測' if value is None else f'{value:,.{decimals}f}'


def cost(row):
    text=number(row.get('known_total_tokens'))
    if row.get('unknown_usage_calls'):text+=f"＋不明{row['unknown_usage_calls']}"
    if row.get('unmeasured'):text+=f"＋未計測{row['unmeasured']}条件"
    return text


def signed(value):
    return '未確定' if value is None else f'{value:+,}'


def figure(output, plan, rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'Hiragino Sans','font.size':9,
        'axes.spines.top':False,'axes.spines.right':False})
    folder=output/'figures';folder.mkdir()
    fig,ax=plt.subplots(figsize=(11,4),layout='constrained',facecolor='#f6f4ed')
    ax.set_facecolor('#f6f4ed')
    colors=('#727d89','#286d9a','#177b79')
    for n,item in enumerate(plan['known_tasks']):
        for j,policy in enumerate(POLICIES):
            row=next(r for r in rows if r['task_id']==item['task_id'] and r['notice_policy']==policy)
            y=3-n+(1-j)*.23;color=colors[j]
            if row.get('known_total_tokens') is None:
                ax.text(.02,y,LABELS[policy]+'：未計測',transform=ax.get_yaxis_transform(),va='center',color=color)
                continue
            value=row['known_total_tokens']/1000
            marker='>' if row['unknown_usage_calls'] else ('o','s','D')[j]
            ax.scatter(value,y,marker=marker,s=52,edgecolor=color,
                facecolor=color if row['success'] is True else '#f6f4ed',lw=1.5)
            ax.annotate(f'{value:.1f}'+('＋不明' if row['unknown_usage_calls'] else '')+' '+outcome(row),
                        (value,y),xytext=(6,0),textcoords='offset points',va='center',color=color,fontsize=8)
    largest=max((r['known_total_tokens']/1000 for r in rows if r.get('known_total_tokens') is not None),default=1)
    ax.set_yticks(range(4),TASKS[::-1]);ax.set_ylim(-.55,3.55);ax.set_xlim(0,max(1,largest)*1.4)
    ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    ax.set_xlabel('開始からの論理入力＋出力token（千）／右向き三角：既知小計＋不明使用量')
    for j,p in enumerate(POLICIES):ax.plot([],[],color=colors[j],marker=('o','s','D')[j],linestyle='',label=LABELS[p])
    ax.legend(loc='upper center',bbox_to_anchor=(.5,1.15),ncol=3,frameon=False)
    for ext in ('svg','png','pdf'):fig.savefig(folder/('P97_whole_task_costs.'+ext),dpi=180,facecolor='#f6f4ed')
    plt.close(fig)


def build(output, root=ROOT):
    plan,report,pre,activation,session,notices=validated(root)
    output.mkdir(parents=True,exist_ok=False)
    rows=report['rows'];aggregate=[totals(rows,p) for p in POLICIES];parts=contributions(report)
    fields=('run_id','task_id','notice_policy','record_status','success','stop_reason','model_calls',
        'known_total_tokens','unknown_usage_calls','input_tokens','cached_input_tokens','output_tokens',
        'api_requests','invocation_exceptions','setup_wall_seconds','wall_seconds','cleanup_wall_seconds','full_wall_seconds')
    pair_rows=[{'left':p['left'],'right':p['right'],**r} for p in report['pairs'] for r in p['tasks']]
    for name,data,columns in [('all_twelve_conditions.csv',rows,fields),
        ('all_twelve_task_pairs.csv',pair_rows,tuple(pair_rows[0])),
        ('cost_contributions.csv',parts,tuple(parts[0]))]:
        with (output/name).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(data)
    figure(output,plan,rows)
    write_json(output/'whole_cohort_summary.json',dict(totals=aggregate,contributions=parts,
        pairs=report['pairs'],matched_before_notice_tasks=report['matched_before_notice_tasks'],
        factual_notice_benefit_gate_met=report['factual_notice_benefit_gate_met'],
        all_planned_rows=12,novel_method_established=False))
    slides=[]
    def add(title,body,takeaway,notes):slides.append(dict(title=title,body=body,takeaway=takeaway,notes=notes))
    add('通常の回復通知を、課題の完了まで比較する',
        table(('条件','追加する回復通知'),[(LABELS['none'],'なし。共通の検出と記録は行う'),
            (LABELS['generic'],'残った要求と保持したPython変数を見直す'),
            (LABELS['factual'],'再観測の事実と限界を示し、同じ見直しを促す')])+
        '<p class="body">既知４課題 ×３条件、各１回。再観測が２境界連続した直後に最大１回。</p>',
        'P96の由来追跡は単純対照と同等だった。P97も新提案として扱わない。',
        'reasoning -1、持続Python、全返却推論、残り実時間非表示を共通化。初期12入力を確認し、各課題の３要求は同一。全読取・API権限は残し、通知文だけを一時入力に加える。文量差と計算費用も評価に含む。')
    add('全12条件の結果と、失敗を含めた費用',
        table(('課題','条件','成否','全仕事token','生成','API','仕事秒'),
            [(TASKS[n-1],LABELS[p].split()[0],outcome(r),cost(r),number(r.get('model_calls')),
              number(r.get('api_requests')),number(r.get('wall_seconds'),1))
             for n,p in run_order() for r in rows if r['run_id']==cell_id(n,p)],'results'),
        '使用量不明は０にせず、未実行・未評価を失敗数へ混ぜない。',
        '初期状態から１回ずつ独立に実行し、公式最終状態で１回評価。評価の基準・結果はモデルへ戻さない。CSVが本当に完了したかもこの表で確認する。')
    add('同じ課題の成否と、全仕事費用',
        '<img class="cost-figure" src="figures/P97_whole_task_costs.svg" alt="全12条件の費用と成否">',
        '塗りは成功。三角は不明が残る既知小計。早く未達で終えた差も残す。',
        '全論理入力＋出力で比較する。cacheを含める。tokenの削減と経過時間や金額の削減は同一ではない。')
    add('全４課題で、３つの対照を判定する',
        table(('比較（右−左）','全論理token差','課題ごとの成功喪失なし','通常対照の基準'),
            [(LABELS[p['right']].split()[0]+'−'+LABELS[p['left']].split()[0],signed(p['aggregate_token_difference']),
              '確認' if p['no_per_task_success_loss'] else '未確認／非該当',
              '達成' if p['ordinary_control_gate_met'] else '未達') for p in report['pairs']])+
        '<p class="body">同じ通知前入力で両通知を送った課題数：'+str(len(report['matched_before_notice_tasks']))+
        '<br>事実通知の便益候補：'+('基準達成' if report['factual_notice_benefit_gate_met'] else '基準未達')+'</p>',
        '全12評価・使用量確定、成功喪失なし、両成功１件以上、全費用減を要求。',
        '事実通知にはnoneとgenericの両対照への基準と同じ前史での実送信も必要。成立しても既知４課題の通常対照の結果で、独立な新手法、一般的品質維持、採録の根拠へ自動昇格しない。')
    group_labels=dict(both_successful='両成功',both_failed='両未達',discordant='成否相違',unevaluated='未評価あり')
    add('成功仕事と失敗仕事の費用差を分ける',
        table(('比較','成否の区分','課題数','全論理token差'),
            [(LABELS[p['right']].split()[0]+'−'+LABELS[p['left']].split()[0],group_labels[p['group']],
              p['task_count'],signed(p['right_minus_left_tokens'])) for p in parts],'results'),
        '失敗を安く終えただけの差を、成功仕事の改善へ読み替えない。',
        '全件使用量が既知なら区分の差を足すと全課題の差になる。不明があれば選んだ既知部分を全体の寄与として表示しない。')
    add('cache、出力、呼出しを別に残す',
        table(('計測対象',*[LABELS[p] for p in POLICIES]),
            [(label,*[number(r[key]) for r in aggregate]) for key,label in [
                ('input_tokens','既知の全入力token'),('cached_input_tokens','既知入力のcache再利用'),
                ('known_uncached_input_tokens','既知のcache除外入力'),('output_tokens','既知の出力token'),
                ('model_calls','生成試行'),('api_requests','API要求'),('unknown_usage_calls','使用量不明の生成')]]),
        '通知、推論、失敗、回復を含む。既知小計に不明生成は含まれない。',
        '共通の検出・保存費用は全条件で仕事時間に含む。観測処理の小計は全制御費用ではない。noneは無計測の実行ではない。')
    add('検出候補と、通知の送信試行を区別する',
        table(('課題','条件','候補境界（exact/drop/origin）','回復通知の送信試行'),
            [(TASKS[n-1],LABELS[p].split()[0],
              '/'.join(str(r['candidate_counts'][m]) for m in ('exact','drop_auth_argument','login_request_origin'))
                if r.get('record_present') else '未計測',
              ','.join(x['next_call_id'] for x in r.get('offers',[]) if x['model_attempted']) or 'なし')
             for n,p in run_order() for r in notices['rows'] if r['run_id']==cell_id(n,p)],'results'),
        '入力予算で拒否された通知を、モデルへの送信試行として数えない。',
        '監視対象APIを含む既知課題はCSVの１つ。他の３課題を検出の陰性例として数えない。影の検出器も全境界を保存。認証引数除外は観測の比較だけで、認証・将来の値・進捗の保証ではない。')
    add('ロードから終了までの資源を残す',
        table(('計測対象','実測値'),[
            ('所有推論器の稼働秒',number(session['wall_seconds'],2)),
            ('モデルロード秒（稼働時間に含む）',number(session['load_wall_seconds'],2)),
            ('計測済みセルのsetup＋仕事＋cleanup秒',number(session['cell_full_wall_seconds'],2)),
            ('独立評価秒（稼働時間に含む）',number(session['evaluation_wall_seconds'],2)),
            ('推論器の最大実測RSS GiB',number(session['sampled_peak_rss_bytes']/2**30,2)),
            ('最大システムswap GiB',number(session['peak_system_swap_bytes']/2**30,2))]),
        '所有サーバ停止とPID不在を確認。重なる時間は二重加算しない。',
        '１セル上限80生成/450000 token/1800仕事秒。全12セル予約960生成/5400000 token/1200 API、所有サーバ32400秒。ホスト上で軽量な編集・資料準備を実施し、排他的な速度測定ではない。RSSはGPU全体の使用量ではない。')
    sections=[]
    for n,slide in enumerate(slides,1):
        sections.append(f'<section class="slide"><div class="eyebrow">10月24日 通常の回復通知 / {n:02d}</div><h2>{slide["title"]}</h2>{slide["body"]}<div class="takeaway">{slide["takeaway"]}</div><div class="footer"><span>既知４課題・固定12条件・各１回</span><span>{n}/{len(slides)}</span></div><div class="notes">{html.escape(slide["notes"])}</div></section>')
    nav='<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    css='h2{font-size:28px}table{font-size:17px}td{padding:8px 11px}.results td,.results th{font-size:14px;padding:5px 7px}.cost-figure{width:100%;height:355px;object-fit:contain}'
    (output/'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P97 全仕事の回復通知</title><style>'+STYLE+css+'</style></head><body>'+''.join(sections)+nav+'<script>'+SCRIPT+'</script></body></html>')
    write_json(output/'slides.json',slides)
    manifest=dict(pages=len(slides),generated_at=datetime.now(timezone.utc).isoformat(),
        source_sha256={name:sha(root/name) for name in FILES},builder_sha256=sha(Path(__file__)),
        all_planned_rows=12,independent_tasks=4,repetitions=1,totals=aggregate,contributions=parts,
        factual_notice_benefit_gate_met=report['factual_notice_benefit_gate_met'],
        csv_sha256={name:sha(output/name) for name in ('all_twelve_conditions.csv','all_twelve_task_pairs.csv','cost_contributions.csv')},
        summary_sha256=sha(output/'whole_cohort_summary.json'),visual_reviewed=False,
        novel_method_claim=False,general_quality_preservation_claim=False,unknown_usage_imputed=False)
    write_json(output/'build_manifest.json',manifest)
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--repo-root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path,default=ROOT/'materials/20261024_p97_results')
    parser.add_argument('--pdf',action='store_true');args=parser.parse_args()
    result=build(args.output,args.repo_root)
    print({k:result[k] for k in ('pages','all_planned_rows','factual_notice_benefit_gate_met')})
    if args.pdf:
        build_budget_report.STEM=STEM;build_budget_report.export(args.output)
