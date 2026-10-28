"""Vector figures from fixed closed public aggregates; no model or API calls."""
import argparse,hashlib,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,FancyArrowPatch,Patch

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(fig,out,stem):
    d={}
    for ext in ['pdf','svg','png','eps']:
        f=out/(stem+'.'+ext);fig.savefig(f,dpi=500,facecolor='white');d[f.name]=sha(f)
    plt.close(fig);return d

def architecture(out):
    from render_control_points import render
    # Local font/vector settings do not alter the separate-study results figure.
    with matplotlib.rc_context():
        return render(out,'detailed_architecture')['outputs']

def results(d,out):
    a=d['study_A'];b=d['study_B'];fig,axes=plt.subplots(1,2,figsize=(130/25.4,72/25.4),gridspec_kw={'width_ratios':[1,1]})
    fig.subplots_adjust(left=.10,right=.99,top=.83,bottom=.23,wspace=.34)
    ax=axes[0];modes=['single_checkpoint','rolling_separate','rolling_inline'];other=[];csv=[]
    for m in modes:
        rr=[r for r in a['rows'] if r['checkpoint_policy']==m];csv.append(next(r['known_total_tokens']/1000 for r in rr if r['task_id']=='6104387_1'));other.append(sum(r['known_total_tokens']/1000 for r in rr if r['task_id']!='6104387_1'))
    ax.bar(range(3),other,width=.6,color='.78',edgecolor='black',linewidth=.5)
    ax.bar(range(3),csv,bottom=other,width=.6,color='white',edgecolor='black',linewidth=.5,hatch='///')
    for i,m in enumerate(modes):ax.text(i,a['totals'][m]/1000+20,f"{a['totals'][m]:,}\n4/4",ha='center',va='bottom',fontsize=7)
    ax.set_xticks(range(3),['Single','Separate','Inline']);ax.set_ylim(0,1100);ax.set_title('(a) Four known tasks',fontsize=8,pad=8);ax.set_ylabel('Logical input + output (k tokens)',fontsize=7)
    ax.legend(handles=[Patch(facecolor='.78',edgecolor='black',label='Other 3 tasks'),Patch(facecolor='white',edgecolor='black',hatch='///',label='CSV')],frameon=False,fontsize=7,loc='upper center',bbox_to_anchor=(.5,1.22),ncol=2,columnspacing=.8,handlelength=1.4)
    ax=axes[1];xs=[0,.8,2.2,3];labels=['Ord.','Stop','Ord.','Stop'];vals=[r['known_total_tokens']/1000 for r in b['rows']]
    ax.bar(xs,vals,width=.56,color=['.78','white','.78','white'],edgecolor='black',linewidth=.5)
    for x,v,r in zip(xs,vals,b['rows']):ax.text(x,v+4,f"{r['known_total_tokens']:,}\nS",ha='center',va='bottom',fontsize=7)
    ax.set_xticks(xs,labels);ax.set_ylim(0,195);ax.set_title('(b) One photo task',fontsize=8,pad=8)
    ax.text(.4,-.16,'Documented',transform=ax.get_xaxis_transform(),ha='center',va='top',fontsize=7)
    ax.text(2.6,-.16,'Named',transform=ax.get_xaxis_transform(),ha='center',va='top',fontsize=7)
    for ax in axes:
        ax.tick_params(labelsize=7,width=.5);ax.spines[['top','right']].set_visible(False)
        for s in ax.spines.values():s.set_linewidth(.5)
    fig.text(.5,.055,'S: official success. Different y-axis scales; studies are not pooled.',ha='center',fontsize=7)
    fig.text(.5,.015,'Cached input included. No unknown usage in these two studies.',ha='center',fontsize=7)
    return save(fig,out,'separate_studies')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data',type=Path,required=True);ap.add_argument('--output-dir',type=Path,required=True);args=ap.parse_args()
    d=json.loads(args.data.read_text());assert d['study_A']['success_each']==4 and len(d['study_A']['rows'])==12 and len(d['study_B']['rows'])==4 and d['studies_pooled'] is False
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':7,'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none'})
    args.output_dir.mkdir(parents=True,exist_ok=False);outputs={**architecture(args.output_dir),**results(d,args.output_dir)}
    manifest={'scope':'separate closed P123 and P64/P66 studies','source_sha256':sha(Path(__file__)),'data_sha256':sha(args.data),'outputs':outputs,'width_mm':130,'architecture_height_mm':85,'results_height_mm':72,'minimum_font_pt':7,'line_width_pt':.5,'architecture_source':'render_control_points.py','architecture_source_sha256':sha(Path(__file__).with_name('render_control_points.py')),'architecture_variant':'detailed_architecture','architecture_language':'Japanese','architecture_minimum_font_pt':7,'architecture_line_width_pt':.65,'architecture_vector_text_representation':'outlined glyph paths; no external font dependency','additional_model_API_eval_tokenizer_calls':0}
    (args.output_dir/'figures_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Rendered method and separate-study cost figures.')
if __name__=='__main__':main()
