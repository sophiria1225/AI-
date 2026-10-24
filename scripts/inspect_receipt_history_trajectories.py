"""P113: inspect every P111 request, response and execution record; never replay."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import time

from inspect_input_exposure import check_resume
from inspect_recorded_action_agreement import sha, read_bound, verify_ci
from receipt_reasoning_history import require
from recorded_action_agreement import analyze_run, summarize_pairs
from receipt_history_trajectory import describe_call, compare_trajectories, EQUALITY_FIELDS, equality_summary

PLAN = 'configs/P113_receipt_history_trajectories_v01.json'
ZERO = ('model_generations', 'environment_API_requests', 'saved_code_executions',
        'evaluations', 'task_databases_read', 'reserved_scenarios_read')
FIXED = dict(phase='P113', source_audit='reports/P111_comparison.json',
    source_diagnosis='reports/P112_realized_history_inputs.json',
    source_session='reports/P111_server_session.json', cells=12, known_tasks=4,
    original_model_attempts=204, original_API_requests=610, original_known_logical_tokens=2026162,
    original_unknown_usage_calls=2, condition_pairs=12, aligned_positions=219,
    max_saved_calls_per_cell=80, max_events_per_cell=4000, max_file_bytes=16777216,
    max_total_private_input_bytes=536870912, max_wall_seconds=180, automatic_retries=0,
    alignment='same_generation_ordinal_union_not_semantic_correspondence',
    selection='all_P111_conditions_and_all_saved_attempts',
    private_reasoning_inspected_semantically=False, causal_effect_claim=False,
    semantic_equivalence_claim=False, novel_method_claim=False, **{k:0 for k in ZERO})


def read(path): return json.loads(path.read_text())
def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def inspect(storage, root):
    began = time.monotonic()
    plan = read(root/PLAN)
    require(all(type(plan.get(k)) is type(v) and plan[k] == v for k, v in FIXED.items()), 'fixed_P113_scope_changed')
    stop = storage/'.runtime/P113.stop'
    require(not stop.exists(), 'explicit_P113_stop')
    resume = check_resume(storage)
    for rel, expected in plan['source_sha256'].items():
        require(sha(root/rel) == expected, 'fixed_source_changed:'+rel)
    head, ci = verify_ci(root)
    audit, diagnosis, session = (read(root/plan[k]) for k in ('source_audit', 'source_diagnosis', 'source_session'))
    require(audit['batch_status'] == 'complete' and not audit['audit_errors'] and audit['owned_processes_absent']
            and session['status'] == 'stopped' and session['owned_processes_absent']
            and session['audit_source_sha256'] == sha(root/plan['source_audit']), 'closed_audited_P111_required')
    require(diagnosis['status'] == 'complete' and not diagnosis['errors']
            and diagnosis['completed_renderings'] == len(diagnosis['rows']) == 612
            and diagnosis['source_audit_sha256'] == sha(root/plan['source_audit']), 'complete_all_P112_inputs_required')
    require(len(audit['rows']) == 12 and [r['run_id'] for r in audit['rows']] == plan['run_ids'], 'all_twelve_conditions_required')
    require(all(not (storage/rel).exists() for rel in plan['absent_private_sources']), 'missing_private_source_was_added')
    require(sum((storage/rel).stat().st_size for rel in plan['private_source_sha256']) <= plan['max_total_private_input_bytes'],
            'total_private_input_bound')
    actual = {(r['run_id'], r['call_id']):r for r in diagnosis['rows'] if r['policy'] == r['actual_policy']}
    require(len(actual) == 204, 'every_original_attempt_required')
    fields = ('run_id', 'task_id', 'reasoning_display_policy', 'success', 'stop_reason', 'model_calls',
              'api_requests', 'known_total_tokens', 'unknown_usage_calls')
    result = dict(**FIXED, source_commit=head, ci=ci, research_resume=resume,
        plan_sha256=sha(root/PLAN), started_at=datetime.now(timezone.utc).isoformat(),
        status='incomplete', errors=[], runs=[dict(**{k:r[k] for k in fields},
            diagnosis_status='not_inspected', calls=[dict(call_id=c['call_id'], status='not_inspected')
                for c in r['request_checks']]) for r in audit['rows']], pairs=[],
        source_sha256=plan['source_sha256'], private_source_sha256=plan['private_source_sha256'],
        absent_private_sources=plan['absent_private_sources'], measured_savings=None,
        original_P111_gate_changed=False, full_state_equivalence_established=False)
    target = root/'reports/P113_receipt_history_trajectories.json'
    seen = set()
    def get(rel):
        path = storage/rel
        path.resolve().relative_to((storage/'records/context_pilot').resolve())
        require(not path.is_symlink(), 'private_source_symlink_rejected')
        if rel in plan['absent_private_sources']:
            require(not path.exists(), 'missing_private_source_was_added')
            return None
        require(rel in plan['private_source_sha256'], 'unbound_private_source')
        seen.add(rel)
        return read_bound(path, plan['private_source_sha256'][rel])
    try:
        for index, original in enumerate(audit['rows']):
            require(not stop.exists(), 'explicit_P113_stop')
            require(time.monotonic()-began < plan['max_wall_seconds'], 'finite_P113_deadline')
            rid = original['run_id']; prefix = 'records/context_pilot/'+rid+'/'
            usage, events, spans = (get(prefix+n+'.json') for n in ('usage', 'events', 'spans'))
            responses = {c['call_id']:get(prefix+c['call_id']+'/response.json') for c in original['request_checks']}
            described = analyze_run(usage, events, spans, responses)
            require(len(described) == original['model_calls']
                    and sum(c['API_requests'] for c in described) == original['api_requests']
                    and sum(c['known_total_tokens'] or 0 for c in described) == original['known_total_tokens']
                    and sum(c['known_total_tokens'] is None for c in described) == original['unknown_usage_calls'],
                    'original_cost_or_API_totals_changed')
            calls = []
            for call in described:
                require(not stop.exists(), 'explicit_P113_stop')
                cid = call['call_id']; inp = actual[rid, cid]
                require(inp['status'] == 'counted' and inp['actual_policy'] == original['reasoning_display_policy'],
                        'actual_counted_P112_input_required')
                request = get(prefix+cid+'/request.json')
                calls.append(describe_call(call, request, responses[cid], inp))
            result['runs'][index].update(diagnosis_status='complete', calls=calls)
        require(seen == set(plan['private_source_sha256']), 'every_bound_private_source_required')
        pairs = compare_trajectories(result['runs'])
        positions = [row for pair in pairs for row in pair['rows']]
        require(len(pairs) == 12 and len(positions) == 219, 'all_condition_pairs_and_tail_positions_required')
        require(sum(r['model_calls'] for r in result['runs']) == 204
                and sum(r['api_requests'] for r in result['runs']) == 610
                and sum(r['known_total_tokens'] for r in result['runs']) == 2026162
                and sum(r['unknown_usage_calls'] for r in result['runs']) == 2, 'whole_cohort_accounting_changed')
        for rel, expected in plan['private_source_sha256'].items():
            require(sha(storage/rel) == expected, 'private_source_changed_during_diagnosis')
        require(all(not (storage/rel).exists() for rel in plan['absent_private_sources']), 'missing_private_source_was_added')
        result.update(status='complete', pairs=pairs, all_aligned=summarize_pairs(positions),
            matched_prior_API_prefix=summarize_pairs([p for p in positions if p['prior_API_prefix_equal'] is True]),
            comparison_position_counts={field:{key:sum(p['equality'][field][key] for p in pairs)
                for key in ('equal', 'different', 'unavailable')} for field in EQUALITY_FIELDS},
            same_request_different_public_output=sum(p['same_request_different_public_output'] for p in pairs),
            same_request_different_reasoning=sum(p['same_request_different_reasoning'] for p in pairs),
            only_reasoning_field_differs_in_request=sum(p['only_reasoning_field_differs_in_request'] for p in pairs),
            comparisons_are_not_independent_samples=True)
    except BaseException as error:
        result['errors'].append(dict(type=type(error).__name__,
            reason=str(error) if type(error) in (ValueError, TimeoutError, InterruptedError) else 'inspect_private_log'))
        raise
    finally:
        result.update(ended_at=datetime.now(timezone.utc).isoformat(), wall_seconds=time.monotonic()-began,
            inspected_private_sources=len(seen), completed_conditions=sum(r['diagnosis_status'] == 'complete' for r in result['runs']))
        write_new(target, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(); root = args.repo_root.resolve()
    target = root/'reports/P113_receipt_history_trajectories.json'
    failure = root/'reports/P113_receipt_history_trajectories_failure.json'
    require(not target.exists() and not failure.exists(), 'preserve_every_P113_attempt')
    began = time.monotonic()
    def expired(*_): raise TimeoutError('finite_P113_deadline')
    old = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 180)
    try:
        data = inspect(args.storage_root.resolve(), root)
    except BaseException as error:
        write_new(failure, dict(status='failed', error_type=type(error).__name__,
            detail=str(error) if type(error) in (ValueError, TimeoutError, InterruptedError) else 'inspect_private_log',
            wall_seconds=time.monotonic()-began, **{k:0 for k in ZERO}))
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, old)
    print(json.dumps({k:data[k] for k in ('status', 'completed_conditions', 'inspected_private_sources',
        'same_request_different_public_output', 'same_request_different_reasoning', 'all_aligned', 'wall_seconds')}))


if __name__ == '__main__': main()
