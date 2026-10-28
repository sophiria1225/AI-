"""Four scientific figure candidates; no experimental data are generated.

Run with Python + matplotlib + Pillow. Set JAPANESE_FONT to a suitable local
font when not on macOS. SVG text is outlined; PDF fonts are embedded.
"""
from pathlib import Path
import hashlib
import json
import os
import unicodedata

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle, FancyArrowPatch
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
font_candidates = [p for p in Path('/System/Library/Fonts').glob('*.ttc')
                   if unicodedata.normalize('NFC', p.name) == 'ヒラギノ角ゴシック W3.ttc']
FONT = Path(os.environ.get('JAPANESE_FONT', str(font_candidates[0]) if font_candidates else ''))
if not FONT.is_file():
    raise RuntimeError('Set JAPANESE_FONT to a Japanese font file')
FP = font_manager.FontProperties(fname=str(FONT))
plt.rcParams.update({'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'path',
                     'svg.hashsalt': 'harness-architecture-candidates-20261029',
                     'axes.unicode_minus': False, 'savefig.facecolor': 'white'})
INK = '#1b2730'
GRAY = '#eef1f3'
BLUE = '#e8f0f5'
figures = []


class Drawing:
    def __init__(self, width, height, name):
        self.width, self.height, self.name = width, height, name
        self.fig = plt.figure(figsize=(width/25.4, height/25.4))
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set(xlim=(0, width), ylim=(height, 0), aspect='equal')
        self.ax.axis('off')
        self.texts = []

    def text(self, x, y, s, size=9, ha='center', va='center', color=INK, bold=False):
        t = self.ax.text(x, y, s, fontsize=size, fontproperties=FP,
            ha=ha, va=va, linespacing=1.35, color=color,
            fontweight='bold' if bold else 'normal', zorder=5)
        self.texts.append(t)
        return t

    def box(self, x, y, w, h, s, size=9, fill='white', dashed=False):
        self.ax.add_patch(Rectangle((x, y), w, h, linewidth=.9,
            edgecolor=INK, facecolor=fill, linestyle='--' if dashed else '-', zorder=2))
        self.text(x+w/2, y+h/2, s, size=size)
        return (x, y, w, h)

    def line(self, points, dashed=False, width=.85, color=INK):
        xs, ys = zip(*points)
        self.ax.plot(xs, ys, color=color, linewidth=width,
                     linestyle='--' if dashed else '-', solid_joinstyle='round', zorder=1)

    def arrow(self, points, dashed=False):
        if len(points)>2:
            self.line(points[:-1], dashed=dashed)
        self.ax.add_patch(FancyArrowPatch(points[-2], points[-1],
            arrowstyle='-|>', mutation_scale=9, linewidth=.85, color=INK,
            linestyle='--' if dashed else '-', shrinkA=0, shrinkB=0, zorder=3))

    def save(self, title, description, intended_width):
        self.fig.canvas.draw()
        renderer=self.fig.canvas.get_renderer()
        outside=[]
        for t in self.texts:
            r=t.get_window_extent(renderer)
            if not self.fig.bbox.contains(r.x0,r.y0) or not self.fig.bbox.contains(r.x1,r.y1):
                outside.append(t.get_text())
        if outside:raise ValueError(('text outside figure',outside))
        for ext in ['png','svg','pdf']:
            self.fig.savefig(OUT/f'{self.name}.{ext}', dpi=300,
                metadata={'Creator':'Reproducible matplotlib scientific diagram'} if ext=='pdf' else None)
        plt.close(self.fig)
        figures.append(dict(id=self.name,title=title,description_ja=description,
            width_mm=self.width,height_mm=self.height,intended_paper_width_mm=intended_width,
            png=f'{self.name}.png',svg=f'{self.name}.svg',pdf=f'{self.name}.pdf'))


def candidate1():
    d=Drawing(180,166,'candidate_01_two_studies')
    d.text(6,7,'実験A：入力履歴の制御',11,ha='left',bold=True)
    d.text(174,7,'単発／別呼出し反復／同時反復を比較',8,ha='right')
    d.box(6,18,33,19,'課題・指示\n保持する履歴')
    d.box(49,18,36,19,'入力履歴の構成\n要約＋残存履歴',fill=BLUE)
    d.box(95,18,33,19,'課題実行LLM\n（actor）')
    d.box(138,18,36,19,'環境・API\n生成コードの実行')
    d.arrow([(39,27.5),(49,27.5)])
    d.arrow([(85,27.5),(95,27.5)])
    d.arrow([(128,27.5),(138,27.5)])
    d.box(99,48,75,17,'完全な履歴をホストに保存',fill=GRAY)
    d.box(49,48,36,17,'要約機会での\n候補生成・採否判定',fill=BLUE,size=8.5)
    d.arrow([(156,37),(156,48)])
    d.arrow([(99,56.5),(85,56.5)])
    d.arrow([(67,48),(67,37)])
    d.text(6,56,'実行中の\n履歴更新',8,ha='left')
    d.text(6,73,'focus＝要約専用のLLM呼出し。同時反復はactorが行動と要約候補を出力。',8,ha='left')
    d.line([(6,81),(174,81)],dashed=True,color='#69747c')
    d.text(6,89,'実験B：次の生成に進む前の終了制御',11,ha='left',bold=True)
    d.box(6,101,35,20,'課題実行LLM\n（actor）')
    d.box(51,101,38,20,'環境・API\n応答内の全コードを実行')
    d.box(100,101,38,20,'公開記録から\n完了根拠を検査',fill=BLUE)
    d.box(149,101,25,20,'通常の\n完了通知',size=8.5)
    d.arrow([(41,111),(51,111)])
    d.arrow([(89,111),(100,111)])
    d.arrow([(138,111),(149,111)])
    d.text(143.5,97,'支持あり',7.5)
    d.arrow([(119,121),(119,133),(23.5,133),(23.5,121)])
    d.text(72,130,'未知・未対応・矛盾 → 通常継続',8)
    d.line([(6,142),(174,142)],dashed=True,color='#69747c')
    d.text(6,150,'両実験で共通の評価',9,ha='left',bold=True)
    d.text(65,150,'全モデル呼出しの入力＋出力を集計',8.5,ha='left')
    d.text(6,159,'実行後：終了時の状態 → 公式評価器 → 最終成功を判定（答えをLLMへ返さない）',8,ha='left')
    d.save('案1：独立した二つの実験の構成',
        '上段に入力履歴の制御、下段に完了後継続の制御を配置。二つは別実験であり、組合せ方式の効果は示さない。研究全体を初めて説明するときに向く。',180)


def candidate2():
    d=Drawing(180,137,'candidate_02_summary_comparison')
    d.text(90,7,'実験A：要約呼出しの配置を比較',11,bold=True)
    d.text(90,16,'課題実行とAPI操作を繰り返し、入力履歴が閾値に達すると要約機会を設ける',8)
    labels=[('単発別要約','Single','最大1回の要約機会'),
            ('別呼出し反復','Separate','最大3回の要約機会'),
            ('同時反復','Inline','最大3回の要約機会')]
    for i,(ja,en,frequency) in enumerate(labels):
        x=6+i*58
        d.box(x,25,52,18,ja+'\n'+en,9.2,fill=GRAY)
        d.text(x+26,49,frequency,8)
        if i<2:
            d.box(x,57,52,20,'要約専用LLM（focus）\n古い履歴から要約候補を生成',8.5,fill=BLUE)
        else:
            d.box(x,57,52,20,'課題実行LLM（actor）\n行動と要約候補を同時に生成',8.5,fill=BLUE)
        d.arrow([(x+26,52),(x+26,57)])
        d.box(x,86,52,17,'候補の形式・長さを検査\n次の入力が短くなれば採用',8.5)
        d.arrow([(x+26,77),(x+26,86)])
        d.box(x,112,52,14,'次のactorへ\n要約＋残存履歴を入力',8.5)
        d.arrow([(x+26,103),(x+26,112)])
    d.text(90,133,'生成コードは通常どおり実行。要約用呼出しを含む総トークン数と最終成功で比較。',8)
    d.save('案2：要約3方式の並列比較',
        '要約機会、要約候補の生成役、採否判定、次の課題実行入力を3列で比較。反復要約と同時生成方式の違いを最も直接説明できる。実験Bは含めない。',180)


def candidate3():
    d=Drawing(180,160,'candidate_03_execution_boundary')
    d.text(90,7,'実行中の制御と、実行後の評価を分離',11,bold=True)
    xs=[25,71,117,160]
    names=['ハーネス\n入力・実行制御','LLM\n課題実行（actor）','環境・API\n公開実行結果','公式評価器\n最終成功の判定']
    for x,name in zip(xs,names):
        d.box(x-18,17,36,19,name,8.5,fill=GRAY)
        d.line([(x,36),(x,151)],dashed=True,color='#859099')
    def label(x,y,text):
        t=d.text(x,y,text,8)
        t.set_bbox(dict(facecolor='white',edgecolor='none',pad=1.3))
    d.arrow([(25,46),(71,46)]);label(48,42,'課題・入力履歴')
    d.arrow([(71,59),(25,59)]);label(48,55,'生成プログラム')
    d.arrow([(25,72),(117,72)]);label(71,68,'環境APIを操作')
    d.arrow([(117,85),(25,85)]);label(71,81,'公開結果・実行記録')
    d.box(8,94,127,22,'実験A：次回入力の要約制御\n実験B：公開根拠による終了判断\nA・Bは別々の実験で適用する',8.5,fill=BLUE)
    d.arrow([(8,105),(3,105),(3,46),(25,46)])
    d.text(142,105,'実行中は\n評価の答えを\n利用しない',8,ha='left')
    d.line([(7,124),(174,124)],dashed=True,width=1.1)
    d.text(8,121,'実行終了',8,ha='left')
    d.arrow([(117,136),(160,136)]);label(138.5,132,'終了時の状態')
    d.arrow([(160,149),(25,149)]);label(92.5,145,'成功・失敗を記録（実行後のみ）')
    d.text(90,157,'費用は全モデル呼出しを集計。公式評価器からLLMへ向かう経路は設けない。',8)
    d.save('案3：実行と評価の境界を示す時系列',
        '左からハーネス・LLM・環境・公式評価器の順。上から下へ処理が進む。実行中に評価の正解を使わず、終了後の状態で成功を測ることを明確にする。',180)


def candidate4():
    d=Drawing(85,147,'candidate_04_single_column')
    d.text(42.5,6,'ハーネスの二つの作用点',10.5,bold=True)
    d.text(42.5,14,'実験A・Bは別々に評価',8)
    d.text(5,23,'実験A：入力履歴',9,ha='left',bold=True)
    d.box(14,29,57,16,'要約機会で候補を生成・検査\n単発／別呼出し反復／同時反復',8,fill=BLUE)
    d.box(14,53,57,13,'課題実行LLM（actor）',8.5)
    d.arrow([(42.5,45),(42.5,53)])
    d.text(46,49,'要約＋残存履歴',7,ha='left')
    d.box(14,74,57,13,'環境API・実行履歴の保存',8.2)
    d.arrow([(42.5,66),(42.5,74)])
    d.arrow([(71,80.5),(79,80.5),(79,37),(71,37)])
    d.line([(5,94),(80,94)],dashed=True,color='#69747c')
    d.text(5,102,'実験B：次の生成の要否',9,ha='left',bold=True)
    d.box(5,109,34,17,'全コード実行後\n公開完了根拠を検査',7.5,fill=BLUE)
    d.box(49,109,31,17,'支持：完了通知\n不確定：通常継続',7.5)
    d.arrow([(39,117.5),(49,117.5)])
    d.text(42.5,135,'共通：全呼出しの入力＋出力を集計',7.5)
    d.text(42.5,143,'実行後の公式評価器で最終成功を判定',7.5)
    d.save('案4：レター1段向けの簡潔な構成',
        '85 mm幅を前提とする省スペース案。二つの作用点と共通の測定だけに絞る。方式の詳細は本文で説明し、全体像を小さく載せたい場合に向く。',85)


def contact_sheet():
    canvas=Image.new('RGB',(2200,2550),'#edf0f2')
    draw=ImageDraw.Draw(canvas)
    tf=ImageFont.truetype(str(FONT),37)
    sf=ImageFont.truetype(str(FONT),26)
    for i,row in enumerate(figures):
        x=35+(i%2)*1100;y=25+(i//2)*1260
        draw.rectangle((x,y,x+1030,y+1215),fill='white')
        draw.text((x+25,y+22),row['title'],font=tf,fill=INK)
        draw.text((x+25,y+77),f"原図 {row['width_mm']} × {row['height_mm']} mm",font=sf,fill='#47515a')
        im=Image.open(OUT/row['png']).convert('RGB')
        im.thumbnail((980,1080))
        canvas.paste(im,(x+(1030-im.width)//2,y+120+(1080-im.height)//2))
    canvas.save(OUT/'contact_sheet.png')


if __name__=='__main__':
    candidate1();candidate2();candidate3();candidate4();contact_sheet()
    manifest=dict(status='candidates_not_adopted',language='ja',font_name='Hiragino Sans W3',
        font_sha256=hashlib.sha256(FONT.read_bytes()).hexdigest(),svg_text='outlines',
        pdf_fonttype=42,scientific_source='harness_efficiency_20261029_v04/main.tex',
        source_commit='b6ce22771bd959c125b6c47208e015eac5eec2dc',
        studies_combined=False,eval_answers_fed_to_llm=False,
        generated_experimental_data=False,candidates=figures,
        notes_ja=['全図は説明用の候補であり、本文への採用は未確定。',
                  'LLMの呼出し配置や制御の位置を表し、モデル内部構造は表さない。',
                  'SVG/PDFはベクタ形式。PNGは300 dpi。フォントファイルは配布しない。'])
    manifest['sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted(OUT.iterdir()) if p.suffix in {'.png','.svg','.pdf','.py'}}
    (OUT/'candidates.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    print('Created four candidates and contact_sheet.png')
