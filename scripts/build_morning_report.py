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
            if name.startswith(('reports/', 'configs/', 'docs/')) and not p.is_file():
                raise ValueError('missing public source '+name)
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
    s=f'<defs><marker id="flowarrow" markerUnits="userSpaceOnUse" markerWidth="24" markerHeight="18" refX="10" refY="4" viewBox="0 0 10 8" orient="auto"><path d="M0 0L10 4L0 8" fill="{TEAL}"/></marker></defs>'
    for path in ['M275 92 C470 4 699 4 845 92',
                 'M976 120 C1130 220 890 410 620 315',
                 'M480 315 C230 415 25 260 150 120']:
        s+=f'<path d="{path}" fill="none" stroke="{TEAL}" stroke-width="5" marker-end="url(#flowarrow)"/>'
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
            s+=txt(226+w,yy+17,f'{v:,}  {mark}',17,NAVY if a=='baseline' else color)
    s+=txt(210,399,f'灰：{baseline}　青緑：{other}。全４件・各１seed。',18)
    return svg(s,h=425,label='同じ四課題でAPI呼出型とコード型の全トークンと最終成否を比較')


def state_lifetime_diagram():
    s=txt(5,24,'比較で変える場所：プログラムの間の状態',24,weight=700)
    for y,title,color,keep in [(95,'毎回初期化',ORANGE,False),(245,'課題内で保持',TEAL,True)]:
        s+=txt(5,y+9,title,23,color,700)
        for x,label in [(310,'取得'),(610,'計算'),(910,'操作')]:
            s+=circle(x,y,32,'#e1eae2' if keep else '#eee2da')+txt(x,y+7,label,21,color,700,'middle')
        for left,right in [(350,570),(650,870)]:
            s+=line(left,y,right,y,color,3,arrow=keep,dash=not keep)
            if not keep:
                mid=(left+right)/2
                s+=line(mid-9,y-9,mid+9,y+9,ORANGE,4)+line(mid-9,y+9,mid+9,y-9,ORANGE,4)
        s+=txt(610,y+65,'変数が消える：元観測の再読・再取得・再計算が必要' if not keep else '変数・関数が残る：取得した値を後の操作へ使える',20,anchor='middle')
    return svg(s,h=340,label='プログラム間で変数を初期化する条件と課題内で保持する条件の違い')


def handoff_diagram():
    s=txt(20,28,'共通の途中地点：各課題の４応答後',25,weight=700)
    for y,w in [(78,245),(108,215),(138,185)]:
        s+=f'<path d="M35 {y} h{w} v20 h-18 l-8 10 v-10 h-{w-26} z" fill="#dfe9e5"/>'
    s+=txt(40,204,'会話履歴',24,weight=700)+txt(40,235,'全部 ／ 直近１ターン',20)
    s+=txt(370,141,'{ 変数・関数 }',33,TEAL,700)+txt(370,204,'Pythonの作業状態',24,weight=700)
    s+=txt(370,235,'保持 ／ 一回初期化',20)
    s+='<path d="M840 97 v44 a95 24 0 0 0 190 0 V97" fill="#e6e8eb" stroke="#7d8b96" stroke-width="2"/>'
    s+='<ellipse cx="935" cy="97" rx="95" ry="24" fill="#eef0f2" stroke="#7d8b96" stroke-width="2"/>'
    s+=txt(935,204,'環境の状態',24,weight=700,anchor='middle')+txt(935,235,'全条件で同じ',20,anchor='middle')
    s+=line(20,272,1090,272,color='#cbd4cc',width=1)
    for x,label in [(20,'全履歴 ＋ 保持'),(300,'直近 ＋ 保持'),(580,'全履歴 ＋ 初期化'),(860,'直近 ＋ 初期化')]:
        s+=circle(x+14,322,10,TEAL if '保持' in label else ORANGE)+txt(x+36,330,label,20,weight=700)
    s+=txt(20,383,'同じ後続予算：16生成・12万token・８分。原記録への再アクセスは全条件で可能。',21)
    return svg(s,h=415,label='会話履歴とPython作業状態を二要因に分け、環境を固定した四条件の引き継ぎ比較')


def handoff_result_chart(data):
    s=txt(440,35,'会話：全部',25,weight=700,anchor='middle')+txt(840,35,'会話：直近だけ',25,weight=700,anchor='middle')
    for y,runtime,label in [(105,'keep','変数を保持'),(267,'reset','変数を初期化')]:
        s+=txt(5,y+25,label,25,TEAL if runtime=='keep' else ORANGE,700)
        for x,history in [(440,'full'),(840,'recent')]:
            arm=history+'_'+runtime;v=data['totals'][arm]
            for i,r in enumerate([r for r in data['rows'] if r['arm']==arm]):
                s+=circle(x-92+i*44,y,12,TEAL if r['success'] else '#ddd9cf')
            s+=txt(x+85,y+12,f'{v["successes"]}/4',34,TEAL,700)
            mark='*' if v['unknown_usage_calls'] else ''
            s+=txt(x,y+53,f'{v["known_total_tokens"]:,}{mark} token ／ {v["api_requests"]} API',21,anchor='middle')
    s+=line(235,196,1080,196,color='#cbd4cc',width=1)
    return svg(s,h=365,label='同じ途中状態からの四条件の成功件数と後続トークン・API費用')


def control_table(stages):
    names=[('P27','初期接続'),('P28','関数説明を補足'),('P29','説明＋変数保持')]
    rows='<table class="compact"><thead><tr><th>課題</th>'+''.join('<th>'+label+'</th>' for _,label in names)+'</tr></thead><tbody>'
    for i,label in enumerate(['写真整理','共有・依頼','返金','曲情報の書出']):
        rows+='<tr><td>'+label+'</td>'
        for phase,_ in names:
            if phase not in stages:rows+='<td class="muted">未集計</td>';continue
            r=stages[phase]['pairs'][i]['code']
            rows+='<td>'+('成功' if r['success'] else '未達')+' ／ '+num(r['known_total_tokens'])+'</td>'
        rows+='</tr>'
    rows+='<tr><td><strong>成功数 / 全費用</strong></td>'
    for phase,_ in names:
        if phase not in stages:rows+='<td class="muted">未集計</td>';continue
        t=stages[phase]['totals']['code']
        rows+='<td><strong>'+str(t['successes'])+'/4 ／ '+num(t['known_total_tokens'])+'</strong></td>'
    return rows+'</tr></tbody></table>'


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
.slide.cover{display:flex;align-items:center;justify-content:center;padding:70px}.slide.cover h1{font-size:57px;line-height:1.65;letter-spacing:0;text-align:center}.story-table{font-size:21px;margin-top:24px}.story-table td,.story-table th{padding-top:12px;padding-bottom:12px}.factor-table{font-size:24px;margin-top:35px}.factor-table td{padding-top:24px;padding-bottom:24px}.factor-table b{font-size:32px;color:var(--teal);margin-right:10px}.factor-table th{font-size:22px}.results-table td:not(:first-child){text-align:center}.results-table th{text-align:center}.results-table th:first-child{text-align:left}.ok{color:var(--teal);font-weight:700}.miss{color:var(--muted)}.story-diagram svg{max-height:365px}body.present .slide.cover.active{display:flex}body.on-cover #nav{opacity:0;transition:opacity .2s}body.on-cover #nav:hover,body.on-cover #nav:focus-within{opacity:1}
.results-table{margin-top:16px}.results-table th,.results-table td{padding-top:7px;padding-bottom:7px}
@media print{@page{size:1280px 720px;margin:0}html,body{background:white}.slide,body.present .slide,body.present .slide.active{display:block!important;position:relative!important;top:auto!important;left:auto!important;transform:none!important;margin:0!important;box-shadow:none!important;break-after:page;page-break-after:always}.slide:last-of-type{break-after:auto;page-break-after:auto}#nav,#speaker{display:none!important}.slide.cover,body.present .slide.cover.active{display:flex!important}}
'''

SCRIPT=r'''
const slides=[...document.querySelectorAll('.slide')];let current=Math.max(0,Math.min(slides.length-1,(+location.hash.slice(1)||1)-1));
const label=document.querySelector('#count');function fit(){document.body.style.setProperty('--scale',Math.min(innerWidth/1280,innerHeight/720));}function show(n){current=Math.max(0,Math.min(slides.length-1,n));slides.forEach((s,i)=>s.classList.toggle('active',i===current));document.body.classList.toggle("on-cover",slides[current].classList.contains("cover"));label.textContent=`${current+1} / ${slides.length}`;history.replaceState(null,'','#'+(current+1));document.querySelector('#speaker').innerHTML=slides[current].querySelector('.notes').innerHTML;fit();}
document.querySelector('#prev').onclick=()=>show(current-1);document.querySelector('#next').onclick=()=>show(current+1);document.querySelector('#all').onclick=()=>{document.body.classList.toggle('present');document.body.classList.toggle('overview');};document.querySelector('#note').onclick=()=>{let e=document.querySelector('#speaker');e.style.display=e.style.display==='block'?'none':'block';};document.querySelector('#print').onclick=()=>print();addEventListener('resize',fit);addEventListener('keydown',e=>{if(['ArrowRight','PageDown',' '].includes(e.key)){e.preventDefault();show(current+1);}if(['ArrowLeft','PageUp'].includes(e.key)){e.preventDefault();show(current-1);}if(e.key==='Home')show(0);if(e.key==='End')show(slides.length-1);if(e.key==='n')document.querySelector('#note').click();if(e.key==='o')document.querySelector('#all').click();});
document.fonts.ready.then(()=>{document.body.className='overview';const errors=[];slides.forEach((s,i)=>{const a=s.getBoundingClientRect();for(const e of s.querySelectorAll('h1,h2,.lead,.body,.two,.three,.diagram,.takeaway,table,.timeline,.footer')){const b=e.getBoundingClientRect();if(b.left<a.left+30||b.right>a.right-30||b.bottom>a.bottom-15||b.top<a.top+20)errors.push({slide:i+1,tag:e.className||e.tagName,reason:'outside-slide'});}const footer=s.querySelector('.footer');if(!footer)return;const f=footer.getBoundingClientRect();for(const e of s.children){if(e===footer||e.classList.contains('notes')||e.classList.contains('progressbar'))continue;const b=e.getBoundingClientRect();if(b.height&&b.bottom>f.top-8)errors.push({slide:i+1,tag:e.className||e.tagName,reason:'overlaps-footer'});}const take=s.querySelector('.takeaway');if(take){const t=take.getBoundingClientRect();for(const e of s.children){if(e===take||e===footer||e.classList.contains('notes')||e.classList.contains('progressbar'))continue;const b=e.getBoundingClientRect();if(b.height&&b.bottom>t.top-12)errors.push({slide:i+1,tag:e.className||e.tagName,reason:'overlaps-takeaway'});}}});const el=document.createElement('script');el.id='layout-checks';el.type='application/json';el.textContent=JSON.stringify({pages:slides.length,errors});document.body.appendChild(el);document.body.className='present';show(current);});
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
    stages={} if code is None else {'P27':code}
    for phase in ('P28','P29'):
        name=f'reports/{phase}_comparison.json'
        if (root/name).exists():
            result=e.read(name)
            if not result.get('all_four_reviewed') or len(result['pairs'])!=4:
                raise ValueError(phase+' is not fully reviewed')
            stages[phase]=result
    handoff=None;later_handoff=None
    if (root/'reports/P31_comparison.json').exists():
        handoff=e.read('reports/P31_comparison.json')
        if not handoff.get('all_sixteen_reviewed') or len(handoff['rows'])!=16:
            raise ValueError('P31 requires all sixteen continuations')
    if (root/'reports/P32_comparison.json').exists():
        later_handoff=e.read('reports/P32_comparison.json')
        if not later_handoff.get('all_sixteen_reviewed') or len(later_handoff['rows'])!=16:
            raise ValueError('P32 requires all sixteen continuations')
    later_prefix=e.read('reports/P32_prefix_checks.json')
    later_state=e.read('reports/P32_prefix_characterization.json')
    if not later_prefix['all_observable_prefixes_match'] or any(r['status']!='counted' for r in later_state['rows']):
        raise ValueError('later-boundary preparation is not verified')
    timestamp=dt.datetime.now(JST).strftime('%Y-%m-%d %H:%M JST')
    slides=[]
    def add(section,title,body,notes,refs=(),dark=False,takeaway=None):
        slides.append(dict(section=section,title=title,body=body,notes=notes,refs=refs,dark=dark,takeaway=takeaway))

    add('RESEARCH PROGRESS / 2026.10.22', 'AIハーネスの引き継ぎで<br>何を残すべきか',
        '<p class="lead">会話履歴と実行中の作業状態を分け、<br>どの情報を残すと仕事を継続できるか調べる。</p>'
        '<div class="three"><div class="col"><span class="badge">対象</span><h3>状態を変える<br>複数工程の仕事</h3></div>'
        '<div class="col"><span class="badge">現在地</span><h3>通常方式の比較から、<br>引き継ぎの条件比較へ</h3></div>'
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
    add('03 / 今回の問い','作業状態が残れば、渡す会話は減らせるか',
        '<div class="three"><div class="col"><div class="n">01</div><h3>完了できるか</h3><p class="body">要件を満たす最終状態を、実行とは別に評価する。</p></div>'
        '<div class="col"><div class="n">02</div><h3>費用に見合うか</h3><p class="body">記憶生成・調整・失敗も含め、トークンと時間を測る。</p></div>'
        '<div class="col"><div class="n">03</div><h3>なぜ変わったか</h3><p class="body">指示、情報保持、操作形式、予算を切り分ける。</p></div></div>',
        '成功率だけが高くても、予算や情報が増えていれば内部機構の効果とはいえません。全費用と失敗を含め、同じ課題の対応比較をします。',
        [('研究と評価の範囲',LINK+'docs/letter_evaluation_scope_20261021.md')],takeaway='目標：条件をそろえた比較で、必要な機構と不要な追加処理を示す。')
    add('04 / 当初案と現在地','再編の効果と、引き継ぎの効果を分けたい',
        '<div class="two"><div class="col"><span class="badge wait">当初の新提案候補・未評価</span><h3>作業間依存に応じた実行単位の再編</h3><p class="body">分担の継続・情報共有・中央調整・作業集約を、同じ途中状態から比較する。</p></div>'
        '<div class="col"><span class="badge">現在の実験</span><h3>担当を変えず、残す状態を比較</h3><p class="body">再編時には会話や変数の持ち方も変わる。まずその影響を、同じ地点・担当・継続予算で調べる。</p></div></div>',
        '当初案の研究目的は引き継いでいますが、今ある実験はその仮説を直接実証していません。担当範囲と会話・変数を同時に変えると、成績差がどちらから生じたか判断しにくいため、引き継ぐ状態の比較を先行しています。これを再編の有効性を示した結果とは扱いません。',
        [('現在の成果と未確定事項',LINK+'README.md')],takeaway='現在の結果だけで、マルチエージェント再編の有効性は主張できない。')
    add('05 / 既存との差分','既にある機能を、独自の技術と数えない',
        '<table class="compact"><thead><tr><th>先行研究・仕組み</th><th>既に扱われていること</th><th>今回の扱い</th></tr></thead><tbody>'
        '<tr><td>CodeAct / ICML 2024</td><td>Pythonで行動を統合し、実行結果から修正</td><td>通常コード型の比較相手</td></tr>'
        '<tr><td>FOCUS / 著者公開原稿</td><td>今後の作業に必要な情報の選択・保持</td><td>共通環境向けに接続した比較</td></tr>'
        '<tr><td>SelfCompact / 著者公開原稿</td><td>コンテキスト整理とキャッシュ費用</td><td>費用の差を新原理としない</td></tr>'
        '<tr><td>CaveAgent / Runtime Contracts</td><td>状態の保持・共有、一時移管・通知の比較</td><td>保持と可視性だけでも既出</td></tr></tbody></table>',
        'CodeActは正式会議録を確認済みです。CaveAgent v4とRuntime Contracts v3も確認し、変数の一時保持と名前の通知まで先行研究に含まれることを記録しました。公開原稿と正式採録は区別します。ここは機能の重なりの整理で、全方式の完全再現や網羅的な新規性調査の完了を意味しません。',
        [('CodeAct', 'https://proceedings.mlr.press/v235/wang24h.html'),('近接研究と確認範囲',LINK+'docs/output_access_review_20261021.md'),('実行状態の原典照合',LINK+'docs/runtime_state_overlap_20261022.md')])
    add('06 / 新提案技術の現在地','独自方式の有効性は、まだ確立していない',
        '<div class="two"><div class="col"><span class="badge">実装・確認済み</span><h3>比較と原因分析の基盤</h3><p class="body">公開APIの接続／状態保存と再生／全費用の記録／独立評価／コード実行型。</p><p class="small muted subtle">いずれも、それだけを新規性とはしない。</p></div>'
        '<div class="col"><span class="badge warn">研究仮説・未確立</span><h3>持っている作業状態に応じて、引き継ぐ履歴を変える</h3><p class="body">保持状態と履歴削減の関係が残れば、選択規則を固定し、強い基準・同じ予算・未調整課題で確認する。</p></div></div>',
        '仮説はまだ制御方式として確立していません。CaveAgentは既に実行状態と意味履歴を分けており、状態に応じるという表現だけでは差分になりません。固定地点の交差比較で条件が残るかを先に確認します。P16の候補は観測根拠がなく見送っています。',
        [('見送った候補と理由',LINK+'docs/P16_findings.md'),('原稿の現状',LINK+'papers/202610_letter/current_status.json')],
        takeaway='今の成果は検証基盤と切り分け。新規性・採録可能性の証明はこれから。')
    add('07 / 実験環境','同じモデル・同じ環境で、構成差を比較する',
        '<div class="two"><div><table class="compact"><tbody><tr><td>計算機</td><td>Mac Studio / M3 Ultra<br>256 GiB RAM</td></tr><tr><td>モデル</td><td>MiniMax-M3 / IQ4_XS<br>重み約229.7 GB・版固定</td></tr><tr><td>推論</td><td>llama.cpp / 64K context<br>KV q8・１スロット</td></tr></tbody></table></div>'
        '<div><table class="compact"><tbody><tr><td>環境</td><td>AppWorld 0.1.3.post1<br>復元可能な模擬アプリ</td></tr><tr><td>全体実行の上限</td><td>45万token・80生成・30分</td></tr><tr><td>引き継ぎ後の上限</td><td>12万token・16生成・８分</td></tr><tr><td>評価</td><td>終了後の別プロセス<br>正解をモデルへ戻さない</td></tr></tbody></table></div></div>',
        '現物の計測は256 GiBのメモリで、最初の相談にあったSSD256GBという申告とは区別します。重みは229.7GBの保存サイズで、ピーク推論メモリではありません。１スロットの実験なので物理並列化の速度向上を示していません。全体実行と固定境界からの継続実験では上限が異なり、両者の費用を直接同じ試行と扱いません。１生成の出力上限は4,096 token。',
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
        add('14 / 初期のコード実行型','初期接続は3/4。通常API基準の4/4に届かない',
            '<div class="diagram">'+bar_chart(code['pairs'])+'</div>',
            'P27の全４課題を監査した。コード型は3/4、比較相手は4/4。費用が減った失敗を効率改善とは呼ばない。全件で最初のプログラムにインポートエラーがあり、返金では21プログラムがAPI未到達。曲の書出では同じ一覧の再取得と、消えた変数の参照があった。ここから説明と変数保持を分ける次の比較へ進んだ。',
            [('全結果と実装差',LINK+'docs/P27_findings.md')])
    else:
        add('14 / コード実行型の結果','全４件の評価・監査が終わるまで、結論を留保する',
            '<div class="two"><div class="col"><span class="badge">固定済み</span><h3>４既知課題・１seed</h3><p class="body">写真は160 API、他３件は80 API。<br>モデル・トークン・時間は比較相手と同じ。</p></div><div class="col"><span class="badge wait">この資料の集計時点</span><h3>確定した比較報告は未収録</h3><p class="body">実行中・監査中の数字を、完成した成績へ置き換えない。</p></div></div>',
            'このページは全４件を監査した報告がまだない場合の表示です。資料の生成時点とGitHubの実行状態を確認します。未収録を失敗ゼロや成功扱いにはしません。',
            [('自動進捗・Issue132','https://github.com/sophiria1225/AI-/issues/132')],takeaway='確定済みの全件報告が保存されたら、直前の生成時にこのページへ反映する。')
    if code:
        add('14a / 次の比較で変える場所','関数の説明と、変数を残す効果を分ける',
            '<p class="small">先に説明だけを補い、その後に課題内の状態保持を比較。モデル・課題・API上限は維持。</p><div class="diagram tight">'+state_lifetime_diagram()+'</div>',
            'P27では提供済み関数の探索と状態の再取得が観測された。P28は関数が既に定義されているとだけ補足し、変数は毎回初期化する。P29はその説明を保ち、状態保持とその正確な案内を加える。いずれも通常方式であり、CodeActやCaveAgentと同じ原理を新提案とはしない。',
            [('説明だけの条件',LINK+'docs/experiments/P28_code_clarification.md'),('状態保持の範囲',LINK+'docs/experiments/P29_stateful_preparation.md')])
        add('14b / 条件を分けた比較結果','同じ４課題の全結果を、成功と費用で見る',
            control_table(stages)+'<p class="small muted">数値＝全入力＋全出力トークン。各１seedの開発比較。未集計は未実行・実行中・監査待ちを含む。</p>',
            'この表には全４件の評価・監査が終了した段階だけを載せる。課題の選び直しや失敗の自動再試行はしていない。状態保持を追加して改善しても、既存原理の校正の結果である。後続の固定比較と未調整課題で確認するまで、一般的な優位は主張しない。',
            [(phase+'の全比較',LINK+'reports/'+phase+'_comparison.json') for phase in stages],
            takeaway='追加の仕組みが必要かを決めるため、通常方式を十分にした状態で比べる。')
    add('14c / 引き継ぎの実験設計','履歴を減らす影響は、変数が残るかで変わるか',
        '<div class="diagram tight">'+handoff_diagram()+'</div>',
        '固定４応答後を全４課題で使います。最終成否から都合のよい地点を選びません。模擬世界を別に再構成し、API返却・公開スキーマ・保存DBを照合します。Pythonは記録済み応答で再生しますが、全プロセスの完全な同一性は保証しません。環境再構成と後続の費用を分離し、状態初期化はモデルにも正確に知らせます。',
        [('事前仕様と採らなかった案',LINK+'docs/experiments/P31_handoff_factors.md')],
        takeaway='二要因の比較は効果を切り分ける手段。この設計だけを新規性とはしない。')
    if handoff:
        unknown=sum(v['unknown_usage_calls'] for v in handoff['totals'].values())
        add('14d / 引き継ぎの比較結果','同じ途中状態から、全16分岐を評価する',
            '<div class="diagram tight">'+handoff_result_chart(handoff)+'</div><p class="small muted">● 成功 ／ 淡色 未達。各４既知課題・１seed。数値は後続のみ。'+
            (f'＊：使用量不明あり（全体で {unknown} 呼出）。表示は既知分。' if unknown else 'トークン不明０。')+'</p>',
            '主表には後続費用を示しますが、環境再構成・Python再生の費用も元の報告へ保存しています。４件の少数比較で一般的な優位は断定しません。８分の後続制限と早い固定境界に依存し、作業責任の移管やマルチエージェントの集約を直接評価したものでもありません。',
            [('全16件・費用・監査',LINK+'reports/P31_comparison.json')],
            takeaway='履歴と作業状態の組合せを観測。新しい選択方式の有効性は別の検証が必要。')
    else:
        add('14d / 引き継ぎ比較の進捗','全16分岐の結果がそろうまで、効果は未確定',
            '<div class="two"><div><h3>用意したもの</h3><p class="body">４条件の切り替え、費用の分離、同じ前半の照合、独立した最終評価。</p></div><div><h3>まだ確定していないもの</h3><p class="body">全件の効果差、失敗の内訳、選択規則へ進む根拠。</p></div></div>',
            'このページは全16件の集計が公開されていない場合の表示です。未実行・前提確認中・実行中・監査待ちを成功結果へ置き換えません。最新の具体的な状態はIssueと研究記録を参照してください。',
            [('引き継ぎ比較・Issue145','https://github.com/sophiria1225/AI-/issues/145')])
    if handoff:
        arms=['full_keep','recent_keep','full_reset','recent_reset']
        tasks=list(dict.fromkeys(r['task_id'] for r in handoff['rows']))
        labels=['写真整理','共有・依頼','返金','曲情報の書出']
        cells={(r['task_id'],r['arm']):r for r in handoff['rows']}
        table='<table><thead><tr><th>課題</th><th>全履歴＋保持</th><th>直近＋保持</th><th>全履歴＋初期化</th><th>直近＋初期化</th></tr></thead><tbody>'
        for task,label in zip(tasks,labels):
            table+='<tr><td>'+label+'</td>'+''.join('<td class="'+('teal' if cells[task,a]['success'] else 'muted')+'">'+('成功' if cells[task,a]['success'] else '未達')+'</td>' for a in arms)+'</tr>'
        table+='</tbody></table>'
        add('14f / 課題ごとの結果','成功した課題も、全条件で止まった課題も残す',table+
            '<p class="body">未達12件の停止理由：トークン予算７件、API上限３件、時間上限２件。</p>',
            '各セルは１回の実行です。未達の停止理由は実行を止めた直接の理由で、そこまでに予算を消費した根本原因ではありません。全条件で未達の課題も除かずに報告します。観測誤読や推論の失敗を、この表だけで特定したとは扱いません。',
            [('全16件と停止理由',LINK+'reports/P31_comparison.json')],
            takeaway='失敗をすべて情報欠落やハルシネーションにまとめず、経過と予算を確認する。')
        full=handoff['totals']['full_keep'];recent=handoff['totals']['recent_keep']
        change=100*(recent['known_total_tokens']/full['known_total_tokens']-1)
        add('14g / 今回の考察','変数を残すだけでは、会話短縮を補えなかった',
            '<div class="two"><div class="col"><span class="badge">観測できたこと</span><h3>保持したまま会話を短縮</h3>'+
            f'<p class="body">成功：{full["successes"]}/4 → {recent["successes"]}/4<br>後続トークン：{full["known_total_tokens"]:,} → {recent["known_total_tokens"]:,}<br>総量は {change:.1f}% 増加。</p>'+
            '<p class="small muted">この２条件の使用量不明は０。</p></div>'+
            '<div class="col"><span class="badge warn">まだ仮説の部分</span><h3>状態の存在と、利用は別</h3><p class="body">値を保持していても、何を取得済みで、どう使うかが伝わらない可能性。原因は軌跡と追加対照で確認する。</p></div></div>',
            '今回の早い境界・４既知課題・１seedでは、変数を保持すれば履歴を短縮できるという期待は支持されませんでした。総費用も減っていません。ただし変数が少ない地点、状態一覧を自動提示しない実装、短い後続予算に依存する結果です。CaveAgentや状態保持一般への反証ではありません。二要因の比較だけを新規アルゴリズムとも扱いません。',
            [('結果と考察',LINK+'docs/P31_findings.md'),('既存との重なり',LINK+'docs/runtime_state_overlap_20261022.md')],
            takeaway='次の焦点：保持されている値が、継続時に実際に利用される条件を調べる。')
    if later_handoff:
        unknown=sum(v['unknown_usage_calls'] for v in later_handoff['totals'].values())
        add('14e / 作業が進んだ地点での比較','８応答後でも、同じ４条件・後続予算で調べる',
            '<div class="diagram tight">'+handoff_result_chart(later_handoff)+'</div><p class="small muted">同じ４課題の別地点。新しい４課題ではない。後続費用のみ。'+
            (f'＊：使用量不明あり（全体で {unknown} 呼出）。表示は既知分。' if unknown else 'トークン不明０。')+'</p>',
            '４応答後の状態量が少なかったため、P31全16結果を見る前に８応答後を固定しました。全４前半を復元し、公開返却・保存DB・Pythonを照合済み。変数数は5/3/10/10ですが、意味的な重要性の指標ではありません。時点間では状態だけでなく後続seed列も違うため、時期だけの因果効果とは言いません。各境界内の四条件ではseed列と予算をそろえています。',
            [('全16件の結果',LINK+'reports/P32_comparison.json'),('事前の選定理由',LINK+'docs/experiments/P32_later_handoff.md')],
            takeaway='２時点×16分岐でも、独立した対象は既知の４課題。一般化には別の確認が必要。')
    else:
        add('14e / 次の地点の準備','８応答後の前提確認も済ませ、全件結果を待つ',
            '<div class="two"><div class="col"><h3>なぜ追加するか</h3><p class="body">４応答後では、３課題にユーザー変数が２つだけ。状態が蓄積した地点も同じ規則で調べる。</p></div><div class="col"><h3>何を固定したか</h3><p class="body">元の全４軌跡の８応答後。<br>同じ４条件・16生成・12万token・８分。<br>失敗した地点だけを選ばない。</p></div></div>',
            '８応答後の全４地点で公開返却51件・保存DB各13ファイル・Python32プログラムが一致しました。P31の全16結果を見る前に追加地点を固定しています。ここは準備の説明で、P32の全件結果を含んでいません。最新の実行状況はIssue150。',
            [('８応答後の仕様',LINK+'docs/experiments/P32_later_handoff.md'),('実行状況','https://github.com/sophiria1225/AI-/issues/150')],
            takeaway='会話の短縮と変数の保持の効果を測る。担当再編の有効性はまだ直接測っていない。')
    add('15 / これまでの考察','失敗の観測と、追加機構の必要性は分ける',
        '<div class="three"><div class="col"><h3>指示で解消する失敗</h3><p class="body">元の低成績だけでは、記憶・ゲート・分担変更が必要だとはいえない。</p></div><div class="col"><h3>予算で止まる処理</h3><p class="body">未完了をすべて情報欠落やハルシネーションへまとめない。</p></div><div class="col"><h3>正解でも残る未確認</h3><p class="body">57曲中56曲の詳細取得で正解した例。正解と網羅的な確認は別。</p></div></div>',
        '57曲の例は未確認の１曲が誤答を起こした実例ではありません。公開一覧には曲の長さがなく、未確認を一覧で既に読めたとみなすこともできません。これだけで全取得を強制する制御を提案するのは早計です。',
        [('成功と網羅性',LINK+'docs/P24_findings.md'),('一律の全取得を採らない理由',LINK+'docs/collection_frontier_findings_20261021.md')],takeaway='改善を確認できた要因から順に閉じ、残る問題にだけ新しい処理を加える。')
    add('16 / 現在の限界','まだ言えないことを、実験結果の隣に置く',
        '<div class="two"><div><h3>一般性の限界</h3><ul class="body"><li>主に１モデル・各条件１seed。</li><li>既知の少数開発課題を繰り返し利用。</li><li>別モデル・別分野への転用は未確認。</li></ul></div><div><h3>技術的主張の限界</h3><ul class="body"><li>再編の固有効果は未測定。</li><li>通常コード型にも提示方法などの実装差。</li><li>独自方式の新規性・有効性は未確定。</li></ul></div></div>',
        'この研究では12シナリオを調整から分離し、要求文を未閲覧にしています。ただしモデルの学習汚染がないことや公式テストと同じことを意味しません。実装を完成させただけで論文の中心結果ができたとは扱いません。',
        [('確認用シナリオの分離',LINK+'docs/letter_scenario_reservation_20261021.md')],takeaway='未閲覧12シナリオは、方式・閾値・比較条件を固定してから使う。')
    add('17 / 今後の実験','次は、通常方式でも残る一つの問題に絞る',
        '<div class="three"><div class="col"><div class="n">1</div><h3>引き継ぎ比較を閉じる</h3><p class="body">履歴・変数・再取得の関係と、費用・失敗を確認する。</p></div><div class="col"><div class="n">2</div><h3>選択規則が必要か判断</h3><p class="body">一律に保持すれば十分か。状態に応じる利益が残るか。</p></div><div class="col"><div class="n">3</div><h3>未調整課題で確認</h3><p class="body">差分が成立する規則だけを、同じ予算の基準と比較する。</p></div></div>',
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

    # The revised main story starts with a concrete task, before experiment IDs.
    from morning_story import build_story_slides
    diagnostics=e.read('reports/P31_program_diagnostics.json')
    e.hashes['docs/research_objective_20261022.md']=sha(root/'docs/research_objective_20261022.md')
    by_key={s['section'].split('/')[0].strip():s for s in slides}
    ordered,story_figures=build_story_slides(handoff,diagnostics,later_handoff)
    remaining=[by_key[k] for k in ('07','14d','14e','14b','12','11') if k in by_key]
    main_pages=len(ordered)
    for i,s in enumerate(ordered[1:],1):
        s['section']=f'{i:02d} / '+s['section']
    for i,s in enumerate(remaining,1):
        s['section']=f'補足 {i:02d} / '+s['section'].split('/',1)[1].strip()
    slides=ordered+remaining
    output.mkdir(parents=True,exist_ok=True)
    parts=[]
    for i,s in enumerate(slides,1):
        if s.get('cover'):
            parts.append(f'<section class="slide dark cover" id="slide-{i}"><h1>{s["title"]}</h1>'+
                         f'<div class="notes">{esc(s["notes"])}</div></section>')
            continue
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
    (output/'README.md').write_text(
        '# 10月22日朝の進捗報告資料\n\n生成時刻：'+timestamp+'。'+
        ('レイアウト確認版。最終配布版ではありません。' if draft else '生成時点の監査済み集計を反映しています。')+'\n\n'
        '- [PDF・全'+str(len(slides))+'枚](AI_harness_progress_20261022.pdf)：本編'+str(main_pages)+'枚、残りは実行条件・過去比較の補足。\n'
        '- [HTMLスライド](index.html)：ダウンロードしてブラウザーで開くと、ネット接続なしで表示できます。GitHubの通常表示ではHTMLのソースが見えます。\n'
        '- [説明用メモ](speaker_notes.md)：各ページの説明と、数値の読み方・限界。\n'
        '- [図と集計データ](figures/)／[出典と生成記録](build_manifest.json)。\n\n'
        'HTMLの操作：左右キーで移動、Oで一覧、Nで説明メモ。印刷時はスライド単位になります。\n\n'
        '**主目的は、ハーネスによって不要な情報取得・共有・AI呼び出し・実行を削減し、タスクの性能を維持することです。** 履歴・状態の引き継ぎ比較は、そのための局所検証として位置づけ直しました。表紙は題名のみです。\n\n'
        '冒頭で、費用が発生する経路、性能維持と総費用削減の目標、改善の判定方法を説明します。その後、具体例・現在の検証範囲・実験の前提・比較理由・結果へ進みます。\n\n'
        '| PDFのページ | 内容 |\n|---|---|\n'+
        '\n'.join(f'| {i} | '+('補足：' if i>main_pages else '')+s['title'].replace('<br>',' ')+' |' for i,s in enumerate(slides,1))+'\n\n'
        '現在の結果は４既知課題・１モデル・各条件各境界１回の探索実験です。品質を保った費用削減、担当再編や独自制御方式の有効性は未確立です。全件監査された結果のみを含めます。\n')
    figures=output/'figures';figures.mkdir(exist_ok=True)
    for name,content in list(story_figures.items())+[('work_scope',scope_diagram()),('harness_loop',loop_diagram()),('code_architecture',architecture()),('state_lifetime',state_lifetime_diagram()),('photo_budget',photo_chart()),('guidance_success',guidance_chart(p6,p4))]:
        (figures/(name+'.svg')).write_text(content+'\n')
    with (figures/'guidance_success.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['task_group','arm','successes','tasks','known_tokens','unknown_calls'])
        for group,p in [('six',p6),('four',p4)]:
            for arm,v in p['totals'].items():w.writerow([group,arm,v['successes'],v['trials'],v['known_total_tokens'],v['unknown_usage_calls']])
    if code:
        (figures/'code_comparison.svg').write_text(bar_chart(code['pairs'])+'\n')
        with (figures/'code_comparison.csv').open('w') as f:
            w=csv.writer(f);w.writerow(['task_id','arm','success','model_calls','api_requests','known_tokens','unknown_calls','wall_seconds'])
            for row in code['pairs']:
                for arm in ('baseline','code'):
                    d=row[arm];w.writerow([row['task_id'],arm,d['success'],d['model_calls'],d['api_requests'],d['known_total_tokens'],d['unknown_usage_calls'],d['execution_wall_seconds']])
    if stages:
        with (figures/'code_state_controls.csv').open('w') as f:
            w=csv.writer(f);w.writerow(['phase','task_id','success','tokens','calls','api_requests'])
            for phase,data in stages.items():
                for row in data['pairs']:
                    d=row['code'];w.writerow([phase,row['task_id'],d['success'],d['known_total_tokens'],d['model_calls'],d['api_requests']])
    (figures/'handoff_design.svg').write_text(handoff_diagram()+'\n')
    if handoff:
        (figures/'handoff_results.svg').write_text(handoff_result_chart(handoff)+'\n')
        with (figures/'handoff_results.csv').open('w') as f:
            keys=['task_id','arm','success','known_total_tokens','unknown_usage_calls','api_requests','setup_api_requests','setup_wall_seconds','continuation_wall_seconds']
            w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(handoff['rows'])
    if later_handoff:
        (figures/'later_handoff_results.svg').write_text(handoff_result_chart(later_handoff)+'\n')
        with (figures/'later_handoff_results.csv').open('w') as f:
            keys=['task_id','arm','success','known_total_tokens','unknown_usage_calls','api_requests','setup_api_requests','setup_wall_seconds','continuation_wall_seconds']
            w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(later_handoff['rows'])
    manifest=dict(generated_at=timestamp,draft=draft,pages=len(slides),main_pages=main_pages,p27_included=code is not None,code_control_phases=list(stages),p31_included=handoff is not None,p32_included=later_handoff is not None,
        source_sha256=e.hashes,builder_sha256=sha(Path(__file__)),story_sha256=sha(root/'scripts/morning_story.py'),
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
