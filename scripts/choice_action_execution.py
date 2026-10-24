"""P102 accounting for all saved-output slots, including unavailable outputs."""
from itertools import combinations, product

from choice_context_replay import conditions, schedule

FIXED = dict(phase='P102', source_phase='P101', planned_slots=36, independent_contexts=1,
    source_batch='records/context_pilot/P101_choice_context_v01',
    required_closed_pipeline='records/context_pilot/P101_pipeline_v01',
    required_closed_audit='reports/P101_choice_context.json',
    prefix_source='records/context_pilot/BOC_P80_04_NOT_EXPOSED', task_id='6104387_1', world_seed=42,
    original_prefix_programs=12, original_prefix_api_requests=28,
    active_deadline_seconds=1800, per_condition_deadline_seconds=180,
    max_api_requests_per_condition=80, max_api_requests_total=2880,
    program_timeout_seconds=30, bridge_timeout_seconds=30, max_file_bytes=16777216,
    observation_page_characters=24000, model_generations=0, evaluator_calls=0,
    reserved_scenarios_read=0, automatic_retries=0, original_full_state_restored=False,
    task_quality_measured=False, novel_method_claim=False, unavailable_sources_preserved=True,
    all_known_outputs_attempted_in_fixed_order=True)


def validate_plan(plan):
    if any(plan.get(k) != v for k, v in FIXED.items()) or plan.get('schedule') != schedule():
        raise ValueError('fixed_P102_design_budget_or_order_changed')


def source_slots(audit):
    """Do not repair, regenerate, or select on static validity of known outputs."""
    if (audit.get('phase') != 'P101' or audit.get('audit_errors') != []
            or audit.get('owned_processes_absent') is not True
            or audit.get('server', {}).get('status') != 'stopped'
            or audit.get('pipeline_status') not in ('complete', 'stopped')
            or len(audit.get('rows', [])) != 36):
        raise ValueError('closed_audited_all_36_source_slots_required')
    result = []; unavailable_seen = False
    for planned, row in zip(schedule(), audit['rows'], strict=True):
        if (any(row.get(k) != v for k, v in planned.items())
                or row.get('source_context') != 'P83_CSV_call_014'):
            raise ValueError('unchanged_source_schedule_required')
        status = row['record_status']
        known = status == 'audited'
        if known:
            if (unavailable_seen or row.get('status') != 'ok'
                    or type(row.get('input_tokens')) is not int or row['input_tokens'] <= 0
                    or type(row.get('output_tokens')) is not int or row['output_tokens'] < 0
                    or row.get('known_total_tokens') != row['input_tokens'] + row['output_tokens']
                    or not row.get('response_sha256') or not row.get('public_output_sha256')):
                raise ValueError('known_original_terminal_accounting_required')
        else:
            if status not in ('unknown_usage', 'unknown_missing_terminal_record', 'unattempted'):
                raise ValueError('unknown_or_unattempted_source_reason_required')
            if (row.get('input_tokens') is not None or row.get('output_tokens') is not None
                    or status != 'unattempted' and unavailable_seen
                    or status == 'unattempted' and row.get('status') != 'unattempted'
                    or status != 'unattempted' and row.get('status') != 'error'):
                raise ValueError('unavailable_output_cannot_be_imputed_or_reordered')
            unavailable_seen = True
        result.append(dict(**planned, should_execute=known, source_record_status=status,
            source_response_sha256=row.get('response_sha256'),
            source_public_output_sha256=row.get('public_output_sha256'),
            source_complete_generation=row.get('complete_generation') if known else None,
            source_static_submission=row.get('complete_static_submission') if known else None,
            source_known_total_tokens=row.get('known_total_tokens') if known else None,
            unavailable_reason=None if known else status))
    known = sum(r['should_execute'] for r in result)
    unknown = sum(r['source_record_status'].startswith('unknown_') for r in result)
    attempted = sum(r['source_record_status'] != 'unattempted' for r in result)
    if (audit.get('model_calls_attempted') != attempted or audit.get('unknown_usage_calls') != unknown
            or audit.get('known_total_tokens') != sum(r['source_known_total_tokens'] or 0 for r in result)
            or audit.get('all_36_audited') is not (known == 36)):
        raise ValueError('source_attempt_and_usage_accounting_disagrees')
    return result


def execution_comparisons(rows):
    """Nonempty sent requests and executed Python are different denominators."""
    if len(rows) != 36 or any(any(row.get(k) != v for k, v in item.items())
                            for row, item in zip(rows, schedule(), strict=True)):
        raise ValueError('all_36_execution_slots_in_original_order_required')
    def completed(row):
        return row['status'] == 'complete' and row.get('public_prefix_matched') is True
    def compare(pairs):
        done = [(a,b) for a,b in pairs if completed(a) and completed(b)]
        nonempty = [(a,b) for a,b in done if a['suffix_api_requests'] > 0 and b['suffix_api_requests'] > 0]
        python = [(a,b) for a,b in done if a['structured_submissions'] > 0
                  and b['structured_submissions'] > 0 and a['suffix_saved_programs'] > 0
                  and b['suffix_saved_programs'] > 0]
        return dict(pairs=len(pairs), independent_samples=False,
            both_execution_records_complete=len(done), unavailable_pairs=len(pairs)-len(done),
            both_nonempty_API_sequences=len(nonempty),
            nonempty_API_request_sequences_equal=sum(a['suffix_request_sequence_sha256'] == b['suffix_request_sequence_sha256'] for a,b in nonempty),
            both_empty_API_sequences=sum(a['suffix_api_requests'] == b['suffix_api_requests'] == 0 for a,b in done),
            one_empty_API_sequence=sum((a['suffix_api_requests'] == 0) != (b['suffix_api_requests'] == 0) for a,b in done),
            both_submitted_Python_executed=len(python),
            Python_execution_evidence_equal=sum(a['suffix_execution_evidence_sha256'] == b['suffix_execution_evidence_sha256'] for a,b in python),
            both_without_structured_submissions=sum(a['structured_submissions'] == b['structured_submissions'] == 0 for a,b in done),
            pairs_with_truncated_source=sum(a.get('source_complete_generation') is False or b.get('source_complete_generation') is False for a,b in done))
    grouped = {key: [r for r in rows if r['condition'] == key] for key in conditions()}
    within = [dict(condition=key, **compare(list(combinations(grouped[key], 2)))) for key in conditions()]
    cross = [dict(left=a, right=b, **compare(list(product(grouped[a], grouped[b]))))
             for a,b in combinations(conditions(), 2)]
    return dict(within=within, cross=cross, planned_slots=36, condition_groups=12,
        within_condition_pairs=36, cross_condition_pairs=594, independent_saved_contexts=1,
        request_equality_is_not_correctness=True, task_quality_measured=False,
        whole_task_savings_measured=False, novel_method_claim=False)
