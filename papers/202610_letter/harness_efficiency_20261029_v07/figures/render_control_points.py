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
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon
from PIL import Image, ImageDraw
import pymupdf

WIDTH, HEIGHT = 130, 58
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

    def headers(self):
        self.text(3, 3, '（a）入力履歴を短くする（実験A）', size=8, ha='left')
        self.line([(3, 26.7), (127, 26.7)], color=GRAY, lw=.5)
        self.text(3, 30, '（b）完了後の生成を省く（実験B）', size=8, ha='left')
        self.text(65, 56.2, '各制御を独立に評価', size=7)

    def lower(self, variant):
        # All programs in one model response run before this host-side decision.
        x, y, w, h = 3, 36.2, 23, 10.4
        self.ax.add_patch(Polygon([(x+2.2, y), (x+w, y), (x+w-2.2, y+h), (x, y+h)],
            closed=True, edgecolor=INK, facecolor=PALE, linewidth=LW, zorder=2))
        self.text(x+w/2, y+h/2, '操作を実行', size=7.2)
        self.arrow([(26.4, 41.4), (32, 41.4)])
        self.document(33, 36.2, 22, 10.4, '実行記録')
        self.arrow([(55.5, 41.4), (61, 41.4)])
        cx, cy, dx, dy = 73, 41.4, 11.5, 6.8
        self.ax.add_patch(Polygon([(cx-dx, cy), (cx, cy-dy), (cx+dx, cy), (cx, cy+dy)],
            closed=True, edgecolor=INK, facecolor='white', linewidth=LW, zorder=2))
        self.text(cx, cy, '完了を\n確認', size=7.2)
        self.arrow([(84.5, 41.4), (93, 41.4), (93, 38.2), (103, 38.2)])
        self.text(94.5, 34.6, '根拠あり')
        self.process(104, 35, 23, 6.4, '終了通知', terminal=True)
        self.text(115.5, 44, '次の生成を省く')
        self.arrow([(73, 48.2), (73, 51.4), (103, 51.4)])
        self.text(89, 48.8, '不足・不明', background=True)
        self.process(104, 48.2, 23, 6.4, '次の行動を生成', fill='white')
        self.text(14.5, 50.5, '生成した全操作')

    def upper(self, variant):
        self.document(5, 10, 22, 10.5, '古い履歴', stacked=True)
        if variant == 'split_documents':
            self.arrow([(28, 15), (46, 15)])
            self.text(37, 10.6, '短くまとめる')
            self.document(47, 10, 16, 10.5, '要約', short=True)
            self.text(69, 15, '＋', size=9)
            self.document(75, 10, 21, 10.5, '直近履歴')
            self.arrow([(97, 15), (105.5, 15)])
            self.process(106.5, 9.7, 21, 11, 'LLM\n行動を生成')
            self.text(15.5, 24, '元の履歴は保存')
            self.text(80, 24, '反復方式では必要時に要約を更新')
        elif variant == 'compressed_view':
            # The narrowing wedge denotes a history transformation, not an LLM
            # call boundary: Separate and Inline produce candidates differently.
            self.ax.add_patch(Polygon([(32, 10), (43, 13), (43, 17), (32, 20)],
                closed=False, fill=False, edgecolor=INK, linewidth=LW, zorder=2))
            self.arrow([(43, 15), (49, 15)])
            self.text(37, 7.5, '要約')
            self.document(50, 10, 41, 10.5, '要約 ＋ 直近履歴', short=True)
            self.arrow([(92, 15), (104.5, 15)])
            self.process(105.5, 9.7, 22, 11, 'LLM\n行動を生成')
            self.text(15.5, 24, '元の履歴は保存')
            self.text(81, 24, '反復方式では必要時に要約を更新')
        else:
            raise ValueError(variant)

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


def render(out, variant, stem='control_points'):
    plt.rcParams.update({'pdf.fonttype': 42, 'ps.fonttype': 42,
                         'svg.fonttype': 'path', 'axes.unicode_minus': False,
                         'svg.hashsalt': 'harness-v07-control-points-20261029'})
    d = Drawing()
    d.headers()
    d.upper(variant)
    d.lower(variant)
    return d.save(out, stem, variant)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--variant', choices=('split_documents', 'compressed_view', 'both'),
                   default='split_documents')
    p.add_argument('--update-manifest', action='store_true')
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.variant == 'both':
        if args.update_manifest:
            p.error('--update-manifest requires one selected variant')
        records = []
        for i, v in enumerate(('split_documents', 'compressed_view'), 1):
            records.append(render(args.output_dir, v, f'candidate_{i:02d}_{v}'))
        sheets = [Image.open(args.output_dir/f'candidate_{i:02d}_{v}.png').convert('RGB')
                  for i, v in enumerate(('split_documents', 'compressed_view'), 1)]
        gap = 55
        contact = Image.new('RGB', (sheets[0].width, sum(s.height for s in sheets)+3*gap), 'white')
        draw = ImageDraw.Draw(contact)
        y = gap
        for i, im in enumerate(sheets, 1):
            draw.text((15, y-30), f'Candidate {i}: 130 x 58 mm', fill='black')
            contact.paste(im, (0, y))
            y += im.height+gap
        contact.save(args.output_dir/'contact_sheet.png')
        (args.output_dir/'candidates_manifest.json').write_text(json.dumps(records, ensure_ascii=False, indent=2)+'\n')
    else:
        record = render(args.output_dir, args.variant)
        (args.output_dir/'control_points_manifest.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
        if args.update_manifest:
            path = args.output_dir/'figures_manifest.json'
            manifest = json.loads(path.read_text())
            manifest['outputs'].update(record['outputs'])
            manifest['architecture_height_mm'] = HEIGHT
            manifest['architecture_source'] = Path(__file__).name
            manifest['architecture_source_sha256'] = sha(__file__)
            manifest['architecture_variant'] = args.variant
            manifest['architecture_language'] = 'Japanese'
            manifest['architecture_minimum_font_pt'] = record['minimum_font_pt']
            manifest['architecture_line_width_pt'] = LW
            manifest['architecture_vector_text_representation'] = record['vector_text_representation']
            manifest['source_sha256'] = sha(Path(__file__).with_name('render_figures.py'))
            path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(f'Rendered {args.variant} at {WIDTH} x {HEIGHT} mm; no model/API calls.')


if __name__ == '__main__':
    main()
