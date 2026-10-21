"""Pinned standard Python comparator. Isolation is provided by Docker, not exec.

No host mounts, credentials, benchmark files, network or Docker socket are passed
to generated programs. This is supplementary infrastructure, not the P21 runner.
"""
import json
from pathlib import Path
import resource
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_LIMIT = 2 * 1024 * 1024

BOOTSTRAP = r'''
import contextlib, csv, io, json, sys
packet = json.load(sys.stdin)
def csv_text(rows, headers):
    out = io.StringIO(newline='')
    writer = csv.writer(out, lineterminator='\n')
    writer.writerow(headers)
    writer.writerows(rows)
    return out.getvalue()
scope = {'__name__': '__main__', 'observations': packet['observations'],
         'csv_text': csv_text}
with contextlib.redirect_stdout(sys.stderr):
    exec(compile(packet['code'], '<generated>', 'exec'), scope, scope)
result = scope.get('result')
if type(result) is not str or len(result) > 1048576:
    raise ValueError('result must be a string of at most 1048576 characters')
json.dump({'content': result, 'python': sys.version.split()[0]}, sys.stdout)
'''


def docker_command(storage_root):
    return ['sh', str(storage_root/'scripts/with_container_env.sh'),
            str(storage_root/'.tools/bin/docker')]


def inspect_controls(info, selection):
    host, config = info['HostConfig'], info['Config']
    accepted_ids = {selection['manifest_digest'], selection['config_digest']}
    checks = {
        'pinned_reference': config['Image'] == selection['image'],
        'pinned_image_id': info['Image'] in accepted_ids,
        'network_none': host['NetworkMode'] == 'none',
        'readonly_root': host['ReadonlyRootfs'] is True,
        'no_host_mounts': not info['Mounts'] and not host.get('Binds'),
        'unprivileged': host['Privileged'] is False,
        'nonroot': config['User'] == '65534:65534',
        'drop_caps': 'ALL' in {x.upper() for x in host.get('CapDrop') or []},
        'no_new_privileges': any(x in ('no-new-privileges', 'no-new-privileges:true', 'no-new-privileges=true')
                                 for x in host.get('SecurityOpt') or []),
        'memory_limit': host['Memory'] == 268435456,
        'cpu_limit': host['NanoCpus'] == 1000000000,
        'process_limit': host['PidsLimit'] == 64,
        'no_daemon_logs': host['LogConfig']['Type'] == 'none',
        'owned_label': config['Labels'].get('harness.export-purpose') == 'bounded-python-comparator',
    }
    if not all(checks.values()):
        raise ValueError('container configuration rejected: ' + ','.join(k for k,v in checks.items() if not v))
    return checks


def _limit_cli_output():
    resource.setrlimit(resource.RLIMIT_FSIZE, (OUTPUT_LIMIT, OUTPUT_LIMIT))


def prepare_payload(source, observations, timeout=10):
    if type(source) is not str or len(source) > 20000 or not 0 < timeout <= 30:
        raise ValueError('source or timeout limit')
    payload = json.dumps({'code': source, 'observations': observations}, allow_nan=False).encode()
    if len(payload) > 1048576:
        raise ValueError('input byte limit')
    return payload


def run_program(source, observations, *, storage_root, record_dir, timeout=10):
    payload = prepare_payload(source, observations, timeout)
    selection = json.loads((ROOT/'configs/python_export_image_v01.json').read_text())
    command = docker_command(Path(storage_root))
    record_dir = Path(record_dir)
    record_dir.mkdir(parents=True, exist_ok=False)
    name = 'harness-export-' + uuid.uuid4().hex
    created, creation_attempted, process = False, False, None
    result = {'status': 'not_started', 'image': selection['image'],
              'timeout': False, 'oom_killed': False, 'container_exit_code': None,
              'container_removed': False, 'host_mounts': 0, 'network': 'none'}
    started = time.monotonic()
    try:
        creation_attempted = True
        creation = subprocess.run(command + [
            'create', '--name', name, '--label', 'harness.export-purpose=bounded-python-comparator',
            '--platform', selection['platform'], '--network', 'none', '--read-only',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges=true',
            '--user', '65534:65534', '--memory', '256m', '--memory-swap', '256m',
            '--cpus', '1', '--pids-limit', '64', '--log-driver', 'none',
            '--env', 'PYTHONDONTWRITEBYTECODE=1', '-i',
            selection['image'], 'python', '-I', '-S', '-c', BOOTSTRAP],
            capture_output=True, timeout=30)
        (record_dir/'create_stderr.txt').write_bytes(creation.stderr)
        if creation.returncode:
            raise RuntimeError('container creation failed')
        created = True
        inspect = subprocess.run(command+['inspect', name], capture_output=True, check=True, timeout=15)
        info = json.loads(inspect.stdout)[0]
        result['controls'] = inspect_controls(info, selection)
        (record_dir/'controls.json').write_text(json.dumps(result['controls'], indent=2)+'\n')
        with (record_dir/'stdout_private.txt').open('wb') as out, (record_dir/'stderr_private.txt').open('wb') as err:
            process = subprocess.Popen(command+['start', '-a', '-i', name],
                stdin=subprocess.PIPE, stdout=out, stderr=err, preexec_fn=_limit_cli_output)
            try:
                process.communicate(payload, timeout=timeout)
            except subprocess.TimeoutExpired:
                result['timeout'] = True
                process.kill()
                process.communicate(timeout=5)
        inspect = subprocess.run(command+['inspect', name], capture_output=True, check=True, timeout=15)
        state = json.loads(inspect.stdout)[0]['State']
        result.update(container_exit_code=None if state['Running'] else state['ExitCode'],
                      running_before_cleanup=state['Running'], oom_killed=state['OOMKilled'],
                      client_exit_code=process.returncode)
        if result['timeout']:
            result['status'] = 'timeout'
        elif state['OOMKilled']:
            result['status'] = 'memory_limit'
        elif process.returncode or state['Running'] or state['ExitCode']:
            result['status'] = 'execution_error'
        else:
            value = json.loads((record_dir/'stdout_private.txt').read_text())
            if (set(value) != {'content', 'python'} or type(value['content']) is not str
                    or len(value['content']) > 1048576 or value['python'] != selection['expected_python']):
                raise ValueError('invalid result protocol')
            result.update(status='ok', content=value['content'], python=value['python'])
    except Exception as exc:
        result.update(status='harness_error', error_type=type(exc).__name__)
        (record_dir/'error_private.txt').write_text(str(exc))
    finally:
        if process and process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
        try:
            if creation_attempted and not created:
                # The create client can time out after the daemon created the
                # container. Only remove this invocation's UUID and owned label.
                check = subprocess.run(command+['inspect', name], capture_output=True, timeout=15)
                if check.returncode == 0:
                    found = json.loads(check.stdout)[0]
                    if found['Config'].get('Labels', {}).get('harness.export-purpose') != 'bounded-python-comparator':
                        raise RuntimeError('refusing to clean a container without the owned label')
                    created = True
                elif b'No such object' not in check.stderr and b'No such container' not in check.stderr:
                    raise RuntimeError('container absence could not be confirmed')
            if created:
                removal = subprocess.run(command+['rm', '-f', name], capture_output=True, timeout=30)
                result['container_removed'] = removal.returncode == 0
                (record_dir/'removal_stderr.txt').write_bytes(removal.stderr)
                if removal.returncode:
                    raise RuntimeError('owned container cleanup failed')
        except Exception as exc:
            result.update(status='harness_error', cleanup_error_type=type(exc).__name__)
            (record_dir/'cleanup_error_private.txt').write_text(str(exc))
        result['wall_seconds'] = time.monotonic()-started
        for filename in ('stdout_private.txt', 'stderr_private.txt'):
            path = record_dir/filename
            result[filename.removesuffix('_private.txt')+'_bytes'] = path.stat().st_size if path.exists() else 0
        (record_dir/'result_private.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    return result
