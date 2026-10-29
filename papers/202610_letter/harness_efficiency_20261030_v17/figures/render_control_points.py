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

WIDTH, HEIGHT = 130, 110
INK, PALE, GRAY = '#202020', '#f1f1f1', '#777777'
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

    def process(self, x, y, w, h, label, role='harness'):
        fill = '#dedede' if role == 'action' else 'white'
        hatch = '////' if role == 'summary' else None
        style = (0, (3, 2)) if role == 'summary' else '-'
        self.ax.add_patch(Rectangle((x, y), w, h, edgecolor=INK,
            facecolor=fill, hatch=hatch, linewidth=LW, linestyle=style, zorder=2))
        self.text(x+w/2, y+h/2, label, size=7,
                  background=(role == 'summary'))

    def combined(self, x, y, w, h):
        # One gray outer box denotes one action-generating model call.
        # Dedicated-summary hatching is deliberately absent here.
        self.process(x,y,w,h,'1回のモデル呼出し\n行動＋要約候補を\n同じ応答に出力','action')

    def frame(self,x,y,w,h):
        self.ax.add_patch(Rectangle((x,y),w,h,edgecolor=GRAY,
            facecolor='none',linewidth=.55,zorder=1))

    def draw(self):
        self.frame(1,1,128,78)
        self.text(3,4,'実験A：要約機会での呼出し順序',8,ha='left')
        # Fills and borders retain their meaning in monochrome printing.
        for x,label,role in [(3,'行動生成の呼出し','action'),
                              (48,'要約専用の呼出し','summary'),
                              (94,'ハーネス処理','harness')]:
            self.process(x,7.5,4,3,'',role)
            self.text(x+6,9,label,ha='left')
        self.text(3,17.2,'専用1回方式',7.5,ha='left')
        self.text(3,21.1,'機会は最大1回',ha='left')
        self.text(3,31.2,'専用反復方式',7.5,ha='left')
        self.text(3,35.1,'機会は最大3回',ha='left')
        for y,tail in [(14,'以後は\n再要約なし'),(28,'次の機会へ')]:
            self.process(33,y,15,9,'要約生成','summary')
            self.process(51,y,12,9,'採否\n検査')
            self.process(66,y,17,9,'行動生成','action')
            self.process(86,y,20,9,'実行・記録')
            self.process(109,y,17,9,tail)
            for x0,x1 in [(48.4,50.6),(63.4,65.6),(83.4,85.6),(106.4,108.6)]:
                self.arrow([(x0,y+4.5),(x1,y+4.5)])
        self.arrow([(117.5,37.4),(117.5,41),(31,41),(31,32.5),(32.6,32.5)])
        self.text(77,41,'新たな履歴が増え，条件を満たすと繰り返す',background=True)

        self.text(3,47,'行動併記方式',7.5,ha='left')
        self.text(3,51.2,'機会は最大3回',ha='left')
        self.text(3,55.4,'要約専用の追加なし',ha='left')
        self.combined(33,45,25,13)
        self.process(63,46,23,11,'プログラム実行\n結果を記録')
        self.process(89,46,13,11,'採否\n検査')
        self.process(105,46,21,11,'次の行動生成','action')
        for x0,x1 in [(58.4,62.6),(86.4,88.6),(102.4,104.6)]:
            self.arrow([(x0,51.5),(x1,51.5)])
        self.text(3,60.7,'行動併記の候補は今回の実行結果を含めず，その行動と結果は原文で残す',ha='left')

        self.process(3,64,77,13.5,
            '採否検査：形式・文字数・次回入力全体の短縮\n'
            '採用：要約＋未要約履歴\n'
            '不採用：現在の入力表現を維持')
        self.process(83,64,43,13.5,
            '全ての行動・結果を別に保存\n'
            '元の全履歴は削除しない\n'
            '初期入力は元の履歴')

        # B is an independent evaluation, with no path connecting it to A.
        self.frame(1,81,128,28)
        self.text(3,84,'実験B：API実行記録に基づく終了制御',8,ha='left')
        self.process(3,90,24,11,'プログラム実行後の\nAPI実行記録')
        self.arrow([(27.4,95.5),(30.6,95.5)])
        self.process(31,90,48,11,'完了判定：既知要求の手書き規則\n全対象の移動・名前の保持を照合')
        self.arrow([(79.4,95.5),(86,95.5),(86,92),(99.6,92)])
        self.arrow([(79.4,95.5),(86,95.5),(86,104),(99.6,104)])
        self.process(100,86.5,27,11,'根拠あり\n完了APIを1回\n次の生成を省く')
        self.process(100,100,27,8,'不足・矛盾など\n通常どおり継続')

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
                'font_file_sha256': sha(font_path()), 'font_name': self.font.get_name(),
                'vector_text_representation': 'outlined glyph paths; no external font dependency',
                'outputs': outputs, 'additional_model_API_eval_tokenizer_calls': 0}


def render(out, variant='independent_control_flows', stem='control_points'):
    if variant != 'independent_control_flows':
        raise ValueError('v17 requires the independent control-flow variant')
    plt.rcParams.update({'svg.fonttype': 'path', 'axes.unicode_minus': False,
                         'svg.hashsalt': 'harness-v17-control-flows-20261030'})
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
    record['diagram_A_scope'] = '専用方式は要約生成・採否検査・行動生成の順。行動併記方式は同じ応答で行動と候補を生成し，プログラム実行と結果記録の後，次の行動生成前に採否を決める。候補はその新しい実行結果を含まない。'
    record['panel_titles'] = ['実験A：要約機会での呼出し順序', '実験B：API実行記録に基づく終了制御']
    record['method_names'] = ['専用1回方式', '専用反復方式', '行動併記方式']
    record['summary_opportunity_limits'] = [1, 3, 3]
    record['monochrome_encoding'] = 'Action calls: solid gray. Dedicated summary calls: hatched with dashed border. Harness steps: plain white. Inline action and candidate share one gray outer response box with no dedicated-summary hatching.'
    record['B_rule_scope'] = 'Handwritten completion check for the known request type: all target moves and name retention; complete API once when supported, otherwise continue.'
    record['recurrent_summary_input'] = 'Previous accepted summary plus newly eligible older unsummarized history; task and recent context remain intact.'
    record['initial_history_without_summary'] = 'Original history remains visible until a summary is accepted.'
    record['evaluator_scope'] = 'After the task run only; no answer flows into the running model.'
    (args.output_dir/'control_points_manifest.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
    if args.update_manifest:
        path = args.output_dir/'figures_manifest.json'
        manifest = json.loads(path.read_text())
        manifest['outputs'].update(record['outputs'])
        manifest.setdefault('figures', {})['control_points'] = record
        manifest['source_sha256'] = sha(__file__)
        manifest['architecture_source_sha256'] = sha(__file__)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(f'Rendered {args.variant} at {WIDTH} x {HEIGHT} mm; no model/API calls.')


if __name__ == '__main__':
    main()
