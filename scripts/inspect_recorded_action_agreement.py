"""P98: inspect all closed P82 outputs and receipts once; no execution replay."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time

from recorded_action_agreement import analyze_run, compare_runs, summarize_pairs

PLAN = 'configs/P98_recorded_action_agreement_v01.json'
ZERO = ('model_generations', 'environment_API_requests', 'evaluations',
        'saved_code_executions', 'task_databases_read', 'reserved_scenarios_read')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_bound(path, expected):
    if path.stat().st_size > 16777216 or sha(path) != expected:
        raise ValueError('bound_or_changed_private_record')
    return json.loads(path.read_text())


def verify_ci(root):
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
        if detail['headSha'] != head or detail['event'] != event or detail['conclusion'] != 'success' or len(jobs) != 1:
            raise ValueError('exact_head_job_success_required')
        proof.append(dict(event=event, workflow=run['databaseId'], job=jobs[0]['databaseId'], head=head, success=True))
    return head, proof


def inspect(storage, root):
    started = time.monotonic(); plan = json.loads((root / PLAN).read_text())
    fixed = dict(phase='P98', cells=24, independent_known_tasks=4, condition_pairs=60,
        max_model_calls_per_cell=80, max_events_per_cell=4000, max_file_bytes=16777216,
        max_wall_seconds=180, alignment='same_generation_ordinal_union',
        causal_intervention_claim=False, novel_method_claim=False, **{k: 0 for k in ZERO})
    if any(plan.get(k) != v for k, v in fixed.items()):
        raise ValueError('fixed_analysis_scope_changed')
    for rel, expected in plan['source_sha256'].items():
        if sha(root / rel) != expected:
            raise ValueError('fixed_source_changed:' + rel)
    head, ci = verify_ci(root)
    audit = json.loads((root / 'reports/P82_comparison.json').read_text())
    profile = json.loads((root / 'reports/P82_call_profile.json').read_text())
    trace = json.loads((root / 'reports/P82_trajectory_stability.json').read_text())
    session = json.loads((root / 'reports/P82_server_session.json').read_text())
    audit_sha = sha(root / 'reports/P82_comparison.json')
    if (audit['audit_errors'] or audit['batch_status'] != 'complete' or len(audit['rows']) != 24
            or sorted(r['run_id'] for r in audit['rows']) != sorted(plan['run_ids'])
            or profile['comparison_sha256'] != audit_sha or trace['comparison_sha256'] != audit_sha
            or session['audit_source_sha256'] != audit_sha or session['status'] != 'stopped'):
        raise ValueError('closed_complete_original_cohort_required')
    rows = []
    for original in audit['rows']:
        folder = storage / 'records/context_pilot' / original['run_id']
        folder.resolve().relative_to((storage / 'records/context_pilot').resolve())
        expected = profile['private_record_sha256'][original['run_id']]
        values = {name: read_bound(folder / name, expected[name]) for name in ('usage.json', 'events.json', 'spans.json')}
        if expected['usage.json'] != original['usage_sha256']:
            raise ValueError('original_usage_changed')
        responses = {}
        for entry in original['request_checks']:
            path = folder / entry['call_id'] / 'response.json'
            expected_response = entry['response_sha256']
            if expected_response is None:
                if path.exists(): raise ValueError('missing_response_was_added')
                responses[entry['call_id']] = None
            else:
                responses[entry['call_id']] = read_bound(path, expected_response)
        calls = analyze_run(values['usage.json'], values['events.json'], values['spans.json'], responses)
        if (len(calls) != original['model_calls']
                or sum(c['API_requests'] for c in calls) != original['api_requests']
                or sum(c['known_total_tokens'] or 0 for c in calls) != original['known_total_tokens']
                or sum(c['known_total_tokens'] is None for c in calls) != original['unknown_usage_calls']):
            raise ValueError('original_full_cost_or_request_totals_changed')
        saved = trace['traces'][original['run_id']]['calls']
        if len(saved) != len(calls): raise ValueError('all_original_trace_slots_required')
        for call, old in zip(calls, saved, strict=True):
            if call['call_id'] != old['call_id'] or call['response']['public_output_sha256'] != old['public_output_sha256']:
                raise ValueError('previous_public_output_fingerprint_differs')
            call['request_sha256'] = old['request_sha256']
            call['without_current_time_treatment_sha256'] = old['without_current_time_treatment_sha256']
        rows.append(dict(**{k: original[k] for k in ('run_id', 'task_id', 'time_visibility', 'repetition',
            'success', 'stop_reason', 'model_calls', 'api_requests', 'known_total_tokens', 'unknown_usage_calls')},
            calls=calls, private_record_sha256=expected,
            private_response_sha256={x['call_id']: x['response_sha256'] for x in original['request_checks']}))
    pairs = compare_runs(rows)
    if len(pairs) != 60 or len({r['task_id'] for r in rows}) != 4:
        raise ValueError('all_four_times_fifteen_pairs_required')
    all_slots = [s for p in pairs for s in p['rows']]
    return dict(phase='P98', status='complete', finished_at=datetime.now(timezone.utc).isoformat(),
        source_commit=head, CI=ci, plan_sha256=sha(root / PLAN), source_sha256=plan['source_sha256'],
        rows=rows, pairs=pairs, all_aligned=summarize_pairs(all_slots),
        matched_prior_API_prefix=summarize_pairs([s for s in all_slots if s['prior_API_prefix_equal'] is True]),
        original_model_attempts=sum(r['model_calls'] for r in rows),
        original_API_requests=sum(r['api_requests'] for r in rows),
        original_known_tokens=sum(r['known_total_tokens'] for r in rows),
        original_unknown_usage_calls=sum(r['unknown_usage_calls'] for r in rows),
        wall_seconds=time.monotonic() - started, private_reasoning_inspected_semantically=False,
        independent_known_tasks=4, condition_pairs=60, pairs_independent=False,
        no_action_is_not_nonempty_API_agreement=True, full_state_equivalence_established=False,
        causal_intervention_claim=False, novel_method_claim=False, measured_savings=None,
        **{k: 0 for k in ZERO})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, required=True)
    args = parser.parse_args(); root = Path(__file__).resolve().parents[1]
    target = root / 'reports/P98_recorded_action_agreement.json'
    failure = root / 'reports/P98_recorded_action_agreement_failure.json'
    if target.exists() or failure.exists(): raise FileExistsError('preserve_every_P98_attempt')
    started = time.monotonic()
    def expired(*_): raise TimeoutError('finite_readonly_deadline')
    previous = signal.signal(signal.SIGALRM, expired); signal.setitimer(signal.ITIMER_REAL, 180)
    try:
        result = inspect(args.storage_root.resolve(), root)
        with target.open('x') as stream: json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
    except BaseException as error:
        with failure.open('x') as stream:
            json.dump(dict(phase='P98', status='failed', error_type=type(error).__name__,
                detail=str(error)[:300], wall_seconds=time.monotonic() - started, **{k: 0 for k in ZERO}), stream, indent=2)
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)
    print(json.dumps({k: result[k] for k in ('status', 'original_model_attempts', 'original_API_requests',
        'original_known_tokens', 'original_unknown_usage_calls', 'all_aligned', 'matched_prior_API_prefix', 'wall_seconds')}))


if __name__ == '__main__': main()
