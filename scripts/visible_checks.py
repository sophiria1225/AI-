"""Run each configured visible check as an argv, recording its own exit status.

This does not infer the success of arbitrary shell sequences emitted by a model.
Checks are selected from public task/source information, never hidden evaluation.
"""
import hashlib
import json
from pathlib import Path
import time

from run_e0_pilot import TASK_ENV


def run_checks(container, checks, out, remaining_wall):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    results = []
    started = time.monotonic()
    for index, check in enumerate(checks):
        argv = check['argv']
        if not argv or not all(isinstance(a, str) and '\x00' not in a for a in argv):
            raise ValueError('check argv must be a nonempty list of strings')
        if Path(argv[0]).name in {'bash', 'sh', 'zsh', 'dash', 'fish'}:
            raise ValueError('visible checks require direct argv, not shell scripts')
        left = remaining_wall - (time.monotonic() - started)
        item = {'id': check['id'], 'argv': argv, 'status': 'not_run', 'exit_code': None}
        if left < 1:
            item['reason'] = 'wall_budget_exhausted'
        else:
            timeout = max(1, min(int(left), int(check.get('timeout_seconds', 120))))
            item.update(timeout_seconds=timeout, started_monotonic=time.monotonic())
            command = ['timeout', '--signal=TERM', '--kill-after=2s', str(timeout), *argv]
            try:
                execution = container.exec_run(command, workdir='/testbed', environment=TASK_ENV)
                raw = execution.output
                filename = f'{index:03d}.log'
                (out / filename).write_bytes(raw)
                code = execution.exit_code
                item.update(exit_code=code, status='passed' if code == 0 else
                            'timeout' if code in (124, 137) else 'failed' if code is not None else 'unknown',
                            log=filename, log_sha256=hashlib.sha256(raw).hexdigest(),
                            output_bytes=len(raw), output_tail=raw.decode(errors='replace')[-2000:])
            except Exception as error:
                item.update(status='infrastructure_error', error=repr(error))
            item['wall_seconds'] = time.monotonic() - item.pop('started_monotonic')
        results.append(item)
        (out / 'checks.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
    return {'checks': results, 'all_passed': bool(results) and all(r['status'] == 'passed' for r in results),
            'wall_seconds': time.monotonic() - started}
