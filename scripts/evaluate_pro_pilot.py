"""Evaluate only the frozen final candidate, once, outside the generator."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import time
import docker

from pro_runtime import ROOT, sha, require_controls
from evaluate_pro_environment import private_bundle, evaluate


def frozen_patch(run):
    summary = json.loads((run / 'summary.json').read_text())
    audit = json.loads((run / 'audit.json').read_text())
    patch = (run / 'final.patch').read_bytes()
    digest = hashlib.sha256(patch).hexdigest()
    if (summary.get('execution_status') != 'completed' or summary.get('audit_errors')
            or audit.get('errors') or not summary.get('usage_complete')
            or not summary.get('artifact_frozen_at') or not summary.get('container_removed')
            or digest != summary.get('artifact_sha256')
            or digest != audit.get('artifact_sha256')):
        raise ValueError('Candidate is incomplete, unaudited, or changed after freezing')
    return summary, patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--trial', required=True)
    args = parser.parse_args()
    if not args.trial.isidentifier():
        raise ValueError('Invalid trial ID')
    storage = args.storage_root.resolve()
    run = storage / 'records/pro_pilot' / args.trial
    summary, patch = frozen_patch(run)
    config = json.loads((run / 'config.json').read_text())
    require_controls(storage, config)
    plan_path = ROOT / 'configs/pro_environment_feasibility_v01.json'
    if sha(plan_path) != config['environment_plan_sha256']:
        raise ValueError('Environment plan changed')
    plan = json.loads(plan_path.read_text())
    if any(plan[k] != config[k] for k in ('instance_id', 'base_commit', 'image')):
        raise ValueError('Evaluator and candidate belong to different tasks')
    frozen = json.loads((run / 'plan.json').read_text())
    if sha(run / 'plan.json') != summary['plan_sha256']:
        raise ValueError('Saved model plan changed')
    for name in ('evaluate_pro_pilot.py', 'evaluate_pro_environment.py', 'pro_verifier_result.py'):
        if sha(ROOT / 'scripts' / name) != frozen['source_sha256'][name]:
            raise ValueError('Evaluator changed since model execution')
    client = docker.from_env(timeout=60)
    if client.containers.list():
        raise ValueError('Research VM already has an active container')
    record = run / 'independent_evaluation'
    record.mkdir(exist_ok=False)
    result = {
        'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'artifact_sha256': summary['artifact_sha256'], 'evaluation_status': 'error',
        'infra_failure': True, 'model_calls': 0, 'private_contents_displayed': False,
        'image': plan['image'],
    }
    for name in ('evaluate_pro_pilot.py', 'evaluate_pro_environment.py', 'pro_verifier_result.py'):
        (record / name).write_bytes((ROOT / 'scripts' / name).read_bytes())
    started = time.monotonic()
    try:
        bundle, manifest = private_bundle(storage, plan)
        result['private_manifest_sha256'] = sha(bundle / 'manifest.json')
        result.update(evaluate(client, plan, bundle, 'candidate_evaluation', '/app', record,
                               candidate_patch=patch))
        valid = result['status'] == 'completed' and result.get('required_results_complete')
        result.update(evaluation_status='completed' if valid else 'error',
                      infra_failure=not valid,
                      resolved=(result.get('reward') == 1) if valid else None)
    except Exception as error:
        result['error'] = repr(error)
    finally:
        result['total_wall_seconds'] = time.monotonic() - started
        (record / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
        with (run / 'final_evaluation_summary.json').open('x') as output:
            output.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'trial': args.trial, 'status': result['evaluation_status'],
                      'resolved': result.get('resolved'), 'infra_failure': result['infra_failure']}))
    return not result['infra_failure']


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
