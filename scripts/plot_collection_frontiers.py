"""Publication-sized descriptive figure from the fixed public audit."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    r=json.loads(args.input.read_text())
    rows=r['trials']
    if len(rows)!=16 or len({t['task_id'] for t in rows})!=16:
        raise ValueError('expected all sixteen observed development tasks')
    data=[]
    for success in (True,False):
        subset=[t for t in rows if t['official_success'] is success]
        data.append((len(subset),sum(t['any_no_terminal'] for t in subset),
                     sum(t['any_no_terminal_without_later_app_write'] for t in subset)))
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'pdf.fonttype':42,
                         'axes.spines.top':False,'axes.spines.right':False})
    fig,ax=plt.subplots(figsize=(4.7,3.1),layout='constrained')
    for i,(count,all_,current) in enumerate(data):
        positions=[x+(-0.18 if i==0 else 0.18) for x in (0,1)]
        bars=ax.bar(positions,[100*all_/count,100*current/count],width=.32,
            color=('#246A88','#C57A22')[i],label=('Successful tasks','Unsuccessful tasks')[i])
        for b,n in zip(bars,(all_,current)):
            ax.annotate(f'{n}/{count}',(b.get_x()+b.get_width()/2,b.get_height()),
                        xytext=(0,3),textcoords='offset points',ha='center',fontsize=9)
    ax.set_xticks([0,1],['Any query group','Groups without later\nsame-app writes'])
    ax.set_ylim(0,75);ax.set_ylabel('Tasks with no-terminal flag (%)')
    ax.set_title('Open queries also occur in successful runs',fontsize=10,pad=10)
    ax.legend(loc='upper right',frameon=False,fontsize=8)
    ax.set_axisbelow(True);ax.yaxis.grid(True,linewidth=.5,alpha=.25)
    fig.supxlabel('16 observed development tasks; no gate was executed.\nTask relevance and complete enumeration are unverified.',fontsize=7)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    for suffix in ('pdf','png'):
        fig.savefig(args.output_dir/f'observed_flags.{suffix}',dpi=240)
    plt.close(fig)
    manifest=dict(input_sha256=digest(args.input),script_sha256=digest(Path(__file__)),
        counts={'successful':data[0],'unsuccessful':data[1]},
        files={p.name:digest(p) for p in sorted(args.output_dir.glob('observed_flags.*'))},
        note='Count tuples: tasks, flagged-any-group, flagged-without-later-same-app-write. Descriptive only.')
    (args.output_dir/'sources.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest))


if __name__=='__main__':
    main()
