"""Summarize only the predeclared P5 trials; leave earlier reports untouched."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path

from summarize_pro_pilot import collect

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_batch(storage, batch_id):
    if not batch_id.isidentifier():
        raise ValueError('Invalid batch identifier')
    directory = storage / 'records/pro_batches' / batch_id
    plan_path = directory / 'plan.json'
    plan, state = read(plan_path), read(directory / 'summary.json')
    if plan['batch_id'] != batch_id or sha(plan_path) != state['plan_sha256']:
        raise ValueError('Recorded batch identity/hash differs')
    trials = plan['trials']
    if (plan['trial_count'] != 2 or len(trials) != 2
            or [t['strategy'] for t in trials] != ['fixed_pair', 'single']
            or len({t['trial_id'] for t in trials}) != 2
            or not all(t['trial_id'].isidentifier() for t in trials)):
        raise ValueError('Invalid predeclared comparison')
    return plan, state


def collect_trial(storage, trial):
    directory = storage / 'records/pro_pilot' / trial['trial_id']
    row = {'trial_id': trial['trial_id'], 'strategy': trial['strategy'],
           'record': str(directory.relative_to(storage))}
    if not directory.exists():
        return {**row, 'stage': 'not_started', 'result': None}
    # A just-started process can have created the directory but not its summary.
    path = directory / 'summary.json'
    if not path.exists():
        return {**row, 'stage': 'initializing', 'result': None}
    summary = read(path)
    row.update(recorded_calls=len(summary['calls']),
               recorded_tokens=summary['total_recorded_tokens'],
               usage_complete=summary['usage_complete'],
               started_at=summary['started_at'])
    if (summary['phase'] != 'P5' or summary['strategy'] != trial['strategy']
            or summary['plan_sha256'] != trial['plan_sha256']):
        raise ValueError('Trial identity or plan differs: ' + trial['trial_id'])
    if sha(directory / 'plan.json') != trial['plan_sha256']:
        raise ValueError('Recorded child plan differs: ' + trial['trial_id'])
    if 'execution_status' not in summary:
        return {**row, 'stage': 'running', 'result': None}
    if summary['execution_status'] != 'completed':
        return {**row, 'stage': 'execution_error', 'result': None,
                'stop_reason': summary.get('stop_reason'),
                'execution_status': summary['execution_status']}
    result = collect(storage, directory)
    metrics = result['measurements']
    outcome = metrics.get('evaluation')
    if outcome is None:
        stage = 'awaiting_evaluation'
    elif outcome.get('evaluation_status') != 'completed':
        stage = 'evaluation_error'
    elif metrics['errors'] or metrics['unknown_usage_calls']:
        stage = 'audit_error'
    else:
        stage = 'evaluated'
    return {**row, 'stage': stage, 'result': result}


def comparison_status(rows, batch_state):
    if any(row['stage'].endswith('_error') for row in rows):
        return 'requires_review'
    if batch_state.get('status') == 'error':
        return 'requires_review'
    if len(rows) == 2 and all(row['stage'] == 'evaluated' for row in rows):
        return 'completed'
    return 'in_progress'


def build_report(storage, batch_id):
    plan, state = load_batch(storage, batch_id)
    rows, errors = [], []
    for trial in plan['trials']:
        try:
            row = collect_trial(storage, trial)
        except (OSError, ValueError, KeyError) as error:
            row = {'trial_id': trial['trial_id'], 'strategy': trial['strategy'],
                   'stage': 'record_error', 'result': None, 'error': str(error)}
        rows.append(row)
    configs = []
    for trial in plan['trials']:
        path = storage / 'records/pro_pilot' / trial['trial_id'] / 'config.json'
        if path.exists():
            configs.append((trial['trial_id'], read(path)))
    config_match = None
    if len(configs) == 2:
        config_match = configs[0][1] == configs[1][1]
        if not config_match:
            errors.append('Actual saved configurations differ between arms')
    known_tokens = sum(row.get('recorded_tokens', 0) for row in rows)
    known_calls = sum(row.get('recorded_calls', 0) for row in rows)
    if known_tokens > plan['max_total_input_output_tokens']:
        errors.append('Batch token upper bound exceeded')
    if known_calls > plan['max_total_model_calls']:
        errors.append('Batch call upper bound exceeded')
    status = 'requires_review' if errors else comparison_status(rows, state)
    names = ('summarize_pro_comparison.py', 'summarize_pro_pilot.py',
             'analyze_p3_timeline.py', 'summarize_p3.py', 'audit_p2.py', 'audit_p3.py')
    return {
        'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scope': 'P5 predeclared one-task development comparison only; no confirmatory effect estimate',
        'batch_id': batch_id, 'batch_plan_sha256': state['plan_sha256'],
        'batch_status': state['status'], 'comparison_status': status,
        'batch_error': state.get('error'), 'configuration_match': config_match,
        'recorded_calls_so_far': known_calls, 'recorded_tokens_so_far': known_tokens,
        'errors': errors, 'runs': rows,
        'analysis_source_sha256': {name: sha(ROOT/'scripts'/name) for name in names},
        'limitations': [
            'One previously exposed task and one trial per arm; no quality equivalence or general efficiency claim.',
            'Unstarted and pending trials have no outcome; running token counts are partial known usage.',
            'Both P5 arms share 7200 seconds. P4 used 3600 seconds and is not the matched control.',
            'One physical model slot; prompt cache reuse and wall time depend on the schedule.',
            'Private evaluation counts are researcher outputs and are not passed to the subsequent generator.',
            'Final artifact timing is retrospective; repeat reads or edits alone do not establish wasted work or dependency.',
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--batch', default='P5_01')
    args = parser.parse_args()
    report = build_report(args.storage_root.resolve(), args.batch)
    output = ROOT / 'reports/P5_pro_measurements.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in (
        'batch_id', 'batch_status', 'comparison_status', 'recorded_calls_so_far',
        'recorded_tokens_so_far', 'errors')}))
    return report['comparison_status'] != 'requires_review'


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
