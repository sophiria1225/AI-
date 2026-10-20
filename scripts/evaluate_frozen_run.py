"""Evaluate one frozen run, outside the generator, without selecting past candidates."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import docker
import swebench.harness.run_evaluation as evaluation
from swebench.harness.utils import make_test_spec
from container_policy import evaluator_create_container

ROOT = Path(__file__).resolve().parents[1]
PIN = '02e7a74ffd0b707aab73d203fe87bdc7c76afc8e'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True, help='Path of an already frozen run under records/')
    args = parser.parse_args()
    run = (ROOT / args.run).resolve()
    if not run.is_relative_to(ROOT / 'records'):
        raise ValueError('run must be inside records/')
    result_file = run / 'final_evaluation_summary.json'
    if result_file.exists():
        raise RuntimeError('evaluation already recorded; refusing to overwrite')
    commit = subprocess.check_output(['git', '-C', str(ROOT / 'vendor/SWE-bench'), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(ROOT / 'vendor/SWE-bench'), 'status', '--porcelain'])
    if commit != PIN or dirty:
        raise RuntimeError('evaluator checkout revision differs from the pinned version')
    if not Path(evaluation.__file__).resolve().is_relative_to((ROOT / 'vendor/SWE-bench').resolve()):
        raise RuntimeError('imported evaluator is outside the pinned checkout')
    state = json.loads((run / 'summary.json').read_text())
    if not state.get('artifact_frozen_at') or not state.get('artifact_sha256'):
        raise ValueError('run has no explicitly frozen final artifact')
    patch = (run / 'final.patch').read_bytes()
    if hashlib.sha256(patch).hexdigest() != state['artifact_sha256']:
        raise ValueError('frozen artifact changed')
    private = {'django__django-15957': 'selected_task.json',
               'django__django-15380': 'P1_second_task.json'}
    task = json.loads((ROOT / 'private_eval' / private[state['instance_id']]).read_text())[0]
    if task['instance_id'] != state['instance_id']:
        raise ValueError('evaluation task mismatch')
    spec = make_test_spec(task)
    config = json.loads((run / 'config.json').read_text())
    client = docker.from_env(timeout=60)
    generator_image = client.images.get(config['image']).id
    if client.images.get(spec.image).id != generator_image:
        raise RuntimeError('evaluation and generation images differ')
    lock = run / 'evaluation.started.json'
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with lock.open('x') as handle:
        json.dump({'started_at': started_at, 'artifact_sha256': state['artifact_sha256']}, handle)
    source_hashes = {}
    for source in ('evaluate_frozen_run.py', 'container_policy.py'):
        content = (ROOT / 'scripts' / source).read_bytes()
        (run / ('evaluation_' + source)).write_bytes(content)
        source_hashes[source] = hashlib.sha256(content).hexdigest()
    evaluation.create_container = evaluator_create_container
    run_id = 'P2_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + run.name
    record = {'run_id': run.name, 'instance_id': state['instance_id'], 'evaluation_run_id': run_id,
              'artifact_sha256': state['artifact_sha256'], 'evaluator_commit': commit,
              'source_hashes': source_hashes, 'image_id': generator_image,
              'started_at': started_at, 'evaluation_status': 'error', 'resolved': None}
    started = time.monotonic()
    try:
        prediction = {'instance_id': task['instance_id'], 'model_name_or_path': state['model'],
                      'model_patch': patch.decode()}
        report = evaluation.run_instance(spec, prediction, client,
                                         run_id, timeout=180, skip_patch=not bool(patch.strip()))
        if report:
            task_id, reports = report
            full = reports[task_id]
            record.update(evaluation_status='completed', resolved=full.get('resolved'),
                          infra_failure=full.get('infra_failure', False),
                          patch_applied=full.get('patch_successfully_applied'),
                          test_counts={category: {status: len(items) for status, items in values.items()}
                                       for category, values in full.get('tests_status', {}).items()})
        else:
            record['evaluation_status'] = 'no_report'
    except Exception as error:
        record['error'] = repr(error)
    finally:
        record['evaluation_seconds'] = time.monotonic() - started
        result_file.write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps(record), flush=True)
    return record['evaluation_status'] == 'completed' and not record.get('infra_failure')


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
