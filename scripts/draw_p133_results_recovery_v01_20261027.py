"""P133 recovery-only closed loader; reuse the original fixed plotting implementation.
Public redraw uses the original renderer's --redraw mode and published data/digest.
The original collector was never completed; this loader does not fabricate it.
"""
import argparse,hashlib,importlib.util,json
from copy import deepcopy
from pathlib import Path

RECOVERY_HEAD='309e2eb7d6be27dde63d97912d9bfb690e8da7db'
MARKER_SHA='73b982c18522739eb1b8fbf5e695727bae053969d7f4842ba23d451bc247c20b'
REVIEW_SHA='7b497da4c3defad00e46d35881e4aecf295c660a73ed4ca910c088461243ca80'
RENDERER_SHA='d2e0ed6bbb560981c951392c5ce7eac586dd7c411be854df4681b102b500651e'
MATERIAL='materials/20261027_p133_results_recovery_v01'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def require(c,m):
    if not c:raise ValueError(m)
def renderer(p):
    require(sha(p)==RENDERER_SHA,'original_renderer_source_required')
    spec=importlib.util.spec_from_file_location('fixed_p133_renderer',p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def load_recovery(args,r):
    recovery=read(args.recovery_complete)
    require(recovery.get('status')=='complete'and recovery.get('completed_conditions')==4,'reporting_recovery_complete_first')
    require(sha(args.recovery_complete)==MARKER_SHA,'fixed_recovery_marker')
    root=args.repo_root.resolve()
    require(recovery['source_head']==RECOVERY_HEAD and recovery['original_head']==r.HEAD
        and recovery['original_plan_sha256']==r.PLAN_SHA and recovery['recovery_root']==str(root)
        and recovery['original_collector_started']is False,'original_and_recovery_lineage')
    require(all(type(recovery[k])is int and recovery[k]==0 for k in('additional_model_calls','additional_API_requests','additional_evaluations','additional_tokenizer_calls')),'data_only_recovery')
    review=read(args.independent_review)
    require(review.get('status')=='pass'and review.get('review_script_sha256')==REVIEW_SHA
        and review.get('fixed_head')==r.HEAD and review.get('plan_sha256')==r.PLAN_SHA
        and review.get('reporting_recovery_source_head')==RECOVERY_HEAD
        and review.get('reporting_recovery_complete_seen_before_trial_read')is True
        and review.get('reporting_recovery_complete_sha256')==MARKER_SHA
        and review.get('original_collector_started')is False
        and review.get('start_registry_ledgers')==189 and review.get('start_registry_bindings')==2290,'independent_recovery_review_required')
    require(sha(root/r.PLAN)==r.PLAN_SHA,'fixed_original_plan')
    sources={r.PLAN:r.PLAN_SHA}
    def bind(name,h):
        p=r.safe(root,name);require(sha(p)==h,'public_source_hash_mismatch');sources[name]=h
    plan=read(root/r.PLAN);require(len(plan['source_sha256'])==1459,'all_original_sources')
    for name,h in plan['source_sha256'].items():bind(name,h)
    for name,h in recovery['recovery_source_sha256'].items():bind(name,h)
    bind(recovery['audit_path'],recovery['audit_sha256']);bind(recovery['session_path'],recovery['session_sha256'])
    require(recovery['recovery_manifest_path']==MATERIAL+'/build_manifest.json','recovery_material_path')
    bind(recovery['recovery_manifest_path'],recovery['recovery_manifest_sha256'])
    manifest=read(root/recovery['recovery_manifest_path'])
    for name,h in manifest['source_sha256'].items():bind(name,h)
    for name,h in manifest['artifact_sha256'].items():bind(MATERIAL+'/'+name,h)
    audit=read(root/recovery['audit_path']);session=read(root/recovery['session_path']);summary=read(root/MATERIAL/'summary.json')
    require(audit['phase']==session['phase']==summary['phase']=='P133'and audit['owned_processes_absent']is True
        and session['owned_processes_absent']is True and session['status']=='stopped','original_closed_audit')
    require([(x['run_id'],x['replication'],x['model_seed'],x['payback_mode'])for x in audit['rows']]==[(f'BOC_P133_R{rep:02d}_01_{mode.upper()}',rep,r.SEEDS[rep-1],mode)for rep,mode in r.ORDER],'all_four_ordered_slots')
    rows=[]
    for raw in audit['rows']:
        row={k:raw.get(k)for k in('replication','model_seed','payback_mode','record_status','success',*r.COUNT_FIELDS,'payback_contract_failed','payback_accounting_complete')}
        row['usage_by_role']=deepcopy(raw.get('usage_by_role'))
        row['exact_total_tokens']=row['known_total_tokens']if r.integer(row['unknown_usage_calls'])and row['unknown_usage_calls']==0 else None
        rows.append(row)
    criteria=r.criteria(rows,len(audit['audit_errors']))
    for k,v in criteria.items():require(v==audit[k]==summary['audited_criteria'][k]==review['independent_criteria'][k],'scientific_criteria_binding')
    for a,b in zip(audit['rows'],summary['conditions'],strict=True):
        for k in('run_id','record_status','success',*r.COUNT_FIELDS):require(a.get(k)==b.get(k),'public_row_binding')
    data=dict(phase='P133',synthetic=False,rows=rows,criteria=criteria,audit_error_count=len(audit['audit_errors']),
        server_wall_seconds=session['wall_seconds'],server_time_scope='Whole owned original session, not a paired speed estimate.',
        timing_superiority_claim=False,forecast_is_guarantee=False,novelty_established=False,
        reporting_attempt='recovery_v01',original_collector_completed=False,
        original_report_failure_preserved=True,source_sha256=sources,
        evidence_sha256={'reporting_recovery_complete':MARKER_SHA,'independent_recovery_review':sha(args.independent_review),
            'actual_recovery_loader':sha(__file__),'original_report_failure':recovery['original_failure_sha256'],
            'actual_recovery_protocol':recovery['source_protocol_sha256']})
    return r.validate_data(data)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in('repo-root','recovery-complete','independent-review','renderer-source','output-dir'):p.add_argument('--'+k,type=Path,required=True)
    args=p.parse_args();r=renderer(args.renderer_source);data=load_recovery(args,r);out=r.render(data,args.output_dir)
    print(json.dumps({'phase':'P133','reporting_attempt':'recovery_v01','artifacts':len(out['artifact_sha256']),'data_sha256':out['figure_data_sha256']}))
