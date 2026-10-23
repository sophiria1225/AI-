"""Conditional logical-token intervals for the closed P80/P81 cohort.

Reads numeric server logs and saved request controls only. No inference, token
counting, API calls, evaluator execution or terminal-usage imputation.
"""
import argparse
import hashlib
import time
from pathlib import Path

from inspect_budget_visibility_usage_bounds import COMMIT, bound_calls, parse_numeric_log
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

BACKEND_BLOBS = {
    'tools/server/server-context.cpp': 'a18b7542c3af4fc367e6dcfcd09870e399bdca4b',
    'tools/server/server-schema.cpp': '54e126aa0c3572895042cd0a8c4faf4a0eb0b9f7',
    'tools/server/server-common.cpp': 'c32c0d1a5aa7b09e0afe4655a305c6d73f8e27d7',
}


def interval_calls(calls, tasks, requests):
    if len(requests) != len(calls):
        raise ValueError('every_saved_request_required')
    rows, known = bound_calls(calls, tasks)
    for c, r, request in zip(calls, rows, requests):
        cap = c['output_cap']
        if (type(cap) is not int or not 1 <= cap <= 4096
                or type(request.get('max_tokens')) is not int or request['max_tokens'] != cap
                or any(k in request for k in ('n_predict', 'max_completion_tokens', 'n', 'n_cmpl'))
                or request.get('stream') is not False):
            raise ValueError('unambiguous_single_completion_output_cap_required')
        if c['status'] == 'ok':
            if not 0 <= c['output_tokens'] <= cap:
                raise ValueError('known_receipt_exceeds_pinned_cap')
            upper = r['logical_tokens_lower_bound']
        else:
            if c['status'] != 'error' or any(c.get(k) is not None for k in
                    ('input_tokens', 'output_tokens', 'cached_input_tokens')):
                raise ValueError('preserve_original_unknown_terminal_usage')
            upper = c['predicted_input_tokens'] + cap
            r['generated_tokens_upper_bound'] = cap
        if upper < r['logical_tokens_lower_bound']:
            raise ValueError('inconsistent_interval')
        r.update(logical_tokens_upper_bound=upper, terminal_usage_imputed=False,
                 repetition=c['repetition'], task_id=c['task_id'], success=c['success'],
                 time_visibility=c['time_visibility'])
    return rows, known


def cost_partition(rows):
    if not rows:
        return {'measured': [0, 0], 'not_exposed': [0, 0], 'H_minus_M': [0, 0],
                'original_unknown_usage_calls': 0}
    totals = {p: [sum(r[f'logical_tokens_{edge}_bound'] for r in rows if r['time_visibility'] == p)
                  for edge in ('lower', 'upper')] for p in ('measured', 'not_exposed')}
    return {**totals, 'H_minus_M': [totals['not_exposed'][0] - totals['measured'][1],
                                  totals['not_exposed'][1] - totals['measured'][0]],
            'original_unknown_usage_calls': sum(not r['complete_usage'] for r in rows)}


def summarize(rows):
    outcomes = {}
    for r in rows:
        if type(r['success']) is not bool or r['time_visibility'] not in ('measured', 'not_exposed'):
            raise ValueError('evaluated_binary_outcomes_and_two_frozen_arms_required')
        key = (r['repetition'], r['task_id'], r['time_visibility'])
        if key in outcomes and outcomes[key] != r['success']:
            raise ValueError('inconsistent_cell_outcome')
        outcomes[key] = r['success']
    pairs = {(rep, task) for rep, task, _ in outcomes}
    categories = {}
    for rep, task in pairs:
        if any((rep, task, p) not in outcomes for p in ('measured', 'not_exposed')):
            raise ValueError('paired_cell_outcomes_required')
        m, h = [outcomes[rep, task, p] for p in ('measured', 'not_exposed')]
        categories[rep, task] = 'both_success' if m and h else 'both_failure' if not m and not h else 'discordant'
    result = {'total': cost_partition(rows)}
    for category in ('both_success', 'both_failure', 'discordant'):
        selected = [r for r in rows if categories[r['repetition'], r['task_id']] == category]
        result[category] = cost_partition(selected)
        result[category]['task_pairs'] = sum(c == category for c in categories.values())
    return result


def run(storage, root, backend):
    began = time.monotonic()
    target = root / 'reports/P81_usage_intervals_20261024.json'
    if target.exists():
        raise FileExistsError('preserve_first_supplemental_intervals')
    source_hashes, backend_sources, session_results, all_rows = {}, {}, [], []
    for name, expected in BACKEND_BLOBS.items():
        data = (backend / name).read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if blob != expected:
            raise ValueError('pinned_backend_source_required')
        backend_sources[name] = {'git_blob': blob, 'sha256': sha(backend / name)}
    p80, p81 = read(root / 'reports/P80_comparison.json'), read(root / 'reports/P81_repetitions.json')
    if p81['anchor_sha256'] != sha(root / 'reports/P80_comparison.json'):
        raise ValueError('closed_anchor_identity_required')
    for phase, audit, report_name, provenance_name, count, known_count in (
        ('P80', p80, 'P80_comparison.json', 'P80_results_provenance_20261024.json', 143, 142),
        ('P81', p81, 'P81_repetitions.json', 'P81_P83_results_provenance_20261024.json', 286, 285),
    ):
        report_path = root / 'reports' / report_name
        session_path = root / 'reports' / f'{phase}_server_session.json'
        provenance_path = root / 'reports' / provenance_name
        provenance, session = read(provenance_path), read(session_path)
        for path in (report_path, session_path):
            if sha(path) != provenance['source_sha256'][str(path.relative_to(root))]:
                raise ValueError('closed_result_changed')
        if (audit['batch_status'] != 'complete' or audit['audit_errors']
                or session['status'] != 'stopped' or not session['owned_processes_absent']
                or session['audit_source_sha256'] != sha(report_path) or session['runtime']['commit'] != COMMIT):
            raise ValueError('closed_audited_session_required')
        pipeline_path = storage / f'records/context_pilot/{phase}_pipeline_v01/status.json'
        pipeline = read(pipeline_path)
        server = storage / pipeline['server_record_directory']
        if sha(server / 'summary.json') != session['source_sha256']:
            raise ValueError('wrong_closed_server')
        command = read(server / 'summary.json')['command']
        if command[command.index('--parallel') + 1] != '1' or '--no-context-shift' not in command:
            raise ValueError('serial_nonshifting_runtime_required')
        calls, requests, request_hashes, usage_hashes = [], [], [], {}
        for row in audit['rows']:
            directory = storage / 'records/context_pilot' / row['run_id']
            usage_path = directory / 'usage.json'
            if sha(usage_path) != row['usage_sha256'] or row['record_status'] != 'evaluated':
                raise ValueError('audited_evaluated_usage_required')
            usage_hashes[row['run_id']] = sha(usage_path)
            usage = read(usage_path)
            checks = {c['call_id']: c for c in row['request_checks']}
            if len(checks) != len(usage) or len(usage) != row['model_calls']:
                raise ValueError('all_audited_calls_required')
            for c in usage:
                request_path = directory / c['id'] / 'request.json'
                digest = sha(request_path)
                if digest != checks[c['id']]['request_sha256']:
                    raise ValueError('audited_request_changed')
                calls.append({**c, **{k: row[k] for k in ('run_id', 'task_id', 'success', 'time_visibility')},
                              'repetition': row.get('repetition', 1)})
                requests.append(read(request_path))
                request_hashes.append(digest)
        log_path = server / 'server.log'
        tasks = parse_numeric_log(log_path.read_text())
        rows, known = interval_calls(calls, tasks, requests)
        if len(rows) != count or known != known_count:
            raise ValueError('whole_frozen_cohort_required')
        for row, digest in zip(rows, request_hashes):
            row['saved_request_sha256'] = digest
        all_rows.extend(rows)
        session_results.append({'phase': phase, 'attempts': len(rows), 'server_launches': len(tasks),
            'known_receipts_checked': known, 'private_log_sha256': sha(log_path),
            'private_usage_sha256': usage_hashes, 'private_pipeline_sha256': sha(pipeline_path)})
        for path in (report_path, session_path, provenance_path):
            source_hashes[str(path.relative_to(root))] = sha(path)
    if len({(r['repetition'], r['task_id'], r['time_visibility']) for r in all_rows}) != 24:
        raise ValueError('all_24_cells_required')
    for name in ('scripts/inspect_repetition_usage_intervals.py',
                 'scripts/inspect_budget_visibility_usage_bounds.py', 'scripts/local_llama.py',
                 'scripts/residual_output_budget.py', 'reports/P81_interval_backend_source_proof_20261024.json'):
        source_hashes[name] = sha(root / name)
    result = dict(phase='P81_supplemental_usage_intervals', posthoc=True, rows=all_rows,
        sessions=session_results, repetitions={str(rep): summarize([r for r in all_rows if r['repetition'] == rep])
                                               for rep in (1, 2, 3)},
        combined=summarize(all_rows), conditional_intervals=True,
        complete_terminal_usage_recovered=False, original_unknown_usage_preserved=2,
        backend_commit=COMMIT, backend_sources=backend_sources, source_sha256=source_hashes,
        additional_generations=0, additional_input_count_requests=0, additional_api_requests=0,
        additional_evaluations=0, reserved_scenarios_read=0, private_reasoning_inspected_semantically=False,
        original_results_changed=False, original_adoption_gate_changed=False, novel_method_claim=False,
        general_quality_preservation_claim=False, wall_seconds=time.monotonic() - began,
        assumptions=[
            'Complete logs of two owned serial servers, with no unrecorded external generations.',
            'Ordinal matching is corroborated by all 427 known receipts, not cryptographic client/server request binding.',
            'Positive pinned-backend generation counters follow complete prompt consumption.',
            'Pre-dispatch input counts describe the same messages/tools used for generation, including cached input.',
            'Pinned max_tokens alias and n_predict_max enforcement bound accepted generated tokens, including work after client cancellation.',
            'Bounds concern logical input plus accepted output tokens, not FLOPs, speculative draft work, billed money or elapsed time.',
            'The three repetitions are four previously seen tasks, not twelve independent tasks; no population confidence interval is estimated.',
        ])
    write_json(target, result)
    print({k: result[k] for k in ('sessions', 'repetitions', 'combined', 'original_unknown_usage_preserved', 'wall_seconds')})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--backend-source-root', type=Path, required=True)
    args = parser.parse_args()
    run(args.storage_root, args.repo_root, args.backend_source_root)
