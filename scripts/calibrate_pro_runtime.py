"""No-model checks through the same tools and capture path used by an agent."""
import argparse
import datetime
import json
from pathlib import Path
import time
import docker

from pro_runtime import ROOT, POLICY, sha, load_public_task, require_controls, create_container
from repository_runtime import runtime_for
from run_e0_pilot import tool_command
from artifact_capture import capture_artifact
from visible_checks import run_checks


def run(storage, run_id):
    if not run_id.isidentifier():
        raise ValueError('Invalid run ID')
    config_path = ROOT / 'configs/pro_public_runtime_v01.json'
    config = json.loads(config_path.read_text())
    require_controls(storage, config)
    load_public_task(storage, config)
    client = docker.from_env(timeout=60)
    if client.containers.list():
        raise ValueError('Research VM already has an active container')
    out = storage / 'records/pro_runtime' / run_id
    out.mkdir(parents=True, exist_ok=False)
    summary = {'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'status': 'error', 'model_calls': 0, 'policy': POLICY,
               'config_sha256': sha(config_path), 'steps': [], 'source_sha256': {}}
    for name in ('calibrate_pro_runtime.py', 'pro_runtime.py', 'repository_runtime.py',
                 'run_e0_pilot.py', 'artifact_capture.py', 'visible_checks.py',
                 'prepare_pro_environment.py'):
        source = ROOT / 'scripts' / name
        (out / name).write_bytes(source.read_bytes())
        summary['source_sha256'][name] = sha(source)
    (out / 'config.json').write_bytes(config_path.read_bytes())
    container = None
    started = time.monotonic()
    try:
        container = create_container(client, config, 'harness_pro_runtime')
        summary['container_id'] = container.id
        runtime = runtime_for(config, {})
        options = {'workdir': runtime['workdir'], 'python_path': runtime['python']}
        for label, command, code in (
            ('python_and_workdir', "python3 -c \"import os,sys; assert os.getcwd() == '/app'; print(sys.version.split()[0])\"", 0),
            ('nonzero', 'exit 13', 13),
            ('new_file', "printf 'runtime capture probe\\n' > harness_runtime_probe.txt", 0),
        ):
            folder = out / label
            folder.mkdir()
            result = tool_command(container, command, config, folder, 180)
            summary['steps'].append({'name': label, 'exit_code': result['exit_code'],
                                     'status_known': result['exit_code_known']})
            if result['exit_code'] != code or not result['exit_code_known'] or result.get('running'):
                raise ValueError('Unexpected public tool result: ' + label)
        folder = out / 'changed_artifact'
        folder.mkdir()
        changed = capture_artifact(container, config['base_commit'], folder, **options)
        patch = (folder / 'final.patch').read_bytes()
        if changed['artifact_bytes'] == 0 or b'harness_runtime_probe.txt' not in patch:
            raise ValueError('New file missing from artifact')
        summary['captured_new_file'] = changed
        folder = out / 'remove_probe'
        folder.mkdir()
        result = tool_command(container,
            'git reset -- harness_runtime_probe.txt && rm harness_runtime_probe.txt',
            config, folder, 180)
        if result['exit_code'] != 0:
            raise ValueError('Could not remove only the synthetic calibration file')
        folder = out / 'clean_artifact'
        folder.mkdir()
        clean = capture_artifact(container, config['base_commit'], folder, **options)
        if clean['artifact_bytes'] != 0:
            raise ValueError('Calibration did not restore the clean base')
        summary['clean_artifact'] = clean
        summary['visible_checks'] = run_checks(
            container, config['visible_checks'], out / 'public_checks', 300,
            workdir=runtime['workdir'], environment=runtime['environment'])
        folder = out / 'after_public_checks'
        folder.mkdir()
        after = capture_artifact(container, config['base_commit'], folder, **options)
        summary['after_public_checks'] = after
        if after['artifact_sha256'] != clean['artifact_sha256']:
            raise ValueError('Public checks changed the deliverable')
        if not summary['visible_checks']['all_passed']:
            raise ValueError('Public base check needs diagnosis; no model was called')
        summary['status'] = 'completed'
    except Exception as error:
        summary['error'] = repr(error)
    finally:
        if container is not None:
            try:
                container.remove(force=True)
                summary['container_removed'] = True
            except Exception as error:
                summary['cleanup_error'] = repr(error)
        summary['wall_seconds'] = time.monotonic() - started
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'record': str(out), 'status': summary['status'],
                      'error': summary.get('error'), 'model_calls': 0}))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    result = run(args.storage_root.resolve(), args.run_id)
    raise SystemExit(0 if result['status'] == 'completed' else 1)
