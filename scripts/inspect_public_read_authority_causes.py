"""One-time bounded P90 historical-cause diagnostic of the closed P89 targets."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import subprocess
import time

from field_read_contract import verify_public_implementation
from inspect_public_read_opportunity import read_bound, sha
from public_read_authority_causes import analyze

PLAN = 'configs/P90_public_read_authority_causes_v01.json'
ZERO = ('model_generations', 'environment_api_requests', 'evaluator_calls',
        'saved_code_executions', 'task_databases_read', 'reserved_scenarios_read')


def inspect(storage, root):
    started = time.monotonic()
    plan = json.loads((root / PLAN).read_text())
    if (plan['phase'] != 'P90' or plan['max_wall_seconds'] != 120
            or plan['max_file_bytes'] != 16777216 or plan['max_historical_records_per_cell'] != 8192
            or plan['cells'] != 8 or plan['target_requests'] != 4
            or any(plan[k] != 0 for k in ZERO) or plan['new_authorities_granted'] != 0):
        raise ValueError('fixed_P90_scope_changed')
    for name, expected in plan['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('fixed_helper_changed: ' + name)
    old = read_bound(root / plan['source_report'], plan['source_report_sha256'])
    verify_public_implementation(storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps/spotify')
    if len(old['rows']) != 8 or sum(len(r['analysis']['targets']) for r in old['rows']) != 4:
        raise ValueError('frozen_P89_population_changed')
    rows = []
    for source in old['rows']:
        folder = storage / 'records/context_pilot' / source['run_id']
        folder.resolve().relative_to((storage / 'records/context_pilot').resolve())
        values = {name:read_bound(folder / name, expected)
                  for name, expected in source['source_sha256'].items()}
        result = analyze(values['events.json'], values['spans.json'], values['usage.json'],
                         source['analysis']['targets'])
        if (result['counts'].get('sent_requests', 0) != source['api_requests']
                or len(values['usage.json']) != source['model_calls']):
            raise ValueError('original_request_or_generation_count_differs')
        rows.append({k:v for k,v in source.items() if k != 'analysis'} | {'analysis':result})
    return dict(phase='P90', status='complete', checked_at=datetime.now(timezone.utc).isoformat(),
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        plan_sha256=sha(root / PLAN), source_report_sha256=plan['source_report_sha256'],
        source_sha256=plan['source_sha256'], rows=rows, cells=8,
        original_api_requests=sum(r['api_requests'] for r in rows),
        original_known_logical_tokens=sum(r['known_total_tokens'] for r in rows),
        original_unknown_usage_calls=sum(r['unknown_usage_calls'] for r in rows),
        wall_seconds=time.monotonic()-started, **{k:0 for k in ZERO},
        new_authorities_granted=0, measured_savings=None, novel_method_claim=False,
        interpretation='Prior observations and intervening invalidations only. Historical agreement cannot grant reuse. No new API-effect exemption, field-demand inference, or task-quality result.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = root / 'reports/P90_public_read_authority_causes.json'
    failure = root / 'reports/P90_public_read_authority_causes_failure.json'
    if target.exists() or failure.exists():
        raise FileExistsError('preserve_every_prior_P90_inspection')
    def expired(*_): raise TimeoutError('fixed_readonly_deadline')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 120)
    started = time.monotonic()
    try:
        result = inspect(args.storage_root.resolve(), root)
        target.write_text(json.dumps(result, indent=2)+'\n')
    except BaseException as error:
        failure.write_text(json.dumps(dict(phase='P90', status='failed_readonly_inspection',
            error_type=type(error).__name__, detail=str(error), wall_seconds=time.monotonic()-started,
            **{k:0 for k in ZERO}), indent=2)+'\n')
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    print(json.dumps({'cells':result['cells'],'wall_seconds':result['wall_seconds'],
        'rows':[dict(run_id=r['run_id'], counts=r['analysis']['counts'],
                     targets=r['analysis']['targets']) for r in result['rows']]}))


if __name__ == '__main__':main()
