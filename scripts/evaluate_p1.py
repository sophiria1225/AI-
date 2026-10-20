"""Independent P1 controls or frozen submissions. No feedback into executing agents."""
import argparse
import datetime
import hashlib
import json
import pathlib
import time

import docker
import swebench.harness.run_evaluation as evaluation
from swebench.harness.utils import make_test_spec

from container_policy import evaluator_create_container

ROOT=pathlib.Path(__file__).resolve().parents[1]
evaluation.create_container=evaluator_create_container
parser=argparse.ArgumentParser()
parser.add_argument('--controls',action='store_true')
args=parser.parse_args()
tasks=[json.loads((ROOT/'private_eval'/name).read_text())[0]
       for name in ['selected_task.json','P1_second_task.json']]
client=docker.from_env(timeout=60)
stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
results=[]
cases=[]
if args.controls:
    # First task's evaluator and image are unchanged; its completed controls are reused.
    task=tasks[1]
    cases=[(label,task,task['patch'] if label=='reference' else '',None)
           for label in ['unmodified','reference']]
else:
    for run_dir in sorted((ROOT/'records/p1').glob('*')):
        if not (run_dir/'summary.json').exists():
            continue
        summary=json.loads((run_dir/'summary.json').read_text())
        if (run_dir/'final_evaluation_summary.json').exists():
            raise RuntimeError('refusing to overwrite an existing evaluation: '+str(run_dir))
        if not summary.get('artifact_sha256'):
            results.append({'run_id':run_dir.name,'evaluation_status':'no_frozen_artifact','resolved':None})
            continue
        patch=(run_dir/'final.patch').read_bytes()
        if hashlib.sha256(patch).hexdigest()!=summary['artifact_sha256']:
            raise RuntimeError('frozen artifact hash changed')
        task=next(t for t in tasks if t['instance_id']==summary['instance_id'])
        cases.append((run_dir.name,task,patch.decode(),run_dir))
for label,task,patch,run_dir in cases:
    run_id='P1_'+stamp+'_'+label
    started=time.monotonic()
    prediction={'instance_id':task['instance_id'],'model_name_or_path':'P1_control' if args.controls else label,
                'model_patch':patch}
    report=evaluation.run_instance(make_test_spec(task),prediction,client,run_id,
                                   timeout=180,skip_patch=not bool(patch.strip()))
    record={'run_id':label,'instance_id':task['instance_id'],'evaluation_run_id':run_id,
            'evaluation_seconds':time.monotonic()-started,
            'artifact_sha256':hashlib.sha256(patch.encode()).hexdigest()}
    if report:
        task_id,reports=report
        full=reports[task_id]
        record.update(evaluation_status='completed',resolved=full.get('resolved'),
            infra_failure=full.get('infra_failure',False),patch_applied=full.get('patch_successfully_applied'),
            test_counts={category:{status:len(items) for status,items in values.items()}
                         for category,values in full.get('tests_status',{}).items()})
    else:
        record.update(evaluation_status='no_report',resolved=None)
    if run_dir:
        (run_dir/'final_evaluation_summary.json').write_text(json.dumps(record,indent=2)+'\n')
    results.append(record)
    print(json.dumps(record),flush=True)
output=ROOT/('private_eval/P1_controls_'+stamp+'.json' if args.controls else 'records/p1_evaluations_'+stamp+'.json')
output.write_text(json.dumps(results,indent=2)+'\n')
if args.controls:
    valid=all(r.get('evaluation_status')=='completed' and not r.get('infra_failure')
              and r['resolved']==(r['run_id']=='reference') for r in results)
else:
    valid=all(r.get('evaluation_status')=='completed' and not r.get('infra_failure') for r in results)
raise SystemExit(0 if valid else 1)
