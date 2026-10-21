"""Render completed P20/P21 diagnostics, including non-submissions and all costs."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from build_research_presentation import SLIDES, slide, text, node, arrow, banner, table, picture, NAVY, TEAL, MUTED
from presentation_renderer import render

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'materials/20261021_p21'
STEM = 'AI_harness_P20_P21_20261021'
REPO = 'https://github.com/sophiria1225/AI-/blob/main/'


def sources():
    all_rows, groups, paths = [], [], []
    for phase in ('P20', 'P21'):
        p = f'reports/{phase}_export_diagnostic_summary.json'
        q = f'reports/{phase}_generation_budget_audit.json'
        result, budget = [json.loads((ROOT/name).read_text()) for name in (p,q)]
        if (result['audit_errors'] or budget['schema_disagreements']
                or result['model_calls'] != 6 or len(result['outputs']) != 6
                or len(budget['outputs']) != 6 or result['unknown_usage_calls']
                or result['known_total_tokens'] != budget['known_total_tokens']):
            raise ValueError('completed, audited six-output batch required')
        for value, cost in zip(result['outputs'], budget['outputs'], strict=True):
            if any(value[k] != cost[k] for k in ('call_id', 'variant', 'seed', 'schema_valid')):
                raise ValueError('outcome/budget row mismatch')
            if value['known_tokens'] != cost['input_tokens'] + cost['output_tokens']:
                raise ValueError('row token mismatch')
            all_rows.append({'phase': phase, 'cap': 4096 if phase == 'P20' else 8192,
                             **{k: value[k] for k in ('call_id', 'variant', 'seed', 'schema_valid', 'complete_export')},
                             **{k: cost[k] for k in ('input_tokens', 'output_tokens', 'wall_seconds', 'finish_reason')}})
        for variant in ('literal_csv', 'data_program'):
            rows = [r for r in all_rows if r['phase'] == phase and r['variant'] == variant]
            if len(rows) != 3:
                raise ValueError('three fixed seeds per variant required')
            groups.append({'phase': phase, 'variant': variant, 'cap': rows[0]['cap'],
                           'submitted': sum(r['schema_valid'] for r in rows),
                           'correct': sum(r['complete_export'] for r in rows),
                           'input_tokens': sum(r['input_tokens'] for r in rows),
                           'output_tokens': sum(r['output_tokens'] for r in rows),
                           'wall_seconds': sum(r['wall_seconds'] for r in rows)})
        paths += [p,q]
    return all_rows, groups, paths


def plot(rows, groups):
    folder = OUTPUT/'figures'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder/'export_budget.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    plt.rcParams.update({'font.family': 'Hiragino Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(13.5,4.8), layout='constrained')
    labels = [g['phase']+' / '+('直接CSV' if g['variant']=='literal_csv' else '計算コード') for g in groups]
    indices = list(range(4))
    axes[0].barh([i-.17 for i in indices], [g['submitted'] for g in groups], height=.3, color='#276B8C', label='形式適合の提出')
    axes[0].barh([i+.17 for i in indices], [g['correct'] for g in groups], height=.3, color='#2A8F7A', label='完全な書出')
    axes[0].set_yticks(indices, labels); axes[0].invert_yaxis()
    axes[0].set_xlim(0,3.7); axes[0].set_xticks([0,1,2,3])
    axes[0].set_xlabel('各条件３生成中の件数'); axes[0].legend(loc='lower right')
    for i,g in enumerate(groups):
        axes[0].text(g['submitted']+.05,i-.17,str(g['submitted']),va='center',fontsize=10)
        axes[0].text(g['correct']+.05,i+.17,str(g['correct']),va='center',fontsize=10)
    left = [g['input_tokens']/1000 for g in groups]
    right = [g['output_tokens']/1000 for g in groups]
    axes[1].barh(indices, left, color='#8FA4B6', label='入力')
    axes[1].barh(indices, right, left=left, color='#A66A32', label='出力')
    axes[1].set_yticks(indices, labels); axes[1].invert_yaxis()
    upper = max(a+b for a,b in zip(left,right))
    axes[1].set_xlim(0,upper*1.22); axes[1].set_xlabel('総入力＋出力（千トークン）')
    axes[1].legend(loc='lower right', bbox_to_anchor=(1, 1.01), ncol=2, frameon=False)
    for i,(a,b) in enumerate(zip(left,right)):
        axes[1].text(a+b+.3,i,f'{a+b:.1f}',va='center',fontsize=10)
    for ax in axes:
        ax.grid(axis='x',alpha=.15); ax.set_axisbelow(True)
    fig.suptitle('P20 / P21：未提出も除外せず、全12生成を表示',fontsize=16)
    fig.supxlabel('１つの既知開発状態の反復。提出なしの場合は内容の品質差を判断しない。\n出力には推論過程も含む。使用量不明０。',fontsize=10)
    for ext in ('png','pdf','svg'):
        fig.savefig(folder/('export_budget.'+ext),dpi=180,metadata={'Creator':'build_export_presentation.py'})
    plt.close(fig)
    path = folder/'export_budget.svg'
    path.write_text('\n'.join(s.rstrip() for s in path.read_text().splitlines())+'\n')


def build(groups, interpretation, supplementary):
    SLIDES.clear()
    footer = '2026-10-21｜既知１状態・各方式３seed｜出力部分の診断。独立６課題・全体性能ではない'
    totals = {phase: {key: sum(g[key] for g in groups if g['phase']==phase)
                      for key in ('submitted','correct','input_tokens','output_tokens','wall_seconds')}
              for phase in ('P20','P21')}
    s = slide('RESEARCH CHECKPOINT / P20・P21', '出力方式の比較と、生成上限の制約', source=footer)
    text(s,40,170,880,98,interpretation['headline'],27,NAVY,True)
    for i,phase in enumerate(('P20','P21')):
        v=totals[phase]
        text(s,45,292+52*i,870,38,
             f"{phase}：提出 {v['submitted']}/6、完全な書出 {v['correct']}/6、総 {v['input_tokens']+v['output_tokens']:,} トークン",21)
    banner(s,'目的：通常の計算で足りるかを確認し、追加のハーネス機構が必要か判断する。',size=17)

    s = slide('01 / 比較のアーキテクチャ','両方式へ同じ取得済み観測を渡す',
              'P18のCSVや欠落行、正解件数、隠し評価を生成側へ渡さない。',footer)
    node(s,35,235,220,100,'要求＋66観測','観測文字列・モデルは共通')
    node(s,310,173,230,90,'直接CSVの生成','文字列として全内容を提出')
    node(s,310,315,230,90,'計算コードの生成','限定されたデータ実行器')
    node(s,610,235,305,115,'全６生成後に内容を照合','公開観測から分析者が定義した評価')
    arrow(s,255,260,305,215); arrow(s,255,310,305,355)
    arrow(s,540,215,605,265); arrow(s,540,355,605,315)
    text(s,40,428,880,55,'P20は4,096出力、P21は8,192出力。両方式を等しく変更。\nseed・指示・入力は固定。思考と提出物の生成を含む全費用を記録する。',17,MUTED)

    s = slide('02 / 全条件の結果','提出の有無と、提出内容の正しさを分ける',
              '３seedは同じ入力の反復。課題数を水増ししない。',footer)
    values=[]
    for g in groups:
        values.append([g['phase'],'直接CSV' if g['variant']=='literal_csv' else '計算コード',
                       f"{g['cap']:,}",f"{g['submitted']}/3",f"{g['correct']}/3",
                       f"{g['input_tokens']+g['output_tokens']:,}"])
    table(s,['実験','方式','出力上限','提出','完全書出','総トークン'],values,
          [85,185,140,125,125,220],y=174,row_h=53,size=17)
    text(s,45,465,870,43,'未提出・打切りは成功に数えない。CSVが存在しない場合、\n欠落行数や余分な行数は「評価対象なし」であり、０件の正解ではない。',16,MUTED)

    s = slide('03 / 費用と提出','全12生成を残し、予算変更の効果を分ける',
              '計算コードを使うだけで新規性が得られるとは扱わない。',footer)
    picture(s,'export_budget',x=30,y=164,w=900,h=320)

    s = slide('04 / 補助検査と解釈','１入力での正解を、一般的な正しさへ広げない',source=footer)
    text(s,45,170,870,90,
         f"提出コードの補助評価：対象 {supplementary['eligible_programs']} 件。\n"
         f"４変換すべてに適合 {supplementary['programs_passing_all_four']} 件。追加モデル呼出し０。\n"
         '固定CSVには適用しない。検査対象なしを合格とは数えない。',20)
    text(s,45,292,870,130,'\n'.join(interpretation['interpretation_points']),18)
    banner(s,'補助検査は既存の検査原理を利用。自律的な仕様生成や新機構の実績ではない。',size=16)

    s = slide('05 / 次の判断と投稿','４ページの原稿に載せる主張を、実測で絞る',
              '10/23主要実験・あらまし、10/31投稿完了。採録は査読に依存する。',footer)
    text(s,45,167,870,116,interpretation['next_action'],19)
    links=[('P20：全結果と上限を増やした理由','docs/P20_findings.md'),
           ('P21：全結果・解釈・採らない案','docs/P21_findings.md'),
           ('既存研究との機能の重なり','docs/export_mechanism_review_20261021.md'),
           ('確認群を残した追加開発課題の準備','docs/experiments/P22_development_preparation.md')]
    for i,(label,path) in enumerate(links):
        text(s,48,327+39*i,860,29,label,17,TEAL,True,url=REPO+path)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--font',type=Path,default=Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'))
    args=p.parse_args()
    rows,groups,paths=sources()
    paths+=['reports/P21_interpretation.json','reports/P21_supplementary_summary.json','docs/P21_findings.md']
    interpretation=json.loads((ROOT/paths[-3]).read_text())
    supplementary=json.loads((ROOT/paths[-2]).read_text())
    if interpretation['primary_results_finalized'] is not True or supplementary['phase']!='P21_supplementary':
        raise ValueError('finalized interpretation and supplementary report required')
    plot(rows,groups);build(groups,interpretation,supplementary)
    render(SLIDES,OUTPUT,args.font,stem=STEM,title='P20・P21：出力方式と生成上限の診断')
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    manifest={'pages':len(SLIDES),'source_sha256':{p:digest(ROOT/p) for p in paths},
              'builder_source_sha256':{p:digest(ROOT/p) for p in ('scripts/build_export_presentation.py',
                  'scripts/build_research_presentation.py','scripts/presentation_renderer.py')},
              'figures_sha256':{p.stem:digest(p) for p in (OUTPUT/'figures').glob('*.png')},
              'all_twelve_outputs_retained':True,'font':str(args.font),'font_file_redistributed':False}
    (OUTPUT/'build_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    transcript=['# P20・P21：出力方式と生成上限の診断','']
    for i,spec in enumerate(SLIDES,1):
        transcript += [f"## {i}. {spec['title']}",'']+[e['text']+'\n' for e in spec['elements'] if e['kind']=='text']
    (OUTPUT/'transcript.md').write_text('\n'.join(transcript)+'\n')
    print(json.dumps({'pages':len(SLIDES),'output':str(OUTPUT)}))


if __name__=='__main__':
    main()
