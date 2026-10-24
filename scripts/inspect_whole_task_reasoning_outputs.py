"""Describe all audited P88 public output boundaries after the cohort closes.

No semantic reading of reasoning, execution, repair, tokenization or inference.
Syntactic completion is an output property, never a task-quality certificate.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from pathlib import Path
import time

from build_whole_task_reasoning_budget_report import FILES, validated
from fixed_reasoning_budget_replay import code_completion
from inspect_closed_output_budgets import count_response
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha
from whole_task_reasoning_budget import BUDGETS, POLICIES

DEPENDENCIES = ("scripts/inspect_whole_task_reasoning_outputs.py",
    "scripts/build_whole_task_reasoning_budget_report.py",
    "scripts/fixed_reasoning_budget_replay.py", "scripts/inspect_closed_output_budgets.py")
CALL_FIELDS = ("run_id", "task_id", "reasoning_policy", "call_id", "task_success",
    "requested_max_tokens", "reasoning_budget_tokens", "terminal_observed", "done_reason",
    "output_tokens", "at_requested_token_cap", "reasoning_characters", "content_characters",
    "tool_calls", "argument_characters", "terminal_reasoning_token_count", "python_calls",
    "malformed_json_calls", "shape_invalid_calls", "syntax_invalid_calls", "other_tool_calls",
    "complete_code_submission", "task_quality_established", "request_sha256", "response_sha256")


def checked_json(path, expected):
    if expected is None:
        if path.exists():
            raise ValueError('file_appeared_after_audit:' + path.name)
        return None
    if sha(path) != expected:
        raise ValueError('audited_file_changed:' + path.name)
    return read(path)


def profile_cell(storage, row):
    cell = {k: row[k] for k in ('run_id', 'task_id', 'reasoning_policy', 'record_status', 'success')}
    if row['record_status'] in ('not_run', 'incomplete_worker'):
        cell.update(attempts=None, known_terminals=None, unknown_terminals=None,
                    known_output_tokens=None, complete_code_submissions=None)
        return cell, []
    if row['record_status'] not in ('evaluated', 'unevaluated'):
        raise ValueError('closed_audited_cell_required')
    folder = storage / 'records/context_pilot' / row['run_id']
    for name in ('summary', 'usage', 'evaluation'):
        checked_json(folder / (name + '.json'), row[name + '_sha256'])
    calls = []
    for index, check in enumerate(row['request_checks'], 1):
        if check['call_id'] != f'call_{index:03d}':
            raise ValueError('all_calls_in_original_order_required')
        path = folder / check['call_id']
        request = checked_json(path / 'request.json', check['request_sha256'])
        response = checked_json(path / 'response.json', check['response_sha256'])
        if request is not None and request.get('reasoning_budget_tokens') != BUDGETS[row['reasoning_policy']]:
            raise ValueError('explicit_executed_budget_required')
        if response is not None and response['status'] != check['status']:
            raise ValueError('audited_response_status_changed')
        if check['status'] == 'ok' and (request is None or response is None):
            raise ValueError('known_terminal_requires_request_and_response')
        value = response if response is not None else {'status': 'error'}
        cap = request['max_tokens'] if request is not None else None
        item = dict(run_id=row['run_id'], task_id=row['task_id'],
            reasoning_policy=row['reasoning_policy'], call_id=check['call_id'],
            task_success=row['success'], requested_max_tokens=cap,
            reasoning_budget_tokens=request.get('reasoning_budget_tokens') if request is not None else None,
            request_sha256=check['request_sha256'], response_sha256=check['response_sha256'])
        item.update(count_response(value, cap)); item.update(code_completion(value))
        calls.append(item)
    if (len(calls) != row['model_calls']
            or sum(not c['terminal_observed'] for c in calls) != row['unknown_usage_calls']
            or sum(c['output_tokens'] for c in calls if c['terminal_observed']) != row['output_tokens']):
        raise ValueError('all_attempts_and_known_output_must_match_audit')
    known = [c for c in calls if c['terminal_observed']]
    cell.update(attempts=len(calls), known_terminals=len(known), unknown_terminals=len(calls)-len(known),
        known_output_tokens=sum(c['output_tokens'] for c in known),
        complete_code_submissions=sum(c['complete_code_submission'] for c in known))
    return cell, calls


def aggregate(cells, calls, policy):
    selected = [r for r in cells if r['reasoning_policy'] == policy]
    attempted = [r for r in calls if r['reasoning_policy'] == policy]
    known = [r for r in attempted if r['terminal_observed']]
    return dict(reasoning_policy=policy, planned_conditions=len(selected),
        evaluated_conditions=sum(r['record_status'] == 'evaluated' for r in selected),
        unmeasured_conditions=sum(r['attempts'] is None for r in selected),
        observed_attempts=len(attempted), known_terminals=len(known),
        unknown_terminals=len(attempted)-len(known),
        known_output_tokens=sum(r['output_tokens'] for r in known),
        all_attempted_calls_accounted=all(r['record_status'] != 'incomplete_worker' for r in selected),
        finish_reason_counts=dict(Counter(r['done_reason'] for r in known)),
        at_requested_cap=sum(r['at_requested_token_cap'] for r in known),
        complete_code_submissions=sum(r['complete_code_submission'] for r in known),
        known_responses_without_tool_calls=sum(r['tool_calls'] == 0 for r in known),
        malformed_json_calls=sum(r['malformed_json_calls'] for r in known),
        shape_invalid_calls=sum(r['shape_invalid_calls'] for r in known),
        syntax_invalid_calls=sum(r['syntax_invalid_calls'] for r in known),
        other_tool_calls=sum(r['other_tool_calls'] for r in known),
        explicit_reasoning_token_receipts=sum(r['terminal_reasoning_token_count'] is not None for r in known))


def inspect(storage, root, output):
    started = time.monotonic()
    if output.exists():
        raise FileExistsError('preserve_first_P88_output_diagnosis')
    _, report, _, _, _ = validated(root)
    private = storage / 'records/context_pilot/P88_pipeline_v01'
    state = checked_json(private / 'status.json', report['pipeline_status_sha256'])
    server = checked_json(private / 'server_final.json', report['server_final_sha256'])
    if (state['status'] not in ('complete', 'stopped') or not state['server_stopped']
            or server['status'] != 'stopped'):
        raise ValueError('owned_pipeline_must_be_closed')
    cells, calls = [], []
    for row in report['rows']:
        cell, observed = profile_cell(storage, row); cells.append(cell); calls.extend(observed)
    output.mkdir(parents=True, exist_ok=False)
    for name, rows, fields in [('all_calls.csv', calls, CALL_FIELDS),
                              ('all_eight_conditions.csv', cells, tuple(cells[0]))]:
        with (output / name).open('x', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader(); writer.writerows(rows)
    result = dict(phase='P88_closed_public_output_boundaries', created_at=datetime.now(timezone.utc).isoformat(),
        independent_tasks=4, planned_conditions=8, repetitions=1, observed_attempts=len(calls),
        all_planned_conditions_retained=True,
        cells=cells, by_policy=[aggregate(cells, calls, p) for p in POLICIES],
        source_sha256={p: sha(root / p) for p in (*FILES, *DEPENDENCIES)},
        all_calls_sha256=sha(output / 'all_calls.csv'),
        all_eight_conditions_sha256=sha(output / 'all_eight_conditions.csv'),
        primary_gate_changed=False, syntax_is_task_quality=False,
        forced_budget_activation_observable_from_this_profile=False,
        per_call_outputs_are_independent_tasks=False, character_counts_are_token_allocations=False,
        reasoning_semantically_read=False, raw_code_or_reasoning_published=False,
        additional_model_generations=0, additional_tokenizations=0,
        additional_environment_api_requests=0, additional_evaluations=0,
        analysis_wall_seconds=time.monotonic()-started)
    write_json(output / 'diagnosis.json', result)
    print({k: result[k] for k in ('observed_attempts', 'by_policy', 'analysis_wall_seconds')})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); inspect(args.storage_root.resolve(), args.repo_root.resolve(), args.output.resolve())
