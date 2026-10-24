"""Show all four new and twelve historical conditions with explicit unknowns."""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from plot_receipt_history_results import read, sha, write_new, require, success_label, save, TASKS

POLICIES = ('full', 'recent', 'execution_gated', 'public_only')
LABELS = ('Full\nP111 reference', 'Recent\nP111 reference',
          'Execution gated\nP111 reference', 'Public only\nP114 new')


def sources(root):
    paths = {key: root/rel for key,rel in (
        ('new_audit','reports/P114_comparison.json'),('new_session','reports/P114_server_session.json'),
        ('new_plan','configs/P114_whole_task_public_only_history_v01.json'),
        ('historical_audit','reports/P111_comparison.json'),('historical_session','reports/P111_server_session.json'))}
    data = {key: read(path) for key,path in paths.items()}
    plan = data['new_plan']
    require(plan['source_sha256']['reports/P111_comparison.json'] == sha(paths['historical_audit'])
            and plan['source_sha256']['reports/P111_server_session.json'] == sha(paths['historical_session']),
            'frozen_historical_reference_changed')
    for prefix,phase,policies in (('new','P114',('public_only',)),('historical','P111',POLICIES[:3])):
        audit,session = data[prefix+'_audit'],data[prefix+'_session']
        require(audit['phase'] == phase and not audit['audit_errors'] and audit['owned_processes_absent']
                and audit['batch_status'] in ('complete','stopped') and session['status'] == 'stopped'
                and session['owned_processes_absent']
                and session['audit_source_sha256'] == sha(paths[prefix+'_audit']),
                'closed_owned_audited_cohorts_required')
        expected = {(task,policy) for task in TASKS for policy in policies}
        keys = [(r['task_id'],r['reasoning_display_policy']) for r in audit['rows']]
        require(len(keys) == len(set(keys)) == len(expected) and set(keys) == expected,
                'all_new_and_historical_slots_required')
    require(data['new_audit']['plan_sha256'] == sha(paths['new_plan'])
            and data['new_audit']['contemporaneous_comparison'] is False,
            'bound_historical_design_required')
    return data, {str(path.relative_to(root)):sha(path) for path in paths.values()}


def costs_figure(rows, folder, plt, Patch, *, synthetic=False):
    lookup = {(r['task_id'],r['reasoning_display_policy']):r for r in rows}
    require(len(rows) == len(lookup) == 16 and set(lookup) == {(t,p) for t in TASKS for p in POLICIES},
            'all_sixteen_rows_required')
    fig,axes = plt.subplots(2,2,figsize=(14,9.5))
    maximum = max((r.get('known_total_tokens') or 0)/1000 for r in rows)
    limit = max(1,maximum)*1.32
    for ax,(task,title) in zip(axes.flat,TASKS.items(),strict=True):
        ax.axvspan(2.6,3.4,color='#edf4f2',zorder=0)
        for position,policy in enumerate(POLICIES):
            row = lookup[task,policy]
            if row['record_status'] not in ('evaluated','unevaluated'):
                ax.text(position,limit*.08,row['record_status'].replace('_','\n'),
                        ha='center',va='bottom',fontsize=9,color='#596575')
                continue
            require(row['known_total_tokens'] == row['input_tokens']+row['output_tokens'],
                    'known_cost_components_disagree')
            require(type(row['unknown_usage_calls']) is int and row['unknown_usage_calls'] >= 0,
                    'explicit_unknown_count_required')
            inputs,outputs = row['input_tokens']/1000,row['output_tokens']/1000
            unknown = row['unknown_usage_calls'] > 0
            hatch = '///' if unknown else None
            ax.bar(position,inputs,width=.58,color='#4676a8',edgecolor='#274665',hatch=hatch)
            ax.bar(position,outputs,bottom=inputs,width=.58,color='#e6a24b',edgecolor='#825319',hatch=hatch)
            label = f"{row['known_total_tokens']:,}"+(' + ?' if unknown else '')+'\n'+success_label(row['success'])
            if unknown:label += f"\n{row['unknown_usage_calls']} unknown usage"
            ax.text(position,inputs+outputs+limit*.025,label,ha='center',va='bottom',fontsize=9)
        ax.set_title(title+' / '+task,loc='left',fontsize=12,fontweight='bold')
        ax.set_xticks(range(4),LABELS,fontsize=9)
        ax.set_xlim(-.6,3.6);ax.set_ylim(0,limit)
        ax.set_ylabel('Logical input + output tokens (thousands)')
        ax.grid(axis='y',alpha=.22);ax.set_axisbelow(True);ax.spines[['top','right']].set_visible(False)
    fig.suptitle('P114 ordinary control with historical P111 references',fontsize=17,fontweight='bold',y=.98)
    fig.legend(handles=[Patch(facecolor='#4676a8',label='Input, including cached input'),
        Patch(facecolor='#e6a24b',label='Output'),
        Patch(facecolor='white',edgecolor='#596575',hatch='///',label='Known subtotal; total unknown')],
        loc='upper center',bbox_to_anchor=(.5,.945),ncol=3,frameon=False,fontsize=9)
    fig.text(.045,.025,'Four known tasks; one new run per task. All 16 conditions retained; P111 was run earlier.\n'
        'Historical, descriptive comparison. Unknown usage is not zero. Failures and unrun slots do not establish quality-preserving savings.',
        fontsize=10,color='#394452')
    if synthetic:
        fig.text(.5,.5,'SYNTHETIC PREVIEW — NOT EXPERIMENT RESULTS',ha='center',va='center',
            rotation=25,color='#a00000',fontsize=25,alpha=.45,weight='bold')
    fig.tight_layout(rect=(0,.09,1,.90))
    save(fig,folder,'P114_all_conditions');plt.close(fig)


def main(root):
    data,hashes = sources(root)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    plt.rcParams.update({'font.family':'DejaVu Sans','svg.fonttype':'none','font.size':10})
    folder = root/'materials/20261025_p114_figures';folder.mkdir()
    costs_figure(data['historical_audit']['rows']+data['new_audit']['rows'],folder,plt,Patch)
    write_new(folder/'build_manifest.json',dict(created_at=datetime.now(timezone.utc).isoformat(),
        builder_sha256=sha(Path(__file__)),helper_sha256=sha(root/'scripts/plot_receipt_history_results.py'),
        source_sha256=hashes,public_artifact_sha256={p.name:sha(p) for p in sorted(folder.iterdir())},
        matplotlib_version=matplotlib.__version__,new_conditions=4,historical_conditions=12,
        contemporaneous_comparison=False,unknown_usage_imputed=False,
        additional_model_calls=0,additional_API_requests=0,additional_evaluations=0))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo-root',type=Path,required=True)
    main(p.parse_args().repo_root.resolve())
