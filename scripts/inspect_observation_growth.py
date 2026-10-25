"""P116: profile all closed P111/P114 inputs and API records, without replay."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import time

from inspect_input_exposure import check_resume
from inspect_recorded_action_agreement import sha, read_bound, verify_ci
from observation_growth_profile import ObservationExposure, api_repetitions, summarize_call_characters
from receipt_reasoning_history import require
from recorded_action_agreement import analyze_run

PLAN = 'configs/P116_observation_growth_v01.json'
TARGET = 'reports/P116_observation_growth.json'
ZERO = ('model_generations', 'environment_API_requests', 'saved_code_executions',
        'evaluations', 'task_databases_read', 'reserved_scenarios_read', 'tokenizer_calls')


def fixed_parameters():
    return dict(phase='P116', source_audits=['reports/P111_comparison.json', 'reports/P114_comparison.json'],
        source_sessions=['reports/P111_server_session.json', 'reports/P114_server_session.json'],
        original_conditions=16, independent_known_tasks=4, original_model_attempts=283,
        original_API_requests=820, original_known_logical_tokens=3026706,
        original_unknown_usage_calls=2, max_saved_calls_per_cell=80, max_events_per_cell=4000,
        max_file_bytes=16777216, max_total_private_input_bytes=536870912,
        max_wall_seconds=180, automatic_retries=0,
        selection='all_closed_P111_and_P114_conditions_and_attempts',
        character_accounting='disjoint_text_fields_not_token_attribution',
        repetition='exact_full_arguments_including_authorization',
        prior_results_known=True, private_reasoning_inspected_semantically=False,
        causal_effect_claim=False, semantic_irrelevance_claim=False, novel_method_claim=False,
        **{k:0 for k in ZERO})


def read(path): return json.loads(path.read_text())
def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def inspect(storage, root):
    began = time.monotonic(); plan = read(root/PLAN)
    require(all(type(plan.get(k)) is type(v) and plan[k] == v
                for k, v in fixed_parameters().items()), 'fixed_P116_scope_changed')
    stop = storage/'.runtime/P116.stop'
    require(not stop.exists(), 'explicit_P116_stop')
    resume = check_resume(storage)
    for rel, expected in plan['source_sha256'].items():
        require(sha(root/rel) == expected, 'fixed_source_changed:'+rel)
    head, ci = verify_ci(root)
    originals = []
    for audit_name, session_name in zip(plan['source_audits'], plan['source_sessions'], strict=True):
        audit = read(root/audit_name); session = read(root/session_name)
        require(audit['batch_status'] == 'complete' and not audit['audit_errors']
                and audit['owned_processes_absent'] and session['status'] == 'stopped'
                and session['owned_processes_absent']
                and session['audit_source_sha256'] == sha(root/audit_name), 'closed_original_batch_required')
        originals.extend(dict(source_audit=audit_name, **row) for row in audit['rows'])
    require(len(originals) == 16 and [r['run_id'] for r in originals] == plan['run_ids']
            and len({r['task_id'] for r in originals}) == 4, 'all_original_conditions_required')
    require(all(not (storage/rel).exists() for rel in plan['absent_private_sources']), 'missing_source_was_added')
    require(sum((storage/rel).stat().st_size for rel in plan['private_source_sha256'])
            <= plan['max_total_private_input_bytes'], 'total_private_input_bound')
    fields = ('source_audit', 'run_id', 'task_id', 'reasoning_display_policy', 'success', 'stop_reason',
              'model_calls', 'api_requests', 'known_total_tokens', 'unknown_usage_calls')
    result = dict(**fixed_parameters(), source_commit=head, ci=ci, research_resume=resume,
        plan_sha256=sha(root/PLAN), started_at=datetime.now(timezone.utc).isoformat(), status='incomplete',
        errors=[], runs=[dict(**{k:r[k] for k in fields}, profile_status='not_inspected',
            calls=[dict(call_id=c['call_id'], status='not_inspected') for c in r['request_checks']]) for r in originals],
        source_sha256=plan['source_sha256'], private_source_sha256=plan['private_source_sha256'],
        absent_private_sources=plan['absent_private_sources'], original_P111_gate_changed=False,
        measured_savings=None, full_state_equivalence_established=False)
    seen = set()
    def get(rel):
        require(not stop.exists(), 'explicit_P116_stop')
        require(time.monotonic()-began < plan['max_wall_seconds'], 'finite_P116_deadline')
        path = storage/rel
        path.resolve().relative_to((storage/'records/context_pilot').resolve())
        require(not path.is_symlink(), 'private_source_symlink_rejected')
        if rel in plan['absent_private_sources']:
            require(not path.exists(), 'missing_source_was_added')
            return None
        require(rel in plan['private_source_sha256'], 'unbound_private_source')
        seen.add(rel)
        return read_bound(path, plan['private_source_sha256'][rel])
    try:
        for index, original in enumerate(originals):
            rid = original['run_id']; prefix = 'records/context_pilot/'+rid+'/'
            usage, events, spans = (get(prefix+n+'.json') for n in ('usage', 'events', 'spans'))
            responses = {c['call_id']:get(prefix+c['call_id']+'/response.json') for c in original['request_checks']}
            described = analyze_run(usage, events, spans, responses)
            require(len(described) == original['model_calls']
                    and sum(c['API_requests'] for c in described) == original['api_requests']
                    and sum(c['known_total_tokens'] or 0 for c in described) == original['known_total_tokens']
                    and sum(c['known_total_tokens'] is None for c in described) == original['unknown_usage_calls'],
                    'original_cost_or_API_totals_changed')
            exposure = ObservationExposure(); calls = []
            for call, use in zip(described, usage, strict=True):
                require(call['call_id'] == use['id'], 'usage_call_order_changed')
                request = get(prefix+call['call_id']+'/request.json')
                inp = exposure.add(request, call['ordinal'])
                known = call['usage_status'] == 'ok'
                calls.append(dict(**call, input=inp,
                    measured_input_tokens=use['input_tokens'] if known else None,
                    measured_output_tokens=use['output_tokens'] if known else None,
                    measured_cached_input_tokens=use.get('cached_input_tokens') if known else None,
                    unknown_usage_not_imputed=not known))
            repetitions = api_repetitions(events, spans)
            require(repetitions['requests'] == original['api_requests'], 'all_actual_API_rows_required')
            totals = summarize_call_characters(calls); tool_totals = exposure.summary()
            require(tool_totals['total_characters'] == totals['input_character_exposures']['tool_content_characters'],
                    'all_tool_exposure_characters_required')
            result['runs'][index].update(profile_status='complete', calls=calls,
                tool_exposure=tool_totals, API_repetitions=repetitions, **totals)
        require(seen == set(plan['private_source_sha256']), 'every_bound_private_source_required')
        for field, expected in [('model_calls',283), ('api_requests',820),
                                ('known_total_tokens',3026706), ('unknown_usage_calls',2)]:
            require(sum(r[field] for r in result['runs']) == expected, 'whole_cohort_accounting_changed:'+field)
        for rel, expected in plan['private_source_sha256'].items():
            require(sha(storage/rel) == expected, 'private_source_changed_during_profile')
        require(all(not (storage/rel).exists() for rel in plan['absent_private_sources']), 'missing_source_was_added')
        result['status'] = 'complete'
    except BaseException as error:
        result['errors'].append(dict(type=type(error).__name__,
            reason=str(error) if type(error) in (ValueError, TimeoutError, InterruptedError) else 'inspect_private_log'))
        raise
    finally:
        result.update(ended_at=datetime.now(timezone.utc).isoformat(), wall_seconds=time.monotonic()-began,
            inspected_private_sources=len(seen), completed_conditions=sum(r['profile_status'] == 'complete' for r in result['runs']))
        write_new(root/TARGET, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(); root = args.repo_root.resolve()
    failure = root/'reports/P116_observation_growth_failure.json'
    require(not (root/TARGET).exists() and not failure.exists(), 'preserve_every_P116_attempt')
    began = time.monotonic()
    def expired(*_): raise TimeoutError('finite_P116_deadline')
    old = signal.signal(signal.SIGALRM, expired); signal.setitimer(signal.ITIMER_REAL, 180)
    try:
        data = inspect(args.storage_root.resolve(), root)
    except BaseException as error:
        write_new(failure, dict(status='failed', error_type=type(error).__name__,
            detail=str(error) if type(error) in (ValueError, TimeoutError, InterruptedError) else 'inspect_private_log',
            wall_seconds=time.monotonic()-began, **{k:0 for k in ZERO}))
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, old)
    print(json.dumps({k:data[k] for k in ('status', 'completed_conditions', 'inspected_private_sources', 'wall_seconds')}))


if __name__ == '__main__': main()
