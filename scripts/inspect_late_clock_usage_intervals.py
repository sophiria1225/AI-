"""Posthoc conditional cost intervals for all 24 closed P82 cells.

No terminal-usage imputation, gate relaxation, generation or environment access.
Reuse the pinned P80/P81 numeric-log and output-cap interpretation unchanged.
"""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

from inspect_budget_visibility_usage_bounds import COMMIT, parse_numeric_log
from inspect_repetition_usage_intervals import BACKEND_BLOBS, interval_calls
from late_clock_comparison import cell_id, run_order, summarize, validate_plan
from run_handoff_factors import ROOT, read, sha

P82_COMMIT = 'ce81c87ed4a456543859ee98e5aec9e7c5703b77'
PLAN = 'configs/P82_late_clock_comparison_v01.json'
REPORT = 'reports/P82_comparison.json'
SESSION = 'reports/P82_server_session.json'
POLICIES = ('measured', 'not_exposed', 'late_half')


def natural(value):
    return type(value) is int and value >= 0


def check_cells(cells):
    expected = [cell_id(*item) for item in run_order()]
    if [c.get('run_id') for c in cells] != expected:
        raise ValueError('all_24_cells_in_frozen_order_required')
    tasks = {}
    for (rep, number, policy), c in zip(run_order(), cells, strict=True):
        if (type(c.get('repetition')) is not int or c['repetition'] != rep
                or c.get('time_visibility') != policy or c.get('record_status') != 'evaluated'
                or type(c.get('success')) is not bool or not isinstance(c.get('task_id'), str)
                or not c['task_id'] or any(not natural(c.get(k)) for k in
                    ('model_calls', 'known_total_tokens', 'unknown_usage_calls'))
                or c['unknown_usage_calls'] > c['model_calls']):
            raise ValueError('evaluated_cells_with_original_numeric_accounting_required')
        if number in tasks and tasks[number] != c['task_id']:
            raise ValueError('task_pairing_changed')
        tasks[number] = c['task_id']
    if len(set(tasks.values())) != 4:
        raise ValueError('four_distinct_previously_seen_tasks_required')


def partition(cells, baseline):
    totals = {policy: [sum(c[edge] for c in cells if c['time_visibility'] == policy)
                       for edge in ('lower', 'upper')]
              for policy in (baseline, 'late_half')}
    lo, hi = totals['late_half'], totals[baseline]
    return {**totals, 'late_half_minus_baseline': [lo[0] - hi[1], lo[1] - hi[0]],
            'original_unknown_usage_calls': sum(c['unknown_usage_calls'] for c in cells),
            'paired_task_observations': len(cells) // 2}


def comparison(cells, baseline):
    paired = {}
    for c in cells:
        if c['time_visibility'] in (baseline, 'late_half'):
            paired.setdefault((c['repetition'], c['task_id']), {})[c['time_visibility']] = c
    categories = {'both_success': [], 'both_failure': [], 'discordant': []}
    for pair in paired.values():
        a, b = pair[baseline]['success'], pair['late_half']['success']
        key = 'both_success' if a and b else 'both_failure' if not a and not b else 'discordant'
        categories[key].extend(pair.values())
    return {'baseline': baseline,
            'total': partition([c for group in categories.values() for c in group], baseline),
            **{key: partition(group, baseline) for key, group in categories.items()}}


def summarize_intervals(rows, cells):
    check_cells(cells)
    by_id = {c['run_id']: c for c in cells}
    grouped = {rid: [] for rid in by_id}
    seen = set()
    for r in rows:
        key = (r.get('run_id'), r.get('call_id'))
        if (key[0] not in by_id or not isinstance(key[1], str) or not key[1] or key in seen):
            raise ValueError('unique_audited_call_identity_required')
        seen.add(key)
        c = by_id[key[0]]
        if any(type(r.get(k)) is not type(c[k]) or r[k] != c[k]
               for k in ('repetition', 'task_id', 'success', 'time_visibility')):
            raise ValueError('interval_cell_metadata_disagrees')
        lower, upper = (r.get('logical_tokens_' + edge + '_bound') for edge in ('lower', 'upper'))
        if (not natural(lower) or not natural(upper) or lower > upper
                or type(r.get('complete_usage')) is not bool
                or (r['complete_usage'] and lower != upper)
                or r.get('terminal_usage_imputed') is not False):
            raise ValueError('valid_conditional_interval_without_imputation_required')
        grouped[key[0]].append(r)
    totals = []
    for c in cells:
        selected = grouped[c['run_id']]
        if (len(selected) != c['model_calls']
                or sum(not r['complete_usage'] for r in selected) != c['unknown_usage_calls']
                or sum(r['logical_tokens_lower_bound'] for r in selected if r['complete_usage'])
                    != c['known_total_tokens']):
            raise ValueError('all_calls_and_original_known_unknown_totals_must_match')
        totals.append({**{k: c[k] for k in ('run_id', 'repetition', 'task_id', 'time_visibility',
                       'success', 'model_calls', 'known_total_tokens', 'unknown_usage_calls')},
                       **{edge: sum(r['logical_tokens_' + edge + '_bound'] for r in selected)
                          for edge in ('lower', 'upper')}})
    return {'cells': totals,
            'repetitions': [{'repetition': rep, 'comparisons': [
                comparison([c for c in totals if c['repetition'] == rep], base)
                for base in POLICIES[:2]]} for rep in (1, 2)],
            'combined': [comparison(totals, base) for base in POLICIES[:2]],
            'independent_tasks': 4, 'repetitions_are_independent_tasks': False,
            'original_decisions': summarize(cells, [])}


def validate_closure(pipeline, batch, report, plan):
    validate_plan(plan)
    expected = [cell_id(*v) for v in run_order()]
    if (pipeline.get('status') != 'complete' or not pipeline.get('finished_at')
            or pipeline.get('server_stopped') is not True or pipeline.get('git_commit') != P82_COMMIT
            or batch.get('status') != 'complete' or batch.get('active') is not None
            or batch.get('git_commit') != P82_COMMIT
            or batch.get('planned') != expected or batch.get('completed') != expected
            or report.get('phase') != 'P82' or report.get('batch_status') != 'complete'
            or report.get('audit_errors') != []):
        raise ValueError('closed_frozen_audited_P82_required')
    cells = report['rows']
    check_cells(cells)
    if [r.get('run_id') for r in batch.get('rows', [])] != expected:
        raise ValueError('closed_batch_coverage_disagrees')
    for (_, number, _), c, executed in zip(run_order(), cells, batch['rows'], strict=True):
        if c['task_id'] != plan['known_tasks'][number - 1]['task_id']:
            raise ValueError('frozen_task_identity_changed')
        for key in ('repetition', 'task_id', 'time_visibility', 'success', 'model_calls',
                    'known_total_tokens', 'unknown_usage_calls', 'api_requests'):
            if type(c.get(key)) is not type(executed.get(key)) or c.get(key) != executed.get(key):
                raise ValueError('audit_batch_disagreement:' + key)
    decisions = summarize(cells, [])
    if any(report.get(k) != v for k, v in decisions.items()):
        raise ValueError('all_four_original_decisions_must_be_preserved')
    return decisions


def run(storage, root, backend):
    began = time.monotonic()
    target = root / 'reports/P82_usage_intervals_20261024.json'
    if target.exists():
        raise FileExistsError('preserve_first_P82_supplemental_intervals')
    pipeline_dir = storage / 'records/context_pilot/P82_pipeline_v01'
    pipeline_path = pipeline_dir / 'status.json'
    batch_path = storage / 'records/context_pilot/P82_batch_v01/status.json'
    pipeline, batch, report, plan, session = (read(p) for p in
        (pipeline_path, batch_path, root / REPORT, root / PLAN, root / SESSION))
    decisions = validate_closure(pipeline, batch, report, plan)
    for name, digest in plan['source_sha256'].items():
        if sha(root / name) != digest:
            raise ValueError('frozen_P82_source_changed:' + name)
    if (report['plan_sha256'] != sha(root / PLAN)
            or report['auditor_sha256'] != sha(root / 'scripts/audit_late_clock_comparison.py')
            or session['audit_source_sha256'] != sha(root / REPORT)
            or session['pipeline_source_sha256'] != sha(pipeline_path)
            or session['status'] != 'stopped' or session['owned_processes_absent'] is not True
            or session['runtime']['commit'] != COMMIT):
        raise ValueError('closed_audit_and_session_provenance_required')
    server = storage / pipeline['server_record_directory']
    final = read(server / 'summary.json')
    if (sha(server / 'summary.json') != session['source_sha256']
            or final != read(pipeline_dir / 'server_final.json') or final['status'] != 'stopped'
            or final['supervisor_pid'] != pipeline['server_supervisor_pid']):
        raise ValueError('same_closed_owned_server_required')
    for key in ('pid', 'supervisor_pid'):
        check = subprocess.run(['ps', '-p', str(final[key]), '-o', 'command='],
                               capture_output=True, text=True, timeout=10)
        if check.returncode != 1 or check.stdout.strip():
            raise ValueError('recorded_owned_process_still_present')
    command = final['command']
    if command[command.index('--parallel') + 1] != '1' or '--no-context-shift' not in command:
        raise ValueError('serial_nonshifting_runtime_required')
    backend_sources = {}
    for name, expected in BACKEND_BLOBS.items():
        data = (backend / name).read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if blob != expected:
            raise ValueError('pinned_backend_source_required')
        backend_sources[name] = {'git_blob': blob, 'sha256': sha(backend / name)}
    calls, requests, request_hashes, private_hashes = [], [], [], {}
    for row in report['rows']:
        directory = storage / 'records/context_pilot' / row['run_id']
        for stem in ('summary', 'usage', 'evaluation'):
            path = directory / (stem + '.json')
            if sha(path) != row[stem + '_sha256']:
                raise ValueError('audited_record_changed')
            private_hashes[str(path.relative_to(storage))] = sha(path)
        usage = read(directory / 'usage.json')
        checks = row['request_checks']
        if (len(usage) != row['model_calls']
                or [c['id'] for c in usage] != [c['call_id'] for c in checks]):
            raise ValueError('audited_call_order_required')
        for call, check in zip(usage, checks, strict=True):
            for stem in ('request', 'response'):
                path = directory / call['id'] / (stem + '.json')
                digest = sha(path) if path.exists() else None
                if digest != check[stem + '_sha256'] or (stem == 'request' and digest is None):
                    raise ValueError('audited_request_or_response_changed')
                private_hashes[str(path.relative_to(storage))] = digest
            calls.append({**call, **{k: row[k] for k in
                          ('run_id', 'repetition', 'task_id', 'success', 'time_visibility')}})
            requests.append(read(directory / call['id'] / 'request.json'))
            request_hashes.append(check['request_sha256'])
    log_path = server / 'server.log'
    tasks = parse_numeric_log(log_path.read_text())
    rows, known = interval_calls(calls, tasks, requests)
    for row, digest in zip(rows, request_hashes, strict=True):
        row['saved_request_sha256'] = digest
    aggregated = summarize_intervals(rows, report['rows'])
    if aggregated['original_decisions'] != decisions:
        raise ValueError('original_decisions_changed')
    names = (REPORT, PLAN, SESSION, 'scripts/inspect_late_clock_usage_intervals.py',
             'scripts/inspect_budget_visibility_usage_bounds.py',
             'scripts/inspect_repetition_usage_intervals.py', 'scripts/late_clock_comparison.py',
             'reports/P81_interval_backend_source_proof_20261024.json')
    result = dict(phase='P82_supplemental_usage_intervals', posthoc=True, rows=rows, **aggregated,
        conditional_intervals=True, complete_terminal_usage_recovered=False,
        original_unknown_usage_preserved=sum(not r['complete_usage'] for r in rows),
        known_receipts_checked=known, server_launches=len(tasks), backend_commit=COMMIT,
        backend_sources=backend_sources, source_sha256={name: sha(root / name) for name in names},
        private_record_sha256=private_hashes, private_log_sha256=sha(log_path),
        private_pipeline_sha256=sha(pipeline_path), private_batch_sha256=sha(batch_path),
        additional_generations=0, additional_input_count_requests=0, additional_api_requests=0,
        additional_evaluations=0, reserved_scenarios_read=0, private_reasoning_inspected_semantically=False,
        original_results_changed=False, original_adoption_gate_changed=False, novel_method_claim=False,
        general_quality_preservation_claim=False, wall_seconds=time.monotonic() - began,
        assumptions=[
            'One complete owned serial server log with no unrecorded external generations.',
            'Ordinal matching is checked against every known receipt; it is not cryptographic client/server binding.',
            'Positive generation progress follows complete input consumption in the pinned backend.',
            'The saved pre-dispatch count describes the same messages/tools as the generation request.',
            'Pinned max_tokens/n_predict_max limits accepted output, including work after cancellation.',
            'Logical input plus accepted output is not FLOPs, speculative draft work, money or elapsed time.',
            'All 24 cells are retained. Two repetitions of four known tasks are not eight independent tasks.',
            'These conditional sensitivity intervals are not confidence intervals or recovered terminal usage.',
        ])
    with target.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print({k: result[k] for k in ('known_receipts_checked', 'server_launches',
                                'original_unknown_usage_preserved', 'wall_seconds')})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--backend-source-root', type=Path, required=True)
    args = parser.parse_args()
    run(args.storage_root, args.repo_root, args.backend_source_root)
