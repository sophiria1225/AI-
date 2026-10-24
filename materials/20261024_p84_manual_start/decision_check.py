"""One explicit post-closure decision; never launches or retries a model."""
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

STORAGE = Path('/Users/tp26013/AI-')
EDITOR = STORAGE / '.runtime/worktrees/p84-prep'
P82 = STORAGE / '.runtime/worktrees/p82-run'
CLOSURE = STORAGE / '.runtime/worktrees/p82-prep'
P84 = STORAGE / '.runtime/worktrees/p84-run'
sys.path.insert(0, str(EDITOR / 'scripts'))
from inspect_late_clock_usage_intervals import validate_closure
from inspect_input_exposure import check_resume
from p84_continuation_guard import P84_COMMIT, P84_PLAN, P84_PLAN_SHA, P82_PLAN, COMPARISON
from probe_fallback_output import sources, previous_session_closed
from run_api_error_pipeline import checked_ci
from run_handoff_factors import read, sha


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def main():
    target = STORAGE / '.runtime/P84_manual_execution_decision_20261024.json'
    require(not target.exists(), 'preserve_first_manual_decision')
    for name in ('P82.stop', 'P82_reports.stop', 'P84.stop', 'P84_reports.stop', 'P84_continuation.stop'):
        require(not (STORAGE / '.runtime' / name).exists(), 'explicit_stop:' + name)
    automatic_path = STORAGE / '.runtime/P84_continuation_status.json'
    automatic = read(automatic_path)
    require(automatic.get('status') == 'stopped' and automatic.get('error') ==
            'P82_closure_failed_no_auto_continuation', 'preserved_auto_refusal_required')
    closure_path = STORAGE / '.runtime/P82_closure_status.json'
    require(read(closure_path).get('status') == 'stopped' and read(closure_path).get('error') ==
            'report_stage_failed_no_retry', 'preserved_original_presentation_failure_required')
    manual_path = STORAGE / '.runtime/P82_manual_closure_status_20261024.json'
    manual = read(manual_path)
    require(manual.get('status') == 'complete' and manual.get('conditions') == 24
            and manual.get('audit_errors') == [] and manual.get('original_status_files_changed') is False,
            'independent_closed_report_review_required')
    for name, expected in manual['sources_sha256'].items():
        require(sha(EDITOR / name) == expected, 'reviewed_closed_output_changed:' + name)
    require(read(STORAGE / '.runtime/P84_closure_status.json').get('error') ==
            'P84_continuation_stopped_without_pipeline', 'preserved_P84_report_waiter_stop_required')
    for name in ('P84_pipeline_v01', 'P84_preflight_v01', 'P84_fallback_output_v01'):
        require(not (STORAGE / 'records/context_pilot' / name).exists(), 'no_prior_P84_attempt_required')
    require(not (P84 / 'reports/P84_initial_checks.json').exists(), 'no_prior_P84_preflight_required')
    require(not (STORAGE / '.runtime/P84_execution_decision.json').exists(), 'automatic_decision_must_remain_absent')
    pipeline_path = STORAGE / 'records/context_pilot/P82_pipeline_v01/status.json'
    batch_path = STORAGE / 'records/context_pilot/P82_batch_v01/status.json'
    report, plan = read(P82 / COMPARISON), read(P82 / P82_PLAN)
    decisions = validate_closure(read(pipeline_path), read(batch_path), report, plan)
    require(sum(r['unknown_usage_calls'] for r in report['rows']) > 0, 'preserve_observed_missing_usage')
    require(report['plan_sha256'] == sha(P82 / P82_PLAN) and
            report['auditor_sha256'] == sha(P82 / 'scripts/audit_late_clock_comparison.py'), 'bound_P82_audit_required')
    for root in (EDITOR, CLOSURE):
        require(sha(root / COMPARISON) == sha(P82 / COMPARISON), 'same_audited_report_required')
    for name, expected in plan['source_sha256'].items():
        require(sha(P82 / name) == sha(EDITOR / name) == expected, 'fixed_P82_source_changed:' + name)
    private_hashes = {}
    for row in report['rows']:
        folder = STORAGE / 'records/context_pilot' / row['run_id']
        for stem in ('summary', 'usage', 'evaluation'):
            path = folder / (stem + '.json')
            require(sha(path) == row[stem + '_sha256'], 'audited_P82_record_changed')
            private_hashes[str(path.relative_to(STORAGE))] = sha(path)
        require(len(row['request_checks']) == row['model_calls'], 'all_audited_calls_required')
        for call in row['request_checks']:
            for stem in ('request', 'response'):
                path = folder / call['call_id'] / (stem + '.json')
                digest = sha(path) if path.exists() else None
                require(digest == call[stem + '_sha256'], 'audited_P82_request_or_response_changed')
                private_hashes[str(path.relative_to(STORAGE))] = digest
    require(sha(P84 / P84_PLAN) == P84_PLAN_SHA, 'fixed_P84_plan_changed')
    p84_plan, _, _ = sources(STORAGE, P84)
    prior = previous_session_closed(STORAGE, p84_plan)
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=P84, text=True).strip() == P84_COMMIT,
            'fixed_P84_head_required')
    require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=P84, text=True).strip(),
            'clean_P84_runtime_required')
    ci = checked_ci(P84, P84_COMMIT)
    result = dict(phase='P84_manual_first_execution_decision', checked_at=datetime.now(timezone.utc).isoformat(),
        reason='The original automatic handoff stopped on a presentation layout failure. Separate corrected slides and the manuscript are now fully reviewed. The fixed P83 saved-input question is independent of missing P82 terminal usage; all 24 P82 cells and all four original decisions remain intact.',
        original_auto_refusal_preserved=True, automatic_guard_changed=False, automatic_waiter_restarted=False,
        original_P82_decisions=decisions, P82_unknown_usage_calls=sum(r['unknown_usage_calls'] for r in report['rows']),
        P82_pipeline_sha256=sha(pipeline_path), P82_batch_sha256=sha(batch_path), P82_comparison_sha256=sha(P82 / COMPARISON),
        P82_closure_status_sha256=sha(closure_path), P82_manual_review_sha256=sha(manual_path),
        P84_auto_refusal_sha256=sha(automatic_path), all_known_auto_guard_would_still_fail=True,
        private_audited_record_sha256=private_hashes, P82_owned_server=prior,
        P84_plan_sha256=P84_PLAN_SHA, P84_runtime_commit=P84_COMMIT, P84_ci=ci, research_resume=check_resume(STORAGE),
        fixed_inputs=6, fixed_repetitions=3, max_generations=18, reserved_tokens=481671,
        input_reselection=False, automatic_retries=0, model_generations_before_decision=0,
        environment_api_requests=0, task_evaluations=0, task_quality_claim=False, novel_method_claim=False,
        decision_script_sha256=sha(Path(__file__)))
    with target.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print({'decision': str(target), 'P82_unknown_usage_calls': result['P82_unknown_usage_calls'],
           'fixed_generations': 18, 'automatic_refusal_preserved': True, 'models_started': 0})


if __name__ == '__main__':
    main()
