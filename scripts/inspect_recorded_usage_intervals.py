"""P100: read closed P97 accounting once, with no model or environment calls."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time

from recorded_usage_intervals import analyze_cell, summarize

PLAN = 'configs/P100_recorded_usage_intervals_v01.json'
ZERO = ('model_generations', 'environment_API_requests', 'evaluations',
        'saved_code_executions', 'task_databases_read', 'reserved_scenarios_read',
        'P99_intermediate_outcomes_read')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_bound(path, expected):
    if path.stat().st_size > 16777216 or sha(path) != expected:
        raise ValueError('bound_or_changed_record')
    return json.loads(path.read_text())


def verify_ci(root):
    # Same exact-head checks as P98; deliberately no import of replay/runtime code.
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True, timeout=10).strip()
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=root, text=True, timeout=10).strip():
        raise ValueError('tracked_sources_must_be_clean')
    runs = json.loads(subprocess.check_output(['gh', 'run', 'list', '--repo', 'sophiria1225/AI-',
        '--commit', head, '--json', 'databaseId,event,headSha,status,conclusion,name'], text=True, timeout=30))
    proof = []
    for event in ('push', 'pull_request'):
        eligible = [r for r in runs if r['headSha'] == head and r['event'] == event
                    and r['status'] == 'completed' and r['conclusion'] == 'success'
                    and r['name'] == 'Lightweight research checks']
        if not eligible:
            raise ValueError('exact_head_CI_required:' + event)
        run = eligible[0]
        detail = json.loads(subprocess.check_output(['gh', 'run', 'view', str(run['databaseId']),
            '--repo', 'sophiria1225/AI-', '--json', 'headSha,event,status,conclusion,jobs'], text=True, timeout=30))
        jobs = [j for j in detail['jobs'] if j['name'] == 'accounting-and-syntax'
                and j['status'] == 'completed' and j['conclusion'] == 'success']
        if (detail['headSha'] != head or detail['event'] != event
                or detail['conclusion'] != 'success' or len(jobs) != 1):
            raise ValueError('exact_head_job_success_required')
        proof.append(dict(event=event, workflow=run['databaseId'], job=jobs[0]['databaseId'],
                          head=head, success=True))
    return head, proof


def inspect(storage, root):
    started = time.monotonic()
    plan = json.loads((root / PLAN).read_text())
    fixed = dict(phase='P100', source_phase='P97', cells=12, independent_known_tasks=4,
        expected_attempts=223, expected_unknown_attempts=2, max_file_bytes=16777216,
        max_wall_seconds=180, posthoc_sensitivity_analysis=True,
        unknown_lower_bound=0, unknown_upper_bound='predicted_input_plus_requested_output_cap',
        second_upper_bound='configured_context_cap', novel_method_claim=False,
        original_gate_replaced=False, **{k: 0 for k in ZERO})
    if any(plan.get(k) != v for k, v in fixed.items()):
        raise ValueError('fixed_analysis_scope_changed')
    for rel, expected in plan['source_sha256'].items():
        if sha(root / rel) != expected:
            raise ValueError('fixed_source_changed:' + rel)
    head, ci = verify_ci(root)
    audit = json.loads((root / 'reports/P97_comparison.json').read_text())
    session = json.loads((root / 'reports/P97_server_session.json').read_text())
    original = json.loads((root / 'configs/P29_stateful_code_v01.json').read_text())
    experiment = json.loads((root / 'configs/P97_recovery_notice_comparison_v01.json').read_text())
    if (audit['audit_errors'] or audit['batch_status'] != 'complete'
            or not audit['owned_processes_absent'] or len(audit['rows']) != 12
            or session['status'] != 'stopped' or not session['owned_processes_absent']
            or session['audit_source_sha256'] != sha(root / 'reports/P97_comparison.json')
            or experiment['automatic_retries'] != 0
            or [r['run_id'] for r in audit['rows']] != plan['run_ids']):
        raise ValueError('closed_complete_original_cohort_required')
    limits = {'context_tokens': original['model']['num_ctx'],
        'output_tokens': original['max_output_tokens'], 'cell_tokens': experiment['max_total_tokens'],
        'max_calls': experiment['max_calls']}
    if limits != plan['limits']:
        raise ValueError('original_limits_changed')
    rows = []
    for row in audit['rows']:
        folder = storage / 'records/context_pilot' / row['run_id']
        folder.resolve().relative_to((storage / 'records/context_pilot').resolve())
        usage = read_bound(folder / 'usage.json', row['usage_sha256'])
        request_caps = {}
        for check in row['request_checks']:
            call_id = check['call_id']
            if (not call_id.startswith('call_') or not call_id[5:].isdigit()
                    or call_id in request_caps or check['request_sha256'] is None):
                raise ValueError('unique_safe_bound_request_required')
            request = read_bound(folder / call_id / 'request.json', check['request_sha256'])
            request_caps[call_id] = request.get('max_tokens')
        rows.append(analyze_cell(row, usage, request_caps, limits))
    result = summarize(rows, plan['task_ids'], plan['policies'])
    totals = result['all_conditions']
    if (totals['model_attempts'] != 223 or totals['unknown_usage_attempts'] != 2
            or totals['known_logical_tokens'] != sum(r['known_total_tokens'] for r in audit['rows'])
            or totals['API_requests'] != sum(r['api_requests'] for r in audit['rows'])):
        raise ValueError('all_original_attempts_and_costs_required')
    return dict(phase='P100', status='complete', finished_at=datetime.now(timezone.utc).isoformat(),
        source_commit=head, CI=ci, plan_sha256=sha(root / PLAN), source_sha256=plan['source_sha256'],
        rows=rows, **result, wall_seconds=time.monotonic() - started,
        assumptions=['The server honors the recorded request output cap.',
            'The recorded tokenizer input count applies to that exact request.',
            'No unrecorded retry or extra generation is included in the defined logical cost.',
            'The context-only bound additionally assumes the recorded context cap is enforced.'],
        lower_bound_does_not_assert_zero_actual_usage=True,
        unknown_terminal_usage_reconstructed=False, independent_known_tasks=4,
        posthoc_sensitivity_analysis=True, pairs_independent=False,
        original_factual_notice_benefit_gate_met=audit['factual_notice_benefit_gate_met'],
        original_gate_replaced=False, novel_method_claim=False,
        general_quality_preservation_established=False, server_cap_compliance_proven_for_unknown=False,
        private_reasoning_inspected_semantically=False, **{k: 0 for k in ZERO})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = root / 'reports/P100_recorded_usage_intervals.json'
    failure = root / 'reports/P100_recorded_usage_intervals_failure.json'
    if target.exists() or failure.exists():
        raise FileExistsError('preserve_every_P100_attempt')
    started = time.monotonic()
    def expired(*_):
        raise TimeoutError('finite_readonly_deadline')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 180)
    try:
        result = inspect(args.storage_root.resolve(), root)
        with target.open('x') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    except BaseException as error:
        with failure.open('x') as stream:
            json.dump(dict(phase='P100', status='failed', error_type=type(error).__name__,
                detail=str(error)[:300], wall_seconds=time.monotonic() - started,
                **{k: 0 for k in ZERO}), stream, indent=2)
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    print(json.dumps({k: result[k] for k in ('status', 'all_conditions',
        'whole_cohort_differences', 'wall_seconds')}))


if __name__ == '__main__':
    main()
