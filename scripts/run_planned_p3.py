"""Run a frozen P3 trial once, with source checks and an exclusive attempt record."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import signal

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_trial(plan_path, trial_id, root=ROOT):
    plan = read(plan_path)
    trials = plan['trials']
    if len(trials) != plan['trial_count'] or len({t['trial_id'] for t in trials}) != len(trials):
        raise ValueError('plan trial count or identities are inconsistent')
    for path, expected in plan['config_sha256'].items():
        if sha(root / path) != expected:
            raise ValueError('frozen config changed: ' + path)
    for name, expected in plan['source_sha256'].items():
        if sha(root / 'scripts' / name) != expected:
            raise ValueError('frozen source changed: ' + name)
    configs = [read(root / t['config']) for t in trials]
    if (sum(c['max_calls'] for c in configs) != plan['max_total_model_calls']
            or sum(c['max_total_tokens'] for c in configs) != plan['max_total_input_output_tokens']):
        raise ValueError('aggregate plan budget differs')
    for trial, config in zip(trials, configs):
        if (config['instance_id'] != trial['task']
                or config['max_wall_seconds'] != plan['per_trial_max_wall_seconds']
                or any(config[key] != plan[key] for key in ('model', 'cache_type_k', 'cache_type_v'))
                or trial['strategy'] not in ('single', 'fixed_pair')):
            raise ValueError('trial conditions differ from plan')
    index = next(i for i, t in enumerate(trials) if t['trial_id'] == trial_id)
    attempts = root / 'records/p3_plan_runs' / plan_path.stem
    for previous in trials[:index]:
        status = read(attempts / previous['trial_id'] / 'status.json')
        if status.get('plan_sha256') != sha(plan_path):
            raise ValueError('plan changed after an earlier trial started')
        if status['status'] != 'execution_completed' or status.get('audit_errors'):
            raise ValueError('previous execution did not complete cleanly')
        evaluation = read(root / status['run_record'] / 'final_evaluation_summary.json')
        if (evaluation['evaluation_status'] != 'completed' or evaluation.get('infra_failure')
                or evaluation['artifact_sha256'] != status['artifact_sha256']):
            raise ValueError('previous independent evaluation is incomplete or mismatched')
        # A completed negative evaluation is a valid observation, not a retry trigger.
    return plan, trials[index], configs[index], attempts / trial_id


def reserve_attempt(directory):
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir()  # Exclusive: any previous start, including a failure, blocks reuse.


def execute(plan_path, trial_id):
    plan, trial, config, directory = prepare_trial(plan_path, trial_id)
    reserve_attempt(directory)
    state = {'trial_id': trial_id, 'plan': str(plan_path.relative_to(ROOT)),
             'plan_sha256': sha(plan_path), 'status': 'started',
             'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    (directory / 'plan.json').write_bytes(plan_path.read_bytes())
    (directory / 'run_planned_p3.py').write_bytes(Path(__file__).read_bytes())
    (directory / 'status.json').write_text(json.dumps(state, indent=2) + '\n')
    try:
        from run_fixed_comparison import run, alarm_handler
        from audit_p2 import audit_run
        from audit_p3 import audit_protocol
        signal.signal(signal.SIGALRM, alarm_handler)
        summary = run(config, trial['strategy'])
        record = ROOT / 'records/p3' / summary['run_id']
        state.update(run_record=str(record.relative_to(ROOT)),
                     artifact_sha256=summary.get('artifact_sha256'))
        row = audit_run(record)
        errors = row['errors'] + audit_protocol(record)
        state['audit_errors'] = errors
        if (errors or not summary['usage_complete'] or not summary.get('container_removed')
                or any(summary.get(k) for k in ('error', 'cleanup_error', 'finalization_error'))):
            raise RuntimeError('execution or accounting failed; keep this attempt and stop the plan')
        state['status'] = 'execution_completed'
    except Exception as error:
        state.update(status='failed', error=repr(error))
    finally:
        state['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (directory / 'status.json').write_text(json.dumps(state, indent=2) + '\n')
        print(json.dumps(state), flush=True)
    return state['status'] == 'execution_completed'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', default='configs/P3_development_plan_v01.json')
    parser.add_argument('--trial', required=True)
    args = parser.parse_args()
    path = (ROOT / args.plan).resolve()
    if not path.is_relative_to(ROOT / 'configs'):
        raise ValueError('plan must be inside this repository configs directory')
    raise SystemExit(0 if execute(path, args.trial) else 1)
