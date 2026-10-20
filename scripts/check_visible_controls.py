"""Real container controls for separate success/failure/timeout records."""
import datetime
import hashlib
import json
from pathlib import Path
import docker

from container_policy import create_task_container
from run_e0_pilot import tool_command, verify_task_environment
from visible_checks import run_checks

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = json.loads((ROOT / 'configs/P1_small_15380.json').read_text())
    out = ROOT / 'records/p2_controls' / datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    out.mkdir(parents=True)
    client = docker.from_env(timeout=60)
    container = create_task_container(client, config['image'], 'harness_visible_controls')
    try:
        container.start()
        environment = verify_task_environment(container)
        (out / 'masked_shell').mkdir()
        masked = tool_command(container, 'false; true', config, out / 'masked_shell', 10)
        result = run_checks(container, [
            {'id': 'pass', 'argv': ['python', '-c', 'print("CONTROL_PASS")']},
            {'id': 'fail', 'argv': ['python', '-c', 'import sys; print("CONTROL_FAIL"); sys.exit(3)']},
            {'id': 'pass_after_fail', 'argv': ['python', '-c', 'print("CONTROL_PASS_LATER")']},
            {'id': 'timeout', 'argv': ['python', '-c', 'import time; time.sleep(5)'], 'timeout_seconds': 1},
        ], out / 'checks', 60)
        status = [v['status'] for v in result['checks']]
        assertions = {'old_compound_shell_reports_zero': masked['exit_code'] == 0,
                      'separate_statuses_preserved': status == ['passed', 'failed', 'passed', 'timeout'],
                      'later_success_does_not_overwrite_failure': not result['all_passed'],
                      'failure_exit_is_three': result['checks'][1]['exit_code'] == 3}
        report = {'scope': 'execution control fixtures; not model quality',
                  'environment': environment, 'assertions': assertions, 'checks': result,
                  'source_sha256': hashlib.sha256((ROOT / 'scripts/visible_checks.py').read_bytes()).hexdigest()}
        (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'path': str(out), 'assertions': assertions}))
        return all(assertions.values())
    finally:
        container.remove(force=True)


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
