"""P38 milestone: only closed aggregate results, explicit limits, no raw tasks."""
import argparse
import csv
import datetime as dt
import html
import json
from pathlib import Path
import re
import subprocess
import tempfile

from build_morning_report import STYLE, SCRIPT, svg, txt, line, circle, scope_diagram
from run_handoff_factors import read, sha

ROOT = Path(__file__).resolve().parents[1]
STEM = 'AI_harness_acquisition_20261022'
LINK = 'https://github.com/sophiria1225/AI-/blob/main/'
NAMES = ['毎回取得', '同一APIを再利用', '別APIの項目も再利用']
ARMS = ['none_keep', 'exact_keep', 'contract_keep']


def evidence(root):
    paths = ['reports/P38_comparison.json', 'reports/P38_cache_replay.json',
             'reports/P38_runtime_costs.json', 'reports/P38_prefix_checks.json',
             'reports/P33_comparison.json', 'reports/P37_field_contract.json',
             'reports/P38_miss_diagnostics.json']
    values = [read(root / p) for p in paths]
    comparison, audit, costs, prefix, _, _, misses = values
    if (not comparison['all_three_reviewed'] or not audit['all_three_attempted']
            or not costs['all_three_profiled'] or not prefix['identical_initial_inputs']
            or not misses['all_three_diagnosed']):
        raise ValueError('closed complete cohort and audits are required')
    for result in (comparison, audit, costs):
        if [r['run_id'] for r in result['rows']] != ['P38_04_' + a.upper() for a in ARMS]:
            raise ValueError('incomplete or reordered cohort')
    for result in (audit, costs, misses):
        for name, expected in result['source_sha256'].items():
            if sha(root / name) != expected: raise ValueError('changed evidence: ' + name)
    for r, c in zip(comparison['rows'], costs['rows']):
        if r['known_total_tokens'] != c['totals']['known_total_tokens']:
            raise ValueError('different token totals')
    return values, {p: sha(root / p) for p in paths}


def architecture():
    s = txt(20,30,'AIがコードで「対象」と「必要項目」を指定',25,weight=700)
    s += txt(20,72,'例：曲のタイトル・アーティスト名を読む',23)
    s += line(300,94,300,135,arrow=True)
    s += '<path d="M300 130 485 205 300 280 115 205Z" fill="#e1eae2"/>'
    s += txt(300,191,'ハーネスが確認',24,weight=700,anchor='middle')
    s += txt(300,223,'対象・項目・状態の版',20,anchor='middle')
    s += line(486,185,635,135,arrow=True) + line(486,225,635,290,arrow=True)
    s += txt(503,139,'揃っている',19) + txt(510,282,'不足・失効',19)
    s += circle(685,130,36,'#d5e7df') + txt(685,137,'再利用',19,weight=700,anchor='middle')
    s += txt(748,125,'既取得の必要項目を返す',24,weight=700)
    s += txt(748,159,'外部APIを呼び直さない',20)
    s += circle(685,295,36,'#eae0d5') + txt(685,302,'取得',19,weight=700,anchor='middle')
    s += txt(748,290,'通常どおりAPIを実行',24,weight=700)
    s += txt(748,324,'応答・費用・状態を記録',20)
    s += txt(20,372,'未知の操作が送信されたら失効。元APIの全項目返却は変えない。',22,weight=700)
    return svg(s,h=400,label='必要項目を指定し、対象と状態が一致する過去値で満たせる場合だけ取得を省く')


def charts(output, comparison):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'Hiragino Sans','font.size':11,
                         'axes.spines.top':False,'axes.spines.right':False,
                         'svg.fonttype':'none','savefig.facecolor':'#f6f4ed'})
    f = output / 'figures'; f.mkdir(exist_ok=True)
    rows = comparison['rows']; colors = ['#8796a2','#177b79','#c66a38']
    fig, axes = plt.subplots(1,2,figsize=(11.5,3.4),layout='constrained',facecolor='#f6f4ed')
    vals = [[r['known_total_tokens']/1000 for r in rows], [r['api_requests'] for r in rows]]
    for index, (ax, v, title, unit) in enumerate(zip(axes, vals,
            ['終了までの総トークン', '後続の実API呼出し'], ['千トークン', '回'])):
        ax.set_facecolor('#f6f4ed'); ax.set_title(title,pad=12)
        bars = ax.barh(NAMES[::-1],v[::-1],color=colors[::-1],height=.53)
        ax.set_xlim(0,max(v+[1])*1.45); ax.set_xlabel(unit)
        ax.grid(axis='x',alpha=.15); ax.set_axisbelow(True)
        for bar, value, row in zip(bars,v[::-1],rows[::-1]):
            unknown = row['unknown_usage_calls'] if index == 0 else 0
            if unknown: bar.set_hatch('///')
            label = f'{value:,.1f}' if index == 0 else str(value)
            if unknown: label += f' ＋不明{unknown}回'
            ax.text(value+max(v+[1])*.025,bar.get_y()+bar.get_height()/2,label,va='center',fontsize=9)
    for ext in ('svg','png','pdf'): fig.savefig(f/('p38_costs.'+ext),dpi=180)
    plt.close(fig)
    with (f/'p38_results.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=['arm','success','model_calls','known_total_tokens',
                             'unknown_usage_calls','api_requests','stop_reason'],extrasaction='ignore')
        writer.writeheader();writer.writerows(rows)


def build(root, output):
    (comparison,audit,costs,prefix,p33,p37,misses), hashes = evidence(root)
    output.mkdir(parents=True,exist_ok=True); charts(output,comparison)
    slides=[]
    def add(title,body='',take='',notes='',refs=(),cover=False):
        slides.append(dict(title=title,body=body,take=take,notes=notes,refs=list(refs),cover=cover))
    add('AIハーネスによる<br>不要な情報取得の削減に向けた検証',cover=True,
        notes='取得制御の実装と検証の進捗。性能維持と総費用削減を達成したという発表ではない。')
    add('背景：仕事を完了するまでに、処理が積み重なる',
        '<p class="lead">AIに任せる対象は、回答生成だけでなく、調査・操作・確認を伴う仕事。</p>'
        '<div class="diagram tight">'+scope_diagram()+'</div>'
        '<p class="small">ハーネス＝AIへ渡す情報、ツール実行、状態管理、検証、停止を制御する外側の仕組み。</p>',
        notes='複数AIへ広げると取得と共有も設計対象になる。現在は、その基礎となる単一作業役の情報取得を検証している。社会全体の普及率や費用増加率を測った資料ではない。',
        refs=('docs/research_objective_20261022.md',))
    add('目的：必要な情報を残して、仕事全体の費用を減らす',
        '<div class="two"><div class="col"><h3>起こり得る無駄</h3><p class="body">すでに取得した値を、別のAPIから再取得する。<br>情報を省きすぎて、調べ直しや追加生成が増える。</p></div>'
        '<div class="col"><h3>今回、測ること</h3><p class="body">最終課題を完了できたか。<br>開始から終了まで何回呼び出したか。<br>全入力・出力と追加処理にいくらかかったか。</p></div></div>',
        '一部の入力・API回数だけが減っても、研究目的の達成とはしない。',
        notes='単一作業役の取得を扱う局所実験。複数AIの通信費用削減や担当再編の有効性はまだ測っていない。',
        refs=('docs/contribution_status_20261022.md',))
    add('なぜこの実験か：入力の省略だけでは総費用が増えた',
        '<p class="lead">直前の４既知課題では、初回入力を減らしても、全体のトークンは増えた。</p>'
        '<table><thead><tr><th>入力の構成</th><th>成功</th><th>総トークン</th></tr></thead><tbody>'+''.join(
            f'<tr><td>{label}</td><td>{p33["totals"][arm]["successes"]}/4</td><td>{p33["totals"][arm]["known_total_tokens"]:,}</td></tr>'
            for arm,label in [('full_keep','全履歴'),('stdout_mask_keep','古い長い出力を省略'),('stdout_mask_index_keep','省略＋変数・API一覧')])+
        '</tbody></table><p class="body">次は、情報を消す前に「すでにある必要項目で、取得を省けるか」を調べる。</p>',
        notes='P33全12件の結果。各１試行なので同数の成功を品質維持の証明にしない。取得後の未参照を、不要と判断する案も見送った。',
        refs=('docs/P33_findings.md','docs/P35_findings.md'))
    add('実装：要求された項目を、状態を確かめて再利用する',
        '<div class="diagram">'+architecture()+'</div>',
        notes='対応範囲はSpotifyの曲一覧から曲詳細の公開５項目。実行単位・対象・項目・版・公開実装を照合する。部分的な一致だけでは成功を返さず、通常取得へ進む。必要項目はモデルがコードで指定する。',
        refs=('docs/P37_findings.md','docs/experiments/P38_projected_runtime.md'))
    add('実験の前提：同じ仕事・途中状態から、３方式を比較',
        '<p class="lead">曲情報を書き出す既知１課題。８応答後の会話・Python・アプリ状態を復元。</p>'
        '<table class="compact"><thead><tr><th>方式</th><th>何を再利用できるか</th></tr></thead><tbody>'
        '<tr><td>毎回取得</td><td>必要項目の読取も、その都度APIを呼ぶ</td></tr>'
        '<tr><td>同一APIを再利用</td><td>同じAPI・引数の過去の全返却</td></tr>'
        '<tr><td>別APIの項目も再利用</td><td>上記に加え、意味と状態を確認した必要項目</td></tr></tbody></table>'
        '<p class="body">全方式で、説明・初回入力13,552 token・モデル・権限が同じ。<br>後続上限：16生成、12万token、480秒。APIは共通前半を含め80回。</p>'
        '<p class="small">MiniMax M3 IQ4_XS・入力上限65,536。各１回。対象は開発後に選んだ機構利用の確認用。</p>',
        notes='毎回取得にも同じ項目読取を与え、道具の説明の差を作らない。通常の同一要求キャッシュを強い対照にする。未閲覧12シナリオは使っていない。固定順序で推論サーバーのKVキャッシュは消去していない。',
        refs=('configs/P38_projected_reads_v01.json','reports/P38_prefix_checks.json'))
    table='<table class="compact"><thead><tr><th>方式</th><th>最終結果</th><th>AI呼出し</th><th>同一API再利用</th><th>別API再利用</th></tr></thead><tbody>'
    for label,r,c in zip(NAMES,comparison['rows'],costs['rows']):
        n=c['read_account']; table+=f'<tr><td>{label}</td><td>{"成功" if r["success"] else "未達"}</td><td>{r["model_calls"]}</td><td>{n.get("raw_exact",0)+n.get("projected_exact",0)}</td><td>{n.get("projected_cross_api",0)}</td></tr>'
    table+='</tbody></table>'
    add('結果：最終成否と、実際に使われた再利用を確認',
        '<div class="diagram"><img src="figures/p38_costs.svg" style="width:100%;height:260px" alt="全３条件の総トークンと実API呼出し"></div>'+table,
        notes='斜線の棒は既知使用量の下限。不明分をゼロとしない。低費用でも失敗なら効率的な完了とは扱わない。３方式の行動列は実行後に異なるため、差の全てをキャッシュに帰属させない。',
        refs=('reports/P38_comparison.json','reports/P38_runtime_costs.json'))
    m=misses['rows'][2]
    add('考察：再利用の対象と、次に必要な対象が違った',
        '<div class="two"><div class="col"><h3>前半で保持していた値</h3>'+
        f'<p class="n">{m["available_source_objects_at_boundary"]}対象</p><p class="body">曲一覧から取得済み。<br>後続の無効化は０回。</p></div>'+
        '<div class="col"><h3>後続の項目読取</h3>'+
        f'<p class="n">{m["explicit_projected_requests"]}要求</p><p class="body">全て、候補キャッシュでは未観測。<br>前半の12対象への要求は０。</p></div></div>'+
        '<p class="body">この要求列では、無効化を緩めても不足している値は作れない。</p>',
        notes='各要求の返却を見る前に照合した。記録列を変えない診断で、モデルの行動を変えた場合の反実仮想ではない。別の取得方法の不存在まで証明していない。P37の別軌跡での11件を今回の節約へ転記しない。',
        refs=('reports/P38_miss_diagnostics.json','docs/P38_findings.md'))
    audit_table='<table class="compact"><thead><tr><th>方式</th><th>照合した通常応答</th><th>再利用値の実取得照合</th><th>最終DB</th></tr></thead><tbody>'
    for label,r in zip(NAMES,audit['rows']):
        audit_table+=f'<tr><td>{label}</td><td>{r["matched_sent"]}</td><td>{r["matched_cached"]}</td><td>{"一致" if r["db_files_match"] else "不一致／未確認"}</td></tr>'
    audit_table+='</tbody></table>'
    add('検証：再利用の正しさと、課題の正しさは別',
        '<p class="lead">実験終了後に、別の隔離環境で同じ操作列を再生。<br>今回は再利用０件のため、通常応答の再現を確認した。</p>'+audit_table+
        f'<p class="body">監査用の追加API：{audit["verification_api_requests"]}回。追加AI・最終評価器：０回。<br>値が一致しても、仕事を最後まで達成できた証明にはならない。</p>',
        notes='モデルには監査結果を戻していない。後から最終成果物を選び直していない。固定された操作列の再現であり、別の課題や実サービスでの一般的な安全性は保証しない。',
        refs=('reports/P38_cache_replay.json','docs/P38_audit_plan.md'))
    add('既存との差：部品の実装だけでは、新規性にならない',
        '<table class="story-table"><thead><tr><th>内容</th><th>現在の位置づけ</th></tr></thead><tbody>'
        '<tr><td>同じ結果をキャッシュする</td><td>既存技術。対照として必要。</td></tr>'
        '<tr><td>別の問い合わせの一部を再利用する</td><td>意味的キャッシュに先行研究がある。</td></tr>'
        '<tr><td>状態・履歴・由来を確認する</td><td>ツールキャッシュ等と重なる。</td></tr>'
        '<tr><td>AIの仕事全体で品質と費用を制御する</td><td>研究目的。独自の制御と追加価値は未確立。</td></tr></tbody></table>'
        '<p class="body">現在は、採用候補を測定して絞る段階。新しい名前を付けて新手法とはしない。</p>',
        notes='Semantic Data Caching and Replacement、TVCache等の確認済み範囲は参考表へ。原典の読んだ範囲と未確認の採録状態を区別している。',
        refs=('docs/data_reuse_overlap_20261022.md','docs/contribution_status_20261022.md'))
    successes=sum(r['success'] for r in comparison['rows'])
    hits=sum(c['read_account'].get('projected_cross_api',0) for c in costs['rows'])
    add('次の判断：局所の節約を、成果の改善につなげられるか',
        f'<p class="lead">今回：成功 {successes}/3、別APIの項目再利用 {hits}回。<br>１既知課題・各１回で、一般的な品質維持と総費用削減は未確立。</p>'
        '<div class="two"><div class="col"><h3>次に確かめること</h3><p class="body">残った失敗は取得費用か、処理の進め方か。<br>既存の通常方式では説明できない改善余地があるか。</p></div>'
        '<div class="col"><h3>進めないこと</h3><p class="body">成功するまで上限を増やす。<br>結果を見て確認用課題を調整する。<br>再利用回数だけで論文の主張にする。</p></div></div>',
        notes='10月31日投稿の目標は維持するが、研究上の中心主張が不足している。23日の実験・あらまし目標に向け、拡大実験より採否の判断を優先する。',
        refs=('docs/P38_findings.md','docs/contribution_status_20261022.md'))
    parts=[]
    for i,s in enumerate(slides,1):
        if s['cover']:
            parts.append(f'<section class="slide cover"><h1>{s["title"]}</h1><div class="notes">{html.escape(s["notes"])}</div></section>');continue
        refs=' / '.join(f'<a href="{LINK+n}">{html.escape(n)}</a>' for n in s['refs'])
        parts.append(f'<section class="slide"><div class="eyebrow">取得制御の検証 / {i-1:02d}</div><h2>{s["title"]}</h2>'+s['body']+
                     (f'<div class="takeaway">{s["take"]}</div>' if s['take'] else '')+
                     f'<div class="footer"><span class="sources">{refs}</span><span>{i}/{len(slides)}</span></div><div class="notes">{html.escape(s["notes"])}</div></section>')
    nav='<nav id="nav"><button id="prev">←</button><span id="count"></span><button id="next">→</button><button id="all">一覧</button><button id="note">説明</button><button id="print">印刷</button></nav><aside id="speaker"></aside>'
    (output/'index.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>AIハーネスによる取得制御の検証</title><style>'+STYLE+'</style></head><body>'+''.join(parts)+nav+'<script>'+SCRIPT+'</script></body></html>')
    (output/'slides.json').write_text(json.dumps(slides,ensure_ascii=False,indent=2)+'\n')
    manifest={'pages':len(slides),'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),
              'source_sha256':hashes,'builder_sha256':sha(Path(__file__)),
              'all_three_results_included':True,'visual_reviewed':False}
    (output/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


def export(output):
    chrome='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    with tempfile.TemporaryDirectory(prefix='p38-report-') as profile:
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
    p.add_argument('--output',type=Path,default=ROOT/'materials/20261022_p38');p.add_argument('--pdf',action='store_true');a=p.parse_args()
    print(json.dumps(build(a.repo_root,a.output)))
    if a.pdf:export(a.output)
