"""Closed P133 figures; data-only public redraw is a separate explicit path.
No model, API, tokenizer, evaluator, saved program or producer auditor executes.
"""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,math,re
from pathlib import Path

HEAD='66d9eb71a1e6b8ee10b377be3bf52dca82d06cca'
PLAN='configs/P133_whole_task_checkpoint_payback_v01.json'
PLAN_SHA='357c59a73ed9637e9171d6729f8f4210533fef90d598ec667fa1d7154d09d986'
PLAN_SOURCE_COUNT=1459
REVIEW_SHA='97d0a16237a844e05dc70dd6dab4235a8ed5fd7d2103ba5f2452eeb2bf1d8178'
WRAPPER_SHA='471adf0e68662385933972516dc0d6cdec23464a19cffcf435786fb6152cf12a'
COLLECTOR_SHA='958703a3c71e2cd539743fc55e901e84e019ce503323fa8647243a03284cdb36'
MATERIAL='materials/20261027_p133_results'
MODES=('rolling_separate','empirical_payback');SEEDS=(57,157)
ORDER=((1,MODES[0]),(1,MODES[1]),(2,MODES[1]),(2,MODES[0]))
COUNT_FIELDS=('known_total_tokens','unknown_usage_calls','api_requests','model_calls','payback_rejections',
 'payback_shadow_rejections','payback_evaluated_opportunities','payback_dispatched_focus_calls',
 'payback_unknown_focus_usage_calls','checkpoint_installations')

def require(v,message):
    if not v:raise ValueError(message)
def integer(v):return type(v)is int and v>=0
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def safe(root,rel):
    p=Path(rel);require(not p.is_absolute()and'..'not in p.parts,'relative public source required');return root/p

def criteria(rows,audit_errors):
    require(len(rows)==4 and {(r['replication'],r['payback_mode'])for r in rows}==set(ORDER),'all four fixed slots required')
    evaluated=all(r['record_status']=='evaluated'and type(r['success'])is bool for r in rows)
    known=evaluated and all(integer(r.get('known_total_tokens'))and integer(r.get('unknown_usage_calls'))and r['unknown_usage_calls']==0 for r in rows)
    common=[];losses=[];delta=[]
    for rep in(1,2):
        a,b=[next(r for r in rows if(r['replication'],r['payback_mode'])==(rep,m))for m in MODES]
        ready=all(r['record_status']=='evaluated'and type(r['success'])is bool for r in(a,b))
        if ready:losses.append(a['success']and not b['success'])
        if ready and a['success']and b['success']:common.append(rep)
        if known:delta.append(b['known_total_tokens']-a['known_total_tokens'])
    paid=[r['payback_rejections']for r in rows if r['payback_mode']==MODES[1]and r['replication']in common]
    exposure=sum(paid)if paid and all(integer(n)for n in paid)else None
    intact=all(r.get('payback_contract_failed')is False and r.get('payback_accounting_complete')is True for r in rows)
    overall=sum(delta)if known else None;common_delta=sum(delta[rep-1]for rep in common)if known else None
    return dict(all_four_complete_with_known_usage=known,paired_success_losses=sum(losses)if evaluated else None,
        paired_successful_task_seed_pairs=len(common)if evaluated else None,empirical_minus_baseline_whole_task_tokens=overall,
        paired_successful_token_difference=common_delta,payback_rejections_on_common_success=exposure,
        mechanism_contracts_intact=intact,development_gate_met=bool(known and not audit_errors and intact
            and not any(losses)and common and overall<0 and common_delta<0 and exposure is not None and exposure>0))

def validate_data(data):
    require(data.get('phase')=='P133'and type(data.get('synthetic'))is bool,'P133 figure data identity')
    rows=data['rows'];require([(r['replication'],r['payback_mode'])for r in rows]==list(ORDER),'fixed four ordered rows')
    for r in rows:
        require(type(r['replication'])is int and type(r['model_seed'])is int and r['model_seed']==SEEDS[r['replication']-1],'fixed seed identity')
        status=r['record_status'];require(status in('evaluated','unevaluated','not_run','incomplete_worker','audit_error'),'record status')
        require(type(r['success'])is bool if status=='evaluated'else r['success']is None,'official success preserved')
        if status in('evaluated','unevaluated'):
            require(all(integer(r.get(k))for k in COUNT_FIELDS),'known nonnegative counts')
            roles=r['usage_by_role'];require(type(roles)is dict and set(roles)=={'agent','focus'},'both role ledgers')
            require(all(all(integer(v.get(k))for k in('calls','unknown_usage','input_tokens','output_tokens'))for v in roles.values()),'typed role usage')
            require(sum(v['input_tokens']+v['output_tokens']for v in roles.values())==r['known_total_tokens'],'whole job includes every known role cost')
            require(sum(v['unknown_usage']for v in roles.values())==r['unknown_usage_calls'],'unknown role count')
            require(sum(v['calls']for v in roles.values())==r['model_calls'],'whole job model calls')
        else:require(all(r.get(k)is None for k in COUNT_FIELDS)and r['usage_by_role']is None,'missing usage stays missing')
        require(r['exact_total_tokens']==(r['known_total_tokens']if integer(r.get('unknown_usage_calls'))and r['unknown_usage_calls']==0 else None),'exact total cannot be known subtotal')
    recomputed=criteria(rows,data['audit_error_count'])
    require(recomputed==data['criteria'],'figure criteria recalculated')
    require(data.get('timing_superiority_claim')is False and data.get('forecast_is_guarantee')is False,'no timing or guarantee claim')
    return data

def load_closed(args):
    # No public report or trial read precedes the completed collector marker.
    collector=read(args.collector_end);require(collector.get('status')=='complete','collector complete required before results')
    closure=read(args.closure);cs=read(args.collector_start);start=read(args.pipeline_start);review=read(args.independent_review)
    require(start['source_head']==cs['source_head']==review['fixed_head']==HEAD,'fixed head')
    require(start['plan_sha256']==review['plan_sha256']==PLAN_SHA,'fixed plan')
    require(start['wrapper_sha256']==WRAPPER_SHA and cs['wrapper_sha256']==COLLECTOR_SHA,'fixed operational sources')
    require(review.get('status')=='pass'and review.get('collector_complete_seen_before_trial_read')is True
        and review['review_script_sha256']==REVIEW_SHA and review['collector_end_sha256']==sha(args.collector_end),'closed independent review required')
    require(cs['closure_sha256']==sha(args.closure),'closure marker binding')
    require(review.get('start_registry_ledgers')==collector.get('prior_ledgers_unchanged')==189 and review.get('start_registry_bindings')==collector.get('prior_bindings_unchanged')==2290,'original start snapshot only')
    require([s['stage']for s in closure['stages']]==['audit','session','report']and all(type(s['exit_code'])is int and(s['stage']=='audit'or s['exit_code']==0)for s in closure['stages']),'all postprocessing closed')
    require(all(collector[k]==0 for k in('additional_model_calls','additional_API_requests','additional_evaluations')),'collector is data only')
    root=args.repo_root.resolve();require(sha(root/PLAN)==PLAN_SHA,'public fixed plan bytes')
    sources={PLAN:PLAN_SHA}
    def bind(rel,expected):
        require(sha(safe(root,rel))==expected,'public source hash mismatch: '+rel);sources[rel]=expected
    plan=read(root/PLAN);require(len(plan['source_sha256'])==PLAN_SOURCE_COUNT,'all frozen source bindings')
    for rel,h in plan['source_sha256'].items():bind(rel,h)
    for rel,h in collector['copied_source_sha256'].items():bind(rel,h)
    for rel,k in [('reports/P133_comparison.json','audit_sha256'),('reports/P133_server_session.json','session_sha256'),(MATERIAL+'/build_manifest.json','report_manifest_sha256')]:bind(rel,closure[k])
    manifest=read(root/MATERIAL/'build_manifest.json')
    for rel,h in manifest['source_sha256'].items():bind(rel,h)
    for rel,h in manifest['artifact_sha256'].items():bind(MATERIAL+'/'+rel,h)
    audit=read(root/'reports/P133_comparison.json');session=read(root/'reports/P133_server_session.json');public=read(root/MATERIAL/'summary.json')
    require(audit['phase']==session['phase']==public['phase']=='P133'and audit['owned_processes_absent']is True
        and session['owned_processes_absent']is True and session['status']=='stopped','closed public audit and server')
    require(len(audit['audit_errors'])==closure['audit_errors']==collector['audit_errors'],'audit errors retained')
    require([(r['run_id'],r['replication'],r['model_seed'],r['payback_mode'])for r in audit['rows']]==[(f'BOC_P133_R{rep:02d}_01_{mode.upper()}',rep,SEEDS[rep-1],mode)for rep,mode in ORDER],'all named fixed slots')
    rows=[]
    for raw in audit['rows']:
        row={k:raw.get(k)for k in('replication','model_seed','payback_mode','record_status','success',*COUNT_FIELDS,'payback_contract_failed','payback_accounting_complete')}
        row['usage_by_role']=deepcopy(raw.get('usage_by_role'))
        row['exact_total_tokens']=row['known_total_tokens']if integer(row['unknown_usage_calls'])and row['unknown_usage_calls']==0 else None
        rows.append(row)
    recalculated=criteria(rows,len(audit['audit_errors']))
    for k,v in recalculated.items():
        require(v==audit[k]==public['audited_criteria'][k]==review['independent_criteria'][k],'independent scientific criterion binding')
    for a,b in zip(audit['rows'],public['conditions'],strict=True):
        for k in ('run_id','record_status','success',*COUNT_FIELDS):require(a.get(k)==b.get(k),'public row binding')
    data=dict(phase='P133',synthetic=False,rows=rows,criteria=recalculated,audit_error_count=len(audit['audit_errors']),
        server_wall_seconds=session['wall_seconds'],server_time_scope='Whole owned session, not a paired speed estimate.',
        timing_superiority_claim=False,forecast_is_guarantee=False,novelty_established=False,
        source_sha256=sources,evidence_sha256={k:sha(getattr(args,k))for k in('collector_end','collector_start','closure','pipeline_start','independent_review')})
    return validate_data(data)

def label(row):return f"Seed {row['model_seed']}\n"+('Rolling separate'if row['payback_mode']==MODES[0]else'Empirical payback')
def status(row):
    value='SUCCESS'if row['success']is True else'FAILURE'if row['success']is False else row['record_status'].replace('_',' ').upper()
    return value+(' / CONTRACT FAILURE'if row['payback_contract_failed']is True else'')
def value_label(row):
    v=row['known_total_tokens']
    if v is None:return status(row)+'\nUsage unmeasured'
    unknown=row['unknown_usage_calls']
    return f"{v:,}"+(' exact'if unknown==0 else' known')+'\n'+status(row)+(f'; unknown {unknown}'if unknown else'')

def render(data,output):
    validate_data(data);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.fonttype':'none'})
    rows=sorted(data['rows'],key=lambda r:(r['replication'],MODES.index(r['payback_mode'])))
    colors=['#356894'if r['payback_mode']==MODES[0]else'#c46a25'for r in rows]
    known=[r['known_total_tokens']or 0 for r in rows];ceiling=max([1,*known]);criterion=data['criteria']
    common=criterion['paired_successful_task_seed_pairs'];delta=criterion['empirical_minus_baseline_whole_task_tokens']
    common_delta=criterion['paired_successful_token_difference'];prefix='SYNTHETIC EXAMPLE — 'if data['synthetic']else''
    fig,ax=plt.subplots(figsize=(12,6.8));bars=ax.bar(range(4),known,color=colors,width=.62)
    for i,(bar,row)in enumerate(zip(bars,rows)):
        if row['known_total_tokens']is None:bar.set_facecolor('none');ax.scatter(i,ceiling*.015,marker='x',color='#555555')
        elif row['unknown_usage_calls']:bar.set_hatch('///');bar.set_edgecolor('#333333')
        ax.text(i,(row['known_total_tokens']or 0)+ceiling*.025,value_label(row),ha='center',va='bottom',fontsize=10)
    ax.set_ylim(0,ceiling*1.28);ax.set_xticks(range(4),[label(r)for r in rows]);ax.set_ylabel('Logical input + output tokens')
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v,p:f'{v:,.0f}'));ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    fig.suptitle(prefix+'P133 — Whole-job cost and official task outcome',fontsize=15,y=.96)
    ax.set_title('All four fixed conditions; one known CSV task, two seeds. Paid focus and failed work included.',fontsize=10,pad=17)
    ds='unknown'if delta is None else f'{delta:+,}'
    cd='unknown'if common_delta is None else f'{common_delta:+,}'
    footer=f"Development gate: {criterion['development_gate_met']}  |  Whole-job payback − rolling: {ds} tokens\nCommon-success pairs: {common if common is not None else 'unknown'} / 2  |  Common-success difference: {cd} tokens\nHatching denotes known subtotal with unmeasured usage. A forecast does not guarantee completion, quality or savings."
    fig.text(.07,.045,footer,fontsize=10,linespacing=1.5);fig.subplots_adjust(bottom=.27,top=.82,left=.09,right=.97)
    for ext in('png','svg','pdf'):fig.savefig(output/('whole_job_cost.'+ext),dpi=180)
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,6.8));actor=[];focus=[]
    for row in rows:
        roles=row['usage_by_role'];actor.append(None if roles is None else roles['agent']['input_tokens']+roles['agent']['output_tokens']);focus.append(None if roles is None else roles['focus']['input_tokens']+roles['focus']['output_tokens'])
    ax.bar(range(4),[v or 0 for v in actor],color='#527b9d',width=.62,label='Actor — known paid tokens')
    ax.bar(range(4),[v or 0 for v in focus],bottom=[v or 0 for v in actor],color='#d7a05b',width=.62,label='Focus — known paid tokens')
    for i,row in enumerate(rows):
        if row['known_total_tokens']is None:note='Usage and control counts unmeasured'
        else:
            note=f"{status(row)}\nFocus calls {row['payback_dispatched_focus_calls']}\nActual skips {row['payback_rejections']} | shadow rejects {row['payback_shadow_rejections']}"
            if row['unknown_usage_calls']:note+=f"\nUnknown usage calls {row['unknown_usage_calls']}"
        ax.text(i,(row['known_total_tokens']or 0)+ceiling*.025,note,ha='center',va='bottom',fontsize=9)
    ax.set_ylim(0,ceiling*1.43);ax.set_xticks(range(4),[label(r)for r in rows]);ax.set_ylabel('Known logical input + output tokens')
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v,p:f'{v:,.0f}'));ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True);ax.legend(loc='upper left',fontsize=9)
    fig.suptitle(prefix+'P133 — Paid actor/focus work and actual skipped summaries',fontsize=15,y=.96)
    fig.text(.07,.055,'Actual skips are new-policy rejections before dispatch; baseline shadow rejects are hypothetical.\nBoth arms share existing budget screens and the first summary. Unknown usage is additional unmeasured cost.\nInput savings, observed time and this forecast do not establish semantic fidelity or technical novelty.',fontsize=10,linespacing=1.5)
    fig.subplots_adjust(bottom=.27,top=.85,left=.09,right=.97)
    for ext in('png','svg','pdf'):fig.savefig(output/('paid_focus_and_control.'+ext),dpi=180)
    plt.close(fig)
    (output/'figure_data.json').write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    artifacts={p.name:sha(p)for p in output.iterdir()if p.is_file()}
    manifest=dict(phase='P133',synthetic=data['synthetic'],renderer_source_sha256=sha(__file__),
        figure_data_sha256=artifacts['figure_data.json'],artifact_sha256=artifacts,
        source_sha256=data['source_sha256'],evidence_sha256=data['evidence_sha256'],
        generated_at=datetime.now(timezone.utc).isoformat(),original_results_changed=False,
        additional_model_API_evaluation_tokenizer_calls=0,redraw_is_not_renewed_scientific_audit=True,
        byte_identical_PNG_or_PDF_not_guaranteed_across_fonts_and_creation_dates=True)
    (output/'output_manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    return manifest

def synthetic():
    rows=[]
    for rep,mode in ORDER:
        known=170000 if mode==MODES[0]else 140000;unknown=int(rep==2 and mode==MODES[1]);success=not(rep==2)
        roles={'agent':dict(calls=10,unknown_usage=unknown,input_tokens=known-30000,output_tokens=10000),'focus':dict(calls=2,unknown_usage=0,input_tokens=19000,output_tokens=1000)}
        row=dict(replication=rep,model_seed=SEEDS[rep-1],payback_mode=mode,record_status='evaluated',success=success,
            known_total_tokens=known,unknown_usage_calls=unknown,exact_total_tokens=known if not unknown else None,
            api_requests=60,model_calls=12,payback_rejections=int(mode==MODES[1]),payback_shadow_rejections=1,
            payback_evaluated_opportunities=3,payback_dispatched_focus_calls=2,payback_unknown_focus_usage_calls=0,
            checkpoint_installations=2,payback_contract_failed=False,payback_accounting_complete=True,usage_by_role=roles)
        rows.append(row)
    return dict(phase='P133',synthetic=True,rows=rows,criteria=criteria(rows,0),audit_error_count=0,server_wall_seconds=1800,
        timing_superiority_claim=False,forecast_is_guarantee=False,novelty_established=False,source_sha256={},evidence_sha256={})

def main():
    p=argparse.ArgumentParser();p.add_argument('--repo-root',type=Path)
    for name in('collector-end','collector-start','closure','pipeline-start','independent-review','output-dir','figure-data','original-manifest'):p.add_argument('--'+name,type=Path)
    p.add_argument('--manifest-sha256');p.add_argument('--synthetic-preview',action='store_true');p.add_argument('--redraw',action='store_true');a=p.parse_args()
    require(a.output_dir is not None,'exclusive output directory required')
    require(not(a.synthetic_preview and a.redraw),'select one rendering path')
    if a.synthetic_preview:data=synthetic()
    elif a.redraw:
        require(a.figure_data is not None and a.original_manifest is not None and a.manifest_sha256 is not None,'published data and trusted manifest digest required')
        require(sha(a.original_manifest)==a.manifest_sha256,'publication manifest digest required')
        manifest=read(a.original_manifest)
        require(manifest['renderer_source_sha256']==sha(__file__)and manifest['figure_data_sha256']==sha(a.figure_data),'original data and renderer bytes required')
        data=validate_data(read(a.figure_data))
    else:
        require(all(getattr(a,k)is not None for k in('repo_root','collector_end','collector_start','closure','pipeline_start','independent_review')),'closed evidence arguments required')
        data=load_closed(a)
    result=render(data,a.output_dir);print(json.dumps({'phase':'P133','synthetic':data['synthetic'],'artifacts':len(result['artifact_sha256']),'data_sha256':result['figure_data_sha256']}))
if __name__=='__main__':main()
