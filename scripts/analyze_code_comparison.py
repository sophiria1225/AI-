"""All-case, post-execution analysis for the fixed ordinary code comparator."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from audit_code_execution import audit as code_audit
from audit_native_boundaries import audit as boundary_audit
from audit_inference_costs import timing_row
from compare_generic_guidance import check_execution_measurement, TOTAL_KEYS
from diagnose_p25_public_traces import sent_rows, photos, export_counts
from summarize_context_pilot import summarize_trial

ROOT=Path(__file__).resolve().parents[1]


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')


def budget(trial):
    plan,summary,usage,events=[read(trial/n) for n in ('plan.json','summary.json','usage.json','events.json')]
    if plan['phase']!='P27' or summary['arm']!='code_guided':raise ValueError('wrong code cohort')
    if plan['max_api_requests']!=plan['api_budget_by_task'][summary['task_id']]:raise ValueError('per-task cap differs')
    rows=[timing_row(u,read(trial/u['id']/'response.json')) for u in usage]
    known=[r for r in rows if r['status']=='ok'];timed=[r for r in rows if r['timing_available']]
    token=sum(r['input_tokens']+r['output_tokens'] for r in known)
    api=sum(bool(e['api_request_sent']) for e in events)
    if (token!=summary['known_total_tokens'] or len(rows)!=summary['model_calls'] or api!=summary['api_requests']
            or len(events)!=summary['tool_turns'] or any(r['role']!='agent' for r in rows)):
        raise ValueError('recorded total differs')
    if token>plan['max_total_tokens'] or api>plan['max_api_requests'] or len(rows)>plan['max_calls']:
        raise ValueError('fixed limit exceeded')
    per_call=Counter(e['call'] for e in events if e['api_request_sent'])
    return dict(run_id=summary['run_id'],model_calls=len(rows),api_requests=api,known_total_tokens=token,
        unknown_usage_calls=len(rows)-len(known),wall_seconds=summary['wall_seconds'],
        max_api_requests_in_one_response=max(per_call.values(),default=0),
        output_limit_finishes=sum(u.get('finish_reason')=='length' for u in usage),
        limits={k:plan[k] for k in ('max_calls','max_api_requests','max_total_tokens','max_wall_seconds','max_output_tokens')},
        cached_input_tokens_in_timed_calls=sum(r['cached_tokens'] for r in timed),
        processed_input_tokens_in_timed_calls=sum(r['processed_input_tokens'] for r in timed),
        prefill_seconds_in_timed_calls=sum(r['prefill_seconds'] for r in timed),
        decode_seconds_in_timed_calls=sum(r['decode_seconds'] for r in timed),
        source_sha256={n:sha(trial/n) for n in ('plan.json','summary.json','usage.json','events.json')})


def require_complete(storage,plan):
    base=storage/'records/context_pilot';status=read(base/plan['batch_id']/'status.json')
    if status['status']!='complete':raise ValueError('wait for all four cases')
    if read(base/plan['batch_id']/'plan.json')!=plan:raise ValueError('batch plan changed')
    for task,arm,rid in plan['run_order']:
        trial=base/rid
        if not (trial/'evaluation.json').exists():raise ValueError('evaluation is missing')
        expected=dict(plan,max_api_requests=plan['api_budget_by_task'][task])
        if read(trial/'plan.json')!=expected:raise ValueError('per-task plan changed')
        s=read(trial/'summary.json')
        if (s['task_id'],s['arm'],s['run_id'])!=(task,arm,rid):raise ValueError('trial identity changed')


def analyze(storage,root):
    plan=read(root/'configs/P27_code_comparison_v01.json');require_complete(storage,plan)
    destination=root/'reports/P27_comparison.json'
    if destination.exists():raise FileExistsError('preserve completed analysis')
    inputs=['configs/P27_code_comparison_v01.json','reports/P18_P25_paired_comparison.json',
            'reports/P26_photo_budget_summary.json','reports/P26_budget_diagnostics.json',
            'reports/P26_interpretation.json','reports/P25_interpretation.json']
    original=read(root/inputs[1]);p26=read(root/inputs[2])['trials'][0];b26=read(root/inputs[3])['trials'][0]
    prior=[dict(r['guided']) for r in original['pairs']]
    prior[0]=dict(task_id=p26['task_id'],run_id=p26['run_id'],success=p26['evaluation']['official_success'],
        declared_complete=p26['declared_complete'],stop_reason=p26['stop_reason'],model_calls=p26['model_calls'],
        known_total_tokens=p26['known_total_tokens'],unknown_usage_calls=p26['unknown_usage_calls'],
        api_requests=b26['api_requests'],output_limit_finishes=b26['output_limit_finishes'],execution_wall_seconds=p26['wall_seconds'])
    pairs=[];diagnoses=[];budgets=[]
    for i,((task,arm,rid),baseline) in enumerate(zip(plan['run_order'],prior,strict=True)):
        t=storage/'records/context_pilot'/rid
        audit=code_audit(t);boundary=boundary_audit(t,storage/'.runtime/appworld/r18_probe_01')
        for tag,data in [('execution_audit',audit),('boundary_audit',boundary)]:
            name=f'reports/{rid}_{tag}.json';put(root/name,data);inputs.append(name)
        if audit['audit_errors'] or audit['code_audit_errors'] or boundary['audit_errors']:
            raise ValueError('audit mismatch; preserve results and investigate before interpretation')
        measurement=summarize_trial(t);check_execution_measurement(audit,measurement,t)
        b=budget(t);budgets.append(b)
        row=dict(task_id=task,run_id=rid,success=measurement['evaluation']['official_success'],
            declared_complete=measurement['declared_complete'],stop_reason=measurement['stop_reason'],
            model_calls=b['model_calls'],known_total_tokens=b['known_total_tokens'],unknown_usage_calls=b['unknown_usage_calls'],
            api_requests=b['api_requests'],output_limit_finishes=b['output_limit_finishes'],execution_wall_seconds=b['wall_seconds'])
        if baseline['task_id']!=task:raise ValueError('wrong baseline task')
        pairs.append(dict(task_id=task,baseline=baseline,code=row,
            outcome='both_success' if baseline['success'] and row['success'] else
                    'both_failure' if not baseline['success'] and not row['success'] else
                    'improved' if row['success'] else 'worsened'))
        spans=read(t/'spans.json');events=read(t/'events.json');sent=sent_rows(spans,events)
        programs=[read(p) for p in sorted((t/'programs').glob('*/result_private.json'))]
        observation_errors=Counter()
        for s in spans.values():
            o=s['observation']
            if isinstance(o,dict):
                for key in ('format_error','not_executed'):
                    if key in o:observation_errors[key]+=1
        detail=dict(run_id=rid,sent_api_counts=dict(Counter(x['name'] for x in sent)),
            code_programs=len(programs),program_status_counts=dict(Counter(p['status'] for p in programs)),
            program_wall_seconds=sum(p['wall_seconds'] for p in programs),
            stdout_truncated_programs=sum(bool(p.get('stdout_truncated')) for p in programs),
            unparsed_inner_error_count=observation_errors,
            source_sha256={n:sha(t/n) for n in ('spans.json','events.json','summary.json')})
        if i==0:detail['photo_counts']=photos(sent)
        if i==3:detail['song_coverage']=export_counts(sent)
        diagnoses.append(detail)
    totals={}
    for arm in ('baseline','code'):
        totals[arm]={k:sum(r[arm][k] for r in pairs) for k in TOTAL_KEYS}
        totals[arm].update(successes=sum(r[arm]['success'] for r in pairs),trials=4)
    for path,data in [('reports/P27_budget_diagnostics.json',dict(phase='P27',trials=budgets)),
                      ('reports/P27_public_trace_diagnostics.json',dict(phase='P27',trials=diagnoses,all_four_read=True))]:
        data.update(model_calls=0,environment_requests=0,evaluator_contents_read=False)
        put(root/path,data);inputs.append(path)
    result=dict(phase='P27',all_four_reviewed=True,pairs=pairs,totals=totals,
        outcome_counts=dict(Counter(p['outcome'] for p in pairs)),
        source_hashes={name:sha(root/name) for name in inputs},script_sha256=sha(Path(__file__)),
        new_model_calls=0,environment_requests=0,novelty_established=False,
        limitations=['Four already observed cases, one seed; not confirmation.','Photo baseline is P26 (160 API); other baselines are P25 (80 API).',
            'Python control flow, schema access and visible output differ; not a language-only intervention.',
            'P27 inherited a native discovery-policy description in the configuration. Actual code updates schemas within each program, as specified in the P27 protocol and code guide. This metadata discrepancy is retained, not silently corrected in the frozen run.',
            'Fresh variables between code programs, unlike a persistent CodeAct interpreter.','A standard code interface is not a proposed novel method.'])
    put(destination,result)
    print(json.dumps(dict(totals=totals,outcome_counts=result['outcome_counts'])))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage-root',type=Path,required=True);p.add_argument('--repo-root',type=Path,default=ROOT)
    a=p.parse_args();analyze(a.storage_root,a.repo_root)
