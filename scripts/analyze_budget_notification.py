"""Independent all-cell audit of P40; no task contents are published."""
import argparse
from collections import Counter
import json
from pathlib import Path

from analyze_handoff_factors import trial_row
from audit_budget_visibility import budget_before_calls
from budget_signal import ARMS, add_notification, digest
from inference_cache_control import cache_measurement
from profile_handoff_costs import summarize_calls
from run_handoff_factors import ROOT, read, sha


def validate_request(request, signal, arm, expected, first):
    if signal['notification_supplied'] != (arm == 'budget_keep'):
        raise ValueError('notification condition mismatch')
    messages = request['messages']
    base = messages[:-1] if arm == 'budget_keep' else messages
    if (digest(base) != signal['base_messages_sha256']
            or digest(messages) != signal['model_messages_sha256']
            or messages != add_notification(base, signal['state'], arm)):
        raise ValueError('actual model input is not the recorded budget intervention')
    for target, source in (('api_calls', 'remaining_api_before'),
                           ('model_calls', 'remaining_calls_before'),
                           ('logical_input_plus_output_tokens', 'remaining_tokens_before')):
        if signal['state']['remaining'][target] != expected[source]:
            raise ValueError('notification differs from accounted remaining budget')
    if request['cache_prompt'] != (not first) or signal['cache_prompt'] != request['cache_prompt']:
        raise ValueError('request cache policy differs')
    return {'notification_characters': len(messages[-1]['content']) if arm == 'budget_keep' else 0,
            'base_messages_sha256': digest(base), 'request_messages_sha256': digest(messages)}


def analyze(storage, root):
    plan = read(root / 'configs/P40_budget_notification_v01.json')
    state = read(storage / 'records/context_pilot' / plan['batch_id'] / 'status.json')
    expected_ids = {f'P40_{n:02d}_{a.upper()}' for n in range(1, 5) for a in ARMS}
    if (state['status'] != 'complete' or len(state['completed']) != 8
            or set(state['completed']) != expected_ids):
        raise ValueError('wait for all eight fixed cells and evaluations')
    original = read(root / plan['source_plan'])
    preflight = read(root / 'reports/P40_prefix_checks.json')
    rows = []
    for number, source in enumerate(plan['source_runs'], 1):
        for arm in ARMS:
            rid = f'P40_{number:02d}_{arm.upper()}'
            folder = storage / 'records/context_pilot' / rid
            row = trial_row(folder, original, source)
            if row['arm'] != arm or row['task_id'] != original['task_ids'][number - 1]:
                raise ValueError('wrong task/condition')
            usage, events = read(folder / 'usage.json'), read(folder / 'events.json')
            limits = read(folder / 'plan.json')
            before, _ = budget_before_calls(usage, events, row['prefix_api_requests'], limits)
            signals = read(folder / 'budget_signals.json')
            attempted = [s for s in signals if s['model_attempted']]
            if ([s['next_call_id'] for s in attempted] != [c['id'] for c in usage]
                    or len(signals) - len(attempted) not in (0, 1)
                    or (len(signals) > len(attempted) and signals[-1]['model_attempted'])):
                raise ValueError('signal/model call correspondence differs')
            checks = []
            for index, (call, signal, budget) in enumerate(zip(usage, attempted, before)):
                p = folder / call['id']; request = read(p / 'request.json')
                check = validate_request(request, signal, arm, budget, index == 0)
                check.update(call_id=call['id'], remaining=signal['state']['remaining'],
                             request_sha256=sha(p / 'request.json'), response_sha256=sha(p / 'response.json'))
                if index == 0:
                    measured = read(p / 'response.json')
                    cache = cache_measurement('cold_1', measured, measured['input_tokens'])
                    if not cache['state_confirmed'] or cache != signal['first_input_measurement']:
                        raise ValueError('first-input cache verification differs')
                    if check['base_messages_sha256'] != preflight['rows'][number - 1]['base_messages_sha256']:
                        raise ValueError('initial base input differs from fixed preparation')
                checks.append(check)
            profile = summarize_calls(usage, lambda cid: read(folder / cid / 'response.json'),
                                      lambda cid: read(folder / cid / 'request.json'))
            if profile['totals']['known_total_tokens'] != row['known_total_tokens']:
                raise ValueError('profile accounting differs')
            row.update(input_tokens=profile['totals']['input_tokens'],
                       output_tokens=profile['totals']['output_tokens'],
                       processed_input_tokens=profile['totals']['processed_input_tokens'],
                       cached_input_tokens=profile['totals']['cached_input_tokens'],
                       prompt_seconds=profile['totals']['prompt_seconds'],
                       decode_seconds=profile['totals']['decode_seconds'],
                       first_input_tokens=usage[0]['input_tokens'],
                       notification_characters=sum(c['notification_characters'] for c in checks),
                       signals_checked=checks, signal_source_sha256=sha(folder / 'budget_signals.json'))
            rows.append(row)
    totals = {}
    for arm in ARMS:
        selected = [r for r in rows if r['arm'] == arm]
        total = {'trials': len(selected), 'successes': sum(r['success'] for r in selected)}
        for key in ('model_calls', 'known_total_tokens', 'unknown_usage_calls', 'api_requests',
                    'prefix_api_requests', 'setup_api_requests', 'input_tokens', 'output_tokens',
                    'processed_input_tokens', 'cached_input_tokens', 'prompt_seconds', 'decode_seconds',
                    'notification_characters', 'continuation_wall_seconds', 'full_wall_seconds'):
            total[key] = sum(r[key] for r in selected)
        total['stop_reasons'] = dict(Counter(r['stop_reason'] for r in selected))
        totals[arm] = total
    pairs = []
    for number in range(4):
        a, b = rows[number * 2:number * 2 + 2]
        if (a['source_boundary_sha256'] != b['source_boundary_sha256'] or
                a['signals_checked'][0]['base_messages_sha256'] != b['signals_checked'][0]['base_messages_sha256']):
            raise ValueError('paired conditions do not start from the same base state/input')
        pairs.append({'task_id': a['task_id'], 'plain_success': a['success'], 'notified_success': b['success'],
                      'notified_minus_plain_tokens': b['known_total_tokens'] - a['known_total_tokens'],
                      'notified_minus_plain_api': b['api_requests'] - a['api_requests'],
                      'notified_minus_plain_calls': b['model_calls'] - a['model_calls']})
    return {'phase': 'P40', 'all_eight_reviewed': True, 'audit_errors': [], 'rows': rows,
            'totals': totals, 'paired_results': pairs, 'independent_task_count': 4,
            'novel_method_claim': False, 'general_quality_preservation_claim': False,
            'source_sha256': {'plan': sha(root / 'configs/P40_budget_notification_v01.json'),
                'activation': sha(root / 'reports/P40_activation_v01.json'),
                'batch_status': sha(storage / 'records/context_pilot' / plan['batch_id'] / 'status.json'),
                'analysis_script': sha(Path(__file__))},
            'limits': ['Four previously inspected development tasks, one continuation per condition.',
                       'Notification is an existing baseline intervention; no novelty claim.',
                       'No hypothesis test or non-inferiority claim from repeated calls within a task.',
                       'Historical runs had a different initial cache policy; they are not paired controls.'],
            'additional_model_calls': 0, 'additional_api_requests': 0, 'additional_evaluator_calls': 0}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT); a = p.parse_args()
    target = a.repo_root / 'reports/P40_comparison.json'
    if target.exists(): raise FileExistsError('preserve original comparison')
    result = analyze(a.storage_root, a.repo_root)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result['totals'], ensure_ascii=False))
