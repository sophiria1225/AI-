"""Small P33 milestone slides from closed, audited aggregates only."""
import argparse
import csv
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import tempfile

from build_morning_report import STYLE,SCRIPT,svg,txt,line,circle
from handoff_output_views import ARMS
from output_view_decision import assess

ROOT=Path(__file__).resolve().parents[1]
LINK='https://github.com/sophiria1225/AI-/blob/main/'
NAMES=['全履歴','出力省略','出力省略＋一覧']
LABELS=['写真整理','共有・依頼','返金','曲一覧の書出']
STEM='AI_harness_P33_20261022'

def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def esc(value):return html.escape(str(value))


def evidence(root):
    paths=['reports/P33_comparison.json','reports/P33_development_gate.json',
           'reports/P33_cost_profile.json','reports/P33_program_diagnostics.json',
           'reports/P33_prefix_checks.json','configs/P29_stateful_code_v01.json',
           'reports/P34_output_residency.json']
    values=[read(root/n) for n in paths]
    report,gate,cost,diagnostics,preflight,plan,residency=values
    recomputed=assess(report,{'status':'complete','completed':[r['run_id'] for r in report['rows']]})
    if any(gate[k]!=recomputed[k] for k in recomputed):raise ValueError('gate differs from complete result')
    for value in (gate,cost,diagnostics):
        if 'comparison_sha256' in value and value['comparison_sha256']!=sha(root/paths[0]):
            raise ValueError('cost/diagnostic source differs')
        for name,expected in value.get('source_sha256',{}).items():
            if sha(root/name)!=expected:raise ValueError('changed report source: '+name)
    if (not cost['all_twelve_profiled'] or not diagnostics['all_twelve_reviewed']
            or len(cost['rows'])!=12 or len(diagnostics['rows'])!=12
            or not preflight['all_observable_prefixes_match']):
        raise ValueError('complete measurements required')
    for arm in ARMS:
        c=cost['by_arm'][arm]['totals'];r=report['totals'][arm]
        if c['known_total_tokens']!=r['known_total_tokens'] or c['calls']!=r['model_calls']:
            raise ValueError('cost totals differ')
    return values,{name:sha(root/name) for name in paths}


def charts(output,report,cost,preflight):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'Hiragino Sans','font.size':12,
                         'axes.spines.top':False,'axes.spines.right':False,
                         'svg.fonttype':'none','savefig.facecolor':'#f6f4ed'})
    folder=output/'figures';folder.mkdir(parents=True,exist_ok=True)
    initial=[sum(r['views'][a]['input_tokens'] for r in preflight['rows'])/1000 for a in ARMS]
    final=[report['totals'][a]['known_total_tokens']/1000 for a in ARMS]
    colors=['#8796a2','#177b79','#c66a38']
    fig,axes=plt.subplots(1,2,figsize=(11.5,3.5),layout='constrained',facecolor='#f6f4ed')
    for ax,values,title in zip(axes,(initial,final),('再開１回目の入力','終了までの全入力＋出力')):
        ax.set_facecolor('#f6f4ed');bars=ax.barh(NAMES[::-1],values[::-1],color=colors[::-1],height=.53)
        ax.set_title(title,pad=12);ax.set_xlabel('４課題合計・千トークン')
        ax.set_xlim(0,max(values)*1.32);ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
        for arm,bar,value in zip(ARMS[::-1],bars,values[::-1]):
            unknown=report['totals'][arm]['unknown_usage_calls'] if ax is axes[1] else 0
            suffix=f' ＋不明{unknown}回' if unknown else ''
            if unknown:bar.set_hatch('///')
            ax.text(value+max(values)*.02,bar.get_y()+bar.get_height()/2,f'{value:,.1f}'+suffix,
                    va='center',fontsize=10)
    for ext in ('svg','png','pdf'):fig.savefig(folder/('input_and_total.'+ext),dpi=180)
    plt.close(fig)
    with (folder/'all_twelve_results.csv').open('w') as stream:
        fields=['task_id','arm','success','known_total_tokens','unknown_usage_calls',
                'model_calls','api_requests','setup_api_requests','continuation_wall_seconds',
                'transfer_wall_seconds']
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(report['rows'])


def design():
    image=txt(10,35,'同じ４課題の８応答後',24,weight=700)
    for i,width in enumerate((220,180,240,170)):
        image+=f'<path d="M20 {72+34*i}h{width}v23H20z" fill="'+('#a7c9c1' if i%2 else '#d6dfdb')+'"/>'
    image+=txt(20,242,'会話・アプリ・Python',22)
    for y,label,sub,color in [(76,'全履歴','出力を全て渡す','#8796a2'),
                               (172,'出力省略','古い長い出力を参照に置換','#177b79'),
                               (268,'出力省略＋一覧','変数・APIの名前も渡す','#c66a38')]:
        image+=line(290,159,473,y,color,3,True)+circle(505,y,21,color)
        image+=txt(548,y+4,label,26,color,700)+txt(548,y+35,sub,20)
    image+=txt(20,326,'Python状態・原記録の再読・モデル・後続予算は共通',21,weight=700)
    return svg(image,h=355,label='同じ途中状態から入力の構成だけが異なる三条件へ分岐')


def build(root,output):
    (report,gate,cost,diagnostics,preflight,plan,residency),hashes=evidence(root)
    output.mkdir(parents=True,exist_ok=True);charts(output,report,cost,preflight)
    rows={(r['task_id'],r['arm']):r for r in report['rows']}
    totals=report['totals'];slides=[]
    def slide(title,body='',take='',notes='',refs=(),cover=False):
        slides.append(dict(title=title,body=body,take=take,notes=notes,refs=list(refs),cover=cover))
    slide('AIハーネスにおける<br>入力削減と実行費用の分析',cover=True,
          notes='P33の追加進捗資料。出力だけの省略と一覧の効果を、最終成否と総費用で確認する。')
    slide('目的：最終品質を保ち、不要な処理を減らす',
        '<p class="lead">ハーネスが、AIへ渡す情報・ツール実行・状態・検証・停止を制御する。</p>'
        '<div class="two"><div class="col"><h3>減らしたい負担</h3><p class="body">同じ長い出力の再入力。<br>省略した情報の再取得。<br>それに伴う追加のAI呼出し。</p></div>'
        '<div class="col"><h3>残す必要があるもの</h3><p class="body">要求・操作・失敗の記録。<br>必要な値と元資料へのアクセス。<br>要求を満たす最終成果。</p></div></div>',
        '今回の問い：操作の手掛かりを残せば、長い出力を省けるか。',
        notes='仕事の分担や通信全体を最適化した実験ではない。今回は入力の構成を変える局所比較。',
        refs=('docs/research_objective_20261022.md','docs/cost_profile_20261022.md'))
    slide('実験：同じ途中状態から、３条件を比べる',
        '<div class="diagram">'+design()+'</div><p class="small">後続上限：16生成・12万総トークン・480秒。元のAPI上限と共通前半を計上。<br>'
        '４既知課題×３条件×各１試行。全履歴の対照も新しく実行。整理・一覧の費用も含める。</p>',
        notes='固定８応答後に一度だけ省略し、後のターンはそのまま追加。元の最後の１ターン、エラー、操作コードを残す。復元費用は別記し、無料の運用処理とはしない。',
        refs=('docs/experiments/P33_output_views.md',))
    summary='<table class="compact"><thead><tr><th>条件</th><th>最終成功</th><th>AI呼出し</th><th>後続API</th><th>使用量不明</th></tr></thead><tbody>'
    for a,label in zip(ARMS,NAMES):
        t=totals[a];summary+=f'<tr><td>{label}</td><td>{t["successes"]}/4</td><td>{t["model_calls"]}</td><td>{t["api_requests"]}</td><td>{t["unknown_usage_calls"]}呼出</td></tr>'
    summary+='</tbody></table>'
    slide('結果：初回の短縮と総費用を分ける',
        '<div class="diagram"><img src="figures/input_and_total.svg" style="width:100%;height:250px" alt="初回入力と全体トークンの比較"></div>'+summary,
        notes='左右の軸は別尺度。未知の使用量を含む棒は既知分の下限。不明分をゼロとは扱わない。',
        refs=('reports/P33_comparison.json','reports/P33_cost_profile.json'))
    paired='<table class="results-table"><thead><tr><th>課題</th>'+''.join('<th>'+n+'</th>' for n in NAMES)+'</tr></thead><tbody>'
    for task,label in zip(plan['task_ids'],LABELS):
        paired+='<tr><td>'+label+'</td>'+''.join('<td class="'+('ok' if rows[(task,a)]['success'] else 'miss')+'">'+('成功' if rows[(task,a)]['success'] else '未達')+'</td>' for a in ARMS)+'</tr>'
    paired+='</tbody></table>'
    notes=[]
    for arm,label in zip(ARMS[1:],NAMES[1:]):
        d=gate['decisions'][arm];unknown=not d['all_usage_known_in_pair']
        notes.append(f'{label}：対照の成功を落とした課題 {len(d["baseline_successes_lost"])}件。'+
            ('費用差は不明呼出しがあるため未確定。' if unknown else f'総トークン差 {d["total_token_change"]:+,}。'))
    slide('品質：成功件数だけでは判断しない',paired+
          '<div class="body">'+''.join('<p>'+esc(n)+'</p>' for n in notes)+'</div>'+
          '<p class="small">書出は全履歴がAPI上限、他２方式がトークン上限で未達。<br>早く打ち切られた低費用を、効率よく完了した結果とは扱わない。</p>',
          '４件各１回の結果。品質維持の一般的な証明にはならない。',
          notes='対照で成功した課題を失っていないかを個別に確認する。別課題の成功で相殺しない。',
          refs=('reports/P33_development_gate.json',))
    passed=[n for a,n in zip(ARMS[1:],NAMES[1:]) if gate['decisions'][a]['prespecified_descriptive_gate_passed']]
    headline=('開発用の採否基準を満たした条件：'+'、'.join(passed)+'。') if passed else '今回の２つの省略条件は、開発用の採否基準を満たさなかった。'
    slide('考察：通常方式の効果と、独自の差を分ける',
          '<p class="lead">'+esc(headline)+'</p><div class="body"><p>出力省略と変数一覧は既存の仕組み。<br>結果が良くても、それだけを新規性とはしない。</p>'
          '<p>値との照合だけで省略を選ぶ候補（P34）は、対象23出力中１出力にしか適用できず、追加のモデル比較を見送った。</p>'
          '<p>次は、コードが参照した情報とAPI返却の対応を、保存記録の再生で調べる。読み取りの記録がないことを、不要だとは判定しない。</p></div>',
          '月末投稿へ向けた独自の主張と、未調整課題での確認は未完了。',
          notes='返金は全方式で成功したが呼出しは２／12／４回。成功の同率だけでは費用を説明できない。12確認シナリオは未閲覧のまま。次の計測も独自の制御技術とはまだ確定していない。',
          refs=('docs/P33_findings.md','docs/experiments/P34_output_residency.md'))
    time_rows='<table class="compact"><thead><tr><th>条件</th><th>総入力</th><th>キャッシュ入力</th><th>新規入力処理</th><th>出力</th></tr></thead><tbody>'
    for arm,label in zip(ARMS,NAMES):
        c=cost['by_arm'][arm]['totals'];time_rows+='<tr><td>'+label+'</td>'+''.join(f'<td>{c[k]:,}</td>' for k in ('input_tokens','cached_input_tokens','processed_input_tokens','output_tokens'))+'</tr>'
    time_rows+='</tbody></table>'
    slide('補足：入力トークンと実際の処理量',time_rows+
          '<div class="body"><p>総入力には、再利用されたキャッシュ部分も含む。<br>小さい入力、少ないAPI、短い実時間は別の指標。</p>'
          '<p>使用量が不明な呼出しは、この内訳の外にある。<br>再構成、制御、失敗を含む詳細は元の集計とCSVへ残した。</p></div>',
          notes='キャッシュや時間の内訳は観測値。原因を特定した介入実験や一般的な速度保証ではない。',
          refs=('reports/P33_cost_profile.json',))
    parts=[]
    for i,s in enumerate(slides,1):
        if s['cover']:
            parts.append(f'<section class="slide dark cover"><h1>{s["title"]}</h1><div class="notes">{esc(s["notes"])}</div></section>');continue
        refs=' ／ '.join(f'<a href="{LINK+n}">{esc(n.rsplit("/",1)[-1])}</a>' for n in s['refs'])
        parts.append(f'<section class="slide"><div class="eyebrow">P33 / {i-1:02d}</div><h2>{s["title"]}</h2>'+s['body']+
            (f'<div class="takeaway">{s["take"]}</div>' if s['take'] else '')+
            f'<div class="footer"><span class="sources">{refs}</span><span>{i}/{len(slides)}</span></div><div class="notes">{esc(s["notes"])}</div></section>')
    nav='<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    (output/'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>P33追加検証</title><style>'+STYLE+'</style></head><body>'+''.join(parts)+nav+'<script>'+SCRIPT+'</script></body></html>')
    (output/'slides.json').write_text(json.dumps(slides,ensure_ascii=False,indent=2)+'\n')
    manifest={'pages':len(slides),'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),
              'source_sha256':hashes,'builder_sha256':sha(Path(__file__)),
              'all_twelve_results_included':True,'visual_reviewed':False}
    (output/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


def export(output):
    chrome='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    with tempfile.TemporaryDirectory(prefix='p33-report-') as profile:
        base=[chrome,'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
              '--disable-background-networking','--disable-extensions','--user-data-dir='+profile,
              '--virtual-time-budget=4000','--run-all-compositor-stages-before-draw']
        uri=(output/'index.html').resolve().as_uri()
        result=subprocess.run(base+['--dump-dom',uri],capture_output=True,text=True,timeout=60)
        if result.returncode:raise RuntimeError('layout process failed')
        match=re.search(r'<script id="layout-checks" type="application/json">(.*?)</script>',result.stdout,re.S)
        if not match:raise ValueError('layout not measured')
        layout=json.loads(html.unescape(match.group(1)))
        (output/'layout_checks.json').write_text(json.dumps(layout,ensure_ascii=False,indent=2)+'\n')
        if layout['errors']:raise ValueError(layout['errors'])
        result=subprocess.run(base+['--no-pdf-header-footer','--print-to-pdf='+str((output/(STEM+'.pdf')).resolve()),uri],capture_output=True,text=True,timeout=60)
        if result.returncode:raise RuntimeError('PDF export failed')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo-root',type=Path,default=ROOT)
    p.add_argument('--output',type=Path,default=ROOT/'materials/20261022_p33');p.add_argument('--pdf',action='store_true');a=p.parse_args()
    print(json.dumps(build(a.repo_root,a.output)))
    if a.pdf:export(a.output)
