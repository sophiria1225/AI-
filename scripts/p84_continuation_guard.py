"""Require a closed, fully audited P82 before the fixed P84 diagnostic.

P84 is not selected by whether late-half wins. All four P82 decisions are retained.
This module does not allocate a model or inspect the meaning of private histories.
"""
from late_clock_comparison import cell_id, run_order, summarize, validate_plan
from probe_fallback_output import previous_session_closed, sources
from run_handoff_factors import read, sha

P82_COMMIT = 'ce81c87ed4a456543859ee98e5aec9e7c5703b77'
P84_COMMIT = '1dfa3cafb9e111cffaea2b563513db890e85ebce'
P84_PLAN_SHA = 'bc8d843e7d61d5d98a42540b0e0dbcc087a54aa7b13e1ba4a56766af627a435b'
P82_PLAN = 'configs/P82_late_clock_comparison_v01.json'
P84_PLAN = 'configs/P84_fallback_output_v01.json'
COMPARISON = 'reports/P82_comparison.json'


def validate_closure(pipeline, batch, report, plan):
    validate_plan(plan)
    expected = [cell_id(*v) for v in run_order()]
    if (pipeline.get('status') != 'complete' or not pipeline.get('finished_at')
            or pipeline.get('server_stopped') is not True
            or pipeline.get('git_commit') != P82_COMMIT
            or batch.get('git_commit') != P82_COMMIT
            or batch.get('status') != 'complete' or batch.get('active') is not None
            or batch.get('planned') != expected or batch.get('completed') != expected):
        raise ValueError('all_24_closed_in_fixed_order_required')
    rows = report.get('rows', [])
    if (report.get('phase') != 'P82' or report.get('batch_status') != 'complete'
            or report.get('audit_errors') != []
            or [r.get('run_id') for r in rows] != expected
            or [r.get('run_id') for r in batch.get('rows', [])] != expected):
        raise ValueError('complete_matching_P82_audit_required')
    for (rep, number, policy), row, executed in zip(run_order(), rows, batch['rows'], strict=True):
        if (row.get('repetition') != rep or row.get('time_visibility') != policy
                or row.get('task_id') != plan['known_tasks'][number - 1]['task_id']
                or row.get('record_status') != 'evaluated' or type(row.get('success')) is not bool
                or row.get('unknown_usage_calls') != 0
                or type(row.get('known_total_tokens')) is not int or row['known_total_tokens'] < 0):
            raise ValueError('fully_evaluated_known_cohort_required_for_auto_continuation')
        for key in ('task_id', 'repetition', 'time_visibility', 'success', 'model_calls',
                    'known_total_tokens', 'unknown_usage_calls', 'api_requests'):
            if row.get(key) != executed.get(key):
                raise ValueError('audit_batch_disagreement:' + key)
    recomputed = summarize(rows, [])
    if any(report.get(key) != value for key, value in recomputed.items()):
        raise ValueError('all_four_P82_decisions_must_match_recomputation')
    return {'P82_all_repetition_gates_met': recomputed['all_repetition_gates_met'],
        'P82_repetitions': recomputed['repetitions'], 'P82_gates_used_to_select_P84': False,
        'P84_question': 'Do the six already fixed saved inputs change the next public output?',
        'P84_cases_reselected': False, 'P84_max_generations': 18,
        'P84_reserved_tokens': 481671, 'P84_novel_method_or_task_quality_claim': False}


def bind_closed_evidence(storage, p82_root, closure_root, p84_root):
    pipeline_dir = storage / 'records/context_pilot/P82_pipeline_v01'
    batch_path = storage / 'records/context_pilot/P82_batch_v01/status.json'
    pipeline, batch = read(pipeline_dir / 'status.json'), read(batch_path)
    plan, report = read(p82_root / P82_PLAN), read(p82_root / COMPARISON)
    decision = validate_closure(pipeline, batch, report, plan)
    closure_path = storage / '.runtime/P82_closure_status.json'
    if read(closure_path).get('status') != 'complete':
        raise ValueError('P82_closure_reporting_must_finish_first')
    if (report['plan_sha256'] != sha(p82_root / P82_PLAN)
            or report['auditor_sha256'] != sha(p82_root / 'scripts/audit_late_clock_comparison.py')
            or sha(p82_root / COMPARISON) != sha(closure_root / COMPARISON)):
        raise ValueError('P82_audit_provenance_changed')
    for name, expected in plan['source_sha256'].items():
        if sha(p82_root / name) != expected:
            raise ValueError('P82_bound_source_changed:' + name)
    # Bind the exact records already checked by the frozen auditor, without
    # re-evaluating tasks or reading private reasoning for interpretation.
    for row in report['rows']:
        folder = storage / 'records/context_pilot' / row['run_id']
        for stem in ('summary', 'usage', 'evaluation'):
            if sha(folder / (stem + '.json')) != row[stem + '_sha256']:
                raise ValueError('audited_P82_record_changed')
        if len(row['request_checks']) != row['model_calls']:
            raise ValueError('audited_P82_request_coverage_changed')
        for call in row['request_checks']:
            for stem in ('request', 'response'):
                if sha(folder / call['call_id'] / (stem + '.json')) != call[stem + '_sha256']:
                    raise ValueError('audited_P82_request_or_response_changed')
    if sha(p84_root / P84_PLAN) != P84_PLAN_SHA:
        raise ValueError('P84_fixed_plan_changed')
    p84_plan, _, _ = sources(storage, p84_root)
    prior = previous_session_closed(storage, p84_plan)
    return {**decision, 'P82_closed_server': prior,
        'P82_pipeline_sha256': sha(pipeline_dir / 'status.json'),
        'P82_batch_sha256': sha(batch_path), 'P82_comparison_sha256': sha(p82_root / COMPARISON),
        'P82_closure_status_sha256': sha(closure_path), 'P84_plan_sha256': P84_PLAN_SHA,
        'P84_runtime_commit': P84_COMMIT, 'additional_model_calls_before_handoff': 0}
