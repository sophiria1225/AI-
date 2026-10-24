"""Once-only P95 inventory of all requests in the eight closed P88 records."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time

from field_read_contract import READ_ONLY_APIS, verify_public_implementation
from recorded_request_repetition import analyze

PLAN='configs/P95_recorded_request_repetition_v01.json'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def read_bound(path,expected):
    if path.stat().st_size>16777216 or sha(path)!=expected:
        raise ValueError('fixed_input_changed_or_oversized')
    return json.loads(path.read_text())


def inspect(storage,root,journal):
    start=time.monotonic();plan=json.loads((root/PLAN).read_text())
    fixed=dict(phase='P95',max_wall_seconds=120,max_cells=8,max_file_bytes=16777216,
        max_events_per_cell=4000,max_model_boundaries_per_cell=80,max_cache_entries=512,
        max_value_bytes=65536,expected_original_requests=399,expected_original_model_calls=150,
        expected_original_known_tokens=1689160,expected_original_unknown_calls=1,
        read_scope_apis=sorted(READ_ONLY_APIS),model_generations=0,environment_api_requests=0,
        evaluator_calls=0,saved_code_executions=0,task_databases_read=0,reserved_scenarios_read=0,
        novel_method_claim=False,measured_savings=None)
    if any(plan.get(k)!=v for k,v in fixed.items()) or len(plan['rows'])!=8 or not plan['source_sha256']:
        raise ValueError('fixed_P95_scope_changed')
    for rel,expected in plan['source_sha256'].items():
        if sha(root/rel)!=expected:raise ValueError('fixed_helper_changed:'+rel)
    audit=read_bound(root/plan['source_report'],plan['source_report_sha256'])
    if (audit['batch_status']!='complete' or audit['audit_errors']
            or not audit['owned_processes_absent'] or len(audit['rows'])!=8):
        raise ValueError('closed_complete_P88_required')
    verify_public_implementation(storage/'.runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps/spotify')
    journal['planned_run_ids']=[r['run_id'] for r in plan['rows']]
    for source,original in zip(plan['rows'],audit['rows'],strict=True):
        journal['current_run_id']=source['run_id']
        for key in ('run_id','task_id','reasoning_policy','record_status','success','model_calls',
                    'known_total_tokens','unknown_usage_calls','api_requests'):
            if source[key]!=original[key]:raise ValueError('original_cohort_or_outcome_changed')
        if (set(source['source_sha256'])!={'summary.json','usage.json','events.json','spans.json'}
                or source['source_sha256']['summary.json']!=original['summary_sha256']
                or source['source_sha256']['usage.json']!=original['usage_sha256']):
            raise ValueError('original_private_bindings_changed')
        folder=storage/'records/context_pilot'/source['run_id']
        folder.resolve().relative_to((storage/'records/context_pilot').resolve())
        values={name:read_bound(folder/name,expected) for name,expected in source['source_sha256'].items()}
        result=analyze(values['events.json'],values['spans.json'],values['usage.json'],
            max_cache_entries=plan['max_cache_entries'],max_value_bytes=plan['max_value_bytes'])
        if (result['counts']['sent_requests']!=source['api_requests']
                or len(values['usage.json'])!=source['model_calls']
                or len(result['requests'])!=source['api_requests']):
            raise ValueError('source_count_changed')
        journal['rows'].append({**source,'analysis':result})
    rows=journal['rows']; totals=dict(
        original_api_requests=sum(r['api_requests'] for r in rows),
        original_model_calls=sum(r['model_calls'] for r in rows),
        original_known_logical_tokens=sum(r['known_total_tokens'] for r in rows),
        original_unknown_usage_calls=sum(r['unknown_usage_calls'] for r in rows))
    if tuple(totals.values())!=(399,150,1689160,1):raise ValueError('full_original_totals_changed')
    return dict(phase='P95',status='complete',checked_at=datetime.now(timezone.utc).isoformat(),
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        plan_sha256=sha(root/PLAN),source_report_sha256=plan['source_report_sha256'],
        source_sha256=plan['source_sha256'],rows=rows,cells=8,**totals,wall_seconds=time.monotonic()-start,
        **{k:fixed[k] for k in ('model_generations','environment_api_requests','evaluator_calls',
            'saved_code_executions','task_databases_read','reserved_scenarios_read','novel_method_claim','measured_savings')},
        interpretation='Every P88 request retained. Equality is descriptive; cache scope is unchanged and no login exemption, state equivalence, cache replacement, removable generation or task improvement is established.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--storage-root',type=Path,required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    target=root/'reports/P95_recorded_request_repetition.json';failure=root/'reports/P95_recorded_request_repetition_failure.json'
    if target.exists() or failure.exists():raise FileExistsError('preserve_every_P95_attempt')
    def expired(*_):raise TimeoutError('fixed_readonly_deadline')
    previous=signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,120)
    started=time.monotonic();journal={'rows':[],'planned_run_ids':[],'current_run_id':None}
    try:
        result=inspect(args.storage_root.resolve(),root,journal)
        target.write_text(json.dumps(result,indent=2)+'\n')
    except BaseException as error:
        failure.write_text(json.dumps(dict(phase='P95',status='failed_readonly_inventory',
            error_type=type(error).__name__,detail=str(error),wall_seconds=time.monotonic()-started,
            completed_rows=journal['rows'],planned_run_ids=journal['planned_run_ids'],current_run_id=journal['current_run_id'],
            model_generations=0,environment_api_requests=0,evaluator_calls=0,saved_code_executions=0),indent=2)+'\n')
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
    print(json.dumps(dict(cells=result['cells'],requests=result['original_api_requests'],wall_seconds=result['wall_seconds'],
        counts=[{'run_id':r['run_id'],**r['analysis']['counts']} for r in result['rows']])))


if __name__=='__main__':main()
