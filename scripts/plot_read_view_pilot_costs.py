"""Plot every P107 call's known cumulative tokens and actual API requests.

Reporting only, prepared while the fixed experiment runs without reading its
outcomes. Unknown token use is marked and never filled with zero. Source
experiments and existing reports are not executed or overwritten.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def build(root):
    source=root/'reports/P107_comparison.json'
    data=json.loads(source.read_text())
    if data['audit_errors'] or len(data['rows'])!=2:
        raise ValueError('both_audited_P107_slots_required')
    target=root/'materials/20261025_p107_results'
    targets=[target/'cumulative_costs_v01.png',target/'cumulative_costs_v01.svg',target/'plot_manifest_v01.json']
    if not target.is_dir() or any(p.exists() for p in targets):raise FileExistsError('preserve_prior_plot_artifacts')
    fig,axes=plt.subplots(1,2,figsize=(9,4.2),layout='constrained')
    unknown_count=0
    labels={'eager_cached':'Eager + cache','coalesced_cached':'Coalesced + cache'}
    for row,color in zip(data['rows'],('#2769a4','#c46b19'),strict=True):
        calls=row.get('request_checks',[]);x=[0];tokens=[0];api=[0];missing=[]
        for index,call in enumerate(calls,1):
            x.append(index)
            known=type(call.get('input_tokens'))is int and type(call.get('output_tokens'))is int
            if known and tokens[-1] is not None:
                tokens.append(tokens[-1]+call['input_tokens']+call['output_tokens'])
            else:
                tokens.append(None);missing.append(index);unknown_count+=1
            api.append(api[-1]+call['API_requests'])
        label=labels[row['read_view_policy']]
        status=('success' if row.get('success') is True else
                'failure' if row.get('success') is False else 'not evaluated')
        axes[0].plot(x,tokens,'o-',color=color,markersize=3,label=label+' ('+status+')')
        axes[1].step(x,api,where='post',color=color,label=label)
        for index in missing:
            axes[0].axvline(index,color=color,linestyle=':',alpha=.45)
        if missing:
            axes[0].annotate(label+': usage unknown at '+','.join(map(str,missing)),
                xy=(.02,.98-.08*(color=='#c46b19')),xycoords='axes fraction',va='top',color=color,fontsize=8)
    axes[0].set_title('Logical input + output tokens')
    axes[0].set_ylabel('Cumulative known tokens')
    axes[1].set_title('Environment API requests')
    axes[1].set_ylabel('Cumulative dispatched requests')
    for axis in axes:
        axis.set_xlabel('Model generation attempt')
        axis.set_xlim(left=0);axis.set_ylim(bottom=0)
        axis.grid(alpha=.2);axis.legend(fontsize=8,loc='lower right')
    fig.suptitle('P107: one previously known task, one run per policy',fontsize=11)
    footer='All planned conditions; no independent replications. API reservations are not dispatched requests.'
    if unknown_count:footer+=' Unknown token use is not imputed.'
    fig.supxlabel(footer,fontsize=8)
    fig.savefig(targets[0],dpi=180);fig.savefig(targets[1]);plt.close(fig)
    manifest=dict(created_at=datetime.now(timezone.utc).isoformat(),plotter_sha256=sha(Path(__file__)),
        audit_sha256=sha(source),all_conditions=2,unknown_token_attempts=unknown_count,
        public_artifact_sha256={p.name:sha(p) for p in targets[:2]},
        unknown_usage_imputed=False,model_or_API_reexecution=False,
        reporting_prepared_after_experiment_started=True,outcomes_inspected_during_preparation=False)
    with targets[2].open('x') as stream:json.dump(manifest,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(conditions=2,unknown_token_attempts=unknown_count)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo-root',type=Path,required=True)
    build(p.parse_args().repo_root.resolve())
