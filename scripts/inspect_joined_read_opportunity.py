"""Once-only P91 availability and syntax inspection of all closed P88 rows."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import subprocess
import time

from inspect_public_read_opportunity import read_bound, sha
from joined_public_read_views import verify_joined_implementation
from joined_read_opportunity import analyze

PLAN='configs/P91_joined_read_opportunity_v01.json'
ZERO=('model_generations','environment_api_requests','evaluator_calls','saved_code_executions',
      'task_databases_read','reserved_scenarios_read')


def inspect(storage,root):
    started=time.monotonic();plan=json.loads((root/PLAN).read_text())
    fixed=dict(phase='P91',cells=8,target_requests=4,max_wall_seconds=120,
        max_file_bytes=16777216,max_events_per_cell=4000,max_model_boundaries_per_cell=80,
        max_source_characters=20000,max_ast_nodes=5000,max_target_program_occurrences=4,
        novel_method_claim=False,measured_savings=None,**{k:0 for k in ZERO})
    if any(plan.get(k)!=v for k,v in fixed.items()):raise ValueError('fixed_P91_scope_changed')
    for name,expected in plan['source_sha256'].items():
        if sha(root/name)!=expected:raise ValueError('fixed_helper_changed: '+name)
    old=read_bound(root/plan['source_report'],plan['source_report_sha256'])
    verify_joined_implementation(storage/'.runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps/spotify')
    if len(old['rows'])!=8 or sum(len(r['analysis']['targets']) for r in old['rows'])!=4:
        raise ValueError('frozen_original_population_changed')
    rows=[]
    for source in old['rows']:
        folder=storage/'records/context_pilot'/source['run_id']
        folder.resolve().relative_to((storage/'records/context_pilot').resolve())
        if set(source['source_sha256'])!={'summary.json','usage.json','events.json','spans.json'}:
            raise ValueError('fixed_record_file_set_changed')
        values={n:read_bound(folder/n,h) for n,h in source['source_sha256'].items()}
        result=analyze(values['events.json'],values['spans.json'],values['usage.json'],source['analysis']['targets'])
        if (result['counts'].get('sent_requests',0)!=source['api_requests']
                or len(values['usage.json'])!=source['model_calls']):
            raise ValueError('original_request_or_generation_count_differs')
        rows.append({k:v for k,v in source.items() if k!='analysis'}|{'analysis':result})
    programs=[p for r in rows for p in r['analysis']['target_programs']]
    if len(programs)>4:raise ValueError('fixed_target_program_bound_exceeded')
    return dict(phase='P91',status='complete',checked_at=datetime.now(timezone.utc).isoformat(),
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        plan_sha256=sha(root/PLAN),source_report_sha256=plan['source_report_sha256'],
        source_sha256=plan['source_sha256'],rows=rows,cells=8,target_program_occurrences=len(programs),
        unique_target_program_sources=len({p['source_sha256'] for p in programs}),
        original_api_requests=sum(r['api_requests'] for r in rows),
        original_known_logical_tokens=sum(r['known_total_tokens'] for r in rows),
        original_unknown_usage_calls=sum(r['unknown_usage_calls'] for r in rows),
        wall_seconds=time.monotonic()-started,**{k:0 for k in ZERO},
        novel_method_claim=False,measured_savings=None,online_replacement_verified=False,
        interpretation='Availability precedes each request. Source syntax is not dynamic field demand or future liveness; no task outcome, avoided request or removed generation is inferred.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--storage-root',type=Path,required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    target=root/'reports/P91_joined_read_opportunity.json';failure=root/'reports/P91_joined_read_opportunity_failure.json'
    if target.exists() or failure.exists():raise FileExistsError('preserve_every_prior_P91_inspection')
    def expired(*_):raise TimeoutError('fixed_readonly_deadline')
    previous=signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,120);started=time.monotonic()
    try:
        result=inspect(args.storage_root.resolve(),root);target.write_text(json.dumps(result,indent=2)+'\n')
    except BaseException as error:
        failure.write_text(json.dumps(dict(phase='P91',status='failed_readonly_inspection',
            error_type=type(error).__name__,detail=str(error),wall_seconds=time.monotonic()-started,
            **{k:0 for k in ZERO}),indent=2)+'\n');raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
    print(json.dumps(dict(cells=8,wall_seconds=result['wall_seconds'],
        target_program_occurrences=result['target_program_occurrences'],
        unique_target_program_sources=result['unique_target_program_sources'],
        rows=[dict(run_id=r['run_id'],**r['analysis']) for r in result['rows']])) )


if __name__=='__main__':main()
