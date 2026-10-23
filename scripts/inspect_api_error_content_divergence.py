"""Separate transport-reference renaming from P78 request-content differences.

The raw-JSON inspection remains untouched. This additional post-hoc report
does not tokenize requests or identify causal effects of failure presentation.
"""
import argparse
import copy
from pathlib import Path

from api_error_comparison import ARMS
from inspect_api_error_divergence import describe_pair, without_wall_snapshot
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def canonical_transport_references(request):
    result, references = copy.deepcopy(request), {}
    for message in result['messages']:
        for call in (message.get('tool_calls') or []):
            ident = call['id']
            if type(ident) is not str or not ident or ident in references:
                raise ValueError('tool_call_reference_must_be_unique_and_nonempty')
            references[ident] = 'transport_reference_' + str(len(references) + 1)
            call['id'] = references[ident]
        if 'tool_call_id' in message:
            ident = message['tool_call_id']
            if ident not in references:
                raise ValueError('tool_result_reference_has_no_prior_call')
            message['tool_call_id'] = references[ident]
    return result


def inspect(storage, root):
    target = root / 'reports/P78_input_content_divergence.json'
    if target.exists(): raise FileExistsError('preserve_content_divergence_inspection')
    report = read(root / 'reports/P78_comparison.json')
    profile = read(root / 'reports/P78_call_profile.json')
    raw = read(root / 'reports/P78_input_divergence.json')
    if (report['audit_errors'] or report['batch_status'] not in ('complete', 'stopped')
            or len(report['rows']) != 8
            or any(x['comparison_sha256'] != sha(root / 'reports/P78_comparison.json') for x in (profile, raw))
            or raw['profile_sha256'] != sha(root / 'reports/P78_call_profile.json')):
        raise ValueError('closed_all_condition_audit_profile_and_raw_inspection_required')
    pairs = []
    for task in dict.fromkeys(r['task_id'] for r in report['rows']):
        cells = {r['arm']: r for r in report['rows'] if r['task_id'] == task}
        sequences, first_errors = [], []
        for arm in ARMS:
            row = cells[arm]; folder = storage / 'records/context_pilot' / row['run_id']
            if row['record_status'] not in ('evaluated', 'unevaluated'):
                sequences.append(None); first_errors.append(None); continue
            calls = [c for c in profile['calls'] if c['run_id'] == row['run_id']]
            first_errors.append(next((i for i, c in enumerate(calls, 1) if c['api_invocation_exceptions']), None))
            path = folder / 'budget_signals.json'
            if (sha(path) if path.exists() else None) != raw['budget_signal_sha256'][row['run_id']]:
                raise ValueError('saved_budget_signals_changed')
            signals = [s for s in (read(path) if path.exists() else []) if s['model_attempted']]
            checks = row['request_checks']
            if ([s['next_call_id'] for s in signals] != [c['call_id'] for c in checks]
                    or [c['call_id'] for c in calls] != [c['call_id'] for c in checks]):
                raise ValueError('call_correspondence_changed')
            sequence = []
            for check, signal in zip(checks, signals, strict=True):
                paths = [folder / check['call_id'] / (key + '.json') for key in ('request', 'response')]
                if any(sha(p) != check[key + '_sha256'] for p, key in zip(paths, ('request', 'response'))):
                    raise ValueError('audited_request_or_response_changed')
                request, response = map(read, paths)
                without_wall_snapshot(request, signal['state'])
                sequence.append({'request': canonical_transport_references(request),
                                 'response': response, 'state': signal['state']})
            sequences.append(sequence)
        comparison = (describe_pair(*sequences, first_errors) if all(s is not None for s in sequences)
                      else {'comparison_available': False})
        if 'actual_request_structures_equal' in comparison:
            comparison['requests_equal_after_transport_id_renaming'] = comparison.pop('actual_request_structures_equal')
            comparison['requests_equal_after_transport_ids_and_wall_snapshot_normalization'] = comparison.pop(
                'requests_equal_after_only_wall_snapshot_normalization')
        pairs.append({'task_id': task, 'first_API_exception_model_call_by_arm': first_errors, **comparison})
    result = {'phase': 'P78', 'posthoc_description': True, 'pairs': pairs,
        'comparison_sha256': sha(root / 'reports/P78_comparison.json'),
        'profile_sha256': sha(root / 'reports/P78_call_profile.json'),
        'raw_divergence_sha256': sha(root / 'reports/P78_input_divergence.json'),
        'script_sha256': sha(Path(__file__)),
        'shared_inspector_sha256': sha(root / 'scripts/inspect_api_error_divergence.py'),
        'additional_generations': 0, 'additional_api_calls': 0, 'additional_evaluations': 0,
        'additional_tokenizations': 0, 'saved_programs_executed': 0,
        'private_reasoning_inspected_semantically': False, 'causal_effect_identified': False,
        'interpretation': 'A second description preserving the raw inspection. Only declared tool-call IDs and their linked result references are consistently renamed; generated text, arguments, reasoning and all other request fields remain intact. A separate equality check also normalizes the current wall-time snapshot. No retokenization, model-state equality, post-divergence alignment or causal attribution is claimed.'}
    write_json(target, result); print(pairs)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT)
    a = p.parse_args(); inspect(a.storage_root, a.repo_root)
