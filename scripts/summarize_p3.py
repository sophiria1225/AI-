"""Describe observable P3 work and cost without inferring causal dependencies."""
from collections import Counter
import datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def summarize_observations(summary, events):
    units = {}
    for call in summary['calls']:
        unit = units.setdefault(call['unit'], {'calls': 0, 'input_tokens': 0,
            'output_tokens': 0, 'unknown_usage_calls': 0, 'tools': 0, 'tool_nonzero_exits': 0,
            'tool_timeouts': 0, 'observed_artifact_changes': 0, 'accepted_completion_votes': 0})
        unit['calls'] += 1
        if type(call.get('input_tokens')) is int and type(call.get('output_tokens')) is int:
            unit['input_tokens'] += call['input_tokens']
            unit['output_tokens'] += call['output_tokens']
        else:
            unit['unknown_usage_calls'] += 1
    for tool in summary['tools']:
        unit = units[tool['unit']]
        unit['tools'] += 1
        unit['tool_nonzero_exits'] += int(tool.get('exit_code_known') is True and tool.get('exit_code') != 0)
        unit['tool_timeouts'] += int(tool.get('timed_out') is True)
    prior_votes = {}
    invalidations = 0
    commands = Counter()
    for event in events:
        unit = units[event['unit']]
        if event['artifact_changed']:
            unit['observed_artifact_changes'] += 1
            invalidations += len(prior_votes)
        unit['accepted_completion_votes'] += int(event['completion_vote_accepted'])
        prior_votes = event['artifact']['votes']
        for operation in event['operations']:
            commands[operation['command']] += 1
    for unit in units.values():
        unit['known_total_tokens'] = unit['input_tokens'] + unit['output_tokens']
    return {'per_unit': units, 'turns_with_saved_artifact': len(events),
            'format_error_turns': sum(bool(e['format_error']) for e in events),
            'invalidated_completion_votes': invalidations,
            'repeated_identical_commands_after_first': sum(max(n - 1, 0) for n in commands.values()),
            'known_total_tokens': sum(u['known_total_tokens'] for u in units.values()),
            'unknown_usage_calls': sum(u['unknown_usage_calls'] for u in units.values()),
            'interpretation': 'Changes are observed only at turn boundaries. Repeated commands may be necessary '
                              'after edits; nonzero test exits can be useful observations. These counts do not '
                              'identify unnecessary work, information loss, or causal task dependencies.'}


def main():
    rows, pending, incomplete = [], [], []
    for path in sorted((ROOT / 'records/p3').glob('*/summary.json')):
        summary = read(path)
        record = str(path.parent.relative_to(ROOT))
        if not summary.get('container_removed') or 'wall_seconds' not in summary:
            pending.append(record)
            continue
        try:
            config = read(path.parent / 'config.json')
            events = [read(p) for p in sorted((path.parent / 'artifact_versions').glob('*/turn.json'))]
            observations = summarize_observations(summary, events)
            if observations['known_total_tokens'] != summary['total_recorded_tokens']:
                raise ValueError('per-unit known usage differs from global ledger')
            if len(events) != len(summary['turns']):
                raise ValueError('event files differ from recorded turn count')
            evaluation_path = path.parent / 'final_evaluation_summary.json'
            row = {'record': record, 'strategy': summary['strategy'], 'task': summary['instance_id'],
                   'model': config['model'], 'context': config['num_ctx'],
                   'cache_type_k': config.get('cache_type_k', 'f16'), 'cache_type_v': config.get('cache_type_v', 'f16'),
                   'stop_reason': summary['stop_reason'], 'wall_seconds': summary['wall_seconds'],
                   'artifact_sha256': summary.get('artifact_sha256'),
                   'visible_checks_all_passed': summary.get('visible_checks', {}).get('all_passed'),
                   'evaluation': read(evaluation_path) if evaluation_path.exists() else None,
                   **observations}
            rows.append(row)
        except Exception as error:
            incomplete.append({'record': record, 'error': repr(error)})
    report = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'scope': 'P3 development observations only; scripted controls excluded; no causal-effect estimate',
              'runs': rows, 'pending': pending, 'incomplete_reports': incomplete,
              'audit_required': 'Use audit_p3.py to check raw usage, settings, artifact and completion invariants.'}
    (ROOT / 'reports/P3_measurements.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'completed_runs': len(rows), 'pending': len(pending), 'incomplete_reports': len(incomplete)}))
    return not incomplete


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
