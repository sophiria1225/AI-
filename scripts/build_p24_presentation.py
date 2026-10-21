"""Report a complete, audited P22/P24 comparison; never read live traces."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from build_research_presentation import (
    SLIDES, slide, text, node, arrow, card, banner, table, picture, NAVY, TEAL, MUTED,
)
from presentation_renderer import render

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'materials/20261021_p24'
STEM = 'AI_harness_P22_P24_20261021'
LINK = 'https://github.com/sophiria1225/AI-/blob/main/'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sources():
    paths = ['reports/P22_P24_paired_comparison.json', 'reports/P24_interpretation.json',
             'reports/P24_public_trace_diagnostics.json', 'docs/P24_findings.md']
    pair, note = [json.loads((ROOT/p).read_text()) for p in paths[:2]]
    if len(pair['pairs']) != 6 or not note['all_six_reviewed']:
        raise ValueError('complete six-task review required')
    for p, expected in {**pair['source_hashes'], **note['source_sha256']}.items():
        if sha(ROOT/p) != expected:
            raise ValueError('changed comparison source: '+p)
        paths.append(p)
    if len(note['task_labels']) != 6:
        raise ValueError('six labels required')
    return pair, note, sorted(set(paths))


def figures(pair):
    out = FOLDER/'figures'
    out.mkdir(parents=True, exist_ok=True)
    rows = [dict(task_number=i, arm=arm, **r[arm])
            for i,r in enumerate(pair['pairs'],1) for arm in ('baseline','guided')]
    with (out/'paired_costs.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n')
        w.writeheader();w.writerows(rows)
    plt.rcParams.update({'font.family':'Hiragino Sans','font.size':10,
                         'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,3,figsize=(13.5,4.8),layout='constrained')
    for ax,(key,scale,label) in zip(axes,[
        ('known_total_tokens',1000,'既知の総トークン（千）'),
        ('api_requests',1,'送信したAPI要求'),
        ('execution_wall_seconds',60,'実行時間（分）')],strict=True):
        for arm,offset,color,name in [('baseline',-.18,'#788695','P22：旧基準'),
                                       ('guided',.18,'#277C85','P24：一般指示あり')]:
            values=[r[arm][key]/scale for r in pair['pairs']]
            ax.barh([i+offset for i in range(6)],values,height=.34,color=color,label=name)
            for i,(r,v) in enumerate(zip(pair['pairs'],values,strict=True)):
                val=str(r[arm][key]) if scale==1 else f'{v:.1f}'
                if key=='known_total_tokens' and r[arm]['unknown_usage_calls']:
                    val+=' + 不明1'
                ax.text(v+max(values)*.014,i+offset,val,va='center',fontsize=8)
        maximum=max(r[a][key]/scale for r in pair['pairs'] for a in ('baseline','guided'))
        ax.set_xlim(0,maximum*1.33)
        ax.set_yticks(range(6),[f'課題{i}' for i in range(1,7)] if ax is axes[0] else [])
        ax.invert_yaxis();ax.set_xlabel(label);ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    axes[0].legend(loc='lower right',fontsize=9)
    fig.suptitle('同じ６開発課題・同じ上限：通常指示を補った比較',fontsize=16)
    fig.supxlabel('各条件１seed。P22には使用量不明１呼出しがあり、正確な総トークン差は算出しない。',fontsize=10)
    for ext in ('png','pdf','svg'):
        fig.savefig(out/('paired_costs.'+ext),dpi=180)
    plt.close(fig)
    p=out/'paired_costs.svg'
    p.write_text('\n'.join(x.rstrip() for x in p.read_text().splitlines())+'\n')


def build(pair,note):
    SLIDES.clear()
    b,g=pair['totals']['baseline'],pair['totals']['guided']
    footer='2026-10-21｜同じ６開発課題・各条件１seed｜既知の指示による校正。新方式の検証ではない'
    s=slide('RESEARCH CHECKPOINT / P24','一般指示をそろえ、独自機構の必要性を見直す',source=footer)
    text(s,40,173,880,100,note['headline'],25,NAVY,True)
    text(s,45,291,870,112,
         f"旧基準 {b['successes']}/6 → 一般指示あり {g['successes']}/6。全件を評価・監査。\n"
         f"P24：{g['model_calls']}生成、{g['known_total_tokens']:,}トークン、{g['api_requests']} API。\n"
         f"使用量不明 {g['unknown_usage_calls']}件。モデル・予算・課題は維持。",21)
    banner(s,'この差を独自技術の効果には数えない。新規性と有効性は、引き続き未確定。',size=16)

    s=slide('01 / 背景と目的','同じモデルで、仕事を正しく完了できる構成を調べる',source=footer)
    card(s,40,172,420,246,'研究全体',
         '情報が複数の資料・操作へ分散する仕事で、\n'
         '保持・共有・実行制御の違いが、\n'
         '最終品質と費用をどう変えるかを測る。\n'
         'モデルの外側の状態と実行を扱う、\n'
         'ハーネス内部の研究。',body_size=17)
    card(s,500,172,420,246,'今回の役割',
         '弱い比較基準による失敗を、\n'
         '新しい制御の必要性と誤認しない。\n'
         '公式の一般案内を補い、\n'
         '残る失敗と悪影響を全件で確認する。\n'
         '正解集合やデモは追加しない。',body_size=17)
    banner(s,'目標は独自の状態・更新規則と効果を示すこと。基準校正の完了とは分ける。',size=16)

    s=slide('02 / 比較アーキテクチャ','システム指示だけを変更し、同じ初期環境から実行する',source=footer)
    node(s,40,182,230,96,'同じ６件の要求','P22と同じ順序・seed42')
    node(s,340,163,260,77,'P22：旧基準','既存のシステム指示')
    node(s,340,273,260,77,'P24：一般指示を追記','時刻・列挙・完了形式など')
    node(s,670,212,250,106,'模擬アプリと独立評価','履歴・観測・費用を保存')
    arrow(s,270,215,338,201);arrow(s,270,245,338,309)
    arrow(s,600,201,667,244);arrow(s,600,309,667,283)
    text(s,45,377,870,92,
         'M3 IQ4_XS／64K／全履歴。各課題45万token・80 LLM・80 API・30分。\n'
         '一般指示は公式の既知規則。複数規則をまとめたため、個別寄与は未分離。\n'
         '全件終了後に公開観測を分析。最終評価の内容をモデルへ戻さない。',17)

    s=slide('03 / 全６件の成否と費用','改善・悪化・維持を、全て同じ表に残す',source=footer)
    rows=[]
    for label,r in zip(note['task_labels'],pair['pairs'],strict=True):
        br,gr=r['baseline'],r['guided']
        rows.append([label,'成功' if br['success'] else '未達',
                     '成功' if gr['success'] else '未達',
                     f"{br['known_total_tokens']:,}",f"{gr['known_total_tokens']:,}"])
    rows.append(['合計',f"{b['successes']}/6",f"{g['successes']}/6",
                 f"{b['known_total_tokens']:,}",f"{g['known_total_tokens']:,}"])
    table(s,['課題','旧基準','一般指示','旧・既知token','新・既知token'],rows,
          [285,95,105,195,200],y=170,row_h=38,size=15)
    text(s,45,480,870,27,'旧課題３は使用量不明１呼出し。１seedの開発比較から有意差や一般化は主張しない。',14,MUTED)

    s=slide('04 / 全費用','費用が増えた課題も残し、成功数だけで判断しない',source=footer)
    picture(s,'paired_costs',x=22,y=166,w=916,h=326)

    s=slide('05 / 公開観測の考察','行動がどう変わったかと、原因の確定を分ける',source=footer)
    for x,finding in zip((40,500),note['findings'],strict=True):
        card(s,x,169,420,267,finding['title'],finding['text'],body_size=17)
    banner(s,note['interpretation_limit'],size=15)

    s=slide('06 / 新規性と採否','現在の結果から、主張すること・見送ることを決める',source=footer)
    text(s,45,171,870,242,note['decision_text'],19)
    banner(s,'新しい名称や機能の数ではなく、既存対照でも残る具体的な差を検証する。',size=16)

    s=slide('07 / 次に目指す成果',note['next_title'],
            '投稿原稿は２段組４ページ。主要実験・あらまし10/23、投稿完了10/31。',footer)
    text(s,45,169,870,135,note['next_text'],17)
    links=[('P24：全結果・判断理由・代案','docs/P24_findings.md'),
           ('ページ取得規則：成功例への過剰介入','docs/collection_frontier_findings_20261021.md'),
           ('近接研究との機能的な重なり','docs/collection_scope_review_20261021.md'),
           ('４ページ原稿の主張と現在地','papers/202610_letter/README.md')]
    for i,(label,path) in enumerate(links):
        text(s,48,326+38*i,860,28,label,17,TEAL,True,url=LINK+path)


def main():
    pair,note,paths=sources()
    figures(pair);build(pair,note)
    font=Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
    render(SLIDES,FOLDER,font,stem=STEM,title='P22・P24：一般指示の校正、全結果と研究の現在地')
    manifest=dict(pages=len(SLIDES),source_sha256={p:sha(ROOT/p) for p in paths},
        builder_source_sha256={p:sha(ROOT/p) for p in (
            'scripts/build_p24_presentation.py','scripts/build_research_presentation.py',
            'scripts/presentation_renderer.py')},
        figures_sha256={p.name:sha(p) for p in (FOLDER/'figures').iterdir()},
        font=str(font),font_file_redistributed=False,
        scope='Descriptive development comparison of a known instruction bundle, not novel-method evidence.')
    (FOLDER/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'pages':len(SLIDES),'folder':str(FOLDER)}))


if __name__=='__main__':
    main()
