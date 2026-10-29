"""Three publication figures from immutable public aggregates; no experiment calls.

Figure 1 is 130 x 65 mm. Figures 2 and 3 are separate 65 x 58 mm panels.
All fonts are at least 7 pt at these physical sizes. Japanese glyphs are paths
in SVG/PDF/EPS, avoiding host-dependent TTC embedding. Exact integer results
remain in the tables; the plots consistently use thousands of tokens.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re

import cairosvg
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch
from matplotlib.text import Text
import pymupdf
from render_control_points import FIXED_TIME, font_path, render, sha

RESULT_WIDTH, RESULT_HEIGHT = 65, 58


def save_vector(fig, out, stem):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    texts = [t for t in fig.findobj(Text) if t.get_visible() and t.get_text()]
    # The unused tick2 labels are invisible and excluded. Every visible label
    # is checked against the full canvas, not just the plotting rectangle.
    clipped = [t.get_text() for t in texts
               if not fig.bbox.contains(*t.get_window_extent(renderer).p0)
               or not fig.bbox.contains(*t.get_window_extent(renderer).p1)]
    if clipped:
        raise ValueError({'stem': stem, 'clipped_text': clipped})
    outputs = {}
    for ext in ('png', 'svg', 'pdf', 'eps'):
        path = out / f'{stem}.{ext}'
        if ext == 'pdf':
            raw = cairosvg.svg2pdf(url=str(out / f'{stem}.svg'))
            pdf = pymupdf.open(stream=raw, filetype='pdf')
            pdf.set_metadata({'creator': 'render_figures.py',
                'producer': 'CairoSVG outlined vectors',
                'creationDate': 'D:20261029000000Z', 'modDate': 'D:20261029000000Z'})
            path.write_bytes(pdf.tobytes(garbage=4, deflate=True, no_new_id=True))
            pdf.close()
        elif ext == 'eps':
            raw = cairosvg.svg2eps(url=str(out / f'{stem}.svg'))
            path.write_bytes(re.sub(rb'^%%CreationDate:.*$',
                b'%%CreationDate: Thu Oct 29 00:00:00 2026',raw,flags=re.MULTILINE))
        else:
            metadata = {'Date': FIXED_TIME.isoformat(), 'Creator': 'render_figures.py'} if ext == 'svg' else None
            fig.savefig(path, dpi=500, facecolor='white', metadata=metadata)
        outputs[path.name] = sha(path)
    record = {'width_mm': RESULT_WIDTH, 'height_mm': RESULT_HEIGHT,
        'minimum_font_pt': min(t.get_fontsize() for t in texts),
        'clipped_text': clipped, 'outputs': outputs,
        'y_axis_label': '総トークン数（千トークン）', 'y_axis_origin': 0,
        'bar_value_labels': 'omitted; exact integers are in manuscript tables',
        'vector_text_representation': 'outlined glyph paths; no external font dependency'}
    plt.close(fig)
    return record


def plot_base():
    fig = plt.figure(figsize=(RESULT_WIDTH/25.4, RESULT_HEIGHT/25.4))
    ax = fig.add_axes([.225, .175, .745, .64])
    ax.set_ylabel('総トークン数（千トークン）', fontsize=7, labelpad=3)
    ax.tick_params(labelsize=7, width=.5, length=2, pad=2)
    ax.spines[['top', 'right']].set_visible(False)
    for spine in ax.spines.values():
        spine.set_linewidth(.5)
    ax.set_axisbelow(True)
    ax.grid(axis='y', linewidth=.35, color='.85')
    return fig, ax


def result_summary(data, out):
    study = data['study_A']
    modes = ['single_checkpoint', 'rolling_separate', 'rolling_inline']
    csv, other = [], []
    for mode in modes:
        rows = [r for r in study['rows'] if r['checkpoint_policy'] == mode]
        csv.append(next(r['known_total_tokens'] for r in rows if r['task_id'] == '6104387_1'))
        other.append(sum(r['known_total_tokens'] for r in rows if r['task_id'] != '6104387_1'))
    assert [c+o for c,o in zip(csv,other)] == [893529,785656,836922]
    assert csv == [440461,332588,394351]
    assert other == [453068,453068,442571]
    fig, ax = plot_base()
    ax.bar(range(3), [v/1000 for v in other], width=.59, color='.78', edgecolor='black', linewidth=.5)
    ax.bar(range(3), [v/1000 for v in csv], bottom=[v/1000 for v in other],
           width=.59, color='white', edgecolor='black', linewidth=.5, hatch='///')
    ax.set_xticks(range(3), ['Single', 'Separate', 'Inline'])
    ax.set_xlim(-.62,2.62)
    ax.set_ylim(0,1000)
    ax.set_yticks([0,200,400,600,800,1000])
    fig.legend(handles=[Patch(facecolor='white',edgecolor='black',hatch='///',label='CSV処理'),
                        Patch(facecolor='.78',edgecolor='black',label='その他3課題')],
        loc='upper center', bbox_to_anchor=(.56,.985), ncol=2, frameon=False,
        fontsize=7, handlelength=1.1, handletextpad=.4, columnspacing=.9, borderaxespad=0)
    record = save_vector(fig,out,'result_summary')
    record.update(study='P123', csv_tokens=csv, other_three_tasks_tokens=other,
                  total_tokens=[c+o for c,o in zip(csv,other)])
    return record


def result_termination(data, out):
    study = data['study_B']
    rows = {(r['interface'],r['condition']):r for r in study['rows']}
    ordinary = [rows[(k,'ordinary')]['known_total_tokens'] for k in ('documented','named')]
    controlled = [rows[(k,'evidence_stop')]['known_total_tokens'] for k in ('documented','named')]
    assert ordinary == [130439,151664] and controlled == [91116,112233]
    fig, ax = plot_base()
    ax.bar([-.19,.81],[v/1000 for v in ordinary],width=.32,color='.78',edgecolor='black',linewidth=.5)
    ax.bar([.19,1.19],[v/1000 for v in controlled],width=.32,color='white',edgecolor='black',linewidth=.5,hatch='///')
    ax.set_xticks([0,1],['文書必須','名前参照'])
    ax.set_xlim(-.55,1.55)
    ax.set_ylim(0,180)
    ax.set_yticks([0,50,100,150])
    for x, base, value in zip([0,1],ordinary,controlled):
        ax.text(x,168,f'{(base-value)/base*100:.2f}%減',ha='center',va='center',fontsize=7)
    fig.legend(handles=[Patch(facecolor='.78',edgecolor='black',label='通常継続'),
                        Patch(facecolor='white',edgecolor='black',hatch='///',label='完了判定')],
        loc='upper center',bbox_to_anchor=(.56,.985),ncol=2,frameon=False,
        fontsize=7,handlelength=1.1,handletextpad=.4,columnspacing=.9,borderaxespad=0)
    record = save_vector(fig,out,'result_termination')
    record.update(study='P64/P66', ordinary_tokens=ordinary, controlled_tokens=controlled,
                  reduction_percent=[(o-c)/o*100 for o,c in zip(ordinary,controlled)])
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    data=json.loads(args.data.read_text())
    assert data['study_A']['success_each']==4 and len(data['study_A']['rows'])==12
    assert len(data['study_B']['rows'])==4 and data['studies_pooled'] is False
    args.output_dir.mkdir(parents=True,exist_ok=False)
    font_manager.fontManager.addfont(str(font_path()))
    name=font_manager.FontProperties(fname=str(font_path())).get_name()
    plt.rcParams.update({'font.family':name,'font.size':7,'axes.unicode_minus':False,
                         'svg.fonttype':'path','svg.hashsalt':'harness-v09-results-20261029'})
    with matplotlib.rc_context():
        architecture=render(args.output_dir)
    architecture.update(controls_A_B_independently_evaluated=True,
        diagram_A_scope='Candidate generation does not denote an extra model call; Inline uses the action response.',
        initial_history_without_summary='Original unsummarized history until acceptance; summary and the remaining unsummarized history after acceptance; at least the most recent two closed turns stay verbatim at summary creation.',
        archive_scope='The host retains the complete history separately from the model-visible history.',
        evaluator_scope='Removed from diagram; manuscript caption states evaluation occurs only after the run.')
    (args.output_dir/'control_points_manifest.json').write_text(json.dumps(architecture,ensure_ascii=False,indent=2)+'\n')
    summary=result_summary(data,args.output_dir)
    termination=result_termination(data,args.output_dir)
    outputs={**architecture['outputs'],**summary['outputs'],**termination['outputs']}
    manifest={'scope':'Independent P123 and P64/P66 studies; no pooled effect',
        'source_sha256':sha(Path(__file__)),'architecture_source_sha256':sha(Path(__file__).with_name('render_control_points.py')),
        'data_sha256':sha(args.data),'outputs':outputs,'minimum_font_pt':7,
        'font_file_sha256':sha(font_path()),'figures':{'control_points':architecture,
            'result_summary':summary,'result_termination':termination},
        'additional_model_API_eval_tokenizer_calls':0}
    (args.output_dir/'figures_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('Rendered Figure 1 (130 x 65 mm), Figures 2 and 3 (65 x 58 mm), minimum 7 pt.')

if __name__=='__main__':
    main()
