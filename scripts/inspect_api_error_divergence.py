"""Post-hoc first-divergence description for all four closed P78 pairs.

Only equality and structural field names are published. Saved model requests
are compared mechanically; private reasoning is never interpreted or emitted.
No saved program is executed, no tokenization or model/API call is performed.
"""
import argparse
import copy
from pathlib import Path

from api_error_comparison import ARMS, add_notification
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def field_differences(a, b, path='$'):
    if type(a) is not type(b):
        return [path]
    if isinstance(a, dict):
        return [p for key in sorted(set(a) | set(b)) for p in
                ([path + '.' + key] if key not in a or key not in b else
                 field_differences(a[key], b[key], path + '.' + key))]
    if isinstance(a, list):
        if len(a) != len(b):
            return [path + '.length']
        return [p for i, (x, y) in enumerate(zip(a, b))
                for p in field_differences(x, y, f'{path}[{i}]')]
    return [] if a == b else [path]


def without_wall_snapshot(request, state):
    expected = add_notification([], state)[0]
    if request['messages'][-1] != expected:
        raise ValueError('actual_budget_notice_does_not_match_saved_snapshot')
    result, normalized = copy.deepcopy(request), copy.deepcopy(state)
    normalized['remaining']['wall_seconds_at_snapshot'] = 0
    result['messages'][-1] = add_notification([], normalized)[0]
    return result


def public_output(response):
    if response['status'] != 'ok':
        return None
    message = response['message']
    # IDs are transport references, not the generated function name/arguments.
    return {'content': message.get('content'),
            'functions': [call['function'] for call in (message.get('tool_calls') or [])],
            'done_reason': response['done_reason']}


def describe_pair(left, right, first_errors):
    for number, (a, b) in enumerate(zip(left, right), 1):
        if a['response']['status'] != 'ok' or b['response']['status'] != 'ok':
            return {'first_unmatched_call': number, 'reason': 'unknown_response',
                    'divergence_before_any_API_exception': None}
        request_equal = a['request'] == b['request']
        output_equal = public_output(a['response']) == public_output(b['response'])
        if not request_equal or not output_equal:
            return {'first_unmatched_call': number,
                'actual_request_structures_equal': request_equal,
                'requests_equal_after_only_wall_snapshot_normalization':
                    without_wall_snapshot(a['request'], a['state']) ==
                    without_wall_snapshot(b['request'], b['state']),
                'request_differing_fields': field_differences(a['request'], b['request']),
                'generated_public_output_equal_ignoring_transport_ids': output_equal,
                'remaining_wall_seconds': [x['state']['remaining']['wall_seconds_at_snapshot'] for x in (a, b)],
                # A program's API errors occur after that call's model response.
                'divergence_before_any_API_exception': all(e is None or number <= e for e in first_errors)}
    return {'first_unmatched_call': None, 'equal_compared_call_count': min(len(left), len(right)),
            'same_call_count': len(left) == len(right),
            'divergence_before_any_API_exception': None}


def inspect(storage, root):
    target = root / 'reports/P78_input_divergence.json'
    if target.exists():
        raise FileExistsError('preserve_posthoc_divergence_inspection')
    report = read(root / 'reports/P78_comparison.json')
    profile = read(root / 'reports/P78_call_profile.json')
    if (report['audit_errors'] or report['batch_status'] not in ('complete', 'stopped')
            or len(report['rows']) != 8
            or profile['comparison_sha256'] != sha(root / 'reports/P78_comparison.json')):
        raise ValueError('closed_audited_all_condition_records_required')
    pairs, fingerprints = [], {}
    for task in dict.fromkeys(r['task_id'] for r in report['rows']):
        cells = {r['arm']: r for r in report['rows'] if r['task_id'] == task}
        sequences, first_errors = [], []
        for arm in ARMS:
            row = cells[arm]; folder = storage / 'records/context_pilot' / row['run_id']
            if row['record_status'] not in ('evaluated', 'unevaluated'):
                sequences.append(None); first_errors.append(None); continue
            calls = [c for c in profile['calls'] if c['run_id'] == row['run_id']]
            first_errors.append(next((i for i, c in enumerate(calls, 1) if c['api_invocation_exceptions']), None))
            signal_path = folder / 'budget_signals.json'
            signals = [s for s in (read(signal_path) if signal_path.exists() else []) if s['model_attempted']]
            checks = row['request_checks']
            if ([s['next_call_id'] for s in signals] != [c['call_id'] for c in checks]
                    or [c['call_id'] for c in calls] != [c['call_id'] for c in checks]):
                raise ValueError('call_correspondence_changed')
            fingerprints[row['run_id']] = sha(signal_path) if signal_path.exists() else None
            sequence = []
            for check, signal in zip(checks, signals, strict=True):
                paths = [folder / check['call_id'] / (key + '.json') for key in ('request', 'response')]
                if any(sha(p) != check[key + '_sha256'] for p, key in zip(paths, ('request', 'response'))):
                    raise ValueError('audited_request_or_response_changed')
                request, response = map(read, paths)
                without_wall_snapshot(request, signal['state'])
                sequence.append({'request': request, 'response': response, 'state': signal['state']})
            sequences.append(sequence)
        comparison = (describe_pair(*sequences, first_errors) if all(s is not None for s in sequences)
                      else {'comparison_available': False})
        pairs.append({'task_id': task, 'first_API_exception_model_call_by_arm': first_errors, **comparison})
    result = {'phase': 'P78', 'posthoc_description': True, 'pairs': pairs,
        'comparison_sha256': sha(root / 'reports/P78_comparison.json'),
        'profile_sha256': sha(root / 'reports/P78_call_profile.json'),
        'budget_signal_sha256': fingerprints, 'script_sha256': sha(Path(__file__)),
        'additional_generations': 0, 'additional_api_calls': 0, 'additional_evaluations': 0,
        'additional_tokenizations': 0, 'saved_programs_executed': 0,
        'private_reasoning_inspected_semantically': False, 'causal_effect_identified': False,
        'interpretation': 'All four pairs are compared by original model-call index until the first differing request or generated public output. Only the current budget notice wall-time field is normalized in the separate normalized equality check. Requests are compared as JSON, not retokenized prompts. No post-divergence alignment, private-reasoning interpretation, latent-state equality or causal effect is inferred. The original development gate is unchanged.'}
    write_json(target, result)
    print(pairs)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT)
    a = p.parse_args(); inspect(a.storage_root, a.repo_root)
