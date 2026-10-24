"""Once-only P96 comparison of historical observations under three query keys."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import subprocess
import time

from auth_origin_observations import analyze, AUTH_READS, MODES
from field_read_contract import READ_ONLY_APIS
from inspect_recorded_request_repetition import read_bound, sha

PLAN = 'configs/P96_auth_origin_observations_v01.json'


def inspect(storage, root, journal):
    start = time.monotonic(); plan = json.loads((root/PLAN).read_text())
    fixed = dict(phase='P96', max_wall_seconds=120, max_cells=8, max_file_bytes=16777216,
        max_events_per_cell=4000, max_model_boundaries_per_cell=80, max_entries=512,
        max_value_bytes=65536, fixed_candidate_streak=2, modes=list(MODES),
        auth_read_apis=sorted(AUTH_READS), read_scope_apis=sorted(READ_ONLY_APIS),
        expected_original_requests=399, expected_original_model_calls=150,
        expected_original_known_tokens=1689160, expected_original_unknown_calls=1,
        model_generations=0, environment_api_requests=0, evaluator_calls=0,
        saved_code_executions=0, task_databases_read=0, reserved_scenarios_read=0,
        novel_method_claim=False, online_interventions=0, measured_savings=None)
    if (any(plan.get(k)!=v for k,v in fixed.items()) or len(plan['rows'])!=8
            or not plan['source_sha256'] or not plan['public_runtime_sha256']):
        raise ValueError('fixed_P96_scope_changed')
    for rel, expected in plan['source_sha256'].items():
        if sha(root/rel)!=expected: raise ValueError('fixed_public_dependency_changed:'+rel)
    for rel, expected in plan['public_runtime_sha256'].items():
        if sha(storage/rel)!=expected: raise ValueError('fixed_public_runtime_changed:'+rel)
    audit = read_bound(root/plan['source_report'], plan['source_report_sha256'])
    if (audit['status']!='complete' or len(audit['rows'])!=8
            or audit['source_commit']!='f53098db125cdbabd2687821e086925684f0e2d1'
            or audit['original_api_requests']!=399 or audit['original_model_calls']!=150):
        raise ValueError('closed_complete_P95_required')
    journal['planned_run_ids'] = [r['run_id'] for r in plan['rows']]
    for source, original in zip(plan['rows'], audit['rows'], strict=True):
        journal['current_run_id'] = source['run_id']
        if any(original.get(k)!=v for k,v in source.items()):
            raise ValueError('original_cohort_or_bindings_changed')
        if set(source['source_sha256'])!={'summary.json','usage.json','events.json','spans.json'}:
            raise ValueError('complete_fixed_record_files_required')
        folder = storage/'records/context_pilot'/source['run_id']
        folder.resolve().relative_to((storage/'records/context_pilot').resolve())
        values = {name:read_bound(folder/name,h) for name,h in source['source_sha256'].items()}
        result = analyze(values['events.json'], values['spans.json'], values['usage.json'],
                         original['analysis']['requests'], max_entries=plan['max_entries'],
                         max_value_bytes=plan['max_value_bytes'])
        if (len(result['requests'])!=source['api_requests']
                or len(result['model_boundaries'])!=source['model_calls']):
            raise ValueError('complete_original_counts_required')
        journal['rows'].append({**source, 'analysis': result})
    rows=journal['rows']
    totals=dict(original_api_requests=sum(r['api_requests'] for r in rows),
                original_model_calls=sum(r['model_calls'] for r in rows),
                original_known_logical_tokens=sum(r['known_total_tokens'] for r in rows),
                original_unknown_usage_calls=sum(r['unknown_usage_calls'] for r in rows))
    if tuple(totals.values())!=(399,150,1689160,1):
        raise ValueError('original_totals_changed')
    return dict(phase='P96', status='complete', checked_at=datetime.now(timezone.utc).isoformat(),
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        plan_sha256=sha(root/PLAN), source_report_sha256=plan['source_report_sha256'],
        source_sha256=plan['source_sha256'], public_runtime_sha256=plan['public_runtime_sha256'],
        rows=rows, cells=8, **totals, wall_seconds=time.monotonic()-start,
        **{k:fixed[k] for k in ('model_generations','environment_api_requests','evaluator_calls',
            'saved_code_executions','task_databases_read','reserved_scenarios_read',
            'novel_method_claim','online_interventions','measured_savings')},
        interpretation='All prior outcomes retained. Login-request origin is a historical grouping only; not current authorization, safe substitution, progress, removable generation or task improvement. Threshold fixed before this analysis.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root',type=Path,required=True)
    args=parser.parse_args(); root=Path(__file__).resolve().parents[1]
    target=root/'reports/P96_auth_origin_observations.json'
    failure=root/'reports/P96_auth_origin_observations_failure.json'
    if target.exists() or failure.exists():raise FileExistsError('preserve_every_P96_attempt')
    def expired(*_):raise TimeoutError('fixed_readonly_deadline')
    previous=signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,120)
    started=time.monotonic();journal={'rows':[],'planned_run_ids':[],'current_run_id':None}
    try:
        result=inspect(args.storage_root.resolve(),root,journal)
        target.write_text(json.dumps(result,indent=2)+'\n')
    except BaseException as error:
        failure.write_text(json.dumps(dict(phase='P96',status='failed_readonly_inventory',
            error_type=type(error).__name__,detail=str(error),wall_seconds=time.monotonic()-started,
            completed_rows=journal['rows'],planned_run_ids=journal['planned_run_ids'],
            current_run_id=journal['current_run_id'],model_generations=0,
            environment_api_requests=0,evaluator_calls=0,saved_code_executions=0),indent=2)+'\n')
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
    counts=[]
    for row in result['rows']:
        analysis=row['analysis']
        modes={m:dict(
            equal_read_receipts=sum(q.get(m,{}).get('value_equal') is True for q in analysis['requests']),
            qualifying_boundaries=sum(q[m]['all_reads_reobserved_with_only_repeated_logins'] for q in analysis['model_boundaries']),
            fixed_two_boundary_candidates=sum(q[m]['fixed_two_boundary_candidate'] for q in analysis['model_boundaries']))
            for m in MODES}
        counts.append(dict(run_id=row['run_id'],modes=modes))
    print(json.dumps(dict(cells=result['cells'],requests=result['original_api_requests'],
                         wall_seconds=result['wall_seconds'],counts=counts)))


if __name__=='__main__':main()
