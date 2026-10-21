"""Completed-batch budget diagnostics; no evaluator, inference, or world execution."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from audit_inference_costs import timing_row


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def trial_budget(directory):
    plan, summary, usage, events = [read(directory / name) for name in
                                    ('plan.json', 'summary.json', 'usage.json', 'events.json')]
    if summary['arm'] != 'native_roles' or plan['arms'] != ['native_roles']:
        raise ValueError('requires the unchanged full-history native baseline')
    required = ('max_calls', 'max_api_requests', 'max_total_tokens', 'max_wall_seconds',
                'max_output_tokens')
    if any(type(plan[k]) is not int or plan[k] <= 0 for k in required):
        raise ValueError('invalid budget')
    rows = [timing_row(u, read(directory / u['id'] / 'response.json')) for u in usage]
    known = [r for r in rows if r['status'] == 'ok']
    total = sum(r['input_tokens'] + r['output_tokens'] for r in known)
    api_calls = sum(bool(e['api_request_sent']) for e in events)
    if (len(rows) != summary['model_calls'] or total != summary['known_total_tokens']
            or api_calls != summary['api_requests'] or len(events) != summary['tool_turns']):
        raise ValueError('terminal counts disagree with original records')
    if len(rows) > plan['max_calls'] or api_calls > plan['max_api_requests']:
        raise ValueError('dispatched calls exceed fixed budget')
    if total > plan['max_total_tokens']:
        raise ValueError('known usage exceeds fixed budget')
    if any(r['role'] != 'agent' for r in rows):
        raise ValueError('unexpected additional model role in full-history baseline')
    call_ids = {u['id'] for u in usage}
    if len(call_ids) != len(usage) or any(e['call'] not in call_ids for e in events):
        raise ValueError('ambiguous or missing generating call')
    finished_ids = {u['id'] for u in usage if u['status'] == 'ok'}
    if any(e['call'] not in finished_ids for e in events):
        raise ValueError('unknown model result has recorded operations')
    per_call = Counter(e['call'] for e in events if e['api_request_sent'])
    timed = [r for r in rows if r['timing_available']]
    reasons = {'completed', 'declared_complete', 'agent_declared_complete', 'runtime_error',
               'call_limit', 'api_request_limit',
               'wall_limit', 'wall_limit_during_count', 'wall_limit_during_model_call',
               'context_limit', 'token_reservation_limit', 'checkpoint_storage_limit'}
    reason = summary['stop_reason']
    # Unrecognized exception strings may contain response values; do not export them.
    safe_reason = reason if reason in reasons else 'other_stop_reason_not_exported'
    files = ['plan.json', 'summary.json', 'usage.json', 'events.json']
    return {
        'run_id': summary['run_id'], 'stop_reason': safe_reason,
        'declared_complete': summary['declared_complete'],
        'limits': {k: plan[k] for k in required},
        'model_calls': len(rows), 'api_requests': api_calls,
        'known_total_tokens': total, 'unknown_usage_calls': len(rows) - len(known),
        'unused_token_capacity_based_on_known_usage': plan['max_total_tokens'] - total,
        'unused_capacity_is_exact': len(known) == len(rows),
        'peak_known_input_tokens': max((r['input_tokens'] for r in known), default=0),
        'wall_seconds': summary['wall_seconds'],
        'wall_seconds_over_limit': max(0, summary['wall_seconds'] - plan['max_wall_seconds']),
        'max_api_requests_in_one_response': max(per_call.values(), default=0),
        'responses_sending_multiple_api_requests': sum(n > 1 for n in per_call.values()),
        'output_limit_finishes': sum(u.get('finish_reason') == 'length' for u in usage),
        'timed_calls': len(timed),
        'cached_input_tokens_in_timed_calls': sum(r['cached_tokens'] for r in timed),
        'processed_input_tokens_in_timed_calls': sum(r['processed_input_tokens'] for r in timed),
        'prefill_seconds_in_timed_calls': sum(r['prefill_seconds'] for r in timed),
        'decode_seconds_in_timed_calls': sum(r['decode_seconds'] for r in timed),
        'call_wall_seconds_known': sum(r['call_wall_seconds'] for r in known),
        'call_wall_seconds_unknown': sum(r['call_wall_seconds'] for r in rows if r['status'] != 'ok'),
        'source_sha256': {n: digest(directory/n) for n in files},
        'response_sha256': {u['id']: digest(directory/u['id']/'response.json') for u in usage},
    }


def analyze(storage, plan_path):
    plan = read(plan_path)
    batch = storage / 'records/context_pilot' / plan['batch_id']
    if read(batch/'status.json')['status'] != 'complete':
        raise ValueError('all fixed trials must finish before batch interpretation')
    if read(batch/'plan.json') != plan:
        raise ValueError('plan differs from the executed batch')
    directories = [storage/'records/context_pilot'/r[2] for r in plan['run_order']]
    # Check the entire cohort before reading any individual outcome.
    for path, (task_id, arm, run_id) in zip(directories, plan['run_order'], strict=True):
        if not (path/'summary.json').is_file() or not (path/'evaluation.json').is_file():
            raise ValueError('an execution or independent evaluation is not terminal')
        summary = read(path/'summary.json')
        if (summary['task_id'], summary['arm'], summary['run_id']) != (task_id, arm, run_id):
            raise ValueError('cohort identity differs')
        if read(path/'plan.json') != plan:
            raise ValueError('individual trial did not use the frozen batch plan')
    return {
        'phase': plan['phase'], 'trials': [trial_budget(p) for p in directories],
        'plan_sha256': digest(plan_path), 'batch_status_sha256': digest(batch/'status.json'),
        'analysis_source_sha256': {n: digest(Path(__file__).parent/n) for n in
                                   ('analyze_native_budget.py', 'audit_inference_costs.py')},
        'model_calls': 0, 'environment_requests': 0, 'evaluator_contents_read': False,
        'scope': 'Descriptive budget use, not a proof of minimum task cost or a causal failure label. '
                 'Unused tokens do not imply a legal next call: input plus output reservation may not fit. '
                 'Unknown usage stays unknown; server timings do not include all execution overhead. '
                 'API calls within one response are counted individually. '
                 'No task text, arguments, observations, reasoning or private evaluator details exported.',
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    report = analyze(args.storage_root, args.plan)
    with args.output.open('x') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({'phase': report['phase'], 'trials': len(report['trials']),
                      'model_calls': 0, 'evaluator_contents_read': False}))


if __name__ == '__main__':
    main()
