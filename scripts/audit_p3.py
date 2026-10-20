"""Audit P3 raw accounting plus shared budgets and version-specific completion."""
import datetime
import hashlib
import json
from pathlib import Path

from audit_p2 import audit_run, read
from experiment_state import CompletionState

ROOT = Path(__file__).resolve().parents[1]


def audit_protocol(run):
    summary, config = read(run/'summary.json'), read(run/'config.json')
    errors = []
    units = ('single',) if summary['strategy'] == 'single' else ('implementation', 'validation')
    known_total = 0
    for index, call in enumerate(summary['calls'], 1):
        directory = run/call['path']
        before, after = read(directory/'budget_before.json'), read(directory/'budget_after.json')
        if call.get('unit') != units[(index-1) % len(units)]:
            errors.append('unexpected unit sequence: ' + call['path'])
        if (before['recorded_total_tokens'] != known_total or before['attempted_calls'] != index-1
                or before['remaining_tokens'] != config['max_total_tokens']-known_total
                or before['remaining_calls'] != config['max_calls']-(index-1)):
            errors.append('global budget before request differs: ' + call['path'])
        if type(call.get('input_tokens')) is int and type(call.get('output_tokens')) is int:
            known_total += call['input_tokens'] + call['output_tokens']
        if after['recorded_total_tokens'] != known_total or after['attempted_calls'] != index:
            errors.append('global budget after request differs: ' + call['path'])
        if after['pending']:
            errors.append('terminal call still pending: ' + call['path'])
    final_budget = summary['budget']
    if (final_budget['recorded_total_tokens'] != known_total
            or final_budget['attempted_calls'] != len(summary['calls'])
            or final_budget['usage_complete'] != summary['usage_complete'] or final_budget['pending']):
        errors.append('final shared ledger differs')
    initial_patch = run/'artifact_versions/initial/final.patch'
    state = CompletionState(units, hashlib.sha256(initial_patch.read_bytes()).hexdigest())
    if len(summary['turns']) > len(summary['calls']):
        errors.append('more turns than model calls')
    for index, turn in enumerate(summary['turns'], 1):
        directory = run/'artifact_versions'/f'{index:03d}'
        event = read(directory/'turn.json')
        actual_hash = hashlib.sha256((directory/'final.patch').read_bytes()).hexdigest()
        unit = units[(index-1) % len(units)]
        if event['turn'] != index or event['unit'] != unit:
            errors.append(f'wrong turn identity: {index}')
        changed = state.observe_artifact(actual_hash)
        operations = event['operations']
        vote = False
        if len(operations) == 1:
            output = operations[0]['result']
            lines = output['output'].lstrip().splitlines()
            vote = bool(lines and lines[0].strip() == 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT' and output['returncode'] == 0)
        if vote:
            state.vote(unit, actual_hash)
        expected = state.snapshot()
        if event['artifact'] != expected or turn['artifact'] != expected:
            errors.append(f'completion does not match observed artifact: {index}')
        if event['artifact_changed'] != changed or event['completion_vote_accepted'] != vote:
            errors.append(f'completion decision differs: {index}')
    if summary.get('stop_reason') == 'submitted':
        if not state.complete or state.artifact_sha256 != summary.get('artifact_sha256'):
            errors.append('submitted without all votes on final artifact')
    if summary.get('completion') is not None and summary['completion'] != state.snapshot():
        errors.append('final completion snapshot differs')
    return errors


def main():
    rows, pending = [], []
    for path in sorted((ROOT/'records/p3').glob('*/summary.json')):
        state = read(path)
        if 'wall_seconds' not in state or not state.get('container_removed'):
            pending.append(str(path.parent.relative_to(ROOT)))
            continue
        try:
            row = audit_run(path.parent)
            row['strategy'] = state['strategy']
            row['errors'].extend(audit_protocol(path.parent))
        except Exception as error:
            row = {'record': str(path.parent.relative_to(ROOT)), 'errors': ['audit could not read complete records: '+repr(error)]}
        rows.append(row)
    report = {'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'scope': 'P3 development runs only; excludes scripted p3_controls fixtures',
              'completed_runs': len(rows), 'runs': rows, 'pending': pending,
              'audit_errors': sum(len(r['errors']) for r in rows)}
    (ROOT/'reports/P3_task_audit.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'runs'}))
    return report['audit_errors'] == 0


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
