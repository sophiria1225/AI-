"""Japanese publication figure: two independently evaluated control points.

No experiment, model, tokenizer or network calls. Requires matplotlib, Pillow,
CairoSVG and PyMuPDF. PDF/EPS use outlined SVG glyphs, not TTC font embedding.
Set JAPANESE_FONT to a Japanese font file when not on macOS. All dimensions are
millimetres; font sizes are points at the final 130 mm publication width.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import unicodedata

import cairosvg
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle, Circle
import pymupdf

WIDTH, HEIGHT = 130, 85
INK, PALE, GRAY = '#202020', '#f1f1f1', '#777777'
LW = .65
FIXED_TIME = datetime(2026, 10, 29, tzinfo=timezone.utc)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def font_path():
    candidates = [p for p in Path('/System/Library/Fonts').glob('*.ttc')
                  if unicodedata.normalize('NFC', p.name) == 'ヒラギノ角ゴシック W3.ttc']
    p = Path(os.environ.get('JAPANESE_FONT', str(candidates[0]) if candidates else ''))
    if not p.is_file():
        raise RuntimeError('Set JAPANESE_FONT to a Japanese font file')
    return p


class Drawing:
    def __init__(self):
        self.font = font_manager.FontProperties(fname=str(font_path()))
        self.fig = plt.figure(figsize=(WIDTH/25.4, HEIGHT/25.4))
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set(xlim=(0, WIDTH), ylim=(HEIGHT, 0), aspect='equal')
        self.ax.axis('off')
        self.texts = []

    def text(self, x, y, s, size=7, ha='center', color=INK, background=False):
        t = self.ax.text(x, y, s, fontsize=size, fontproperties=self.font,
                        ha=ha, va='center', linespacing=1.2, color=color,
                        bbox=dict(facecolor='white', edgecolor='none', pad=.2)
                             if background else None, zorder=5)
        self.texts.append(t)
        return t

    def line(self, points, color=INK, lw=LW, dashed=False):
        x, y = zip(*points)
        self.ax.plot(x, y, color=color, linewidth=lw,
                     linestyle=(0, (3, 2)) if dashed else '-',
                     solid_joinstyle='round', solid_capstyle='round', zorder=2)

    def arrow(self, points, dashed=False):
        if len(points) > 2:
            self.line(points[:-1], dashed=dashed)
        self.ax.add_patch(FancyArrowPatch(points[-2], points[-1],
            arrowstyle='-|>', mutation_scale=6.6, linewidth=LW, color=INK,
            linestyle=(0, (3, 2)) if dashed else '-', shrinkA=0, shrinkB=0,
            zorder=3))

    def document(self, x, y, w, h, label, stacked=False, short=False):
        if stacked:
            for offset in (2, 1):
                self.ax.add_patch(Polygon([(x-offset, y-offset), (x+w-offset, y-offset),
                    (x+w-offset, y+h-offset), (x-offset, y+h-offset)],
                    closed=True, edgecolor=GRAY, facecolor='white', linewidth=.5, zorder=1))
        fold = 2.1
        self.ax.add_patch(Polygon([(x, y), (x+w-fold, y), (x+w, y+fold),
            (x+w, y+h), (x, y+h)], closed=True,
            facecolor='white', edgecolor=INK, linewidth=LW, zorder=2))
        self.line([(x+w-fold, y), (x+w-fold, y+fold), (x+w, y+fold)])
        self.text(x+w/2, y+3.4, label)
        for j in range(1 if short else 2):
            self.line([(x+3, y+6.2+j*1.7), (x+w-3-(2 if short else j), y+6.2+j*1.7)],
                      color=GRAY, lw=.45)

    def process(self, x, y, w, h, label, terminal=False, fill=PALE):
        self.ax.add_patch(FancyBboxPatch((x, y), w, h,
            boxstyle=f'round,pad=0,rounding_size={h/2 if terminal else 1.5}',
            edgecolor=INK, facecolor=fill, linewidth=LW, zorder=2))
        self.text(x+w/2, y+h/2, label, size=7.2)

    def paper(self, x, y, w, h, label, stacked=False, fill='white'):
        if stacked:
            for offset in (1.6, .8):
                self.ax.add_patch(Rectangle((x-offset, y-offset),w,h,
                    facecolor='white',edgecolor=GRAY,linewidth=.45,zorder=1))
        f=2
        self.ax.add_patch(Polygon([(x,y),(x+w-f,y),(x+w,y+f),(x+w,y+h),(x,y+h)],
            closed=True,facecolor=fill,edgecolor=INK,linewidth=LW,zorder=2))
        self.line([(x+w-f,y),(x+w-f,y+f),(x+w,y+f)])
        self.text(x+w/2,y+h/2,label)

    def diamond(self,cx,cy,dx,dy,label):
        self.ax.add_patch(Polygon([(cx-dx,cy),(cx,cy-dy),(cx+dx,cy),(cx,cy+dy)],
            closed=True,facecolor='white',edgecolor=INK,linewidth=LW,zorder=2))
        self.text(cx,cy,label)

    def marker(self,x,y,label):
        self.ax.add_patch(Circle((x,y),1.8,facecolor='white',edgecolor=INK,
            linewidth=LW,zorder=4))
        self.text(x,y,label,7)

    def draw(self):
        self.text(3,3,'共通の実行経路と制御点（AとBは独立に評価）',8,ha='left')
        self.text(127,6.3,'全LLM呼出しの入出力を計上',7,ha='right')
        self.paper(3,10,17,12,'入力課題')
        self.arrow([(21,16),(30,16)])
        self.paper(31,9,30,15,'実行時の入力\n課題＋提示履歴')
        self.arrow([(62,16),(71,16)])
        self.process(72,10,22,12,'LLM\n行動を生成')
        self.arrow([(95,16),(104,16)])
        self.process(105,10,22,12,'生成した操作\nを実行（API）')
        self.arrow([(116,22.5),(116,28)])
        self.paper(105,29,22,10,'完全な履歴\nホストに保存',stacked=True)
        self.line([(116,26),(95,26),(95,35)])
        self.arrow([(95,35),(74,35)])
        self.text(103,23.9,'生成応答・実行記録',7)
        self.text(84,32.4,'記録を追加',7)
        self.paper(44,29,29,10,'提示する履歴\n採用要約＋未要約分')
        self.arrow([(56,28.5),(56,24.5)])
        self.marker(46,26.5,'A')
        self.marker(95,30.3,'B')
        self.ax.add_patch(Rectangle((2,23.7),39,16,facecolor='white',edgecolor=GRAY,
            linestyle=(0,(3,2)),linewidth=.5,zorder=1))
        self.text(21.5,25.7,'実行終了後のみ',7)
        self.paper(3,29,16,10,'終了時\nの状態')
        self.arrow([(19.5,34),(23.5,34)])
        self.process(24,29,16,10,'公式評価\n最終成功',fill='white')
        self.line([(3,40.7),(127,40.7)],color=GRAY,lw=.5)

        self.text(3,43,'A 提示履歴の更新',7.8,ha='left')
        self.text(127,43,'専用要約の例／同時生成は行動と同じ応答',7,ha='right')
        self.diamond(16,52.5,12,7,'入力長\n新規ターン数\n回数上限')
        self.arrow([(28.5,52.5),(35,52.5)])
        self.process(36,47,23,11,'LLMで要約\n既存要約＋\n古い未要約分')
        self.arrow([(59.5,52.5),(61.5,52.5)])
        self.diamond(75,52.5,13,7,'形式・長さ\n次入力の短縮')
        self.arrow([(88.5,52.5),(103,52.5)])
        self.text(95.5,49.2,'採用',7)
        self.paper(104,47,23,11,'要約＋直近履歴\n提示履歴（A）へ')
        self.arrow([(16,59.5),(16,62.1),(103,62.1)])
        self.line([(75,59.5),(75,62.1)])
        self.text(53,62.1,'条件外・不採用',7,background=True)
        self.process(104,60,23,4.2,'提示履歴を維持',fill='white')
        self.line([(3,65.2),(127,65.2)],color=GRAY,lw=.5)

        self.text(3,67.8,'B 応答内の全操作実行後に完了判定',7.8,ha='left')
        self.paper(3,70,24,10,'API実行記録')
        self.arrow([(28,75),(33,75)])
        self.process(34,70,25,10,'対象・日時\n移動先・名前',fill='white')
        self.arrow([(59.5,75),(66.5,75)])
        self.diamond(78,75,11,6.5,'根拠が\n揃うか')
        self.arrow([(89.5,75),(97,75),(97,72),(104,72)])
        self.text(96,68.5,'根拠あり',7)
        self.process(105,68.8,22,6.4,'終了通知',terminal=True)
        self.text(116,77,'次の生成を省く',7)
        self.arrow([(78,81.5),(98,81.5),(98,81.7),(104,81.7)])
        self.text(95,79.2,'不足・不明',7,background=True)
        self.process(105,79.5,22,4.4,'行動生成へ戻る',fill='white')


    def save(self, out, stem, variant):
        self.fig.canvas.draw()
        renderer = self.fig.canvas.get_renderer()
        bounds = [(t.get_text(), t.get_window_extent(renderer)) for t in self.texts]
        clipped = [s for s, r in bounds if not self.fig.bbox.contains(r.x0, r.y0)
                   or not self.fig.bbox.contains(r.x1, r.y1)]
        overlaps = [(a, b) for i, (a, ra) in enumerate(bounds)
                    for b, rb in bounds[i+1:] if ra.overlaps(rb)]
        if clipped or overlaps:
            raise ValueError({'clipped': clipped, 'text_overlaps': overlaps})
        outputs = {}
        for ext in ('png', 'svg', 'pdf', 'eps'):
            metadata = None
            if ext == 'pdf':
                metadata = {'Creator': 'render_control_points.py',
                            'CreationDate': FIXED_TIME, 'ModDate': FIXED_TIME}
            elif ext == 'svg':
                metadata = {'Date': FIXED_TIME.isoformat(), 'Creator': 'render_control_points.py'}
            elif ext == 'eps':
                metadata = {'Creator': 'render_control_points.py'}
            f = out / f'{stem}.{ext}'
            if ext == 'pdf':
                # SVG has all Japanese glyphs as paths. This avoids the broken
                # Type42 embedding of this CFF-containing macOS TTC font.
                raw = cairosvg.svg2pdf(url=str(out/f'{stem}.svg'))
                pdf = pymupdf.open(stream=raw, filetype='pdf')
                pdf.set_metadata({'creator': 'render_control_points.py',
                    'producer': 'CairoSVG outlined vectors',
                    'creationDate': 'D:20261029000000Z', 'modDate': 'D:20261029000000Z'})
                f.write_bytes(pdf.tobytes(garbage=4, deflate=True, no_new_id=True))
                pdf.close()
            elif ext == 'eps':
                raw = cairosvg.svg2eps(url=str(out/f'{stem}.svg'))
                raw = re.sub(rb'^%%CreationDate:.*$',
                    b'%%CreationDate: Thu Oct 29 00:00:00 2026', raw, flags=re.MULTILINE)
                f.write_bytes(raw)
            else:
                self.fig.savefig(f, dpi=500, facecolor='white', metadata=metadata)
            outputs[f.name] = sha(f)
        plt.close(self.fig)
        return {'variant': variant, 'width_mm': WIDTH, 'height_mm': HEIGHT,
                'minimum_font_pt': min(t.get_fontsize() for t in self.texts),
                'line_width_pt': LW, 'text_clipping': clipped, 'text_overlaps': overlaps,
                'font_file_sha256': sha(font_path()), 'font_name': self.font.get_name(),
                'vector_text_representation': 'outlined glyph paths; no external font dependency',
                'outputs': outputs, 'additional_model_API_eval_tokenizer_calls': 0}


def render(out, variant='detailed_architecture', stem='control_points'):
    if variant != 'detailed_architecture':
        raise ValueError('v08 requires the detailed architecture variant')
    plt.rcParams.update({'svg.fonttype': 'path', 'axes.unicode_minus': False,
                         'svg.hashsalt': 'harness-v08-architecture-20261029'})
    d = Drawing()
    d.draw()
    return d.save(out, stem, variant)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--variant', choices=('detailed_architecture',), default='detailed_architecture')
    parser.add_argument('--update-manifest', action='store_true')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    record = render(args.output_dir, args.variant)
    record['controls_A_B_independently_evaluated'] = True
    record['diagram_A_scope'] = 'Dedicated summary example; Inline co-generates action and summary.'
    record['recurrent_summary_input'] = 'Previous accepted summary plus newly eligible older unsummarized history; task and recent context remain intact.'
    record['initial_history_without_summary'] = 'Original history remains visible until a summary is accepted.'
    record['evaluator_scope'] = 'After the task run only; no answer flows into the running model.'
    (args.output_dir/'control_points_manifest.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
    if args.update_manifest:
        path = args.output_dir/'figures_manifest.json'
        manifest = json.loads(path.read_text())
        manifest['outputs'].update(record['outputs'])
        manifest.update(architecture_height_mm=HEIGHT,
            source_sha256=sha(Path(__file__).with_name('render_figures.py')),
            architecture_source=Path(__file__).name, architecture_source_sha256=sha(__file__),
            architecture_variant=args.variant, architecture_language='Japanese',
            architecture_minimum_font_pt=record['minimum_font_pt'],
            architecture_line_width_pt=LW,
            architecture_vector_text_representation=record['vector_text_representation'])
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(f'Rendered {args.variant} at {WIDTH} x {HEIGHT} mm; no model/API calls.')


if __name__ == '__main__':
    main()
