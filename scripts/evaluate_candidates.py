"""Independent evaluation after artifact freezing; never sends feedback to agents."""
import datetime
import hashlib
import json
import pathlib
import time

import docker
import swebench.harness.run_evaluation as evaluation
from swebench.harness.utils import make_test_spec

from container_policy import evaluator_create_container

ROOT = pathlib.Path(__file__).resolve().parents[1]
evaluation.create_container = evaluator_create_container
task = json.loads((ROOT / 'private_eval/selected_task.json').read_text())[0]
client = docker.from_env(timeout=60)
stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
results = []
for run_dir in sorted((ROOT / 'records/e0').glob('*')):
    if not (run_dir / 'summary.json').exists():
        continue
    summary = json.loads((run_dir / 'summary.json').read_text())
    config = json.loads((run_dir / 'config.json').read_text())
    record = {'run_id': summary['run_id'], 'strategy': summary['strategy'],
              'config_version': config.get('version', 'v01')}
    if config.get('version') is None:
        record.update(evaluation_status='not_evaluated_invalid_preflight', resolved=None)
        results.append(record)
        continue
    artifact_path = run_dir / 'final.patch'
    if not artifact_path.exists():
        record.update(evaluation_status='no_frozen_artifact', resolved=False)
        results.append(record)
        continue
    patch_bytes = artifact_path.read_bytes()
    if hashlib.sha256(patch_bytes).hexdigest() != summary['artifact_sha256']:
        raise RuntimeError('frozen artifact hash changed: ' + run_dir.name)
    if summary['instance_id'] != task['instance_id']:
        raise RuntimeError('wrong task')
    prediction = {'instance_id': task['instance_id'], 'model_name_or_path': summary['strategy'],
                  'model_patch': patch_bytes.decode()}
    run_id = 'E0_final_' + stamp + '_' + summary['run_id']
    started = time.monotonic()
    report = evaluation.run_instance(make_test_spec(task), prediction, client, run_id,
                                     timeout=180, skip_patch=not bool(patch_bytes.strip()))
    record.update(evaluation_run_id=run_id, evaluation_seconds=time.monotonic() - started,
                  artifact_sha256=summary['artifact_sha256'])
    if report:
        task_id, reports = report
        full = reports[task_id]
        record.update(evaluation_status='completed', resolved=full.get('resolved'),
                      infra_failure=full.get('infra_failure', False),
                      patch_applied=full.get('patch_successfully_applied'),
                      test_counts={category: {status: len(items) for status, items in value.items()}
                                   for category, value in full.get('tests_status', {}).items()})
    else:
        record.update(evaluation_status='no_report', resolved=None)
    (run_dir / 'final_evaluation_summary.json').write_text(json.dumps(record, indent=2) + '\n')
    results.append(record)
    print(json.dumps(record), flush=True)
(ROOT / 'records/e0/final_evaluations.json').write_text(json.dumps(results, indent=2) + '\n')
