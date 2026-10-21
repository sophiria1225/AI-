"""Offline, source-linked progress slides. Only audited aggregate reports are read.

This is a presentation document, not an experimental controller. Final rendering
is scheduled separately so late verified results can be included without reading
an ongoing model trace or replacing missing measurements with invented values.
"""
import argparse
import csv
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LINK = 'https://github.com/sophiria1225/AI-/blob/main/'
JST = dt.timezone(dt.timedelta(hours=9))
NAVY, TEAL, ORANGE, GRAY = '#172c43', '#167a78', '#c95c33', '#91a0aa'


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def esc(s): return html.escape(str(s))
def num(n): return f'{n:,}'


class Evidence:
    def __init__(self, root):
        self.root, self.hashes = root, {}

    def read(self, name):
        p=self.root/name
        self.hashes[name]=sha(p)
        data=json.loads(p.read_text())
        for name, expected in data.get('source_hashes',{}).items():
            p=self.root/name
            if p.is_file() and sha(p)!=expected:
                raise ValueError('changed source '+name)
        if data.get('pending') or data.get('audit_errors'):
            raise ValueError('pending or unaudited report '+str(p))
        return data


def svg(inner, w=1120, h=360, label='説明図'):
    return (f'<svg role="img" aria-label="{esc(label)}" viewBox="0 0 {w} {h}" '
            'xmlns="http://www.w3.org/2000/svg"><defs>'
            '<marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">'
            f'<path d="M0,0 L8,3 L0,6" fill="{TEAL}"/></marker></defs>'+inner+'</svg>')


def txt(x,y,s,size=22,color=NAVY,weight=500,anchor='start'):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}">{esc(s)}</text>'


def line(x1,y1,x2,y2,color=TEAL,width=3,arrow=False,dash=False):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"'+(' marker-end="url(#arrow)"' if arrow else '')+(' stroke-dasharray="8 7"' if dash else '')+'/>'


def circle(x,y,r,fill,stroke='none'):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="3"/>'


def scope_diagram():
    s=''
    for x,heading,sub,path in [(135,'情報を集める','文書・要求・観測',
        '<path d="M110 120h46l18 18v64h-64z M156 120v20h18 M122 155h35 M122 170h35 M122 185h26"/>'),
        (545,'処理して変更する','コード・API・ファイル',
        '<path d="m524 145-22 18 22 18m42-36 22 18-22 18m-14-43-14 60"/>'),
        (955,'完了を確かめる','要件と最終状態',
        '<path d="M923 135h64v62h-64z m12 26 12 12 28-31"/>')]:
        s+=circle(x+8,160,69,'#e9efea')+f'<g fill="none" stroke="{TEAL}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round">{path}</g>'
        s+=txt(x+8,270,heading,29,weight=700,anchor='middle')+txt(x+8,310,sub,21,anchor='middle')
    s+=line(235,160,438,160,arrow=True)+line(648,160,850,160,arrow=True)
    return svg(s,label='複数工程をつないで仕事を完了する')


def loop_diagram():
    s=f'<path d="M275 92 C470 4 699 4 845 92 M970 164 C1060 270 760 380 620 315 M480 315 C300 376 80 195 155 172" fill="none" stroke="{TEAL}" stroke-width="7" marker-end="url(#arrow)"/>'
    for x,y,label,sub in [(220,120,'LLM','次に何をするか'),(910,120,'ツール','読取・計算・変更'),(550,302,'状態・履歴','何が分かり、何が終わったか')]:
        s+=circle(x,y,66,'#e8eee7')+txt(x,y+9,label,27,weight=700,anchor='middle')
        s+=txt(x,y+100,sub,21,anchor='middle')
    s+=txt(558,119,'ハーネスが制御する範囲',28,weight=700,anchor='middle')
    s+=txt(558,164,'入力の構成・操作・状態保存・検証・停止',21,anchor='middle')
    return svg(s,h=435,label='LLMとツールと状態を接続するハーネスの循環')


def architecture():
    s=txt(5,26,'上：モデルが個々のAPI引数を出力',23,weight=700)
    for x,label in [(85,'LLM'),(345,'読取API'),(625,'LLM'),(940,'更新API')]:
        s+=circle(x,93,44,'#e8eee7')+txt(x,101,label,20,weight=700,anchor='middle')
    for a,b in [(129,299),(390,579),(670,894)]:s+=line(a,93,b,93,arrow=True)
    s+=txt(490,150,'取得した値を、履歴から次の引数へ',19,anchor='middle')
    s+=line(5,183,1115,183,color='#d7ddd7',width=1)
    s+=txt(5,224,'下：コード内で取得→計算→操作をつなぐ',23,weight=700)
    s+=circle(85,306,44,'#e8eee7')+txt(85,314,'LLM',20,weight=700,anchor='middle')
    s+='<rect x="235" y="252" width="655" height="108" rx="54" fill="#e8eee7"/>'
    for x,label in [(337,'call_api()'),(565,'集合・計算'),(785,'call_api()')]:s+=txt(x,312,label,22,weight=700,anchor='middle')
    s+=line(129,306,235,306,arrow=True)+line(423,306,479,306,arrow=True)+line(649,306,705,306,arrow=True)
    s+=circle(1015,306,44,'#e8eee7')+txt(1015,314,'結果',20,weight=700,anchor='middle')+line(890,306,966,306,arrow=True)
    s+=txt(563,399,'Python内で値を保持。各APIの費用と結果は別々に記録する。',21,anchor='middle')
    return svg(s,h=420,label='ネイティブAPI呼出とコード実行型のデータ経路比較')


def photo_chart():
    s=''
    for top,count,name,stats in [(45,27,'上限80：未達','80 API / 185,739 token'),(195,42,'上限160：成功','97 API / 361,169 token')]:
        s+=txt(5,top+23,name,25,weight=700)+txt(5,top+61,stats,18)
        for i in range(42):
            x,y=367+(i%14)*44,top+(i//14)*34
            color=TEAL if i<count else '#e1dcd1'
            s+=f'<rect x="{x}" y="{y}" width="30" height="23" rx="4" fill="{color}"/>'
        s+=txt(1088,top+59,f'{count}/42',29,TEAL,700,'end')
    s+=txt(367,337,'■ 移動の返却あり　　淡色：移動の返却なし',18)
    return svg(s,h=370,label='写真42件のうち上限80では27件、160では42件移動')


def guidance_chart(pairs6,pairs4):
    s=''
    for x,pair,n,label in [(30,pairs6,6,'同じ６開発課題'),(625,pairs4,4,'別の４開発課題')]:
        s+=txt(x,25,label,26,weight=700)
        for j,(key,name) in enumerate([('baseline','従来の指示'),('guided','一般指示を補足')]):
            successes=pair['totals'][key]['successes']
            y=90+j*106
            s+=txt(x,y,name,22)
            for i in range(n):s+=circle(x+23+i*58,y+39,16,TEAL if i<successes else '#dedbd1')
            s+=txt(x+450,y+47,f'{successes}/{n}',36,TEAL,700,'end')
    s+=txt(30,335,'同じモデル・課題・予算。時刻・全ページ・連絡先・完了形式などを一括で案内。',21)
    return svg(s,h=365,label='一般指示追加前後の成功件数、六課題で二から六、四課題で二から三')


def bar_chart(rows, baseline='既存API型', other='コード実行型'):
    s=txt(5,23,'全入力＋全出力トークン（小さいほど少ない）',23,weight=700)
    maximum=max([r[a]['known_total_tokens'] for r in rows for a in ('baseline','code')]+[1])
    labels=['写真整理','共有・依頼','返金','曲情報の書出']
    for i,(r,label) in enumerate(zip(rows,labels)):
        y=65+i*77;s+=txt(0,y+24,label,21)
        for j,(a,color) in enumerate([('baseline',GRAY),('code',TEAL)]):
            v=r[a]['known_total_tokens'];w=650*v/maximum;yy=y+j*28
            s+=f'<rect x="210" y="{yy}" width="{w:.2f}" height="20" rx="3" fill="{color}"/>'
            mark='成功' if r[a]['success'] else '未達'
            s+=txt(226+w,yy+17,f'{v:,}  {mark}',17,color)
    s+=txt(210,399,f'灰：{baseline}　青緑：{other}。全４件・各１seed。',18)
    return svg(s,h=425,label='同じ四課題でAPI呼出型とコード型の全トークンと最終成否を比較')


STYLE = r'''
:root{--ink:#172c43;--teal:#167a78;--rust:#c95c33;--paper:#f6f4ed;--muted:#596c79}
*{box-sizing:border-box}html,body{margin:0;background:#1b2c3c;color:var(--ink);font-family:"Hiragino Sans","Yu Gothic",sans-serif;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.slide{position:relative;width:1280px;height:720px;padding:48px 64px 65px;background:var(--paper);overflow:hidden;margin:20px auto;box-shadow:0 10px 30px #07172555}
.slide.dark{background:var(--ink);color:var(--paper)}.eyebrow{color:var(--teal);font-size:16px;letter-spacing:2px;font-weight:700;margin-bottom:17px}.dark .eyebrow{color:#92d9ca}
h1,h2,h3,p{margin:0}h1{font-size:61px;line-height:1.35;letter-spacing:-1px}h2{font-size:39px;line-height:1.38;letter-spacing:-.8px}h3{font-size:27px;line-height:1.5;margin-bottom:14px}
.lead{font-size:25px;line-height:1.65;margin-top:19px;max-width:1100px}.body{margin-top:22px;font-size:22px;line-height:1.65}.body p+p{margin-top:18px}.muted{color:var(--muted)}.dark .muted{color:#b5c9d2}.teal{color:var(--teal)}.rust{color:var(--rust)}.dark .teal{color:#92d9ca}.small{font-size:18px;line-height:1.6}.tiny{font-size:15px;line-height:1.6}
.takeaway{position:absolute;left:64px;right:64px;bottom:83px;padding:14px 19px;background:#e4ece3;border-left:5px solid var(--teal);font-size:22px;line-height:1.48}.dark .takeaway{background:#243d52;border-color:#92d9ca}
.footer{position:absolute;bottom:22px;left:64px;right:64px;border-top:1px solid #c6cec5;padding-top:12px;display:flex;justify-content:space-between;gap:25px;font-size:13px;color:var(--muted);line-height:1.35}.dark .footer{border-color:#5b7080;color:#b5c9d2}.footer .sources{max-width:1060px}a{color:inherit;text-decoration-color:#8caa9b;text-underline-offset:3px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:50px;margin-top:30px}.three{display:grid;grid-template-columns:repeat(3,1fr);gap:30px;margin-top:35px}.col{border-top:4px solid var(--teal);padding-top:19px}.col .n{font-size:62px;line-height:1.15;font-weight:700;color:var(--teal)}.dark .col{border-color:#92d9ca}.dark .col .n{color:#92d9ca}
.badge{display:inline-block;border-radius:18px;padding:5px 12px;font-size:15px;font-weight:700;background:#e4ece3;color:var(--teal);margin-right:8px}.badge.warn{background:#f3e6db;color:var(--rust)}.badge.wait{background:#e2e4e3;color:#596c79}
ul{padding-left:1.1em;margin:16px 0 0}li{padding-left:5px;margin-bottom:11px}.diagram{margin-top:18px}.diagram svg{display:block;width:100%;max-height:425px;font-family:inherit}.diagram.tight svg{max-height:360px}
table{border-collapse:collapse;width:100%;font-size:21px;line-height:1.5;margin-top:24px}th{font-weight:700;text-align:left;border-bottom:2px solid #748b88;padding:11px 15px;background:#e8eee7}td{border-bottom:1px solid #ced7cd;padding:14px 15px}td.num{text-align:right;font-variant-numeric:tabular-nums}th:first-child,td:first-child{padding-left:6px}.compact td,.compact th{padding-top:10px;padding-bottom:10px;font-size:19px}
.big{font-size:88px;font-weight:800;line-height:1.05;letter-spacing:-3px}.metric{padding-top:22px}.metric .caption{margin-top:14px;font-size:23px;line-height:1.5}.timeline{display:grid;grid-template-columns:repeat(4,1fr);gap:24px;margin-top:45px}.timeline>div{border-top:5px solid var(--teal);padding-top:18px}.date{font-size:36px;font-weight:800;color:var(--teal);margin-bottom:14px}.progressbar{height:8px;width:100%;position:absolute;bottom:0;left:0;background:#cfd9d0}.progressbar i{display:block;height:100%;background:var(--teal)}
.subtle{border-top:1px solid #c5d1c8;margin-top:20px;padding-top:17px}.notes{display:none}#nav{position:fixed;right:20px;bottom:14px;display:flex;gap:7px;align-items:center;background:#102333e8;color:#fff;padding:8px 13px;border-radius:8px;z-index:10;font-size:14px}button{border:1px solid #7c9a9e;background:transparent;color:inherit;border-radius:4px;padding:5px 11px;cursor:pointer}#speaker{position:fixed;left:30px;bottom:30px;max-width:820px;background:#142a3ef0;color:white;padding:24px;font-size:20px;line-height:1.6;z-index:20;border-radius:9px;display:none}body.present .slide{display:none;margin:0;box-shadow:none}body.present .slide.active{display:block;position:absolute;left:50%;top:50%;transform:translate(-50%,-50%) scale(var(--scale,1));transform-origin:center}body.overview .slide{display:block}body.overview #nav{position:fixed}
@media print{@page{size:1280px 720px;margin:0}html,body{background:white}.slide,body.present .slide,body.present .slide.active{display:block!important;position:relative!important;top:auto!important;left:auto!important;transform:none!important;margin:0!important;box-shadow:none!important;break-after:page;page-break-after:always}.slide:last-of-type{break-after:auto;page-break-after:auto}#nav,#speaker{display:none!important}}
'''

SCRIPT=r'''
const slides=[...document.querySelectorAll('.slide')];let current=Math.max(0,Math.min(slides.length-1,(+location.hash.slice(1)||1)-1));
const label=document.querySelector('#count');function fit(){document.body.style.setProperty('--scale',Math.min(innerWidth/1280,innerHeight/720));}function show(n){current=Math.max(0,Math.min(slides.length-1,n));slides.forEach((s,i)=>s.classList.toggle('active',i===current));label.textContent=`${current+1} / ${slides.length}`;history.replaceState(null,'','#'+(current+1));document.querySelector('#speaker').innerHTML=slides[current].querySelector('.notes').innerHTML;fit();}
document.querySelector('#prev').onclick=()=>show(current-1);document.querySelector('#next').onclick=()=>show(current+1);document.querySelector('#all').onclick=()=>{document.body.classList.toggle('present');document.body.classList.toggle('overview');};document.querySelector('#note').onclick=()=>{let e=document.querySelector('#speaker');e.style.display=e.style.display==='block'?'none':'block';};document.querySelector('#print').onclick=()=>print();addEventListener('resize',fit);addEventListener('keydown',e=>{if(['ArrowRight','PageDown',' '].includes(e.key)){e.preventDefault();show(current+1);}if(['ArrowLeft','PageUp'].includes(e.key)){e.preventDefault();show(current-1);}if(e.key==='Home')show(0);if(e.key==='End')show(slides.length-1);if(e.key==='n')document.querySelector('#note').click();if(e.key==='o')document.querySelector('#all').click();});
document.fonts.ready.then(()=>{document.body.className='overview';const errors=[];slides.forEach((s,i)=>{const a=s.getBoundingClientRect();for(const e of s.querySelectorAll('h1,h2,.lead,.body,.two,.three,.diagram,.takeaway,table,.timeline,.footer')){const b=e.getBoundingClientRect();if(b.left<a.left+30||b.right>a.right-30||b.bottom>a.bottom-15||b.top<a.top+20)errors.push({slide:i+1,tag:e.className||e.tagName,reason:'outside-slide'});}const footer=s.querySelector('.footer');const f=footer.getBoundingClientRect();for(const e of s.children){if(e===footer||e.classList.contains('notes')||e.classList.contains('progressbar'))continue;const b=e.getBoundingClientRect();if(b.height&&b.bottom>f.top-8)errors.push({slide:i+1,tag:e.className||e.tagName,reason:'overlaps-footer'});}const take=s.querySelector('.takeaway');if(take){const t=take.getBoundingClientRect();for(const e of s.children){if(e===take||e===footer||e.classList.contains('notes')||e.classList.contains('progressbar'))continue;const b=e.getBoundingClientRect();if(b.height&&b.bottom>t.top-12)errors.push({slide:i+1,tag:e.className||e.tagName,reason:'overlaps-takeaway'});}}});const el=document.createElement('script');el.id='layout-checks';el.type='application/json';el.textContent=JSON.stringify({pages:slides.length,errors});document.body.appendChild(el);document.body.className='present';show(current);});
'''


def build(root, output, draft=False):
    e=Evidence(root)
    p6=e.read('reports/P22_P24_paired_comparison.json')
    p4=e.read('reports/P18_P25_paired_comparison.json')
    p26=e.read('reports/P26_photo_budget_summary.json')
    review26=e.read('reports/P26_interpretation.json')
    photo=e.read('reports/P26_public_trace_diagnostics.json')
    replay=e.read('reports/completion_replay_results_20261021.json')
    memory=[e.read(f'reports/P{i}_final_measurements.json') for i in (11,12,13,14)]
    e.read('configs/models/minimax_m3_iq4_selection.json')
    if not review26['all_one_reviewed'] or len(p6['pairs'])!=6 or len(p4['pairs'])!=4:
        raise ValueError('missing completed comparison')
    code=None
    if (root/'reports/P27_comparison.json').exists():
        code=e.read('reports/P27_comparison.json')
        if not code.get('all_four_reviewed') or len(code['pairs'])!=4:
            raise ValueError('P27 is not fully reviewed')
    timestamp=dt.datetime.now(JST).strftime('%Y-%m-%d %H:%M JST')
    slides=[]
    def add(section,title,body,notes,refs=(),dark=False,takeaway=None):
        slides.append(dict(section=section,title=title,body=body,notes=notes,refs=refs,dark=dark,takeaway=takeaway))

    add('RESEARCH PROGRESS / 2026.10.22', 'AIハーネスは、<br>どこに判断を残すべきか',
        '<p class="lead">情報の保持・受け渡し・実行方法を変え、<br>仕事の完了と総費用への影響を調べる。</p>'
        '<div class="three"><div class="col"><span class="badge">対象</span><h3>状態を変える<br>複数工程の仕事</h3></div>'
        '<div class="col"><span class="badge">現在地</span><h3>通常方式を校正し、<br>追加技術の必要性を検証</h3></div>'
        '<div class="col"><span class="badge warn">投稿目標</span><h3>10月31日<br>IEICE・４ページ</h3></div></div>',
        '題目は進捗報告用の仮題です。研究目的はモデルの外側の情報と実行の設計です。普通のコード実行や指示改善を新技術とは扱いません。採録ではなく投稿完了が期限です。',dark=True)
    add('01 / 社会背景','必要なのは、複数の工程を最後まで終えること',
        '<p class="lead">調べる・計算する・変更する・確かめる。<br>一つずつ正しくても、全体の要件が残ることがある。</p><div class="diagram tight">'+scope_diagram()+'</div>',
        '例は資料調査、帳票の集計、ファイル整理などです。市場規模や普及率を主張するスライドではなく、なぜ最終状態の評価が必要かを説明します。AppWorldも複数アプリの操作と最終状態・意図しない変更を評価します。',
        [('AppWorld：複数アプリ・最終状態による評価','https://arxiv.org/abs/2407.18901')])
    add('02 / 技術背景','モデルの外側にも、結果を変える設計がある',
        '<div class="diagram">'+loop_diagram()+'</div>',
        'ハーネスは入力の構成、ツール実行、状態・履歴の保持、検証と停止を接続する基盤と定義します。現在は主に単一実行役と補助処理の比較です。複数作業役の再編効果を測った成果ではありません。',
        [('CoALA：記憶・行動・意思決定の構成','https://arxiv.org/abs/2309.02427')])
    add('03 / 目的','同じモデルで、何を外側の設計で改善できるか',
        '<div class="three"><div class="col"><div class="n">01</div><h3>完了できるか</h3><p class="body">要件を満たす最終状態を、実行とは別に評価する。</p></div>'
        '<div class="col"><div class="n">02</div><h3>費用に見合うか</h3><p class="body">記憶生成・調整・失敗も含め、トークンと時間を測る。</p></div>'
        '<div class="col"><div class="n">03</div><h3>なぜ変わったか</h3><p class="body">指示、情報保持、操作形式、予算を切り分ける。</p></div></div>',
        '成功率だけが高くても、予算や情報が増えていれば内部機構の効果とはいえません。全費用と失敗を含め、同じ課題の対応比較をします。',
        [('研究と評価の範囲',LINK+'docs/letter_evaluation_scope_20261021.md')],takeaway='目標：条件をそろえた比較で、必要な機構と不要な追加処理を示す。')
    add('04 / 当初案と現在地','「作業の再編」の前に、通常方式の失敗を確かめる',
        '<div class="two"><div class="col"><span class="badge wait">当初の新提案候補・未評価</span><h3>作業間依存に応じた実行単位の再編</h3><p class="body">分担の継続・情報共有・中央調整・作業集約を、同じ途中状態から比較する。</p></div>'
        '<div class="col"><span class="badge">現在の実験</span><h3>情報保持とデータ処理の比較基準を整える</h3><p class="body">単一役、一般指示、API予算、コード実行を確認し、追加機構が必要な現象を探す。</p></div></div>',
        '当初案の研究目的は引き継いでいますが、今ある実験はその仮説を直接実証していません。作業再編を実装済みの提案として紹介しません。基準の弱さで見かけの新規性を作らないために現在の対照を実施しています。',
        [('現在の成果と未確定事項',LINK+'README.md')],takeaway='現在の結果だけで、マルチエージェント再編の有効性は主張できない。')
    add('05 / 既存との差分','既にある機能を、独自の技術と数えない',
        '<table class="compact"><thead><tr><th>先行研究・仕組み</th><th>既に扱われていること</th><th>今回の扱い</th></tr></thead><tbody>'
        '<tr><td>CodeAct / ICML 2024</td><td>Pythonで行動を統合し、実行結果から修正</td><td>通常コード型の比較相手</td></tr>'
        '<tr><td>FOCUS / 著者公開原稿</td><td>今後の作業に必要な情報の選択・保持</td><td>共通環境向けに接続した比較</td></tr>'
        '<tr><td>SelfCompact / 著者公開原稿</td><td>コンテキスト整理とキャッシュ費用</td><td>費用の差を新原理としない</td></tr>'
        '<tr><td>ECT・CFRC / 著者公開原稿</td><td>証跡・残作業・引き継ぎ時の制御</td><td>参照・契約の追加だけでは弱い</td></tr></tbody></table>',
        'CodeActは正式会議録を確認済みです。他の近接原稿は公開状態や確認範囲を文献記録に残しています。ここは機能の重なりの整理で、全方式の完全再現や網羅的な新規性調査の完了を意味しません。',
        [('CodeAct', 'https://proceedings.mlr.press/v235/wang24h.html'),('近接研究と確認範囲',LINK+'docs/output_access_review_20261021.md'),('契約・完全性の重複',LINK+'docs/collection_scope_review_20261021.md')])
    add('06 / 新提案技術の現在地','独自方式の有効性は、まだ確立していない',
        '<div class="two"><div class="col"><span class="badge">実装・確認済み</span><h3>比較と原因分析の基盤</h3><p class="body">公開APIの接続／状態保存と再生／全費用の記録／独立評価／コード実行型。</p><p class="small muted subtle">いずれも、それだけを新規性とはしない。</p></div>'
        '<div class="col"><span class="badge warn">追加で示す必要がある</span><h3>既存方式では残る問題と、固有の改善</h3><p class="body">新しい操作規則を一つ固定し、強い比較相手・同じ予算・未調整課題で確かめる。</p></div></div>',
        '独自方式が確立したように見せるスライドは作りません。技術の組合せ自体ではなく、既存にない規則や説明可能な新しい知見が必要です。P16の候補は観測根拠がなく見送っています。',
        [('見送った候補と理由',LINK+'docs/P16_findings.md'),('原稿の現状',LINK+'papers/202610_letter/current_status.json')],
        takeaway='今の成果は検証基盤と切り分け。新規性・採録可能性の証明はこれから。')
    add('07 / 実験環境','同じモデル・同じ環境で、構成差を比較する',
        '<div class="two"><div><table class="compact"><tbody><tr><td>計算機</td><td>Mac Studio / M3 Ultra<br>256 GiB RAM</td></tr><tr><td>モデル</td><td>MiniMax-M3 / IQ4_XS<br>重み約229.7 GB・版固定</td></tr><tr><td>推論</td><td>llama.cpp / 64K context<br>KV q8・１スロット</td></tr></tbody></table></div>'
        '<div><table class="compact"><tbody><tr><td>環境</td><td>AppWorld 0.1.3.post1<br>復元可能な模擬アプリ</td></tr><tr><td>１課題の上限</td><td>45万token・80 LLM呼出<br>30分・出力4,096 token</td></tr><tr><td>評価</td><td>終了後の別プロセス<br>正解をモデルへ戻さない</td></tr></tbody></table></div></div>',
        '現物の計測は256 GiBのメモリで、最初の相談にあったSSD256GBという申告とは区別します。重みは229.7GBの保存サイズで、ピーク推論メモリではありません。１スロットの実験なので物理並列化の速度向上を示していません。',
        [('モデル・版と選定理由',LINK+'configs/models/minimax_m3_iq4_selection.json'),('実行条件',LINK+'configs/P27_code_comparison_v01.json')])
    add('08 / 実験の進め方','実験を増やす前に、次へ進む根拠を確認する',
        '<table class="compact"><thead><tr><th>切り分けたいこと</th><th>比較</th><th>ここまでの判断</th></tr></thead><tbody>'
        '<tr><td>履歴を減らす利益</td><td>全履歴／直近／保持／台帳</td><td>今回の設定では品質と総費用を両立せず</td></tr>'
        '<tr><td>通常の環境案内の不足</td><td>一般指示の前後</td><td>同じ６件：2→6成功、別４件：2→3成功</td></tr>'
        '<tr><td>完了形式の影響</td><td>同じ状態＋回答あり／省略</td><td>既知１課題で合否が変化</td></tr>'
        '<tr><td>API上限の影響</td><td>写真整理１件：80／160</td><td>最初の80操作は同じ、追加操作で成功</td></tr>'
        '<tr><td>値の受け渡しの負担</td><td>個別API／取得から操作までのコード</td><td>'+('全４件の結果・監査を確認済み' if code else '固定した全４件の実行・監査を進行中')+'</td></tr></tbody></table>',
        '実験番号は追跡のために残しますが、説明では問いを中心に整理します。成功した課題も残し、未閲覧12シナリオを調整に使わないことを固定しています。',
        [('実験と判断の全記録',LINK+'docs/decision_log.md')])

    rows=[]
    for label,d in zip(['全履歴','直近履歴','FOCUSに基づく保持','旧・作業台帳'],memory):
        success=sum(r['evaluation'].get('official_success') is True for r in d['trials'])
        time=sum(r['wall_seconds'] for r in d['trials'])/60
        token=num(d['known_total_tokens'])+(' ＋不明' if d['unknown_usage_calls'] else '')
        rows.append(f'<tr><td>{label}</td><td>{success}/4</td><td class="num">{token}</td><td class="num">{time:.1f}分</td></tr>')
    add('09 / 履歴保持の比較結果','入力が短くても、システム全体が安くなるとは限らない',
        '<table class="compact"><thead><tr><th>保持方法</th><th>成功</th><th>全役割の既知トークン</th><th>実行時間</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table>'
        '<p class="small subtle">旧台帳は出典の形式契約に不整合があり、後に修正。<br>FOCUSは共通環境向けの接続で、原論文の完全再現ではない。</p>',
        '４課題１seedの結果です。FOCUSの途中中断試行52,285既知トークン＋不明１要求は表の完了cohortとは別に保存しています。全履歴との一般的な順位は主張しません。旧台帳には実装上の不整合があるため、保持という原理の限界と断定しません。',
        [('費用内訳と限界',LINK+'docs/P11_P14_inference_costs.md'),('台帳の修正比較',LINK+'docs/P17_findings.md')])
    add('10 / 通常指示をそろえた結果','新機構を入れる前に、基準の成績が変わった',
        '<div class="diagram">'+guidance_chart(p6,p4)+'</div>',
        '公式の一般案内にある時刻、連絡先、全ページ、行動課題の完了形式等を補いました。複数の案内を一括で追加したため、個々の文の因果効果は分離していません。これを新方式の成功率とは呼びません。',
        [('６課題：全結果',LINK+'docs/P24_findings.md'),('４課題：全結果',LINK+'docs/P25_findings.md')])
    add('11 / 完了形式だけの対照','同じ成果物でも、完了APIの形式で合否が変わった',
        '<table><thead><tr><th>記録済み前半の再生</th><th>回答文あり</th><th>回答文を省略</th></tr></thead><tbody>'
        '<tr><td>一般指示を補う前の操作系列</td><td class="rust">未達</td><td class="teal">成功</td></tr>'
        '<tr><td>一般指示を補った後の操作系列</td><td class="rust">未達</td><td class="teal">成功</td></tr></tbody></table>'
        '<div class="two"><div><h3>４条件とも、完了直前のDBは同一</h3><p class="small">公開返却と保存状態のハッシュを照合。<br>LLM追加０、模擬API要求118。</p></div><div><h3>公開仕様に沿った影響</h3><p class="small">行動依頼では回答文を省く規則がある。<br>評価器の不具合や独自手法の効果とはしない。</p></div></div>',
        '同じ１課題について２前半×２完了形式の４セルを事前に固定しました。４独立課題の実験ではありません。元の結果を置き換えたり、合格する回答を探索したりしていません。',
        [('事前条件・全結果',LINK+'docs/completion_replay_findings_20261021.md')])
    add('12 / API予算だけの対照','写真整理の残り15件は、追加操作で完了した',
        '<div class="diagram">'+photo_chart()+'</div>',
        '同じモデル・指示・道具・seedです。最初の80 APIの名前、引数、返却が一致しています。42件の個別読取りと移動が全戦略の最小費用だとは考えません。１既知課題の事後診断で、追加予算の一般的な効果や最適値は示していません。',
        [('１件の全結果・費用・限界',LINK+'docs/P26_findings.md')])
    add('13 / 新しく接続した比較アーキテクチャ','コード内で、取得した値を次の操作へ渡す',
        '<div class="diagram">'+architecture()+'</div>',
        'これはCodeActと同種の既存原理を共通環境へ接続した比較対象です。Python内で公開APIを取得し、集合やCSVとして処理して次のAPIへ渡せます。１プログラム内の複数APIを１件と数えず、全費用と記録を残します。コード間の変数は保持しない実装差があります。',
        [('実装仕様と原方式との差',LINK+'docs/experiments/P27_code_execution.md'),('CodeAct', 'https://proceedings.mlr.press/v235/wang24h.html')])
    if code:
        add('14 / コード実行型の結果','同じ４課題で、成否と全費用を照合する',
            '<div class="diagram">'+bar_chart(code['pairs'])+'</div>',
            code.get('speaker_summary','全４課題終了後に費用と最終評価を照合した。既知課題１seedの開発比較で、通常コード実行の原理を新規性とはしない。'),
            [('全結果と実装差',LINK+'docs/P27_findings.md')])
    else:
        add('14 / コード実行型の結果','全４件の評価・監査が終わるまで、結論を留保する',
            '<div class="two"><div class="col"><span class="badge">固定済み</span><h3>４既知課題・１seed</h3><p class="body">写真は160 API、他３件は80 API。<br>モデル・トークン・時間は比較相手と同じ。</p></div><div class="col"><span class="badge wait">この資料の集計時点</span><h3>確定した比較報告は未収録</h3><p class="body">実行中・監査中の数字を、完成した成績へ置き換えない。</p></div></div>',
            'このページは全４件を監査した報告がまだない場合の表示です。資料の生成時点とGitHubの実行状態を確認します。未収録を失敗ゼロや成功扱いにはしません。',
            [('自動進捗・Issue132','https://github.com/sophiria1225/AI-/issues/132')],takeaway='確定済みの全件報告が保存されたら、直前の生成時にこのページへ反映する。')
    add('15 / 考察','失敗の観測と、追加機構の必要性は分ける',
        '<div class="three"><div class="col"><h3>指示で解消する失敗</h3><p class="body">元の低成績だけでは、記憶・ゲート・分担変更が必要だとはいえない。</p></div><div class="col"><h3>予算で止まる処理</h3><p class="body">未完了をすべて情報欠落やハルシネーションへまとめない。</p></div><div class="col"><h3>正解でも残る未確認</h3><p class="body">57曲中56曲の詳細取得で正解した例。正解と網羅的な確認は別。</p></div></div>',
        '57曲の例は未確認の１曲が誤答を起こした実例ではありません。公開一覧には曲の長さがなく、未確認を一覧で既に読めたとみなすこともできません。これだけで全取得を強制する制御を提案するのは早計です。',
        [('成功と網羅性',LINK+'docs/P24_findings.md'),('一律の全取得を採らない理由',LINK+'docs/collection_frontier_findings_20261021.md')],takeaway='改善を確認できた要因から順に閉じ、残る問題にだけ新しい処理を加える。')
    add('16 / 現在の限界','まだ言えないことを、実験結果の隣に置く',
        '<div class="two"><div><h3>一般性の限界</h3><ul class="body"><li>主に１モデル・各条件１seed。</li><li>既知の少数開発課題を繰り返し利用。</li><li>別モデル・別分野への転用は未確認。</li></ul></div><div><h3>技術的主張の限界</h3><ul class="body"><li>再編の固有効果は未測定。</li><li>通常コード型にも提示方法などの実装差。</li><li>独自方式の新規性・有効性は未確定。</li></ul></div></div>',
        'この研究では12シナリオを調整から分離し、要求文を未閲覧にしています。ただしモデルの学習汚染がないことや公式テストと同じことを意味しません。実装を完成させただけで論文の中心結果ができたとは扱いません。',
        [('確認用シナリオの分離',LINK+'docs/letter_scenario_reservation_20261021.md')],takeaway='未閲覧12シナリオは、方式・閾値・比較条件を固定してから使う。')
    add('17 / 今後の実験','次は、通常方式でも残る一つの問題に絞る',
        '<div class="three"><div class="col"><div class="n">1</div><h3>コード型との比較を閉じる</h3><p class="body">失敗だけでなく成功・全費用・実装差を確認する。</p></div><div class="col"><div class="n">2</div><h3>新しい規則を一つ固定</h3><p class="body">既存研究との機能差、適用条件、悪影響の比較を定める。</p></div><div class="col"><div class="n">3</div><h3>未調整課題で確認</h3><p class="body">同じ予算の強い基準、単純規則、提案を比較する。</p></div></div>',
        '新規性を探すために無制限に実験を増やす計画ではありません。次の比較から残る現象を一つ選び、機構と評価を固定します。追加価値がなければ提案の優位を主張しない判断も必要です。',
        [('今後の判断と課題',LINK+'docs/task_board.md')],takeaway='成果の形：新しい制御規則、または条件を切り分けた新しい実証知見。')
    add('18 / レターの日程と判断','月末投稿へ、10月23日に中心となる主張を固定する',
        '<div class="timeline"><div><div class="date">10/23</div><h3>主比較・あらまし</h3><p class="small">主張、最も近い先行研究、主要図表を決める。</p></div><div><div class="date">10/25</div><h3>追加確認を終了</h3><p class="small">必要な対照と限界確認に絞り、機能追加を止める。</p></div><div><div class="date">10/29–30</div><h3>４ページ原稿</h3><p class="small">本文・図・引用・公式様式・著者情報を確認する。</p></div><div><div class="date">10/31</div><h3>投稿完了</h3><p class="small">採録時期は査読に依存。投稿と採録を区別する。</p></div></div>',
        '現時点では中心となる新規性と確認結果が未確定なので、間に合うとは保証できません。公式IEICEクラスの取得と実際の４ページ組版、著者情報も未完了です。10月23日に新規性と主要結果が固まらなければ、予定は高リスクになります。',
        [('投稿準備の現状',LINK+'papers/202610_letter/current_status.json')],takeaway='現状：投稿準備は高リスク。新規性と確認実験が、日程の最も大きな制約。')
    add('19 / 進捗報告の結論','作った基盤と、論文に必要な成果を区別する',
        '<div class="two"><div class="col"><h3>ここまでに得られたもの</h3><p class="body">比較可能な実行基盤。<br>一般指示・完了形式・API上限の切り分け。<br>普通のコード実行を含む比較相手。</p></div><div class="col"><h3>これから得るべきもの</h3><p class="body">既存方式を超える必要性。<br>新しい規則または実証知見。<br>同じ予算・未調整課題での裏づけ。</p></div></div>',
        '目的は、同じモデルにどの情報と責任を持たせ、どこを実行基盤が担うべきかを明らかにすることです。次の実験で研究上の差を一つに絞ります。通常機能を繋いだ実装を、そのまま新規技術として発表しません。',dark=True,
        takeaway='目指すのは、構成が効く条件と壊れる条件を説明できるハーネス研究。')

    output.mkdir(parents=True,exist_ok=True)
    parts=[]
    for i,s in enumerate(slides,1):
        refs=' ／ '.join(f'<a href="{esc(url)}">{esc(label)}</a>' for label,url in s['refs']) or f'研究進捗報告 / {timestamp}'
        parts.append(f'<section class="slide'+(' dark' if s['dark'] else '')+f'" id="slide-{i}"><div class="eyebrow">{s["section"]}</div>'+
            (f'<h1>{s["title"]}</h1>' if i==1 else f'<h2>{s["title"]}</h2>')+s['body']+
            (f'<div class="takeaway">{s["takeaway"]}</div>' if s['takeaway'] else '')+
            f'<div class="footer"><div class="sources">{refs}</div><div>{i:02d} / {len(slides):02d}</div></div>'+
            f'<div class="notes">{esc(s["notes"])}</div><div class="progressbar"><i style="width:{i/len(slides)*100:.3f}%"></i></div></section>')
    document='<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AIハーネス研究 10月22日朝 進捗報告</title><style>'+STYLE+'</style></head><body>'+''.join(parts)+'''
<nav id="nav"><button id="prev" aria-label="前のスライド">←</button><span id="count"></span><button id="next" aria-label="次のスライド">→</button><button id="all">一覧 O</button><button id="note">説明 N</button><button id="print">印刷・PDF</button></nav><div id="speaker"></div><script>'''+SCRIPT+'</script></body></html>'
    (output/'index.html').write_text(document)
    (output/'speaker_notes.md').write_text('# 10月22日 朝の進捗報告・説明用メモ\n\n生成：'+timestamp+('\nレイアウト確認版。最終版ではない。' if draft else '')+'\n\n'+
        '\n\n'.join(f'## {i:02d} {s["title"].replace("<br>"," ")}\n\n{s["notes"]}' for i,s in enumerate(slides,1))+'\n')
    (output/'slides.json').write_text(json.dumps(slides,ensure_ascii=False,indent=2)+'\n')
    figures=output/'figures';figures.mkdir(exist_ok=True)
    for name,content in [('work_scope',scope_diagram()),('harness_loop',loop_diagram()),('code_architecture',architecture()),('photo_budget',photo_chart()),('guidance_success',guidance_chart(p6,p4))]:
        (figures/(name+'.svg')).write_text(content+'\n')
    with (figures/'guidance_success.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['task_group','arm','successes','tasks','known_tokens','unknown_calls'])
        for group,p in [('six',p6),('four',p4)]:
            for arm,v in p['totals'].items():w.writerow([group,arm,v['successes'],v['trials'],v['known_total_tokens'],v['unknown_usage_calls']])
    manifest=dict(generated_at=timestamp,draft=draft,pages=len(slides),p27_included=code is not None,
        source_sha256=e.hashes,builder_sha256=sha(Path(__file__)),
        scope='Progress report. Known development cases, standard comparators and unestablished novel contribution.',
        artifacts={str(p.relative_to(output)):sha(p) for p in output.rglob('*') if p.is_file() and p.name!='build_manifest.json'})
    (output/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


def export(output, chrome):
    with tempfile.TemporaryDirectory(prefix='harness-slides-chrome-') as profile:
        base=[str(chrome),'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
              '--disable-background-networking','--disable-extensions','--user-data-dir='+profile,
              '--virtual-time-budget=4000','--run-all-compositor-stages-before-draw']
        p=subprocess.run(base+['--dump-dom',(output/'index.html').resolve().as_uri()],capture_output=True,text=True,timeout=60)
        (output/'chrome_layout.stderr').write_text(p.stderr)
        if p.returncode:raise RuntimeError('Chrome layout inspection failed')
        import re
        match=re.search(r'<script id="layout-checks" type="application/json">(.*?)</script>',p.stdout,re.S)
        if not match:raise RuntimeError('layout measurement did not finish')
        checks=json.loads(html.unescape(match.group(1)))
        (output/'layout_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
        if checks['errors']:raise ValueError('presentation layout errors: '+str(checks['errors']))
        p=subprocess.run(base+['--no-pdf-header-footer','--print-to-pdf='+str((output/'AI_harness_progress_20261022.pdf').resolve()),(output/'index.html').resolve().as_uri()],capture_output=True,text=True,timeout=60)
        (output/'chrome_pdf.stderr').write_text(p.stderr)
        if p.returncode:raise RuntimeError('Chrome PDF export failed')
    return checks


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--draft',action='store_true');p.add_argument('--pdf',action='store_true')
    p.add_argument('--chrome',type=Path,default=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'))
    a=p.parse_args();result=build(ROOT,a.output,a.draft)
    if a.pdf:
        export(a.output,a.chrome)
        result['artifacts']={str(f.relative_to(a.output)):sha(f) for f in a.output.rglob('*') if f.is_file() and f.name!='build_manifest.json'}
        (a.output/'build_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('generated_at','pages','draft','p27_included')}))
