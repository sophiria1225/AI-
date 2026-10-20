"""Run the two predeclared P5 arms and evaluate each frozen final artifact once."""
import argparse
import datetime
import json
from pathlib import Path
import signal
import subprocess
import sys

from pro_runtime import ROOT, sha
from run_pro_pilot import execute, prepare, alarm_handler


def validate_batch(path, expected_sha, storage):
    if sha(path) != expected_sha:
        raise ValueError('Batch plan changed')
    plan = json.loads(path.read_text())
    if plan['trial_count'] != 2 or len(plan['trials']) != 2:
        raise ValueError('Exactly two predeclared trials are allowed')
    if [t['strategy'] for t in plan['trials']] != ['fixed_pair', 'single']:
        raise ValueError('Unexpected trial order')
    ids = [t['trial_id'] for t in plan['trials']]
    if len(set(ids)) != 2 or not all(i.isidentifier() for i in ids):
        raise ValueError('Distinct valid trial IDs are required')
    configs = []
    for trial in plan['trials']:
        child = ROOT/trial['plan']
        if sha(child) != trial['plan_sha256']:
            raise ValueError('Trial plan changed')
        detail, config, task, vendor = prepare(child, storage)
        if detail['strategy'] != trial['strategy'] or detail['trial_id'] != trial['trial_id']:
            raise ValueError('Trial identity differs')
        configs.append(config)
    if configs[0] != configs[1]:
        raise ValueError('Both arms must use exactly the same configuration')
    for name,digest in plan['source_sha256'].items():
        if sha(ROOT/'scripts'/name) != digest:
            raise ValueError('Batch source changed: '+name)
    return plan


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--storage-root',type=Path,required=True)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--expected-sha256',required=True)
    args=parser.parse_args()
    storage=args.storage_root.resolve()
    path=(ROOT/args.plan).resolve()
    if not path.is_relative_to(ROOT/'configs'):
        raise ValueError('Batch plan must be inside configs')
    plan=validate_batch(path,args.expected_sha256,storage)
    record=storage/'records/pro_batches'/plan['batch_id']
    record.mkdir(parents=True,exist_ok=False)
    (record/'plan.json').write_bytes(path.read_bytes())
    summary={'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'plan_sha256':args.expected_sha256,'status':'running','trials':[]}
    def save():
        (record/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    save()
    try:
        for trial in plan['trials']:
            validate_batch(path,args.expected_sha256,storage)
            summary['active_trial']=trial['trial_id']
            save()
            result=execute(ROOT/trial['plan'],storage)
            row={'trial_id':trial['trial_id'],'strategy':trial['strategy'],
                 'execution_status':result['execution_status'],'stop_reason':result['stop_reason']}
            summary['trials'].append(row);save()
            if result['execution_status'] != 'completed':
                raise ValueError('Execution requires review; no retry or next trial')
            evaluation=subprocess.run(
                [sys.executable,str(ROOT/'scripts/evaluate_pro_pilot.py'),
                 '--storage-root',str(storage),'--trial',trial['trial_id']],
                cwd=ROOT,capture_output=True,text=True,check=False)
            (record/(trial['trial_id']+'_evaluation_stdout.txt')).write_text(evaluation.stdout)
            (record/(trial['trial_id']+'_evaluation_stderr.txt')).write_text(evaluation.stderr)
            if evaluation.returncode:
                raise ValueError('Independent evaluation requires review; no next trial')
            outcome=json.loads((storage/'records/pro_pilot'/trial['trial_id']/'final_evaluation_summary.json').read_text())
            row.update(evaluation_status=outcome['evaluation_status'],resolved=outcome['resolved'])
            save()
            # Outcome is recorded for the researcher and is never added to model input.
        summary.update(status='completed',active_trial=None)
    except Exception as error:
        summary.update(status='error',error=repr(error))
    finally:
        summary['last_update_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()
    print(json.dumps(summary),flush=True)
    return summary['status']=='completed'


if __name__=='__main__':
    signal.signal(signal.SIGALRM,alarm_handler)
    raise SystemExit(0 if main() else 1)
