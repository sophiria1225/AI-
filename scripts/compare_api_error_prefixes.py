"""Compare public API prefixes for all four P78 pairs, after the batch closes.

This is descriptive matching, not proof of equal model inputs, Python heaps,
RNG state or causal effects. Normalize only the declared error presentation.
No request values or exception messages are emitted in the public report.
"""
import argparse
import hashlib
import json
from pathlib import Path

from api_error_comparison import ARMS
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def digest(value):
    # Preserve string content and dictionary insertion order as observed.
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def signature(event, span, arm):
    receipt = event['api_execution']; observation = span['observation']
    status = receipt['status']
    if status == 'returned':
        result = json.loads(observation['observation'])
    elif status == 'raised':
        result = (json.loads(observation['observation']) if arm == 'error_value'
                  else observation['api_error'])
        if type(result) is not str:
            raise ValueError('confirmed_exception_requires_original_text')
    elif status == 'unknown':
        return None
    else:
        raise ValueError('unexpected_dispatched_result_status')
    return {'request_sha256': digest(span['action']),
            'result_sha256': digest({'status': status, 'value_or_error': result,
                                     'declared_complete': receipt['declared_complete']})}


def compare(left, right):
    matched, count, first_exception = [], 0, None
    for a, b in zip(left, right):
        if a['signature'] is None or b['signature'] is None or a['signature'] != b['signature']:
            break
        count += 1
        matched.append({'api_index': count, 'api': a['api'], 'status': a['status'],
                        'value_call_id': a['call_id'], 'exception_call_id': b['call_id']})
        if first_exception is None and a['status'] == 'raised':
            first_exception = count
    return {'matched_initial_api_requests_and_results': count,
        'value_total_sent_requests': len(left), 'exception_total_sent_requests': len(right),
        'whole_public_api_sequences_equal': count == len(left) == len(right),
        'first_matched_invocation_exception_api_index': first_exception,
        'next_value_api': left[count]['api'] if count < len(left) else None,
        'next_exception_api': right[count]['api'] if count < len(right) else None,
        'matched_prefix': matched, 'model_inputs_or_python_state_proven_equal': False,
        'causal_effect_identified': False}


def run(storage, root):
    target = root / 'reports/P78_public_api_prefixes.json'
    if target.exists():
        raise FileExistsError('preserve_public_prefix_inspection')
    report = read(root / 'reports/P78_comparison.json')
    profile = read(root / 'reports/P78_call_profile.json')
    if (report['audit_errors'] or report['batch_status'] not in ('complete', 'stopped')
            or len(report['rows']) != 8
            or profile['comparison_sha256'] != sha(root / 'reports/P78_comparison.json')):
        raise ValueError('closed_audited_all_condition_records_required')
    pairs = []
    for task in dict.fromkeys(row['task_id'] for row in report['rows']):
        cells = {r['arm']: r for r in report['rows'] if r['task_id'] == task}
        sequences = []
        for arm in ARMS:
            cell = cells[arm]
            if cell['record_status'] not in ('evaluated', 'unevaluated'):
                sequences.append(None); continue
            folder = storage / 'records/context_pilot' / cell['run_id']
            for name in ('events.json', 'spans.json'):
                if sha(folder / name) != profile['private_record_sha256'][cell['run_id']][name]:
                    raise ValueError('public_record_changed_since_whole_cohort_profile')
            events, spans = read(folder / 'events.json'), read(folder / 'spans.json')
            sequence = []
            for event in events:
                if not event['api_request_sent']:
                    continue
                span = spans[event['span_id']]
                sequence.append({'call_id': event['call'], 'api': span['action']['name'],
                                 'status': event['api_execution']['status'],
                                 'signature': signature(event, span, arm)})
            sequences.append(sequence)
        result = compare(*sequences) if all(s is not None for s in sequences) else {'comparison_available': False}
        first = [cells[arm].get('request_checks', []) for arm in ARMS]
        first_equal = (first[0][0]['request_sha256'] == first[1][0]['request_sha256']
                       if all(first) else None)
        pairs.append({'task_id': task, **result,
                      'actual_initial_request_bytes_equal': first_equal})
    result = {'phase': 'P78', 'pairs': pairs, 'comparison_sha256': sha(root / 'reports/P78_comparison.json'),
        'call_profile_sha256': sha(root / 'reports/P78_call_profile.json'),
        'script_sha256': sha(Path(__file__)), 'additional_model_calls': 0, 'additional_api_calls': 0,
        'additional_evaluations': 0, 'private_reasoning_read': False,
        'interpretation': 'The initial sequence of sent public API requests and actual returned values or confirmed exception text is compared, normalizing the declared exception presentation. The first actual model request is compared separately using frozen-audit file hashes. Preflight input equality is at elapsed time zero; live resource notices use measured remaining time. Neither equal first requests nor API prefixes prove equal later model inputs, Python state, latent computation or counterfactual behavior.'}
    write_json(target, result)
    print([{k: p.get(k) for k in ('task_id', 'matched_initial_api_requests_and_results',
                                'first_matched_invocation_exception_api_index')} for p in pairs])
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT)
    a = p.parse_args(); run(a.storage_root, a.repo_root)
