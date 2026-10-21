"""P11-P14 milestone: audited development outcomes and a falsifiable next step."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from build_research_presentation import (
    SLIDES, slide, text, arrow, node, card, banner, table, picture,
    NAVY, TEAL, MUTED, AMBER, WARM,
)
from build_p13_presentation import totals
from presentation_renderer import render

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'materials/20261021_p14'
STEM = 'AI_harness_P11_P14_20261021'
LABELS = ['全履歴', '直近履歴', 'FOCUS適合版', '通常台帳']
REPO = 'https://github.com/sophiria1225/AI-/blob/main/'


def figures(data):
    plt.rcParams.update({'font.family': ['Hiragino Sans', 'DejaVu Sans'], 'font.size': 13,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 4.5), layout='constrained')
    colors = ['#286b8a', '#bd732a', '#6c8d55', '#80619e']
    for i, row in enumerate(data):
        base = (row['tokens']-row['memory_tokens'])/1000
        axes[0].bar(i, base, color=colors[i], width=.6)
        axes[0].bar(i, row['memory_tokens']/1000, bottom=base, color=colors[i],
                    hatch='//', edgecolor='#333333', linewidth=.5, width=.6)
        prefix = '≥' if row['unknown'] else ''
        axes[0].text(i, row['tokens']/1000+12, prefix+f"{row['tokens']:,}", ha='center', fontsize=11)
        axes[1].bar(i, row['minutes'], color=colors[i], width=.6)
        axes[1].text(i, row['minutes']+1, f"{row['minutes']:.1f}分", ha='center', fontsize=12)
    for ax in axes:
        ax.set_xticks(range(4), [f"{s}\n成功 {d['successes']}/4" for s,d in zip(LABELS,data)])
        ax.grid(axis='y', alpha=.18); ax.set_axisbelow(True)
    axes[0].set_ylim(0, max(d['tokens']/1000 for d in data)*1.25)
    axes[1].set_ylim(0, max(d['minutes'] for d in data)*1.25)
    axes[0].set_ylabel('既知の入力＋出力（千トークン）')
    axes[1].set_ylabel('実行時間の合計（分）')
    axes[0].legend(handles=[Patch(facecolor='white', edgecolor='#333333', hatch='//',
                                 label='保持を生成する費用')], frameon=False, fontsize=10)
    axes[0].set_title('使用量不明は下限で表示')
    axes[1].set_title('単一スロット・各条件１試行')
    for ext in ('png','pdf','svg'):
        fig.savefig(OUTPUT/'figures'/('cohort_totals.'+ext), dpi=180,
                    metadata={'Creator':'build_p14_presentation.py'})
    plt.close(fig)


def build(measured, data, updates, interrupted):
    SLIDES.clear()
    footer = '2026-10-21｜P11〜P14：４開発課題・各条件１試行｜新規性・一般的優位は未確定'
    p14 = data[-1]
    s = slide('RESEARCH CHECKPOINT / P11–P14', '何を作り、何が分かり、何を論文で問うか', source=footer)
    text(s,40,155,880,110,'AIの作業状態を、後の担当へ\n正しく、少ない費用で渡したい。',32,NAVY,True)
    text(s,40,286,880,118,'通常台帳までの４条件比較を完了。\n今月末の２ページレターに向け、問題を一つに絞る。\n次の問い：未実行の要求を、記憶と修復へどう渡すか。',21)
    banner(s,'今回の結果は既存方式の開発比較。次の機構の有効性は、これから判定する。',size=16)

    s = slide('01 / 目的とアーキテクチャ','研究対象は、モデルの外側の情報・実行境界',
              '共通モデル、共通ツール、独立評価。保持と引き継ぎの仕組みを操作する。',footer)
    node(s,40,177,240,90,'要求・公開API仕様','正解・追加評価は隔離')
    node(s,340,177,280,90,'実行役のLLM','調査・操作・完了判断')
    node(s,680,177,240,90,'実行器 → 模擬環境','引数検査・送信・返却')
    arrow(s,280,222,338,222);arrow(s,620,222,678,222)
    node(s,340,329,280,96,'後続へ渡す作業状態','全履歴／直近／生成記憶',fill=WARM,accent=AMBER)
    node(s,680,329,240,96,'原記録・保存点','根拠・送信状態・総費用')
    node(s,40,329,240,96,'終了後の独立評価','最終状態を別に検査')
    arrow(s,800,267,800,327);arrow(s,680,377,622,377);arrow(s,480,329,480,269)
    arrow(s,800,425,800,438,dashed=True,end=False)
    arrow(s,800,438,160,438,dashed=True,end=False)
    arrow(s,160,438,160,427,dashed=True)
    banner(s,'目標：最終品質を保つ費用削減。台帳の形式適合や参照IDだけで正しさを保証しない。',size=15)

    s = slide('02 / 比較設計','同じ４課題、同じモデル、同じ打ち切り条件',
              '各課題45万総トークン・30分・80 LLM呼出・80 API要求。M3、単一スロット。',footer)
    table(s,['条件','保持するもの','費用に含むもの'],[
        ['全履歴 P11','元の応答・観測を保持','過去の履歴の再入力'],
        ['直近履歴 P12','4K目安・元の応答単位','原文再読・再取得'],
        ['FOCUS適合版 P13','計画引用＋保持の救済','草案生成・無効提出'],
        ['通常台帳 P14','出典付き項目＋直近履歴','台帳生成・無効提出'],
    ],[200,360,320],y=170,row_h=52,size=16)
    banner(s,'P14は一般的なLLM生成台帳。論文「Ledger」の決定的な実行状態方式とは異なる。',size=15.5)

    s = slide('03 / 全体結果','失敗と使用量不明を含めた４条件の比較',
              '４件・１試行なので、方式の一般的な優劣や品質同等性の証明ではない。',footer)
    table(s,['条件','成功','既知総トークン','呼出','不明使用量'],[
        [label,f"{d['successes']}/4",('≥' if d['unknown'] else '')+f"{d['tokens']:,}",
         str(d['calls']),str(d['unknown'])] for label,d in zip(LABELS,data)
    ],[205,100,250,125,200],y=174,row_h=51,size=18)
    banner(s,'全担当・制御の費用を合計。実行役だけの削減を、そのままシステムの節約としない。',size=15.5)

    s = slide('04 / グラフ','短い入力と、仕事全体の低費用は同じではない',
              '保持生成・再取得・時間切れを含む。時間は独立評価を除く。',footer)
    picture(s,'cohort_totals',x=40,y=165,w=880,h=294)
    text(s,45,469,870,25,f"P13の別途中中断：既知{interrupted:,}＋使用量不明１件。上図の完了４試行とは別に保存。",13,MUTED)

    s = slide('05 / 台帳の内訳','台帳を作る費用と、履歴を落とす効果を分ける',
              '適合した台帳の項目が、意味的にもすべて正しいと判定したものではない。',footer)
    rows=[]
    for i,(t,u) in enumerate(zip(measured[-1]['trials'],updates),1):
        c=u['update_status_counts']
        rows.append([str(i),'成功' if t['evaluation']['official_success'] else '未達',
                     f"{c.get('ok',0)}/{c.get('invalid_keep_original',0)}/{c.get('aborted',0)}",
                     f"{u['known_memory_tokens']:,}"+('＋不明' if u['unknown_memory_usage_calls'] else ''),
                     str(u['updates_removing_original_spans'])])
    table(s,['課題','結果','更新 適合/不正/中断','台帳の既知費用','削除した更新'],rows,
          [80,100,235,235,230],y=177,row_h=50,size=16)
    banner(s,f"台帳生成：既知{p14['memory_tokens']:,}トークン。無効な提出は原履歴を維持し、費用は算入。",size=15)

    s = slide('06 / 考察と限界','既存方式をつないだ比較から、独自性はまだ言えない',
              'タイムアウト、形式不備、履歴の変化、単一スロットの再入力が混在する。',footer)
    card(s,40,174,420,254,'今回、確認できたこと',
         '共通接続と全費用の監査。\n通常台帳で原履歴の削除が発生。\n保存点・最終状態との対応を検査。\n失敗を含む比較と具体的な制約。',body_size=18)
    card(s,500,174,420,254,'これだけでは言えないこと',
         '生成台帳は一般に劣るという結論。\n要約が唯一の失敗原因であること。\n大規模タスクや別モデルへの一般化。\n新規アルゴリズムの有効性。',body_size=18)
    banner(s,'この４件の結果を、提案方式の本評価へ流用して成功としない。',size=17)

    s = slide('07 / 新規性の候補と先行研究','狙う差は、誤完了の抑制と修復情報の両立',
              '一般的な状態タグ・出典管理・用途別の記憶アクセスは、既に研究されている。',footer)
    table(s,['近接研究／単純な対策','既にある点・今回確かめる点'],[
        ['HaluMem','記憶の幻覚・未確認情報の評価が既存'],
        ['Ledger / Cordon','観測と試行済み要求、実行境界の管理が既存'],
        ['MemTX','用途や状態に応じた読み分けも既存'],
        ['今回の限定した問い','拒否要求を隠す利益と、修復材料を失う損失を測る'],
    ],[260,620],y=172,row_h=53,size=16)
    banner(s,'追加価値が残るかは未確定。名称変更や部品の接続を新規性の根拠にしない。',size=16)

    s = slide('08 / 次の制御実験','同じ拒否要求を、記憶と修復へ分けて渡す候補',
              '図は提案候補。P16はまず記憶側24生成だけを測り、採否を判断する。',footer)
    node(s,40,177,250,100,'送信前に拒否した要求','実行器の送信０記録で確定')
    node(s,370,177,250,100,'記憶更新への表示','拒否・参照IDを保持')
    node(s,670,177,250,100,'修復への表示','未送信の原要求を参照')
    arrow(s,290,210,368,210);arrow(s,290,245,320,245,end=False)
    arrow(s,320,245,320,300,end=False);arrow(s,320,300,795,300,end=False);arrow(s,795,300,795,279)
    text(s,45,329,870,100,'比較：元入力／未送信タグ／両用途から退避／用途別表示。\nP16：４課題×記録通り・人工拒否×３表示＝24生成。\n未知の引数による人工条件。自然な失敗率や仕事全体の成功率は測らない。',19)
    banner(s,'元入力で再現しない・タグで十分・修復損失がない場合は、追加機構の主張を見直す。',size=15)

    s = slide('09 / 投稿までの成果物','今週に実験とあらまし、月末までに投稿を完了する',
              '暫定投稿先：和文論文誌D・研究速報・人工知能（D140803 知識の共有・再利用）。',footer)
    table(s,['期限','完成させるもの'],[
        ['10/23','限定実験の採否・主結果・あらまし'],
        ['10/25','必要な追加確認・数値と主張の固定'],
        ['10/29〜30','２段組２ページ原稿・図表・著者情報・最終点検'],
        ['10/31','投稿完了。採録日とは分けて管理'],
    ],[200,680],y=174,row_h=53,size=17)
    banner(s,'結果が裏づける範囲へ主張を絞る。改善率と新規性を先に決めてデータを合わせない。',size=15)

    s = slide('10 / 根拠・詳細','数値、選定理由、棄却条件をGitHubから確認できる',
              '原文、模擬認証値、モデル推論、評価正解は公開しない。',footer)
    links=[('４条件とP14の全結果','docs/P14_findings.md'),
           ('機構候補と近接研究の重複','docs/letter_mechanism_review_20261021.md'),
           ('P16の固定条件・採否基準','docs/experiments/P16_event_view_probe.md'),
           ('投稿分野・期限・採用しなかった候補','docs/letter_october2026_plan.md'),
           ('あらまし・本文骨格の準備状況','papers/202610_letter/draft_status.json')]
    for i,(label,path) in enumerate(links):
        text(s,45,177+54*i,870,35,label,21,TEAL,True,url=REPO+path)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--font',type=Path,default=Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'))
    args=parser.parse_args()
    sources=[f'reports/P{p}_final_measurements.json' for p in (11,12,13,14)]
    sources += [f'reports/P14_{n:02d}_ledger_updates.json' for n in range(1,5)]
    sources += ['reports/P13_interruption_20261021.json','docs/P14_findings.md',
                'docs/letter_mechanism_review_20261021.md','docs/experiments/P16_event_view_probe.md',
                'docs/letter_october2026_plan.md','papers/202610_letter/draft_status.json']
    measured=[json.loads((ROOT/p).read_text()) for p in sources[:4]]
    identities=[[r['task_id'] for r in m['trials']] for m in measured]
    if any(ids!=identities[0] for ids in identities):
        raise ValueError('task identities/order differ')
    data=[totals(m) for m in measured]
    updates=[json.loads((ROOT/p).read_text()) for p in sources[4:8]]
    interrupted=json.loads((ROOT/sources[8]).read_text())['interrupted_cost']['known_total_tokens']
    (OUTPUT/'figures').mkdir(parents=True,exist_ok=True)
    figures(data)
    with (OUTPUT/'figures/cohort_totals.csv').open('w',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=['condition']+list(data[0]));w.writeheader()
        w.writerows({'condition':label,**row} for label,row in zip(LABELS,data))
    build(measured,data,updates,interrupted)
    render(SLIDES,OUTPUT,args.font,stem=STEM,title='AIハーネス研究 P14の区切りとレターの検証課題')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    manifest={'pages':len(SLIDES),'scope':'Four development tasks per condition, one trial. No novel-method claim. P16 is a prepared feasibility probe, not an established improvement.',
              'totals':data,'source_sha256':{p:sha(ROOT/p) for p in sources},
              'builder_source_sha256':{p:sha(ROOT/p) for p in (
                  'scripts/build_p14_presentation.py','scripts/build_p13_presentation.py',
                  'scripts/build_research_presentation.py','scripts/presentation_renderer.py')},
              'figures_sha256':{'cohort_totals':sha(OUTPUT/'figures/cohort_totals.png')},
              'font':str(args.font),'font_file_redistributed':False}
    (OUTPUT/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    transcript=['# P11〜P14 開発比較と投稿準備の区切り','',manifest['scope'],'']
    for i,spec in enumerate(SLIDES,1):
        transcript += [f"## {i}. {spec['title']}",'']
        transcript += [e['text']+'\n' for e in spec['elements'] if e['kind']=='text']
    (OUTPUT/'transcript.md').write_text('\n'.join(transcript)+'\n')
    print(json.dumps({'pages':len(SLIDES),'output':str(OUTPUT)}))


if __name__=='__main__':
    main()
