"""Posthoc lower bounds from a closed, serial server log, never terminal usage repair.

Read only numeric logger records. Associate all launches in the frozen batch order,
and require every known prompt/decode count to match before bounding any unknown.
No inference, tokenization, program execution, environment API or evaluation.
"""
import argparse
import hashlib
import re
import time
from pathlib import Path

from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha

COMMIT = '620d2225cc436ab0b001e3200e590e3b286ef9ab'
CONTEXT_BLOB = 'a18b7542c3af4fc367e6dcfcd09870e399bdca4b'


def parse_numeric_log(text):
    tasks, seen, active = [], set(), None
    for number, line in enumerate(text.splitlines(), 1):
        if 'launch_slot_' in line:
            m = re.search(r'id\s+(\d+)\s*\| task\s+(\d+)\s*\| processing task, is_child = 0$', line)
            if not m or active is not None or int(m[1]) != 0 or int(m[2]) in seen:
                raise ValueError('unique_serial_slot_zero_launches_required')
            seen.add(int(m[2]))
            active = dict(server_task=int(m[2]), launch_line=number, generation_progress=[], cancelled=False)
            tasks.append(active)
        if active is None:
            if re.search(r'\b(?:prompt eval time|n_gen)\s*=|stop processing:', line):
                raise ValueError('numeric_record_outside_active_task')
            continue
        tagged = re.search(r'id\s+(\d+)\s*\| task\s+(\d+)\s*\|', line)
        if tagged and (int(tagged[1]) != 0 or int(tagged[2]) != active['server_task']):
            raise ValueError('interleaved_server_task')
        for key, pattern in (
            ('processed_input', r'prompt eval time =\s*[0-9.]+ ms /\s*(\d+) tokens'),
            ('terminal_generated', r'\|\s+eval time =\s*[0-9.]+ ms /\s*(\d+) tokens')):
            m = re.search(pattern, line)
            if m:
                if key in active: raise ValueError('duplicate_terminal_timing')
                active[key] = int(m[1])
        m = re.search(r'n_gen =\s*(\d+), tg =', line)
        if m:
            n = int(m[1])
            if active['generation_progress'] and n < active['generation_progress'][-1]:
                raise ValueError('generation_counter_decreased')
            active['generation_progress'].append(n)
        if 'cancel task' in line:
            m = re.search(r'(?:id_)?task\s*=\s*(\d+)', line)
            if not m or int(m[1]) != active['server_task']:
                raise ValueError('unmatched_cancellation')
            active['cancelled'] = True
        if 'release:' in line:
            m = re.search(r'stop processing: n_tokens = (\d+), truncated = (\d+)$', line)
            if not m or int(m[2]) != 0: raise ValueError('untruncated_release_required')
            active.update(release_line=number, retained_tokens_at_release=int(m[1]))
            active = None
    if active is not None: raise ValueError('incomplete_server_log')
    return tasks


def bound_calls(calls, tasks):
    if not calls or len(calls) != len(tasks):
        raise ValueError('all_client_attempts_and_server_launches_required')
    if len({(c['run_id'], c['id']) for c in calls}) != len(calls):
        raise ValueError('duplicate_client_attempt')
    rows, known_checked = [], 0
    for c, t in zip(calls, tasks):
        peak = max(t['generation_progress'], default=0)
        row = dict(run_id=c['run_id'], call_id=c['id'], status=c['status'],
                   server_task=t['server_task'], launch_line=t['launch_line'], release_line=t['release_line'])
        if c['status'] == 'ok':
            if (t.get('processed_input') != c['input_tokens'] - c['cached_input_tokens']
                    or t.get('terminal_generated') != c['output_tokens']
                    or c['predicted_input_tokens'] != c['input_tokens']
                    or peak > c['output_tokens'] or t['cancelled']):
                raise ValueError('known_receipt_does_not_match_ordinal_server_task')
            known_checked += 1
            row.update(logical_tokens_lower_bound=c['input_tokens'] + c['output_tokens'],
                       complete_usage=True)
        else:
            # n_gen > 0 is logged only after DONE_PROMPT -> GENERATING in the
            # pinned server. Counting/admission uses the same messages/tools.
            if (not t['cancelled'] or peak <= 0 or 'terminal_generated' in t
                    or type(c['predicted_input_tokens']) is not int or c['predicted_input_tokens'] <= 0
                    or peak > c['output_cap']):
                raise ValueError('cancelled_generation_progress_required_for_bound')
            row.update(complete_usage=False, original_usage_unknown=True,
                       input_tokens_lower_bound=c['predicted_input_tokens'],
                       generated_tokens_lower_bound=peak,
                       logical_tokens_lower_bound=c['predicted_input_tokens'] + peak)
        rows.append(row)
    return rows, known_checked


def run(storage, root, server_source):
    began = time.monotonic()
    target = root / 'reports/P80_usage_lower_bounds_20261024.json'
    if target.exists(): raise FileExistsError('preserve_first_supplemental_bound')
    audit_path = root / 'reports/P80_comparison.json'
    report = read(audit_path); session = read(root / 'reports/P80_server_session.json')
    provenance = read(root / 'reports/P80_results_provenance_20261024.json')
    for name in ('reports/P80_comparison.json', 'reports/P80_server_session.json'):
        if sha(root / name) != provenance['source_sha256'][name]:
            raise ValueError('closed_P80_result_changed')
    if (report['batch_status'] != 'complete' or report['audit_errors'] or len(report['rows']) != 8
            or session['status'] != 'stopped' or not session['owned_processes_absent']
            or session['audit_source_sha256'] != sha(audit_path) or session['runtime']['commit'] != COMMIT):
        raise ValueError('closed_audited_P80_required')
    source = server_source.read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest()
    if blob != CONTEXT_BLOB: raise ValueError('pinned_backend_counter_source_required')
    pipeline = read(storage / 'records/context_pilot/P80_pipeline_v01/status.json')
    server = storage / pipeline['server_record_directory']
    if sha(server / 'summary.json') != session['source_sha256']:
        raise ValueError('wrong_closed_server')
    private_summary = read(server / 'summary.json'); command = private_summary['command']
    if command[command.index('--parallel') + 1] != '1' or '--no-context-shift' not in command:
        raise ValueError('serial_nonshifting_runtime_required')
    calls, usage_hashes = [], {}
    for row in report['rows']:
        path = storage / 'records/context_pilot' / row['run_id'] / 'usage.json'
        if sha(path) != row['usage_sha256']: raise ValueError('audited_usage_changed')
        usage_hashes[row['run_id']] = sha(path)
        calls.extend({**c, 'run_id': row['run_id'], 'time_visibility': row['time_visibility']} for c in read(path))
    log_path = server / 'server.log'
    tasks = parse_numeric_log(log_path.read_text())
    rows, known = bound_calls(calls, tasks)
    if len(rows) != 143 or known != 142 or sum(not r['complete_usage'] for r in rows) != 1:
        raise ValueError('whole_fixed_P80_cohort_required')
    totals = {policy: sum(r['logical_tokens_lower_bound'] for c, r in zip(calls, rows)
                         if c['time_visibility'] == policy) for policy in ('measured', 'not_exposed')}
    result = dict(phase='P80_supplemental_usage_bound', posthoc=True, rows=rows,
        complete_terminal_usage_recovered=False, original_unknown_usage_preserved=1,
        ordinal_association_known_calls_checked=known, audited_attempts=len(rows), server_launches=len(tasks),
        logical_token_lower_bounds=totals, measured_complete_total=totals['measured'],
        not_exposed_minus_measured_lower_bound=totals['not_exposed'] - totals['measured'],
        lower_bound_excludes_whole_task_savings=totals['not_exposed'] > totals['measured'],
        source_sha256={'reports/P80_comparison.json':sha(audit_path),
            'reports/P80_server_session.json':sha(root / 'reports/P80_server_session.json'),
            'reports/P80_results_provenance_20261024.json':sha(root / 'reports/P80_results_provenance_20261024.json'),
            'scripts/inspect_budget_visibility_usage_bounds.py':sha(Path(__file__)),
            'scripts/residual_output_budget.py':sha(root / 'scripts/residual_output_budget.py'),
            'scripts/local_llama.py':sha(root / 'scripts/local_llama.py')},
        private_server_log_sha256=sha(log_path), private_usage_sha256=usage_hashes,
        backend_source_commit=COMMIT, backend_context_git_blob=blob,
        backend_context_sha256=sha(server_source), wall_seconds=time.monotonic()-began,
        additional_generations=0, additional_input_count_requests=0, additional_api_requests=0,
        additional_evaluations=0, reserved_scenarios_read=0, private_reasoning_inspected_semantically=False,
        original_results_changed=False, original_adoption_gate_changed=False, novel_method_claim=False,
        assumptions=['Complete log of one owned serial server; no unrecorded external generations.',
            'Ordinal association is corroborated by every known receipt, not a cryptographic request-ID binding.',
            'Positive backend generation counter follows full prompt consumption in the pinned source.',
            'The pre-dispatch server input count describes the same messages/tools used for generation.',
            'This is a logical-token lower bound including cached input and late work, not billed money, FLOPs, a terminal receipt or an exact repaired total.'])
    write_json(target,result)
    print({k:result[k] for k in ('audited_attempts','ordinal_association_known_calls_checked',
        'logical_token_lower_bounds','not_exposed_minus_measured_lower_bound','complete_terminal_usage_recovered')})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root',type=Path,required=True)
    parser.add_argument('--repo-root',type=Path,default=ROOT)
    parser.add_argument('--server-source',type=Path,required=True)
    args=parser.parse_args()
    run(args.storage_root,args.repo_root,args.server_source)
