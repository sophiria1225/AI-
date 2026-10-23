"""Mechanical comparison of all same-condition repetition pairs; no inference."""
import argparse
import copy
from itertools import combinations
from pathlib import Path

from budget_observation import notification
from budget_signal import digest
from clock_notice_replay import output_fingerprints
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def compare_traces(left, right):
    pairs = list(zip(left['calls'], right['calls']))
    complete = left['known_complete'] and right['known_complete']
    same_length = len(left['calls']) == len(right['calls'])

    def first_difference(key):
        return next((i for i, (a, b) in enumerate(pairs, 1)
                     if a.get(key) is not None and b.get(key) is not None and a[key] != b[key]), None)

    first_input = first_difference('request_sha256')
    current_wall_only = None
    if first_input is not None:
        a, b = pairs[first_input - 1]
        current_wall_only = (a['without_current_wall_sha256'] is not None
                            and a['without_current_wall_sha256'] == b['without_current_wall_sha256'])
    same = lambda key: (same_length and all(a[key] == b[key] for a, b in pairs)) if complete else None
    return {'run_ids': [left['run_id'], right['run_id']], 'both_known_complete': complete,
        'call_counts': [len(left['calls']), len(right['calls'])], 'same_call_count': same_length,
        'compared_prefix_calls': len(pairs), 'all_requests_equal': same('request_sha256'),
        'all_public_outputs_equal': same('public_output_sha256'),
        'all_opaque_messages_equal': same('opaque_message_sha256'),
        'first_request_difference': first_input,
        'first_request_difference_is_current_wall_only': current_wall_only,
        'first_public_output_difference': first_difference('public_output_sha256'),
        'first_opaque_message_difference': first_difference('opaque_message_sha256'),
        'first_call_present_in_only_one_run': len(pairs) + 1 if not same_length else None,
        'model_visible_token_sequences_compared': False, 'causal_timing_effect_identified': False}


def trace(storage, row):
    folder = storage / 'records/context_pilot' / row['run_id']
    if row['record_status'] not in ('evaluated', 'unevaluated'):
        return {'run_id': row['run_id'], 'calls': [], 'known_complete': False,
                'record_status': row['record_status']}
    notices_path = folder / 'budget_observations.json'
    notices = {s['next_call_id']: s for s in read(notices_path) if s['model_attempted']}
    calls = []
    for check in row['request_checks']:
        cid = check['call_id']; request = response = None
        for kind in ('request', 'response'):
            path = folder / cid / (kind + '.json')
            expected = check[kind + '_sha256']
            if (sha(path) if path.exists() else None) != expected:
                raise ValueError('audited_record_changed')
            if expected is not None:
                if kind == 'request': request = read(path)
                else: response = read(path)
        entry = {'call_id': cid, 'usage_status': check['status'],
                 'request_sha256': None, 'without_current_wall_sha256': None,
                 **output_fingerprints(response or {})}
        if request is not None:
            notice = notices[cid]
            expected = notification([], notice['measured_state'], row['time_visibility'])[0][0]
            if request['messages'][-1] != expected:
                raise ValueError('saved_current_budget_notice_disagrees')
            normalized, state = copy.deepcopy(request), copy.deepcopy(notice['measured_state'])
            state['remaining']['wall_seconds_at_snapshot'] = 0
            normalized['messages'][-1] = notification([], state, row['time_visibility'])[0][0]
            entry.update(request_sha256=digest(request), without_current_wall_sha256=digest(normalized))
        calls.append(entry)
    if len(calls) != row['model_calls'] or len(notices) != len(calls):
        raise ValueError('all_attempts_must_be_compared')
    return {'run_id': row['run_id'], 'calls': calls,
        'known_complete': row['record_status'] == 'evaluated' and row['unknown_usage_calls'] == 0
                          and all(c['request_sha256'] is not None and c['public_output_sha256'] is not None for c in calls),
        'record_status': row['record_status'], 'notices_sha256': sha(notices_path)}


def run(storage, root):
    path = root / 'reports/P81_repetitions.json'
    target = root / 'reports/P81_trajectory_stability.json'
    if target.exists(): raise FileExistsError('preserve_the_first_stability_analysis')
    report = read(path)
    if (report['batch_status'] not in ('complete', 'stopped') or report['audit_errors']
            or len(report['rows']) != 16 or len(report['anchor_rows']) != 8):
        raise ValueError('closed_audited_full_repetition_cohort_required')
    rows = [{**r, 'repetition': 1} for r in report['anchor_rows']] + report['rows']
    traces = {r['run_id']: trace(storage, r) for r in rows}
    pairs = []
    for group in report['groups']:
        if len(group['run_ids']) != 3: raise ValueError('three_fixed_repetitions_required')
        for a, b in combinations(group['run_ids'], 2):
            pairs.append({'task_id': group['task_id'], 'time_visibility': group['time_visibility'],
                          **compare_traces(traces[a], traces[b])})
    if len(pairs) != 24: raise ValueError('include_all_dependent_pairwise_comparisons')
    result = {'phase': 'P81_stability', 'pairs': pairs, 'traces': traces,
        'comparison_sha256': sha(path), 'inspector_sha256': sha(Path(__file__)),
        'private_reasoning_inspected_semantically': False,
        'additional_model_calls': 0, 'additional_api_calls': 0, 'additional_evaluations': 0,
        'tokenizations': 0, 'independent_tasks': 4, 'dependent_pairs': 24,
        'interpretation': 'Saved requests and output fingerprints only. Model tokens, historical GPU state and environmental state are not proved identical. Pairwise comparisons share runs.'}
    write_json(target, result)
    print({'pairs': len(pairs), 'runs': len(traces)})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    args = parser.parse_args()
    run(args.storage_root, args.repo_root)
