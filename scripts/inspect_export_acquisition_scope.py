"""Bounded read-only analysis of all five declared known CSV records."""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time

from export_acquisition_scope import analyze
from inspect_public_export_scope import usage_for_cost
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

PLAN = 'configs/P69_export_acquisition_scope_v01.json'
RUNS = ['P18_04_ROLES', 'P25_04_GUIDED', 'P29_04_CODE',
        'P68_01_EXPORT_NATIVE', 'P68_02_EXPORT_CONTROLLED']
FILES = {'public_task.json', 'events.json', 'spans.json', 'usage.json', 'summary.json'}


def bounded_read(path, expected):
    if path.stat().st_size > 16777216:
        raise ValueError('fixed source file bound exceeded')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('fixed public source changed: ' + path.name)
    return json.loads(raw)


def inspect(storage):
    began = time.monotonic(); plan = read(ROOT / PLAN)
    fixed = {'phase': 'P69', 'task_id': '6104387_1', 'run_ids': RUNS, 'max_wall_seconds': 120,
        'max_events_per_record': 4000, 'max_model_boundaries': 80, 'max_song_ids': 512,
        'max_file_bytes': 16777216, 'model_generations': 0, 'environment_api_requests': 0,
        'evaluator_calls': 0, 'task_databases_read': 0, 'reserved_scenarios_read': 0, 'novel_method_claim': False}
    if any(plan.get(k) != v for k, v in fixed.items()):
        raise ValueError('fixed P69 scope changed')
    if set(plan['source_files']) != set(RUNS) or any(set(v) != FILES for v in plan['source_files'].values()):
        raise ValueError('only the fixed five public file sets may be read')
    for path, expected in {**plan['audit_reports'], **plan['helper_sha256']}.items():
        if sha(ROOT / path) != expected:
            raise ValueError('closed audit/helper changed: ' + path)
    for app, expected in plan['public_api_implementation_sha256'].items():
        p = storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps' / app / 'apis.py'
        if sha(p) != expected:
            raise ValueError('public API implementation changed')
    fresh = read(ROOT / 'reports/P68_completion_audit.json')
    if fresh['audit_errors'] or not fresh['server_stopped'] or fresh['owned_server_processes_present']:
        raise ValueError('P68 must be closed and reconciled')
    rows = []
    for rid in RUNS:
        source = plan['source_files'][rid]
        values = {name: bounded_read(storage / 'records/context_pilot' / rid / name, source[name]) for name in sorted(FILES)}
        task = values['public_task.json']
        if values['summary.json']['task_id'] != plan['task_id']:
            raise ValueError('different known task')
        if rid.startswith('P68_'):
            old = next(r for r in fresh['rows'] if r['run_id'] == rid)
            if old['status'] != 'evaluated':
                raise ValueError('retain the declared evaluated P68 rows')
            hashes = old['source_sha256']; official = old['official_success']; unknown = old['unknown_usage_calls']
        else:
            old = read(ROOT / ('reports/' + rid + '_execution_audit.json'))
            if old['audit_errors'] or old['task_id'] != plan['task_id']:
                raise ValueError('closed original execution audit required')
            hashes = old['source_hashes']; official = old['evaluation']['official_success']; unknown = old['unknown_usage_calls']
        for name in ('events', 'spans', 'usage', 'summary'):
            if source[name + '.json'] != hashes.get(name, hashes.get(name + '.json')):
                raise ValueError('record differs from its original audit')
        usage = usage_for_cost(values['usage.json'], unknown)
        result = analyze(task, values['spans.json'], values['events.json'], usage)
        result.update(run_id=rid, original_official_success=official, source_sha256=source)
        rows.append(result)
    return {'phase': 'P69', 'known_tasks': 1, 'records': len(rows), 'selection': plan['selection'],
        'git_commit': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
            check=True, capture_output=True, text=True).stdout.strip(),
        'rows': rows, 'plan_sha256': sha(ROOT / PLAN), 'inspector_sha256': sha(Path(__file__)),
        'checker_sha256': sha(ROOT / 'scripts/export_acquisition_scope.py'),
        'public_api_implementation_sha256': plan['public_api_implementation_sha256'],
        'audit_reports': plan['audit_reports'], 'helper_sha256': plan['helper_sha256'],
        'wall_seconds': time.monotonic() - began,
        'model_generations': 0, 'environment_api_requests': 0, 'evaluator_calls': 0,
        'task_databases_read': 0, 'reserved_scenarios_read': 0, 'novel_method_claim': False,
        'online_cache_installed': False, 'measured_savings': None,
        'limits': 'Known output columns and trusted API meanings; full-response equality is posthoc, not an online oracle. No generation is established removable. No P25/P68 causal attribution.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True); a = p.parse_args()
    target = ROOT / 'reports/P69_export_acquisition_scope.json'
    if target.exists():
        raise FileExistsError('preserve the original inspection')
    def timeout(*_):
        raise TimeoutError('fixed 120-second read-only budget')
    old_signal = signal.getsignal(signal.SIGALRM); signal.signal(signal.SIGALRM, timeout); signal.alarm(120)
    try:
        result = inspect(a.storage_root)
    except Exception as error:
        failure = ROOT / 'reports/P69_preflight_failure.json'
        if not failure.exists():
            write_json(failure, {'phase': 'P69', 'status': 'failed_readonly_inspection',
                'exception': type(error).__name__, 'detail': str(error), 'model_generations': 0,
                'environment_api_requests': 0, 'evaluator_calls': 0, 'reserved_scenarios_read': 0})
        raise
    finally:
        signal.alarm(0); signal.signal(signal.SIGALRM, old_signal)
    write_json(target, result)
    print([{k: r[k] for k in ('run_id', 'show_song_requests', 'task_fields_preknown_requests',
        'same_request_response_preknown_requests', 'preknown_task_fields_without_equal_complete_object')}
        for r in result['rows']])
