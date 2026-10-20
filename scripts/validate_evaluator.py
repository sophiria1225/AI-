"""Private positive/negative controls using the official SWE-bench evaluator."""
import datetime
import json
import pathlib
import time

import docker
import swebench.harness.run_evaluation as evaluation
from swebench.harness.utils import make_test_spec
from container_policy import evaluator_create_container, POLICY

evaluation.create_container = evaluator_create_container

root = pathlib.Path(__file__).resolve().parents[1]
task = json.loads((root / 'private_eval/selected_task.json').read_text())[0]
client = docker.from_env(timeout=60)
stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
results = []
for label, skip in [('unmodified', True), ('reference', False)]:
    start = time.monotonic()
    run_id = 'P0_restricted_' + stamp + '_' + label
    pred = {'instance_id':task['instance_id'], 'model_name_or_path':'evaluator_control', 'model_patch':task['patch']}
    try:
        result = evaluation.run_instance(make_test_spec(task), pred, client, run_id, timeout=180, skip_patch=skip)
        record = {'control':label, 'run_id':run_id, 'result':result, 'container_policy': POLICY}
    except Exception as error:
        record = {'control':label, 'run_id':run_id, 'error':repr(error)}
    record['wall_seconds'] = time.monotonic() - start
    results.append(record)
    (root / 'private_eval/evaluator_validation_restricted.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
    if record.get('result'):
        task_id, reports = record['result']
        print(json.dumps({'control':label,'run_id':run_id,'resolved':reports.get(task_id,{}).get('resolved'),'wall_seconds':record['wall_seconds']}),flush=True)
    else:
        print(json.dumps({'control':label,'run_id':run_id,'error':record.get('error','no report'),'wall_seconds':record['wall_seconds']}),flush=True)

valid = []
for record in results:
    if not record.get('result'):
        valid.append(False)
        continue
    task_id, reports = record['result']
    report = reports[task_id]
    valid.append(report.get('resolved') == (record['control'] == 'reference')
                 and not report.get('infra_failure', False))
raise SystemExit(0 if all(valid) else 1)
