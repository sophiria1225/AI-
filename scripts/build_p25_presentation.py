"""Six-slide milestone from the fully audited four-case P18/P25 comparison."""
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
FOLDER = ROOT/'materials/20261021_p25'
STEM = 'AI_harness_P18_P25_20261021'
LINK = 'https://github.com/sophiria1225/AI-/blob/main/'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources():
    paths = ['reports/P18_P25_paired_comparison.json', 'reports/P25_interpretation.json',
             'reports/P25_public_trace_diagnostics.json', 'docs/P25_findings.md']
    pair, note = [json.loads((ROOT/p).read_text()) for p in paths[:2]]
    if (len(pair['pairs']) != 4 or not note['all_four_reviewed']
            or len(note['task_labels']) != 4):
        raise ValueError('complete four-task review required')
    for path, expected in {**pair['source_hashes'], **note['source_sha256']}.items():
        if sha(ROOT/path) != expected:
            raise ValueError('changed comparison source: '+path)
        paths.append(path)
    return pair, note, sorted(set(paths))


def figures(pair):
    out = FOLDER/'figures'; out.mkdir(parents=True, exist_ok=True)
    rows = [dict(task_number=i, arm=arm, **row[arm])
            for i,row in enumerate(pair['pairs'],1) for arm in ('baseline','guided')]
    with (out/'paired_costs.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    plt.rcParams.update({'font.family':'Hiragino Sans','font.size':11,
                         'axes.spines.top':False,'axes.spines.right':False})
    fig, axes = plt.subplots(1,3,figsize=(13.5,4.8),layout='constrained')
    for ax,(key,scale,label) in zip(axes,[('known_total_tokens',1000,'既知の総トークン（千）'),
        ('api_requests',1,'送信したAPI要求'),('execution_wall_seconds',60,'実行時間（分）')],strict=True):
        for arm,offset,color,name in [('baseline',-.18,'#788695','P18：旧基準'),
                                     ('guided',.18,'#277C85','P25：一般指示あり')]:
            values = [r[arm][key]/scale for r in pair['pairs']]
            ax.barh([i+offset for i in range(4)], values, height=.34,color=color,label=name)
            for i,(row,value) in enumerate(zip(pair['pairs'],values,strict=True)):
                label_value = str(row[arm][key]) if scale==1 else f'{value:.1f}'
                if key=='known_total_tokens' and row[arm]['unknown_usage_calls']:
                    label_value += f" + 不明{row[arm]['unknown_usage_calls']}"
                ax.text(value+max(values)*.014,i+offset,label_value,va='center',fontsize=8)
        maximum = max(r[a][key]/scale for r in pair['pairs'] for a in ('baseline','guided'))
        ax.set_xlim(0,max(maximum*1.35,1))
        ax.set_yticks(range(4),[f'課題{i}' for i in range(1,5)] if ax is axes[0] else [])
        ax.invert_yaxis(); ax.set_xlabel(label); ax.grid(axis='x',alpha=.15); ax.set_axisbelow(True)
    fig.suptitle('同じ４開発課題・同じ上限：P24と同じ一般指示を転用\n'
                 '灰：P18（旧基準）　青緑：P25（一般指示あり）',fontsize=13)
    unknown = sum(pair['totals'][arm]['unknown_usage_calls'] for arm in ('baseline','guided'))
    fig.supxlabel(f'各条件１seed。使用量不明 {unknown} 呼出し。取得・計算・書込みの新しい道具は追加していない。',fontsize=10)
    for ext in ('png','pdf','svg'): fig.savefig(out/('paired_costs.'+ext),dpi=180)
    plt.close(fig)
    p=out/'paired_costs.svg'; p.write_text('\n'.join(line.rstrip() for line in p.read_text().splitlines())+'\n')


def build(pair,note):
    SLIDES.clear()
    b,g=pair['totals']['baseline'],pair['totals']['guided']
    footer='同じ４開発課題・各条件１seed｜一般指示の転用確認。独自方式の効果ではない'
    s=slide('RESEARCH CHECKPOINT / P25','取得後の処理を含む４課題で、通常基準を確かめる',source=footer)
    text(s,40,172,880,107,note['headline'],24,NAVY,True)
    text(s,45,294,870,115,
        '研究目的：情報保持・共有・実行制御が、最終品質と費用に与える影響を調べる。\n'
        f"今回：旧基準 {b['successes']}/4 → 一般指示あり {g['successes']}/4。\n"
        f"P25：{g['model_calls']}生成、既知{g['known_total_tokens']:,}トークン、{g['api_requests']} API。",20)
    banner(s,'新規性は未確立。通常機能の校正と、論文で主張する独自の差を区別する。',size=16)

    s=slide('01 / 比較アーキテクチャ','同じ一般指示を、成功例を含む別の４件へ適用する',source=footer)
    node(s,40,183,230,96,'同じ４件の要求','P18と同じ順序・seed42')
    node(s,340,163,260,77,'P18：旧基準','既存のシステム指示')
    node(s,340,273,260,77,'P25：一般指示あり','P24から内容を変更しない')
    node(s,670,212,250,106,'模擬アプリと独立評価','履歴・観測・費用を保存')
    arrow(s,270,215,338,201); arrow(s,270,245,338,309)
    arrow(s,600,201,667,244); arrow(s,600,309,667,283)
    text(s,45,377,870,92,
        'M3 IQ4_XS／64K／全履歴。各課題45万token・80 LLM・80 API・30分。\n'
        '正解件数・デモ・計算道具は追加しない。確認用12シナリオは未閲覧。\n'
        '全件終了後に公開観測を分析。独立評価を実行中のモデルへ戻さない。',17)

    s=slide('02 / 全４件の成否と費用','改善・悪化・維持を、全て同じ表に残す',source=footer)
    rows=[]
    for label,row in zip(note['task_labels'],pair['pairs'],strict=True):
        br,gr=row['baseline'],row['guided']
        rows.append([label,'成功' if br['success'] else '未達','成功' if gr['success'] else '未達',
                     f"{br['known_total_tokens']:,}",f"{gr['known_total_tokens']:,}"])
    rows.append(['合計',f"{b['successes']}/4",f"{g['successes']}/4",
                 f"{b['known_total_tokens']:,}",f"{g['known_total_tokens']:,}"])
    table(s,['課題','旧基準','一般指示','旧・既知token','新・既知token'],rows,
          [285,95,105,195,200],y=177,row_h=48,size=16)
    text(s,45,487,870,25,'全費用を含む記述的比較。４課題・１seedから有意差や一般的な優位は主張しない。',14,MUTED)

    s=slide('03 / 全費用','費用の増加や未完了も含めて比較する',source=footer)
    picture(s,'paired_costs',x=22,y=166,w=916,h=326)

    s=slide('04 / 観測と考察','実際の行動と、新しい機構の必要性を分ける',source=footer)
    for x,finding in zip((40,500),note['findings'],strict=True):
        card(s,x,169,420,267,finding['title'],finding['text'],body_size=17)
    banner(s,note['interpretation_limit'],size=15)

    s=slide('05 / 新規性・次の実験・投稿',note['next_title'],
        '投稿原稿は２段組４ページ。主要実験・あらまし10/23、投稿完了10/31。',footer)
    text(s,45,167,870,143,note['decision_text'],17)
    links=[('P25：全結果・判断理由・代案','docs/P25_findings.md'),
           ('取得・計算・書込み：比較条件と近接研究','docs/output_access_review_20261021.md'),
           ('４ページ原稿：主張と未完了事項','papers/202610_letter/README.md'),
           ('研究の作業ボード','docs/task_board.md')]
    for i,(label,path) in enumerate(links):
        text(s,48,328+38*i,860,28,label,17,TEAL,True,url=LINK+path)


def main():
    pair,note,paths=sources()
    figures(pair); build(pair,note)
    font=Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
    render(SLIDES,FOLDER,font,stem=STEM,title='P18・P25：一般指示の転用、全結果と次の研究判断')
    manifest=dict(pages=len(SLIDES),source_sha256={p:sha(ROOT/p) for p in paths},
        builder_source_sha256={p:sha(ROOT/p) for p in (
            'scripts/build_p25_presentation.py','scripts/build_research_presentation.py',
            'scripts/presentation_renderer.py')},
        figures_sha256={p.name:sha(p) for p in (FOLDER/'figures').iterdir()},
        font=str(font),font_file_redistributed=False,
        scope='Descriptive four-case development comparison, not novel-method evidence.')
    (FOLDER/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'pages':len(SLIDES),'folder':str(FOLDER)}))


if __name__ == '__main__': main()
