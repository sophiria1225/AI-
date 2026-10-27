"""Closed-data local-input / whole-job diagnostic, 65 mm wide; no producers."""
from pathlib import Path
import hashlib
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT=Path(__file__).resolve().parent
DATA_SHA256='66f1aada16282d8fbe66f709686f335feb992d502b936172cebdecb8e85bfdf3'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':7,'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none'})


def draw(data):
    fig=plt.figure(figsize=(65/25.4,69/25.4));ax=fig.add_axes([0,0,1,1]);ax.axis('off')
    ax.set(xlim=(0,65),ylim=(0,69))
    ax.text(1,67,'(a) Local input at checkpoint 2',ha='left',va='top',fontsize=7,fontweight='bold')
    ax.text(1,62,'EDO: two views at the same boundary',ha='left',va='top',fontsize=7)
    x0,scale=18,36/16000
    for y,label,value,fill in [(53,'Current',data['local']['current_view_native_tokens'],'0.70'),
                                (44,'Delta',data['local']['delta_view_native_tokens'],'0.25')]:
        ax.text(1,y+2.5,label,ha='left',va='center',fontsize=7)
        ax.add_patch(Rectangle((x0,y),value*scale,5,facecolor=fill,edgecolor='black',linewidth=.5))
        ax.text(x0+value*scale+1,y+2.5,f'{value:,}',ha='left',va='center',fontsize=7)
    ax.text(1,39,'Native input tokens; delta view installed.',ha='left',va='top',fontsize=7)
    ax.plot([1,64],[34.5,34.5],color='black',lw=.5)
    ax.text(1,32,'(b) Whole job in the same cohort',ha='left',va='top',fontsize=7,fontweight='bold')
    ax.text(1,26,'Method',ha='left',va='center',fontsize=7)
    ax.text(20,26,'Outcome',ha='left',va='center',fontsize=7)
    ax.text(64,26,'Logical I+O',ha='right',va='center',fontsize=7)
    ax.plot([1,64],[23.4,23.4],color='black',lw=.5)
    for y,row in zip((19.5,13.5),data['rows']):
        value=f"{row['known_total_tokens']:,}"+(' + ?' if row['unknown_usage_calls'] else '')
        ax.text(1,y,row['method'],ha='left',va='center',fontsize=7)
        ax.text(20,y,'Success' if row['success'] else 'Failure',ha='left',va='center',fontsize=7)
        ax.text(64,y,value,ha='right',va='center',fontsize=7)
    ax.plot([1,64],[10.5,10.5],color='black',lw=.5)
    ax.text(1,7.5,'+ ?: one call with unknown I/O.',ha='left',va='center',fontsize=7)
    ax.text(1,3.2,'Whole-job cost difference: not determined.',ha='left',va='center',fontsize=7)
    fig.canvas.draw();renderer=fig.canvas.get_renderer();bounds=fig.bbox
    for text in ax.texts:
        q=text.get_window_extent(renderer)
        if q.x0<0 or q.y0<0 or q.x1>bounds.x1 or q.y1>bounds.y1:raise ValueError('text_outside_print_canvas')
    return fig


def main():
    names=['task4_local_vs_job.'+e for e in ('pdf','svg','png','eps')]+['task4_local_vs_job_manifest.json']
    if any((ROOT/n).exists() for n in names):raise FileExistsError('preserve_existing_figure')
    raw=(ROOT/'task4_local_vs_job_data.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA256:raise ValueError('closed_scalar_data_binding_changed')
    data=json.loads(raw)
    if data['actual_data'] is not True or data['P141_reads']!=0 or data['exact_whole_job_difference'] is not None:
        raise ValueError('actual_closed_scope_required')
    fig=draw(data)
    outputs={}
    for e in ('pdf','svg','png','eps'):
        p=ROOT/('task4_local_vs_job.'+e);fig.savefig(p,dpi=600,facecolor='white')
        outputs[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
    plt.close(fig)
    record=dict(scope=data['scope'],width_mm=65,height_mm=69,font_pt=7,stroke_width_pt=.5,
        data_sha256=DATA_SHA256,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),outputs=outputs,
        actual_closed_data=True,known_subtotal_difference_not_computed=True,P141_data_reads=0)
    with (ROOT/'task4_local_vs_job_manifest.json').open('x') as f:json.dump(record,f,indent=2);f.write('\n')
    print(json.dumps(record))
if __name__=='__main__':main()
