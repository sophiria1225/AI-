"""Parse the fixed P35 input manifest without replaying any saved program."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import signal
import subprocess
import time

from return_use_scope import analyze

ROOT = Path(__file__).resolve().parents[1]
PLAN = 'configs/P70_return_use_scope_v01.json'
REPORT = 'reports/P70_return_use_scope.json'
SOURCE_PATH = re.compile(r'records/context_pilot/(?:P29_0[1-4]_CODE|P33_0[1-4]_(?:FULL_KEEP|STDOUT_MASK_KEEP|STDOUT_MASK_INDEX_KEEP))/(?:programs/call_[0-9]{3}_[0-9]{2}|transfer_inventory)/input_private\.json\Z')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def validate(plan, source):
    if (plan['phase'] != 'P70' or plan['known_tasks'] != 4
            or plan['max_wall_seconds'] != 120 or plan['max_input_files'] != 181
            or plan['max_file_bytes'] != 4 * 1024 * 1024
            or plan['max_source_characters'] != 20000 or plan['max_ast_nodes'] != 5000
            or any(plan[k] != 0 for k in ('model_generations', 'environment_api_requests',
                'evaluator_calls', 'task_databases_read', 'reserved_scenarios_read', 'saved_code_executions'))
            or len(plan['rows']) != 12 or len(source['rows']) != 12
            or [r['run_id'] for r in plan['rows']] != [r['run_id'] for r in source['rows']]
            or sum(len(r['inputs']) for r in plan['rows']) != 181):
        raise ValueError('fixed_cohort_or_bounds_changed')
    for row, prior in zip(plan['rows'], source['rows'], strict=True):
        if (not prior['plain']['all_programs_match'] or not prior['instrumented']['all_programs_match']
                or row['task_id'] != prior['task_id'] or row['arm'] != prior['arm']
                or len(row['inputs']) != len(prior['plain']['programs'])):
            raise ValueError('old_replay_identity_changed')
        for item, p in zip(row['inputs'], prior['plain']['programs'], strict=True):
            known = [h for k, h in p['original_source_sha256'].items() if k.endswith('input_private.json')]
            if (len(known) != 1 or item['sha256'] != known[0]
                    or item['program'] != p['program'] or item['phase'] != p['phase']
                    or item['program_index'] != p['original_program_index']
                    or not SOURCE_PATH.fullmatch(item['path'])):
                raise ValueError('fixed_input_identity_changed')


def run(storage):
    target = ROOT / REPORT
    failure = ROOT / 'reports/P70_preflight_failure.json'
    if target.exists() or failure.exists():
        raise FileExistsError('preserve_existing_result_or_failure')
    started = time.monotonic()
    def timed_out(*_):
        raise TimeoutError('read_only_budget')
    old_handler = signal.signal(signal.SIGALRM, timed_out)
    signal.setitimer(signal.ITIMER_REAL, 120)
    try:
        plan = read(ROOT / PLAN)
        if sha(ROOT / plan['source_report']) != plan['source_report_sha256']:
            raise ValueError('old_report_hash_changed')
        validate(plan, read(ROOT / plan['source_report']))
        # Validate every byte source first. Do not run or import saved code.
        inputs = {}
        for row in plan['rows']:
            for item in row['inputs']:
                path = storage / item['path']
                path.resolve().relative_to(storage.resolve())
                if path.stat().st_size > plan['max_file_bytes']:
                    raise ValueError('input_file_size_bound')
                if sha(path) != item['sha256']:
                    raise ValueError('input_hash_changed')
                inputs[item['path']] = path
        rows = []
        for row in plan['rows']:
            programs = []
            for item in row['inputs']:
                packet = read(inputs[item['path']])
                if packet['program_index'] != item['program_index']:
                    raise ValueError('input_program_index_changed')
                try:
                    result = analyze(packet['code'])
                except ValueError as exc:
                    result = {'unsupported_reason': str(exc), 'online_replacement_verified': False}
                programs.append({k: item[k] for k in ('program', 'phase', 'program_index', 'sha256')}
                                | {'analysis': result})
            counts = Counter()
            for p in programs:
                if p['phase'] != 'control':
                    counts.update(p['analysis'].get('use_counts', {}))
            rows.append({k: row[k] for k in ('run_id', 'task_id', 'arm')} | {
                'program_occurrences': len(programs), 'control_programs': sum(p['phase'] == 'control' for p in programs),
                'unsupported_programs': sum('unsupported_reason' in p['analysis'] for p in programs),
                'agent_use_counts': dict(sorted(counts.items())),
                'direct_field_helper_syntax_candidates': sum(p['analysis'].get('direct_field_helper_syntax_candidates', 0)
                    for p in programs if p['phase'] != 'control'),
                'programs': programs})
        result = {'phase': 'P70', 'known_tasks': 4, 'cells': 12, 'program_occurrences': 181,
            'unique_input_files': len(inputs), 'selection': plan['selection'],
            'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'plan_sha256': sha(ROOT / PLAN), 'source_report_sha256': plan['source_report_sha256'],
            'checker_sha256': sha(ROOT / 'scripts/return_use_scope.py'), 'inspector_sha256': sha(Path(__file__)),
            'helper_contract_sha256': sha(ROOT / 'scripts/field_read_contract.py'),
            'wall_seconds': time.monotonic() - started, 'rows': rows,
            **{k: 0 for k in ('model_generations', 'environment_api_requests', 'evaluator_calls',
                              'task_databases_read', 'reserved_scenarios_read', 'saved_code_executions')},
            'novel_method_claim': False, 'online_replacement_verified': False, 'measured_savings': None,
            'limits': 'Syntax sites, not API requests or token savings. Current source only; no future-program liveness. '
                      'Bridge binding and arbitrary Python environment equivalence are not proved. Old outcomes retained.'}
        write(target, result)
        print(json.dumps({'report': REPORT, 'cells': len(rows), 'program_occurrences': 181,
            'unique_input_files': len(inputs), 'syntax_candidates': sum(r['direct_field_helper_syntax_candidates'] for r in rows),
            'unsupported_programs': sum(r['unsupported_programs'] for r in rows), 'wall_seconds': result['wall_seconds']}))
    except Exception as exc:
        if not failure.exists():
            write(failure, {'phase': 'P70', 'error_type': type(exc).__name__, 'wall_seconds': time.monotonic() - started,
                'model_generations': 0, 'environment_api_requests': 0, 'saved_code_executions': 0})
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    run(p.parse_args().storage_root)
