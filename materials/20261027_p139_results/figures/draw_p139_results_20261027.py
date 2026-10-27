"""P139 closed aggregate plots. No producer, model, tokenizer or evaluator runs.

The actual loader first requires the completed build manifest, then validates
fixed source and closed audit/session hashes before parsing public outcomes.
Only the handwritten --synthetic-fixture path is used during preparation.
Native and prefix evidence remain the fixed producer audit's responsibility.
"""
import argparse
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import subprocess

HEAD = 'a203874f0fafbaa76f76cfab3603eb43c623916f'
PLAN_SHA = 'e05b7a0fc0128d972cc2a63afe013fd21d28127c3a74ef9632918b2586b17657'
SOURCE_COUNT = 1617
PLAN = 'configs/P139_whole_task_checkpoint_representation_v01.json'
AUDIT = 'reports/P139_comparison.json'
SESSION = 'reports/P139_server_session.json'
BUILDER = 'scripts/build_checkpoint_representation_summary_p139.py'
DEST = 'materials/20261027_p139_results'
MODES = ('threshold_recursive','threshold_delta','exposure_recursive','exposure_delta')
TASKS = ('34d9492_1','3c13f5a_1','60d0b5b_1','6104387_1')
LABELS = ('Threshold / recursive','Threshold / delta','Exposure / recursive','Exposure / delta')
SHORT = ('T/R','T/D','E/R','E/D')
COLORS = ('#64748b','#679c93','#c58d42','#7b70ac')
COMPARISONS = (
    ('threshold_recursive','exposure_delta','primary_utility'),
    ('exposure_recursive','exposure_delta','representation_at_exposure'),
    ('threshold_delta','exposure_delta','timing_with_delta'),
    ('threshold_recursive','threshold_delta','representation_at_threshold'),
    ('threshold_recursive','exposure_recursive','timing_with_recursive'))
ROW_KEYS = ('run_id','task_id','checkpoint_representation_mode','record_status','success','stop_reason',
    'model_calls','known_total_tokens','unknown_usage_calls','input_tokens','output_tokens','cached_input_tokens',
    'api_requests','checkpoint_installations','decision_differences_from_threshold','decision_differences_from_exposure',
    'actual_decision_differences_from_threshold','actual_decision_differences_from_exposure','delta_installations',
    'fragment_count','actual_delta_actor_calls','actual_delta_known_actor_calls','actual_delta_unknown_actor_calls',
    'checkpoint_representation_contract_failed','checkpoint_representation_accounting_complete',
    'prefix_exposure_contract_failed','prefix_exposure_accounting_complete','wall_seconds','full_wall_seconds')
PAIR_KEYS = ('task_id','baseline','candidate','baseline_success','candidate_success','both_evaluated',
    'both_usage_known','success_lost','both_successful','candidate_minus_baseline_tokens',
    'actual_timing_decision_differences','candidate_delta_known_actor_calls','representation_prefix_match','actual_intervention')
FLAGS = ('checkpoint_representation_contract_failed','checkpoint_representation_accounting_complete',
         'prefix_exposure_contract_failed','prefix_exposure_accounting_complete')
GATES = ('primary_utility_gate_met','both_control_development_gate_met','combination_development_gate_met','development_gate_met')


def require(value, message):
    if not value: raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def equal(a,b):
    return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)


def nni(value):
    return type(value) is int and value >= 0


def positive(value):
    return type(value) is int and value > 0


def order():
    return [(n,MODES[(n-1+k)%4]) for n in range(1,5) for k in range(4)]


def identities():
    return [(f'BOC_P139_{n:02d}_{m.upper()}',TASKS[n-1],m) for n,m in order()]


def safe_path(root,relative):
    require(type(relative) is str and relative and not Path(relative).is_absolute()
            and '..' not in Path(relative).parts,'relative non-traversing path required')
    path=(root/relative).resolve()
    require(path.is_relative_to(root.resolve()) and path.is_file(),'bound file must exist within source root')
    return path


def check_map(root, mapping):
    require(type(mapping) is dict and mapping,'nonempty hash map required')
    for name,digest in mapping.items():
        require(type(digest) is str and len(digest)==64 and sha(safe_path(root,name))==digest,
                'bound file hash mismatch: '+str(name))


def project(summary):
    """Recalculate display arithmetic; preserve the recorded prefix-match decision."""
    require(summary.get('phase')=='P139' and type(summary.get('planned_rows')) is int
            and summary['planned_rows']==16,'all sixteen P139 slots required')
    require(all(type(summary.get(k)) is int and summary[k]==v
                for k,v in (('model_seed',57),('independent_tasks',4),('repetitions',1))),
            'fixed development seed, task count and repetition required')
    require(summary.get('all_model_roles_included') is True and summary.get('cached_input_deducted') is False
            and summary.get('prior_results_pooled') is False and summary.get('unknown_usage_imputed') is False,
            'whole-job cost and nonpooling contract required')
    require(type(summary.get('conditions')) is list and len(summary['conditions'])==16,'sixteen rows required')
    rows=[{k:deepcopy(r.get(k)) for k in ROW_KEYS} for r in summary['conditions']]
    require([(r['run_id'],r['task_id'],r['checkpoint_representation_mode']) for r in rows]==identities(),
            'ordered fixed sixteen identities required')
    counts=('model_calls','known_total_tokens','unknown_usage_calls','input_tokens','output_tokens','cached_input_tokens',
        'api_requests','checkpoint_installations','delta_installations','fragment_count','actual_delta_actor_calls',
        'actual_delta_known_actor_calls','actual_delta_unknown_actor_calls','actual_decision_differences_from_threshold',
        'actual_decision_differences_from_exposure')
    for r in rows:
        require(r['record_status'] in ('evaluated','unevaluated','not_run','incomplete_worker','audit_error'),
                'record status required')
        require(r['success'] is None or type(r['success']) is bool,'outcome bool/null required')
        require((r['record_status']=='evaluated')==(type(r['success']) is bool),'evaluation/outcome mismatch')
        for k in counts: require(r[k] is None or nni(r[k]),'count must be nonnegative exact int or null')
        for k in FLAGS: require(r[k] is None or type(r[k]) is bool,'accounting flags bool/null required')
        if all(nni(r[k]) for k in ('input_tokens','output_tokens','known_total_tokens')):
            require(r['input_tokens']+r['output_tokens']==r['known_total_tokens'],'known input+output mismatch')
        if nni(r['cached_input_tokens']) and nni(r['input_tokens']):
            require(r['cached_input_tokens']<=r['input_tokens'],'cached input exceeds logical input')
        if all(nni(r[k]) for k in ('actual_delta_actor_calls','actual_delta_known_actor_calls','actual_delta_unknown_actor_calls')):
            require(r['actual_delta_actor_calls']==r['actual_delta_known_actor_calls']+r['actual_delta_unknown_actor_calls'],
                    'actual delta usage partition mismatch')
    cells={(r['task_id'],r['checkpoint_representation_mode']):r for r in rows}
    def known(r):
        return r['record_status']=='evaluated' and type(r['success']) is bool and r['unknown_usage_calls']==0 \
            and type(r['unknown_usage_calls']) is int and nni(r['known_total_tokens'])
    all_known=all(known(r) for r in rows)
    totals={m:sum(r['known_total_tokens'] for r in rows if r['checkpoint_representation_mode']==m
                  and nni(r['known_total_tokens'])) for m in MODES}
    success={m:sum(r['success'] is True for r in rows if r['checkpoint_representation_mode']==m) for m in MODES}
    top=dict(all_sixteen_complete_with_known_usage=all_known,known_token_subtotals_by_mode=totals,
        total_tokens_by_mode=totals if all_known else {m:None for m in MODES},success_counts=success,
        usage_count_missing_conditions=sum(r['unknown_usage_calls'] is None for r in rows),
        recorded_unknown_usage_calls=sum(r['unknown_usage_calls'] for r in rows if nni(r['unknown_usage_calls'])))
    for k,v in top.items(): require(equal(summary.get(k),v),'fixed aggregate mismatch: '+k)
    require(type(summary.get('comparisons')) is list and len(summary['comparisons'])==5,'five fixed comparisons required')
    comps=[]
    for supplied,(baseline,candidate,name) in zip(summary['comparisons'],COMPARISONS,strict=True):
        require((supplied.get('baseline'),supplied.get('candidate'),supplied.get('name'))==(baseline,candidate,name),
                'fixed comparison order changed')
        ta,ra=baseline.split('_');tb,rb=candidate.split('_')
        representation_only=ta==tb and ra!=rb;timing_only=ta!=tb and ra==rb
        require(type(supplied.get('pairs')) is list and len(supplied['pairs'])==4,'all four pairs required')
        pairs=[]
        for task,old in zip(TASKS,supplied['pairs'],strict=True):
            a,b=cells[task,baseline],cells[task,candidate]
            require(old.get('task_id')==task,'fixed paired task required')
            evaluated=all(r['record_status']=='evaluated' and type(r['success']) is bool for r in (a,b))
            both_known=known(a) and known(b)
            timing=b['actual_decision_differences_from_'+ta] if ta!=tb else 0
            delta=b['actual_delta_known_actor_calls'] if rb!=ra else 0
            prefix=old.get('representation_prefix_match') if representation_only else None
            require(prefix is None or type(prefix) is bool,'recorded prefix match bool/null required')
            active=(positive(delta) and prefix is True if representation_only else positive(timing)
                    if timing_only else positive(delta) or positive(timing))
            pair=dict(task_id=task,baseline=baseline,candidate=candidate,baseline_success=a['success'],candidate_success=b['success'],
                both_evaluated=evaluated,both_usage_known=both_known,
                success_lost=a['success'] and not b['success'] if evaluated else None,
                both_successful=a['success'] and b['success'] if evaluated else None,
                candidate_minus_baseline_tokens=b['known_total_tokens']-a['known_total_tokens'] if both_known else None,
                actual_timing_decision_differences=timing,candidate_delta_known_actor_calls=delta,
                representation_prefix_match=prefix,actual_intervention=active)
            require(equal({k:old.get(k) for k in PAIR_KEYS},pair),'fixed pair mismatch')
            pairs.append(pair)
        complete=all(p['both_usage_known'] for p in pairs)
        common=[p for p in pairs if p['both_successful'] is True]
        cost=sum(p['candidate_minus_baseline_tokens'] for p in pairs) if complete else None
        common_cost=sum(p['candidate_minus_baseline_tokens'] for p in common) if complete and common else None
        active_common=any(p['actual_intervention'] for p in common)
        intact=all(cells[t,m]['prefix_exposure_contract_failed'] is False
            and cells[t,m]['prefix_exposure_accounting_complete'] is True
            and cells[t,m]['checkpoint_representation_contract_failed'] is False
            and cells[t,m]['checkpoint_representation_accounting_complete'] is True for t in TASKS for m in (baseline,candidate))
        prefixes=all(p['representation_prefix_match'] is True for p in pairs
            if positive(p['candidate_delta_known_actor_calls'])) if representation_only else None
        gate=bool(complete and intact and common and active_common and not any(p['success_lost'] for p in pairs)
            and cost<0 and common_cost<0 and (not representation_only or prefixes is True))
        comp=dict(name=name,baseline=baseline,candidate=candidate,pairs=pairs,representation_only=representation_only,
            timing_only=timing_only,all_four_pairs_complete_with_known_usage=complete,all_task_token_difference=cost,
            common_success_tasks=[p['task_id'] for p in common],common_success_token_difference=common_cost,
            changed_intervention_on_common_success=active_common,all_activated_representation_prefixes_match=prefixes,
            comparison_gate_met=gate)
        require(equal(comp,supplied),'fixed comparison aggregate or gate mismatch')
        comps.append(comp)
    gates=dict(primary_utility_gate_met=comps[0]['comparison_gate_met'],
        **{k:all(c['comparison_gate_met'] for c in comps[:3]) for k in GATES[1:]})
    for k,v in gates.items(): require(type(summary.get(k)) is bool and summary[k]==v,'fixed gate mismatch: '+k)
    return dict(phase='P139',model_seed=57,independent_tasks=4,modes=list(MODES),task_order=list(TASKS),
        conditions=rows,comparisons=comps,**top,**gates,cached_input_deducted=False,all_model_roles_included=True,
        prior_results_pooled=False,unknown_usage_imputed=False,arithmetic_and_gates_recomputed=True,
        observed_prefix_match_recomputed=False,closed_trace_audit_reexecuted=False)


def csv_value(v):
    return '' if v is None else str(v)


def check_csv(path,rows,fields):
    with path.open(newline='') as f:
        reader=csv.DictReader(f);actual=list(reader)
        require(reader.fieldnames==list(fields),'fixed CSV columns required')
    expected=[{k:csv_value(r.get(k)) for k in fields} for r in rows]
    require(actual==expected,'CSV/summary mismatch')


def git_head(root):
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()


def load_closed(root):
    root=Path(root).resolve();target=root/DEST
    # This is deliberately the first result-file read. Partial publication cannot
    # authorize reading the ongoing cohort's audit, conditions or summary.
    manifest=read(target/'build_manifest.json')
    require(manifest.get('phase')=='P139' and manifest.get('status')=='complete','completed P139 build manifest required first')
    for k in ('additional_model_calls','additional_API_requests','additional_evaluations'):
        require(type(manifest.get(k)) is int and manifest[k]==0,'zero-call material construction required')
    require(set(manifest.get('source_sha256',{}))=={AUDIT,SESSION,PLAN,BUILDER},'fixed build source map required')
    check_map(root,manifest['source_sha256']);check_map(target,manifest['artifact_sha256'])
    require({'summary.json','conditions.csv','pairs.csv','model_calls.csv','README.md'}<=set(manifest['artifact_sha256']),
            'all material artifacts required')
    require(sha(root/PLAN)==PLAN_SHA and git_head(root)==HEAD,'fixed P139 head and plan required')
    plan=read(root/PLAN)
    require(type(plan.get('source_sha256')) is dict and len(plan['source_sha256'])==SOURCE_COUNT,
            'fixed source count required')
    check_map(root,plan['source_sha256'])
    require(plan.get('checkpoint_representation_modes')==list(MODES)
            and type(plan.get('max_cells')) is int and plan['max_cells']==16
            and type(plan.get('rolling_checkpoint_max_opportunities')) is int
            and plan['rolling_checkpoint_max_opportunities']==2,'fixed factorial source contract required')
    session=read(root/SESSION)
    require(session.get('phase')=='P139' and session.get('status')=='stopped'
            and session.get('owned_processes_absent') is True
            and session.get('audit_source_sha256')==sha(root/AUDIT)
            and session.get('inspector_sha256')==plan['source_sha256'].get('scripts/inspect_whole_task_checkpoint_representation_session_p139.py'),
            'closed source-bound session required')
    audit=read(root/AUDIT)
    require(audit.get('phase')=='P139' and audit.get('batch_status') in ('complete','stopped')
            and audit.get('owned_processes_absent') is True and type(audit.get('audit_errors')) is list
            and not audit['audit_errors'] and audit.get('plan_sha256')==PLAN_SHA
            and audit.get('auditor_sha256')==plan['source_sha256'].get('scripts/audit_whole_task_checkpoint_representation_p139.py')
            and audit.get('pipeline_status_sha256')==session.get('pipeline_source_sha256')
            and audit.get('server_final_sha256')==session.get('source_sha256'),
            'closed source-bound audit required')
    for source,keys in ((audit,('additional_model_calls','additional_api_calls','additional_evaluator_calls')),
                        (session,('additional_model_calls','additional_api_requests','additional_evaluator_calls'))):
        require(all(type(source.get(k)) is int and source[k]==0 for k in keys),'closed accounting zero-call flags required')
    summary=read(target/'summary.json')
    require(equal(summary.get('source_sha256'),manifest['source_sha256']),'material/source manifest differs')
    for k in ('added_model_calls','added_environment_API_requests','added_evaluations'):
        require(type(summary.get(k)) is int and summary[k]==0,'zero-call material summary required')
    data=project(summary)
    require(len(audit.get('rows',[]))==16 and equal(
        [{k:r.get(k) for k in ROW_KEYS} for r in audit['rows']],summary['conditions']),'audited sixteen rows differ')
    for k in ('comparisons',*GATES,'total_tokens_by_mode','known_token_subtotals_by_mode','success_counts'):
        require(equal(audit.get(k),summary.get(k)),'audit/material aggregate differs: '+k)
    check_csv(target/'conditions.csv',data['conditions'],ROW_KEYS)
    check_csv(target/'pairs.csv',[p for c in data['comparisons'] for p in c['pairs']],PAIR_KEYS)
    return data,dict(source_head=HEAD,plan_sha256=PLAN_SHA,source_files_checked=SOURCE_COUNT,
        build_manifest_sha256=sha(target/'build_manifest.json'),input_summary_sha256=sha(target/'summary.json'),
        source_sha256=manifest['source_sha256'],artifact_sha256=manifest['artifact_sha256'],
        recorded_owned_process_closure_verified=True,live_PID_rechecked=False,
        native_counts_recomputed=False,prefix_evidence_reaudited=False)


def text_num(value,signed=False):
    return 'null' if value is None else (f'{value:+,}' if signed else f'{value:,}')


def render(data,out,*,synthetic,provenance):
    require(type(synthetic) is bool,'synthetic flag required')
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from matplotlib.ticker import FuncFormatter
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'pdf.fonttype':42})
    data=deepcopy(data);data['synthetic']=synthetic
    prefix='SYNTHETIC — NOT EXPERIMENT RESULTS\n' if synthetic else ''
    rows={(r['task_id'],r['checkpoint_representation_mode']):r for r in data['conditions']}
    ceiling=max([1]+[r['known_total_tokens'] for r in data['conditions'] if nni(r['known_total_tokens'])])
    fig,axes=plt.subplots(2,2,figsize=(17,12),sharey=True)
    fig.subplots_adjust(left=.065,right=.98,bottom=.26,top=.82,hspace=.48,wspace=.15)
    for ax,task in zip(axes.flat,TASKS,strict=True):
        for x,mode in enumerate(MODES):
            row=rows[task,mode];known=row['known_total_tokens'];unknown=row['unknown_usage_calls']
            outcome='SUCCESS' if row['success'] is True else 'FAILURE' if row['success'] is False else row['record_status'].replace('_',' ').upper()
            if known is None:
                ax.text(x,.04,'Usage missing\n'+outcome,ha='center',va='bottom',transform=ax.get_xaxis_transform(),fontsize=8)
                continue
            bar=ax.bar(x,known,color=COLORS[x],width=.62)[0]
            if unknown is None or unknown>0:bar.set_hatch('///');bar.set_edgecolor('#222222')
            marker='x' if row['success'] is False else 'o' if row['success'] is True else 'D'
            ax.plot(x,known,marker=marker,color='#111111',markersize=6,markerfacecolor='none')
            cost=f'{known:,} exact' if unknown==0 else f'≥ {known:,} known\nTotal null; '+(f'{unknown} unknown' if unknown is not None else 'count missing')
            state=''
            if any(row[k] is True for k in ('prefix_exposure_contract_failed','checkpoint_representation_contract_failed')):
                state='\nCONTRACT FAILURE'
            elif any(row[k] is False for k in ('prefix_exposure_accounting_complete','checkpoint_representation_accounting_complete')):
                state='\nACCOUNTING INCOMPLETE'
            ax.text(x,known+ceiling*.035,cost+'\n'+outcome+state,ha='center',va='bottom',fontsize=8,linespacing=1.3)
        ax.set_title(f'Task {TASKS.index(task)+1}',fontweight='bold');ax.set_xticks(range(4),SHORT)
        ax.set_xlim(-.65,3.65);ax.set_ylim(0,ceiling*1.70)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda y,_:f'{y/1000:,.0f}k'))
        ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    for ax in axes[:,0]:ax.set_ylabel('Logical input + output tokens')
    fig.suptitle(prefix+'P139 — Whole-job cost and official outcome',y=.985,fontsize=17)
    handles=[Patch(facecolor=c,label=l) for c,l in zip(COLORS,LABELS,strict=True)]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.52,.89),ncol=4,frameon=False)
    mode_lines=[]
    for m,label in zip(MODES,SHORT,strict=True):
        group=[r for r in data['conditions'] if r['checkpoint_representation_mode']==m]
        unknown=sum(r['unknown_usage_calls'] for r in group if nni(r['unknown_usage_calls']))
        missing=sum(r['unknown_usage_calls'] is None for r in group)
        mode_lines.append(f"{label}: successes {data['success_counts'][m]}/4 | known {data['known_token_subtotals_by_mode'][m]:,} | "
            f"fixed exact total {text_num(data['total_tokens_by_mode'][m])} | unknown calls {unknown} | count-missing cells {missing}")
    fig.text(.065,.165,'\n'.join(mode_lines),fontsize=10,linespacing=1.45)
    fig.text(.065,.045,'All 16 planned cells remain. Hatching marks a known lower bound; missing usage is not zero. × failure; ○ success; ◇ unevaluated.\n'
        'Costs include all actor + focus input/output and failed summaries. Cached input is included, never deducted.\n'
        'Fixed mode totals are null unless all 16 cells have known evaluated costs. Four known tasks, seed 57, max 2 opportunities; earlier cohorts excluded.',
        fontsize=10,linespacing=1.5)
    for ext in ('png','pdf'):fig.savefig(out/f'whole_job_cost.{ext}',dpi=170)
    plt.close(fig)

    fig,axes=plt.subplots(5,1,figsize=(17,15))
    fig.subplots_adjust(left=.045,right=.97,bottom=.13,top=.86,hspace=.75)
    for ax,comp in zip(axes,data['comparisons'],strict=True):
        ax.axis('off')
        base=SHORT[MODES.index(comp['baseline'])];cand=SHORT[MODES.index(comp['candidate'])]
        title=('PRIMARY: ' if comp['name']=='primary_utility' else '')+f'{cand} − {base}  |  '+comp['name'].replace('_',' ')
        ax.set_title(title,loc='left',fontweight='bold',fontsize=11,pad=9)
        body=[]
        for i,p in enumerate(comp['pairs'],1):
            a,b=p['baseline_success'],p['candidate_success']
            transition='Not both evaluated' if a is None or b is None else {
                (True,True):'Both successful',(False,False):'Both failed',(True,False):'SUCCESS LOST',(False,True):'Success gained'}[a,b]
            body.append([f'Task {i}',text_num(p['candidate_minus_baseline_tokens'],True),transition,
                str(p['actual_intervention']),('null' if p['representation_prefix_match'] is None else str(p['representation_prefix_match'])) if comp['representation_only'] else 'n/a'])
        table=ax.table(cellText=body,colLabels=['Pair','Δ logical tokens','Official outcome','Actual intervention','Observed prefix match'],
            colWidths=[.12,.20,.26,.20,.22],loc='upper center',cellLoc='center')
        table.auto_set_font_size(False);table.set_fontsize(9);table.scale(1,1.22)
        ax.text(0,-.19,f"All-task Δ {text_num(comp['all_task_token_difference'],True)}  |  "
            f"Common success {len(comp['common_success_tasks'])}/4; Δ {text_num(comp['common_success_token_difference'],True)}  |  "
            f"Common-success intervention {comp['changed_intervention_on_common_success']}  |  Fixed gate {comp['comparison_gate_met']}",
            transform=ax.transAxes,fontsize=10)
    fig.suptitle(prefix+'P139 — Primary comparison and four factorial edges',y=.985,fontsize=17)
    fig.text(.045,.90,f"Primary utility gate: {data['primary_utility_gate_met']}    |    Combination / both-control development gate: {data['development_gate_met']}\n"
        'T = threshold; E = paid prefix exposure; R = recursive replacement; D = second-opportunity delta. All arms allow at most 2 opportunities.',fontsize=11,linespacing=1.5)
    fig.text(.045,.025,'null stays null: all/common cost differences require all four pairs known; empty common-success sets remain null.\n'
        'Per-pair known differences do not replace a null fixed aggregate. A cheap failed run is not preserved task quality.\n'
        'Prefix matching and intervention are recorded audit evidence, not causal or semantic guarantees. No novelty, general quality or prior-cohort pooling claim.',
        fontsize=10,linespacing=1.5)
    for ext in ('png','pdf'):fig.savefig(out/f'paired_comparisons.{ext}',dpi=170)
    plt.close(fig)
    (out/'figure_data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    manifest=dict(phase='P139',synthetic=synthetic,renderer_source_sha256=sha(__file__),input_provenance=provenance,
        artifact_sha256={p.name:sha(p) for p in sorted(out.iterdir()) if p.is_file()},matplotlib_version=matplotlib.__version__,
        arithmetic_and_gate_checks=True,prefix_evidence_reaudited=False,closed_trace_audit_reexecuted=False,
        additional_model_API_evaluation_tokenizer_calls=0,saved_generated_code_executions=0,
        pixel_reproducibility_guaranteed=False)
    (out/'output_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--source-root',type=Path)
    group.add_argument('--synthetic-fixture',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    require(not args.output_dir.exists(),'exclusive new output directory required')
    if args.synthetic_fixture:
        fixture=read(args.synthetic_fixture)
        require(fixture.get('synthetic') is True and fixture.get('warning')=='HANDWRITTEN SYNTHETIC ONLY — NOT P139 RESULTS',
                'explicit handwritten synthetic fixture required')
        data=project(fixture['summary']);provenance={'synthetic_fixture_sha256':sha(args.synthetic_fixture)}
    else:data,provenance=load_closed(args.source_root)
    manifest=render(data,args.output_dir,synthetic=args.synthetic_fixture is not None,provenance=provenance)
    print(json.dumps({'phase':'P139','synthetic':manifest['synthetic'],'artifacts':list(manifest['artifact_sha256'])}))


if __name__=='__main__':main()
