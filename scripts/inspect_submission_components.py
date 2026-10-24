"""P103: decompose every closed P98 submission fingerprint once, without execution."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import time

from inspect_recorded_action_agreement import sha, read_bound, verify_ci
from inspect_input_exposure import check_resume
from submission_components import components, compare, summarize

PLAN='configs/P103_submission_components_v01.json'
SOURCE='reports/P98_recorded_action_agreement.json'
ZERO=('model_generations','environment_API_requests','saved_code_executions',
      'evaluations','task_databases_read','reserved_scenarios_read')


def inspect(storage,root):
    began=time.monotonic();plan=json.loads((root/PLAN).read_text())
    fixed=dict(phase='P103',cells=24,original_model_attempts=426,independent_known_tasks=4,
        condition_pairs=60,aligned_positions=1132,original_target_positions=33,
        original_target_distinct_generations=37,max_file_bytes=16777216,max_wall_seconds=180,
        alignment='original_P98_same_generation_ordinal_union',automatic_retries=0,
        semantic_equivalence_claim=False,novel_method_claim=False,**{k:0 for k in ZERO})
    if any(plan.get(k)!=v for k,v in fixed.items()):raise ValueError('fixed_P103_scope_changed')
    stop=storage/'.runtime/P103.stop'
    if stop.exists():raise InterruptedError('explicit_stop')
    resume=check_resume(storage)
    for rel,value in plan['source_sha256'].items():
        if sha(root/rel)!=value:raise ValueError('fixed_source_changed:'+rel)
    head,ci=verify_ci(root)
    old=json.loads((root/SOURCE).read_text())
    if (old['status']!='complete' or len(old['rows'])!=24 or len(old['pairs'])!=60
            or old['original_model_attempts']!=426 or old['all_aligned']['aligned_slots']!=1132
            or [r['run_id'] for r in old['rows']]!=plan['run_ids']):
        raise ValueError('all_original_P98_records_required')
    runs=[];lookup={};private_hashes={}
    for original in old['rows']:
        calls=[];run_id=original['run_id']
        if len(original['calls'])!=original['model_calls']:
            raise ValueError('original_generation_inventory_disagrees')
        for ordinal,call in enumerate(original['calls'],1):
            if stop.exists():raise InterruptedError('explicit_stop')
            if time.monotonic()-began>=180:raise TimeoutError('finite_readonly_deadline')
            if call['ordinal']!=ordinal or call['call_id']!=f'call_{ordinal:03d}':
                raise ValueError('original_call_order_changed')
            rel='records/context_pilot/'+run_id+'/'+call['call_id']+'/response.json';path=storage/rel
            path.resolve().relative_to((storage/'records/context_pilot').resolve())
            if path.is_symlink():raise ValueError('private_response_symlink_rejected')
            expected=original['private_response_sha256'][call['call_id']]
            if expected is None:
                if path.exists():raise ValueError('missing_response_cannot_be_filled')
                response=None
            else:
                response=read_bound(path,expected);private_hashes[rel]=expected
            value=components(response)
            if (value['public_output_sha256']!=call['response']['public_output_sha256']
                    or value['original_syntax_actions_sha256']!=call['response']['syntax_actions_sha256']):
                raise ValueError('original_response_fingerprint_changed')
            item=dict(call_id=call['call_id'],ordinal=ordinal,usage_status=call['usage_status'],
                known_total_tokens=call['known_total_tokens'],API_requests=call['API_requests'],
                API_requests_known=call['API_requests_known'],execution_kinds=call['execution_kinds'],
                completed_submission=call['completed_submission'],components=value)
            calls.append(item);lookup[run_id,ordinal]=value
        runs.append(dict(**{k:original[k] for k in ('run_id','task_id','time_visibility','repetition',
            'success','stop_reason','model_calls','api_requests','known_total_tokens','unknown_usage_calls')},calls=calls))
    pairs=[]
    for original in old['pairs']:
        rows=[]
        for row in original['rows']:
            left=lookup.get((original['left'],row['ordinal']));right=lookup.get((original['right'],row['ordinal']))
            rows.append(dict(**row,**compare(left,right,row)))
        pairs.append(dict(**{k:v for k,v in original.items() if k!='rows'},rows=rows))
    all_rows=summarize(pairs,runs);matched=summarize(pairs,runs,matched_prefix_only=True)
    if (all_rows['aligned_positions']!=1132 or all_rows['original_target_positions']!=33
            or all_rows['original_target_distinct_generations']!=37
            or matched['original_target_positions']!=19 or matched['original_target_distinct_generations']!=26
            or sum(r['model_calls'] for r in runs)!=426
            or sum(r['known_total_tokens'] for r in runs)!=old['original_known_tokens']
            or sum(r['unknown_usage_calls'] for r in runs)!=old['original_unknown_usage_calls']):
        raise ValueError('original_full_inventory_or_target_scope_changed')
    return dict(phase='P103',status='complete',finished_at=datetime.now(timezone.utc).isoformat(),
        source_commit=head,CI=ci,research_resume=resume,plan_sha256=sha(root/PLAN),
        source_sha256=plan['source_sha256'],private_response_sha256=private_hashes,
        runs=runs,pairs=pairs,all_aligned=all_rows,matched_prior_API_prefix=matched,
        original_known_tokens=old['original_known_tokens'],original_unknown_usage_calls=old['original_unknown_usage_calls'],
        wall_seconds=time.monotonic()-began,private_reasoning_inspected_semantically=False,
        P101_intermediate_results_read=False,original_P98_results_changed=False,
        semantic_equivalence_claim=False,novel_method_claim=False,measured_savings=None,**{k:0 for k in ZERO})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--storage-root',type=Path,required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    target=root/'reports/P103_submission_components.json';failure=root/'reports/P103_submission_components_failure.json'
    if target.exists() or failure.exists():raise FileExistsError('preserve_every_P103_attempt')
    began=time.monotonic()
    def expired(*_):raise TimeoutError('finite_P103_deadline')
    signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,180)
    try:
        result=inspect(args.storage_root.resolve(),root)
        with target.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    except BaseException as error:
        with failure.open('x') as f:
            json.dump(dict(status='failed',error_type=type(error).__name__,detail=str(error)[:300],
                wall_seconds=time.monotonic()-began,**{k:0 for k in ZERO}),f,ensure_ascii=False,indent=2)
        raise
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    print(json.dumps({k:result[k] for k in ('status','all_aligned','matched_prior_API_prefix','wall_seconds')}))
