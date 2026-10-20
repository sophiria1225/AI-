"""Small non-LLM comparison of conda activation and an explicit environment PATH."""
import datetime
import json
import pathlib
import time

import docker

from container_policy import create_task_container

ROOT = pathlib.Path(__file__).resolve().parents[1]
config = json.loads((ROOT / 'configs/E0_pilot_v03.json').read_text())
client = docker.from_env(timeout=25)
explicit_environment = {
    'PATH': '/opt/miniconda3/envs/testbed/bin:/opt/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
    'CONDA_PREFIX': '/opt/miniconda3/envs/testbed',
    'CONDA_DEFAULT_ENV': 'testbed',
}
probe = "python -c 'import sys, json, django; print(json.dumps(dict(prefix=sys.prefix, python=sys.version.split()[0], django=django.get_version())))'"
records = []
for mode in ['activate', 'explicit_path']:
    container = create_task_container(client, config['image'], 'harness_python_' + mode)
    try:
        container.start()
        for repeat in range(5):
            command = probe
            environment = explicit_environment if mode == 'explicit_path' else None
            if mode == 'activate':
                command = 'source /opt/miniconda3/bin/activate testbed; e0_setup_status=$?; printf "SETUP_STATUS=%s\\n" "$e0_setup_status"; ' + command
            start = time.monotonic()
            result = container.exec_run(['timeout', '--kill-after=2s', '15', 'bash', '-c', command],
                                        environment=environment, workdir='/testbed')
            output = result.output.decode(errors='replace')
            parsed = None
            for line in output.splitlines():
                if line.startswith('{'):
                    parsed = json.loads(line)
            core = container.exec_run(['test', '-e', '/testbed/core'])
            record = {'mode': mode, 'repeat': repeat, 'exit_code': result.exit_code,
                      'output': output, 'reported_environment': parsed,
                      'core_exists_after': core.exit_code == 0,
                      'seconds': time.monotonic() - start}
            records.append(record)
    finally:
        container.remove(force=True)
summary = {
    'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'scope': '10 Python import probes, no model calls; absence of a rare crash here does not establish its cause',
    'records': records,
    'all_expected_environment': all(
        r['exit_code'] == 0 and r['reported_environment'] is not None
        and r['reported_environment']['prefix'] == '/opt/miniconda3/envs/testbed'
        and r['reported_environment']['python'] == '3.9.20' for r in records),
}
(ROOT / 'records/environment/python_execution_probe.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({'probes': len(records), 'all_expected_environment': summary['all_expected_environment'],
                  'core_observations': sum(r['core_exists_after'] for r in records)}))
raise SystemExit(0 if summary['all_expected_environment'] else 1)
