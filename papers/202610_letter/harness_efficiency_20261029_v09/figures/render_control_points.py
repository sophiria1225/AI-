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
from matplotlib.patches import FancyArrowPatch, Polygon, Rectangle
import pymupdf

WIDTH, HEIGHT = 130, 65
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

    def process(self, x, y, w, h, label, fill=PALE):
        self.ax.add_patch(Rectangle((x, y), w, h,
            edgecolor=INK, facecolor=fill, linewidth=LW, zorder=2))
        self.text(x+w/2, y+h/2, label, size=7)

    def diamond(self,cx,cy,dx,dy,label):
        self.ax.add_patch(Polygon([(cx-dx,cy),(cx,cy-dy),(cx+dx,cy),(cx,cy+dy)],
            closed=True,facecolor='white',edgecolor=INK,linewidth=LW,zorder=2))
        self.text(cx,cy,label)

    def draw(self):
        # Two separate studies, no shared execution pathway or pooled effect.
        # Candidate generation denotes a function, not an extra model call:
        # Inline places its candidate in the same response as the action.
        self.text(3,3,'（a）次回入力履歴の更新',8,ha='left')
        self.process(3,10,32,12,'モデルに入力する履歴\n採用前：元の履歴\n採用後：要約＋未要約履歴',fill='white')
        self.arrow([(35.5,16),(38.5,16)])
        self.process(39,10,23,12,'要約候補を\n生成')
        self.arrow([(62.5,16),(67.5,16)])
        self.diamond(81,16,13,8,'形式・長さ\n入力短縮')
        self.arrow([(94.5,16),(101.5,16)])
        self.text(98,12.6,'採用')
        self.process(102,10,25,12,'要約＋未要約履歴\nを次回入力へ')
        self.arrow([(81,24.5),(81,28.5),(101.5,28.5)])
        self.text(95,25.8,'不採用')
        self.process(102,25,25,7,'入力履歴を維持',fill='white')
        self.text(3,27.4,'保存した全履歴はホストが保持',ha='left')
        self.line([(3,34),(127,34)],color=GRAY,lw=.5)

        self.text(3,38,'（b）次の生成／終了判断',8,ha='left')
        self.process(3,44,30,11,'応答内の全操作\n実行後のAPI実行記録',fill='white')
        self.arrow([(33.5,49.5),(38.5,49.5)])
        self.process(39,44,23,11,'課題の完了条件\nを検査')
        self.arrow([(62.5,49.5),(67.5,49.5)])
        self.diamond(81,49.5,13,8,'完了の根拠\nが揃うか')
        self.arrow([(94.5,49.5),(101.5,49.5)])
        self.text(98,45.8,'あり')
        self.process(102,44,25,11,'完了APIを呼ぶ\n次の生成を省く')
        self.arrow([(81,58),(81,60),(101.5,60)])
        self.text(95,57.3,'不足・不明')
        self.process(102,57,25,6,'次の行動生成へ',fill='white')

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


def render(out, variant='independent_control_flows', stem='control_points'):
    if variant != 'independent_control_flows':
        raise ValueError('v09 requires the independent control-flow variant')
    plt.rcParams.update({'svg.fonttype': 'path', 'axes.unicode_minus': False,
                         'svg.hashsalt': 'harness-v09-control-flows-20261029'})
    d = Drawing()
    d.draw()
    return d.save(out, stem, variant)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--variant', choices=('independent_control_flows',), default='independent_control_flows')
    parser.add_argument('--update-manifest', action='store_true')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    record = render(args.output_dir, args.variant)
    record['controls_A_B_independently_evaluated'] = True
    record['diagram_A_scope'] = 'Candidate generation is shared functional notation, not an extra model call. Inline co-generates action and summary. Trigger settings and generation modes are defined in the manuscript.'
    record['recurrent_summary_input'] = 'Previous accepted summary plus newly eligible older unsummarized history; task and recent context remain intact.'
    record['initial_history_without_summary'] = 'Original history remains visible until a summary is accepted.'
    record['evaluator_scope'] = 'After the task run only; no answer flows into the running model.'
    (args.output_dir/'control_points_manifest.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
    if args.update_manifest:
        path = args.output_dir/'figures_manifest.json'
        manifest = json.loads(path.read_text())
        manifest['outputs'].update(record['outputs'])
        manifest.setdefault('figures', {})['control_points'] = record
        manifest['source_sha256'] = sha(Path(__file__).with_name('render_figures.py'))
        manifest['architecture_source_sha256'] = sha(__file__)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(f'Rendered {args.variant} at {WIDTH} x {HEIGHT} mm; no model/API calls.')


if __name__ == '__main__':
    main()
