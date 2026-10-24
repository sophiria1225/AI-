"""Once-only P89 read-only inspection of all eight closed P88 conditions."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time

from field_read_contract import verify_public_implementation
from public_read_opportunity import analyze

PLAN = 'configs/P89_public_read_opportunity_v01.json'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_bound(path, expected):
    if Path(path).stat().st_size > 16777216:
        raise ValueError('fixed_file_bound_exceeded')
    if sha(path) != expected:
        raise ValueError('fixed_source_changed')
    return json.loads(Path(path).read_text())


def inspect(storage, root):
    started = time.monotonic()
    plan = json.loads((root / PLAN).read_text())
    fixed = dict(phase='P89', max_wall_seconds=120, max_cells=8,
        max_file_bytes=16777216, max_events_per_cell=4000, max_model_boundaries_per_cell=80,
        max_sources_per_cell=512, model_generations=0, environment_api_requests=0,
        evaluator_calls=0, saved_code_executions=0, task_databases_read=0,
        reserved_scenarios_read=0, novel_method_claim=False, measured_savings=None)
    if (any(plan.get(k) != v for k, v in fixed.items()) or len(plan['rows']) != 8
            or not plan['source_sha256']):
        raise ValueError('fixed_P89_bounds_changed')
    report = read_bound(root / plan['source_report'], plan['source_report_sha256'])
    if (report['batch_status'] != 'complete' or report['audit_errors']
            or not report['owned_processes_absent'] or len(report['rows']) != 8):
        raise ValueError('closed_P88_audit_required')
    for name, expected in plan['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('fixed_helper_changed: ' + name)
    verify_public_implementation(storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps/spotify')
    rows = []
    for source, original in zip(plan['rows'], report['rows'], strict=True):
        for key in ('run_id', 'task_id', 'reasoning_policy', 'record_status', 'success',
                    'model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests'):
            if source[key] != original[key]:
                raise ValueError('original_cohort_or_outcome_changed')
        if (source['source_sha256']['summary.json'] != original['summary_sha256']
                or source['source_sha256']['usage.json'] != original['usage_sha256']
                or set(source['source_sha256']) != {'summary.json', 'usage.json', 'events.json', 'spans.json'}):
            raise ValueError('original_usage_or_summary_changed')
        folder = storage / 'records/context_pilot' / source['run_id']
        folder.resolve().relative_to((storage / 'records/context_pilot').resolve())
        values = {name:read_bound(folder / name, expected)
                  for name, expected in source['source_sha256'].items()}
        result = analyze(values['events.json'], values['spans.json'], values['usage.json'],
                         execution_scope='closed:' + source['run_id'])
        if (result['counts'].get('sent_requests', 0) != source['api_requests']
                or len(values['usage.json']) != source['model_calls']):
            raise ValueError('original_request_or_generation_count_differs')
        rows.append({**source, 'analysis':result})
    return dict(phase='P89', checked_at=datetime.now(timezone.utc).isoformat(),
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        plan_sha256=sha(root / PLAN), source_report_sha256=plan['source_report_sha256'],
        source_sha256=plan['source_sha256'], rows=rows, cells=8,
        original_api_requests=sum(r['api_requests'] for r in rows),
        original_known_logical_tokens=sum(r['known_total_tokens'] for r in rows),
        original_unknown_usage_calls=sum(r['unknown_usage_calls'] for r in rows),
        wall_seconds=time.monotonic()-started,
        **{k:fixed[k] for k in ('model_generations','environment_api_requests','evaluator_calls',
            'saved_code_executions','task_databases_read','reserved_scenarios_read','novel_method_claim',
            'measured_savings')},
        interpretation='Availability before requests only. No Python field demand, alias liveness, avoided API, removable generation or task-quality change inferred.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root',type=Path,required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = root / 'reports/P89_public_read_opportunity.json'
    failure = root / 'reports/P89_public_read_opportunity_failure.json'
    if target.exists() or failure.exists():
        raise FileExistsError('preserve_every_prior_P89_inspection')
    def expired(*_): raise TimeoutError('fixed_readonly_deadline')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL,120)
    started = time.monotonic()
    try:
        result = inspect(args.storage_root.resolve(),root)
        target.write_text(json.dumps(result,indent=2)+'\n')
    except BaseException as error:
        failure.write_text(json.dumps(dict(phase='P89',status='failed_readonly_inspection',
            error_type=type(error).__name__,detail=str(error),wall_seconds=time.monotonic()-started,
            model_generations=0,environment_api_requests=0,saved_code_executions=0),indent=2)+'\n')
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous)
    print(json.dumps({'cells':result['cells'],'original_api_requests':result['original_api_requests'],
        'wall_seconds':result['wall_seconds'],'availability':[
            {'run_id':r['run_id'],'counts':r['analysis']['counts']} for r in result['rows']]}))


if __name__=='__main__':main()
