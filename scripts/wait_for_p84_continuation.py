"""One finite wait, one decision, then exec the already fixed P84 pipeline.

The process is replaced so the existing pipeline owns signal handling and cleanup.
There is no retry, threshold search, background child, or experiment extension.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from p84_continuation_guard import P82_COMMIT, P84_COMMIT, bind_closed_evidence
from run_api_error_pipeline import checked_ci
from run_handoff_factors import ROOT

STOP_NAMES = ('P82.stop', 'P82_reports.stop', 'P84.stop', 'P84_continuation.stop')


def read_pending(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        # The older producer writes status in place. A partial JSON snapshot is
        # not a failed experiment and never authorizes an allocation.
        return None


def run(storage, p82_root, closure_root, p84_root, expected_commit):
    status_path = storage / '.runtime/P84_continuation_status.json'
    state = {'status': 'waiting', 'automatic_retries': 0, 'model_allocated_by_waiter': False,
             'wait_limit_seconds': 72000, 'started_at': datetime.now(timezone.utc).isoformat()}
    began = time.monotonic()
    stop = False
    def interrupt(*_):
        nonlocal stop
        stop = True
    def check_stop():
        if stop or any((storage / '.runtime' / name).exists() for name in STOP_NAMES):
            raise InterruptedError('explicit_continuation_stop')
    def save():
        state['elapsed_seconds'] = time.monotonic() - began
        temporary = status_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(status_path)
    def fixed_tree(root, commit, clean=True):
        actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True, timeout=30).strip()
        dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True, timeout=30).strip()
        if actual != commit or (clean and dirty):
            raise ValueError('fixed_worktree_changed:' + str(root))
    with (storage / '.runtime/P84_continuation.lock').open('x') as handle:
        handle.write(str(os.getpid()))
    previous_handlers = {sig: signal.signal(sig, interrupt) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        check_stop()
        fixed_tree(ROOT, expected_commit)
        state['controller_commit'] = expected_commit
        def ci_expired(*_):
            raise TimeoutError('controller_CI_check_expired')
        previous_alarm = signal.signal(signal.SIGALRM, ci_expired)
        signal.alarm(60)
        try:
            state['controller_ci'] = checked_ci(ROOT, expected_commit)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous_alarm)
        fixed_tree(p82_root, P82_COMMIT, clean=False)
        fixed_tree(p84_root, P84_COMMIT)
        save()
        while True:
            check_stop()
            if time.monotonic() - began > 72000:
                raise TimeoutError('finite_P82_closure_wait_expired')
            pipeline = read_pending(storage / 'records/context_pilot/P82_pipeline_v01/status.json')
            closure = read_pending(storage / '.runtime/P82_closure_status.json')
            if pipeline and pipeline.get('finished_at') and pipeline.get('status') != 'complete':
                raise ValueError('P82_stopped_no_auto_continuation')
            if closure and closure.get('status') == 'stopped':
                raise ValueError('P82_closure_failed_no_auto_continuation')
            if (pipeline and closure and pipeline.get('finished_at')
                    and pipeline.get('status') == closure.get('status') == 'complete'):
                break
            time.sleep(2)
        fixed_tree(ROOT, expected_commit)
        fixed_tree(p84_root, P84_COMMIT)
        decision = bind_closed_evidence(storage, p82_root, closure_root, p84_root)
        check_stop()
        decision['checked_at'] = datetime.now(timezone.utc).isoformat()
        with (storage / '.runtime/P84_execution_decision.json').open('x') as handle:
            json.dump(decision, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        state.update(status='handed_to_fixed_pipeline', decision=decision)
        save()
        check_stop()
        os.chdir(p84_root)
        os.execv(sys.executable, [sys.executable, str(p84_root / 'scripts/run_fallback_output_pipeline.py'),
            '--storage-root', str(storage), '--expected-commit', P84_COMMIT])
    except Exception as error:
        state.update(status='stopped', error_type=type(error).__name__, error=str(error),
                     finished_at=datetime.now(timezone.utc).isoformat())
        save()
        print({'status': state['status'], 'error_type': state['error_type']}, flush=True)
        return 1
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('storage-root', 'p82-root', 'closure-root', 'p84-root'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expected-commit', required=True)
    a = parser.parse_args()
    raise SystemExit(run(a.storage_root.resolve(), a.p82_root.resolve(), a.closure_root.resolve(),
                         a.p84_root.resolve(), a.expected_commit))
