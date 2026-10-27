"""Frozen-source method diagram, 130 x 45 mm. No experiment data are read.

Run this standalone drawing script only into a directory without its outputs.
The diagram describes the P141 implementation, not its experimental results.
"""
from pathlib import Path
import hashlib
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch

plt.rcParams.update({'font.family':'DejaVu Sans','font.size':7,
                     'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none'})
OUT=Path(__file__).resolve().parent
OUTPUTS=['architecture.pdf','architecture.svg','architecture.png','architecture.eps','architecture_manifest.json']


def draw():
    fig=plt.figure(figsize=(130/25.4,45/25.4))
    ax=fig.add_axes([0,0,1,1]);ax.set(xlim=(0,130),ylim=(0,45));ax.axis('off')
    def box(x,y,w,h,title,body):
        ax.add_patch(Rectangle((x,y),w,h,facecolor='white',edgecolor='black',linewidth=.5))
        ax.text(x+w/2,y+h-1.5,title,ha='center',va='top',fontsize=7,fontweight='bold')
        ax.text(x+w/2,y+h/2-1.2,body,ha='center',va='center',fontsize=7,linespacing=1.15)
    def arrow(points,dashed=False):
        for a,b in zip(points[:-2],points[1:-1]):
            ax.plot([a[0],b[0]],[a[1],b[1]],color='black',lw=.5,ls=(0,(2,1.5)) if dashed else '-')
        ax.add_patch(FancyArrowPatch(points[-2],points[-1],arrowstyle='-|>',mutation_scale=5.5,
            linewidth=.5,color='black',linestyle=(0,(2,1.5)) if dashed else '-',shrinkA=0,shrinkB=.5))
    box(1,30,26,11,'Full archive','Append-only history\n+ system / task')
    box(33,30,35,11,'Actor input view','System / task + notes\n+ raw suffix (last 2 kept)')
    box(75,30,18,11,'Actor LLM','Tool action\nPaid I/O')
    box(100,30,29,11,'Environment','Persistent Python\n+ typed public APIs')
    arrow([(27,35.5),(33,35.5)]);arrow([(68,35.5),(75,35.5)]);arrow([(93,35.5),(100,35.5)])
    arrow([(114.5,41),(114.5,43.6),(14,43.6),(14,41)])
    # Exposure is a count-only indicator, not a claim of saved tokens.
    box(1,10,36,15,'Paid-prefix exposure',
        'Δ = I − I(without new raw)\nE ← E + max(0, Δ)\nC = last paid focus (I+O)')
    box(43,10,32,15,'Timing controller','First: input ≥ 16k\nRepeat: 16k or E ≥ C\n≥ 3 fresh; ≤ 2 offers')
    box(81,10,48,15,'Paid focus → host acceptance','TR: replace summary\nTDO/EDO: prior + delta object\nSchema / size / shorter full input')
    arrow([(14,30),(14,25)])
    arrow([(84,30),(84,27.6),(30,27.6),(30,25)],dashed=True)
    arrow([(37,17.5),(43,17.5)]);arrow([(75,17.5),(81,17.5)])
    arrow([(105,25),(105,29),(50.5,29),(50.5,30)])
    # The acceptance arrow updates only the view; no deletion edge to archive.
    ax.plot([1,129],[7.4,7.4],lw=.5,color='black')
    ax.text(65,5.8,'All actor/focus I+O counted (cached input included); unknown remains unknown.',
            ha='center',va='center',fontsize=7)
    ax.text(65,2.5,'Closed task state → official evaluator; no evaluation feedback to the actor.',
            ha='center',va='center',fontsize=7)
    return fig


def main():
    if any((OUT/name).exists() for name in OUTPUTS):
        raise FileExistsError('preserve_existing_architecture_artifacts')
    fig=draw();fig.canvas.draw()
    # Check text is not cropped at the nominal, unscaled print dimensions.
    canvas=fig.canvas.get_renderer();bounds=fig.bbox
    for text in fig.axes[0].texts:
        b=text.get_window_extent(canvas)
        if b.x0<bounds.x0 or b.y0<bounds.y0 or b.x1>bounds.x1 or b.y1>bounds.y1:
            raise ValueError('text_outside_print_canvas')
    hashes={}
    for extension in ('pdf','svg','png','eps'):
        path=OUT/('architecture.'+extension)
        fig.savefig(path,dpi=600,facecolor='white')
        hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    plt.close(fig)
    record=dict(scope='source_only_method_architecture',width_mm=130,height_mm=45,
        minimum_font_pt=7,stroke_width_pt=.5,actual_result_reads=0,
        fixed_source_head='5cab33a2e239f3e6d90e63e32c54ba0764b1c594',
        renderer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        outputs=hashes,method_effectiveness_or_novelty_established=False)
    with (OUT/'architecture_manifest.json').open('x') as handle:
        json.dump(record,handle,indent=2);handle.write('\n')
    print(json.dumps(record))
if __name__=='__main__':main()
