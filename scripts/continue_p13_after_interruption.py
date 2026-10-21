"""Continue the fixed P13 cohort after externally interrupted infrastructure.

Keep completed failures, preserve the incomplete attempt, and execute the
interrupted task from its initial state under a new ID. No parameter adaptation.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def interrupted_cost(trial):
    if (trial / 'summary.json').exists() or (trial / 'evaluation.json').exists():
        raise ValueError('a finished/evaluated trial cannot be replaced')
    usage = read(trial / 'usage.json')
    ids = {row['id'] for row in usage}
    pending = [p for p in sorted(trial.glob('call_*'))
               if (p / 'request.json').exists() and p.name not in ids]
    if any((p / 'response.json').exists() for p in pending):
        raise ValueError('unaccounted response needs a separate audit')
    return {'completed_calls': len(usage), 'incomplete_requests': len(pending),
            'known_total_tokens': sum(c['input_tokens'] + c['output_tokens']
                                      for c in usage if c['status'] == 'ok'),
            'recorded_unknown_usage_calls': sum(c['status'] != 'ok' for c in usage),
            'incomplete_request_usage': 'unknown; request existence alone does not prove execution',
            'source_hashes': {str(p.relative_to(trial)): sha(p) for p in
                              [trial / 'usage.json'] + [x / 'request.json' for x in pending]}}


def validate_cohort(plan, original, base):
    expected = original['run_order']
    schedule = plan['cohort']
    if len(schedule) != 4 or [r[:2] for r in schedule] != [r[:2] for r in expected]:
        raise ValueError('preserve all four tasks, arms and order')
    if schedule[:2] != expected[:2] or schedule[3] != expected[3]:
        raise ValueError('keep completed trials and the unstarted final trial')
    if schedule[2][2] != 'P13_03_FOCUS_RECOVERY01':
        raise ValueError('only the recorded interrupted trial may get a new ID')
    for row in schedule[:2]:
        if not (base / row[2] / 'summary.json').exists():
            raise ValueError('retained trial is incomplete')
        if type(read(base / row[2] / 'evaluation.json')['official_success']) is not bool:
            raise ValueError('retained trial lacks independent evaluation')
    for row in schedule[2:]:
        if (base / row[2]).exists():
            raise FileExistsError('refusing to overwrite or rerun a recovery attempt')
    return interrupted_cost(base / expected[2][2])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    storage = args.storage_root.resolve()
    plan = read(args.plan)
    source = storage / plan['frozen_worktree']
    sys.path.insert(0, str(source / 'scripts'))
    from run_native_batch import check_frozen, public_body, publish
    from watch_context_pilot import collect
    from run_context_comparison import write_json
    check_frozen(read(source / plan['freeze_record']))
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    if commit != plan['source_commit']:
        raise ValueError('frozen executor checkout changed')
    original_path = source / 'configs/P13_native_focus_v01.json'
    original = read(original_path)
    base = storage / 'records/context_pilot'
    interrupted = validate_cohort(plan, original, base)
    if sha(storage / plan['interruption_report']) != plan['interruption_report_sha256']:
        raise ValueError('interruption record changed')
    runtime = read(storage / '.runtime/model_server.json')
    if runtime['record_directory'] != plan['server_record'] or runtime['status'] != 'ready':
        raise ValueError('unexpected server generation')
    with urllib.request.urlopen(original['model']['base_url'] + '/slots', timeout=10) as r:
        if any(row['is_processing'] for row in json.load(r)):
            raise ValueError('another inference is active')
    remaining = (datetime.datetime.fromisoformat(plan['server_lease_end_utc']) -
                 datetime.datetime.now(datetime.timezone.utc)).total_seconds()
    if remaining < 2 * original['max_wall_seconds'] + 3 * 180:
        raise ValueError('insufficient bounded server lease')
    out = base / 'P13_recovery_v01'
    out.mkdir(exist_ok=False)
    observer = out / 'observer'; observer.mkdir()
    write_json(out / 'plan.json', plan)
    write_json(out / 'interrupted_attempt.json', interrupted)
    (out / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    previous = read(base / 'P13_batch_v01/status.json')
    state = {'phase': 'P13', 'status': 'running', 'active': None,
             'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'supervisor_pid': os.getpid(), 'completed': [],
             'comment_id': previous['comment_id'], 'comment_url': previous['comment_url'],
             'original_plan_sha256': sha(original_path), 'source_commit': commit}
    last_publish = 0

    def update(force=False):
        nonlocal last_publish
        rows = collect(storage, plan['cohort'], observer)
        for row, (_, _, run_id) in zip(rows, plan['cohort'], strict=True):
            folder = base / run_id
            p = folder / 'summary.json'
            if not p.exists(): p = folder / 'progress.json'
            if p.exists(): row['api_requests'] = read(p).get('api_requests', 0)
        state['rows'] = rows
        state['updated_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        body = public_body(rows, state)
        body += ('\nRecovery after confirmed process loss: tasks 1 and 2 retain their original '
                 'outcomes. Task 3 restarts from its initial state as P13_03_FOCUS_RECOVERY01; '
                 'task 4 was never started. This is not an exact checkpoint resume.\n'
                 'The interrupted task-3 attempt is preserved separately: '
                 f"{interrupted['completed_calls']} recorded calls, "
                 f"{interrupted['known_total_tokens']:,} known tokens plus "
                 f"{interrupted['incomplete_requests']} incomplete request with unknown usage. "
                 'These costs remain part of total research expenditure.\n')
        (out / 'progress.md').write_text(body)
        if args.publish and (force or time.monotonic() - last_publish > 300):
            try:
                publish(body, state)
                state.pop('publish_error', None)
            except (ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
                state['publish_error'] = type(error).__name__
            last_publish = time.monotonic()
        write_json(out / 'status.json', state)

    child = None
    try:
        update(True)
        for task, arm, name in plan['cohort'][2:]:
            check_frozen(read(source / plan['freeze_record']))
            state['active'] = name
            command = [sys.executable, str(source / 'scripts/run_native_generated.py'),
                       '--plan', str(original_path), '--task-id', task, '--run-id', name,
                       '--storage-root', str(storage), '--appworld-root',
                       str(storage / '.runtime/appworld/r18_probe_01'), '--appworld-python',
                       str(storage / '.runtime/appworld/venv/bin/python')]
            with (out / (name + '.log')).open('w') as log:
                child = subprocess.Popen(command, cwd=source, stdout=log, stderr=subprocess.STDOUT)
                state['child_pid'] = child.pid
                update(True)
                while child.poll() is None:
                    update()
                    time.sleep(30)
            state['completed'].append({'run_id': name, 'exit_code': child.returncode})
            update(True)
            if child.returncode:
                raise RuntimeError('recovery trial failed; no further automatic retry')
        state['status'] = 'complete'
    except Exception as error:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=10)
        state.update(status='runtime_error', error_type=type(error).__name__)
        write_json(out / 'error_private.json', {'type': type(error).__name__, 'message': str(error)})
    finally:
        state.update(active=None, finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        update(True)
    return 0 if state['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
