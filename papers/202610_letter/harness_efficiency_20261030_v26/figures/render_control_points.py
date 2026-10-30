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
from matplotlib.patches import FancyArrowPatch, Rectangle
import pymupdf

WIDTH, HEIGHT = 130, 97
INK = '#000000'
ROLE_COLORS = {'action': '#DCEAF7', 'summary': '#FBE3CC', 'harness': '#FFFFFF'}
MAX3_LABEL = '要約機会：条件成立時，最大3回'
LW = .65
FIXED_TIME = datetime(2026, 10, 30, tzinfo=timezone.utc)


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
        self.processes = []
        self.arrow_paths = []

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
        self.arrow_paths.append(points)
        if len(points) > 2:
            self.line(points[:-1], dashed=dashed)
        self.ax.add_patch(FancyArrowPatch(points[-2], points[-1],
            arrowstyle='-|>', mutation_scale=6.6, linewidth=LW, color=INK,
            linestyle=(0, (3, 2)) if dashed else '-', shrinkA=0, shrinkB=0,
            zorder=3))

    def process(self, x, y, w, h, label, role='harness'):
        self.ax.add_patch(Rectangle((x, y), w, h, edgecolor=INK,
            facecolor=ROLE_COLORS[role], linewidth=LW, linestyle='-', zorder=2))
        self.text(x+w/2, y+h/2, label, size=7)
        self.processes.append({'label': label, 'role': role, 'fill': ROLE_COLORS[role],
                               'bounds_mm': [x, y, w, h]})

    def combined(self, x, y, w, h):
        # One pale-blue outer box denotes one action-generating model call.
        self.process(x,y,w,h,'行動・要約候補生成','action')

    def frame(self,x,y,w,h):
        self.ax.add_patch(Rectangle((x,y),w,h,edgecolor=INK,
            facecolor='none',linewidth=.55,zorder=1))

    def draw(self):
        # Compare the same interval in all three rows. Dedicated summaries
        # resolve before THIS action. Inline candidates resolve after THIS
        # action's execution, before the NEXT action; no future result enters
        # the candidate generated in the current model response.
        self.frame(1,1,128,67)
        self.text(3,4,'実験A：要約機会での呼出し順序',8,ha='left')
        for x,label,role in [(3,'行動生成の呼出し','action'),
                              (48,'要約専用の呼出し','summary'),
                              (94,'ハーネス処理','harness')]:
            self.process(x,7.5,4,3,'',role)
            self.text(x+6,9,label,ha='left')
        self.text(21,14.5,'行動生成前')
        self.text(67,14.5,'今回のターン')
        self.text(110.5,14.5,'次のターンへ')
        self.line([(93.5,17),(93.5,62.5)],lw=.55,dashed=True)

        for label,maximum,top in [
            ('専用1回方式',1,23),
            ('専用反復方式',3,39),
            ('行動併記方式',3,55)]:
            self.text(3,top-3.5,label,7.5,ha='left')
            self.text(28,top-3.5,MAX3_LABEL if maximum == 3 else '要約機会：最大1回',ha='left')
            if label != '行動併記方式':
                self.process(3,top,18,7,'要約生成','summary')
                self.process(25,top,14,7,'採否判定')
                self.process(43,top,26,7,'行動生成','action')
                for x0,x1 in [(21.4,24.6),(39.4,42.6)]:
                    self.arrow([(x0,top+3.5),(x1,top+3.5)])
            else:
                # An empty interval before the actor means no dedicated call.
                self.arrow([(3,top+3.5),(42.6,top+3.5)])
                self.combined(43,top,26,7)
            self.process(73,top,18,7,'実行・記録')
            self.process(114,top,13,7,'行動生成','action')
            self.arrow([(69.4,top+3.5),(72.6,top+3.5)])
            if label == '行動併記方式':
                self.process(97,top,13,7,'採否判定')
                self.arrow([(91.4,top+3.5),(96.6,top+3.5)])
                self.arrow([(110.4,top+3.5),(113.6,top+3.5)])
            else:
                self.arrow([(91.4,top+3.5),(113.6,top+3.5)])
        # Independently evaluated API-record stopping control.
        self.frame(1,71,128,25)
        self.text(3,74,'実験B：API実行記録に基づく終了制御',8,ha='left')
        self.process(3,82,29,8,'API実行記録')
        self.arrow([(32.4,86),(35.6,86)])
        self.process(36,82,32,8,'完了条件の照合')
        self.arrow([(68.4,86),(75,86),(75,80),(93.6,80)])
        self.arrow([(68.4,86),(75,86),(75,91),(93.6,91)])
        self.text(83.5,77.3,'充足')
        self.text(83.5,88.3,'不足・矛盾')
        self.process(94,76,33,8,'完了API呼出し・終了')
        self.process(94,87,33,8,'次の生成','action')

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
        if any(p.get_hatch() for p in self.ax.patches):
            raise ValueError('Hatching must not appear in this figure')
        if any(b[0] < a[0] for points in self.arrow_paths for a,b in zip(points,points[1:])):
            raise ValueError('A return arrow must not appear in this figure')
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
                    'creationDate': 'D:20261030000000Z', 'modDate': 'D:20261030000000Z'})
                f.write_bytes(pdf.tobytes(garbage=4, deflate=True, no_new_id=True))
                pdf.close()
            elif ext == 'eps':
                raw = cairosvg.svg2eps(url=str(out/f'{stem}.svg'))
                raw = re.sub(rb'^%%CreationDate:.*$',
                    b'%%CreationDate: Fri Oct 30 00:00:00 2026', raw, flags=re.MULTILINE)
                f.write_bytes(raw)
            else:
                self.fig.savefig(f, dpi=500, facecolor='white', metadata=metadata)
            outputs[f.name] = sha(f)
        plt.close(self.fig)
        return {'variant': variant, 'width_mm': WIDTH, 'height_mm': HEIGHT,
                'minimum_font_pt': min(t.get_fontsize() for t in self.texts),
                'line_width_pt': LW, 'text_clipping': clipped, 'text_overlaps': overlaps,
                'process_boxes': self.processes,
                'font_file_sha256': sha(font_path()), 'font_name': self.font.get_name(),
                'vector_text_representation': 'outlined glyph paths; no external font dependency',
                'outputs': outputs, 'additional_model_API_eval_tokenizer_calls': 0}


def render(out, variant='independent_control_flows', stem='control_points'):
    if variant != 'independent_control_flows':
        raise ValueError('v20 requires the independent control-flow variant')
    plt.rcParams.update({'svg.fonttype': 'path', 'axes.unicode_minus': False,
                         'svg.hashsalt': 'harness-v20-control-flows-20261030'})
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
    record['diagram_A_scope'] = '専用方式は要約生成・採否判定・行動生成の順。行動併記方式は同じ応答で行動と候補を生成し，プログラム実行と結果記録の後，次の行動生成前に採否を決める。候補はその新しい実行結果を含まない。'
    record['panel_titles'] = ['実験A：要約機会での呼出し順序', '実験B：API実行記録に基づく終了制御']
    record['method_names'] = ['専用1回方式', '専用反復方式', '行動併記方式']
    record['summary_opportunity_limits'] = [1, 3, 3]
    record['aligned_columns_mm'] = {'current_action': [43, 69], 'execution_and_record': [73, 91], 'next_action': [114, 127]}
    record['current_turn_boundary_x_mm'] = 93.5
    record['repetition_notation'] = 'Both maximum-three methods use the same text label; no circular repeat icons, return arrows or separate repeat note appear.'
    record['max3_label'] = MAX3_LABEL
    record['role_colors'] = ROLE_COLORS
    record['text_and_line_color'] = INK
    record['hatching'] = False
    record['circular_repeat_icons'] = False
    record['return_arrows'] = False
    record['details_delegated_to_body'] = ['candidate format/length/whole-next-input shortening check', 'accepted summary plus unsummarized history', 'rejection keeps current input representation', 'full original history archive', 'inline candidate does not contain the current response execution result']
    record['monochrome_encoding'] = 'Pale blue and pale orange fills may appear similar in grayscale. Process labels, the role legend and chronological placement carry the meaning independently of fill differences; all text, borders and arrows are black. The whole inline action-and-candidate box is one action-generating call.'
    record['B_rule_scope'] = 'Handwritten completion check for the known request type: all target moves and name retention; complete API once when supported, otherwise continue.'
    record['recurrent_summary_input'] = 'Previous accepted summary plus newly eligible older unsummarized history; task and recent context remain intact.'
    record['initial_history_without_summary'] = 'Original history remains visible until a summary is accepted.'
    record['evaluator_scope'] = 'After the task run only; no answer flows into the running model.'
    (args.output_dir/'control_points_manifest.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
    if args.update_manifest:
        path = args.output_dir/'figures_manifest.json'
        manifest = json.loads(path.read_text())
        manifest['version'] = 'v20'
        manifest['scope'] = 'Role-colored summary-call timing and independent stopping control; no repeat icons or return arrows. Experimental data and tables unchanged.'
        manifest['outputs'].update(record['outputs'])
        manifest.setdefault('figures', {})['control_points'] = record
        manifest['source_sha256'] = sha(__file__)
        manifest['architecture_source_sha256'] = sha(__file__)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(f'Rendered {args.variant} at {WIDTH} x {HEIGHT} mm; no model/API calls.')


if __name__ == '__main__':
    main()
