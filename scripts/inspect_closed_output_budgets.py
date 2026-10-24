"""Count output-cap exposure in all closed P80/P81/P82 calls, offline.

Character lengths are not token allocations. Reasoning is never interpreted or
published. The diagnostic does not simulate a budget intervention or execution.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_size(value):
    if value is None:
        return 0
    if not isinstance(value, str):
        raise ValueError('non_text_output_outside_diagnostic_scope')
    return len(value)


def count_response(response, cap):
    known = response['status'] == 'ok'
    item = dict(terminal_observed=known, done_reason=None, output_tokens=None,
                at_requested_token_cap=None, reasoning_characters=None,
                content_characters=None, tool_calls=None, argument_characters=None,
                terminal_reasoning_token_count=None)
    if not known:
        return item
    count = response['output_tokens']
    if type(count) is not int or count < 0 or type(cap) is not int or cap < 1:
        raise ValueError('invalid_known_token_count_or_cap')
    if count > cap:
        raise ValueError('known_output_exceeds_requested_cap')
    message = response['message']
    calls = message.get('tool_calls') or []
    usage = response.get('usage_details') or {}
    detail = usage.get('completion_tokens_details') or {}
    reasoning_count = detail.get('reasoning_tokens')
    if reasoning_count is not None and (type(reasoning_count) is not int or
                                        not 0 <= reasoning_count <= count):
        raise ValueError('invalid_reasoning_token_receipt')
    item.update(done_reason=response['done_reason'], output_tokens=count,
                at_requested_token_cap=count == cap,
                reasoning_characters=text_size(message.get('reasoning_content')),
                content_characters=text_size(message.get('content')),
                tool_calls=len(calls),
                argument_characters=sum(text_size(c['function']['arguments']) for c in calls),
                terminal_reasoning_token_count=reasoning_count)
    return item


def inspect(storage, root, output):
    started = time.monotonic()
    if output.exists():
        raise FileExistsError('preserve_first_output_budget_diagnosis')
    names = ['reports/P80_comparison.json', 'reports/P81_repetitions.json',
             'reports/P82_comparison.json',
             'materials/20261024_truncated_code_prefix_scope/diagnosis.json',
             'reports/truncated_prefix_scope_provenance_20261024.json']
    anchor, repeat, late, prefix, ledger = [read(root / n) for n in names]
    for name, expected in ledger['source_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('bound_prefix_scope_changed')
    for name in names[:3]:
        if prefix['source_sha256'][name] != sha(root / name):
            raise ValueError('prefix_cohort_binding_changed')
    if any(x['batch_status'] != 'complete' or x['audit_errors'] for x in (anchor, repeat, late)):
        raise ValueError('closed_audited_cohorts_required')
    cells = anchor['rows'] + repeat['rows'] + late['rows']
    prefix_calls = {(x['run_id'], x['call_id']): x for x in prefix['calls']}
    if len(cells) != 48 or len(prefix_calls) != 855:
        raise ValueError('complete_original_scope_required')
    all_calls, controls = [], []
    for cell in cells:
        folder = storage / 'records/context_pilot' / cell['run_id']
        for index, check in enumerate(cell['request_checks'], 1):
            if check['call_id'] != f'call_{index:03d}':
                raise ValueError('original_call_order_required')
            call_folder = folder / check['call_id']
            for name in ('request', 'response'):
                if sha(call_folder / (name + '.json')) != check[name + '_sha256']:
                    raise ValueError('audited_call_changed')
            request = read(call_folder / 'request.json')
            response = read(call_folder / 'response.json')
            if response['status'] != check['status']:
                raise ValueError('audited_response_status_changed')
            prior = prefix_calls[(cell['run_id'], check['call_id'])]
            if prior['response_sha256'] != check['response_sha256']:
                raise ValueError('prefix_response_binding_changed')
            control = {k: request.get(k) for k in (
                'max_tokens', 'reasoning_effort', 'reasoning_budget_tokens',
                'thinking_budget_tokens', 'reasoning_budget_message',
                'reasoning_control', 'reasoning_format', 'chat_template_kwargs')}
            # No new textual instruction is exported from arbitrary request fields.
            if (control['reasoning_budget_message'] is not None or
                    control['chat_template_kwargs'] != {'thinking_mode': 'enabled'}):
                raise ValueError('unexpected_request_control_requires_separate_review')
            controls.append(json.dumps(control, sort_keys=True))
            item = dict(run_id=cell['run_id'], task_id=cell['task_id'],
                        call_id=check['call_id'], time_visibility=cell['time_visibility'],
                        task_success=cell['success'], requested_max_tokens=request['max_tokens'])
            item.update(count_response(response, request['max_tokens']))
            item.update(malformed_arguments=prior['malformed_arguments'],
                        request_sha256=check['request_sha256'], response_sha256=check['response_sha256'])
            if item['terminal_observed'] != prior['terminal_observed']:
                raise ValueError('prefix_observation_status_changed')
            all_calls.append(item)
    if len(all_calls) != 855 or sum(not x['terminal_observed'] for x in all_calls) != 6:
        raise ValueError('all_855_attempts_and_six_unknowns_required')
    by_reason = []
    for reason in ('tool_calls', 'length', 'stop', None):
        rows = [x for x in all_calls if x['done_reason'] == reason]
        measured = [x for x in rows if x['terminal_observed']]
        by_reason.append(dict(done_reason=reason, attempts=len(rows),
            known_output_tokens=sum(x['output_tokens'] for x in measured),
            at_requested_cap=sum(x['at_requested_token_cap'] for x in measured),
            public_tool_calls=sum(x['tool_calls'] for x in measured),
            malformed_arguments=sum(x['malformed_arguments'] for x in measured),
            reasoning_characters_min=min((x['reasoning_characters'] for x in measured), default=None),
            reasoning_characters_max=max((x['reasoning_characters'] for x in measured), default=None),
            argument_characters_min=min((x['argument_characters'] for x in measured), default=None),
            argument_characters_max=max((x['argument_characters'] for x in measured), default=None)))
    output.mkdir(parents=True, exist_ok=False)
    with (output / 'all_855_calls.csv').open('x', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(all_calls[0])); w.writeheader(); w.writerows(all_calls)
    result = dict(phase='closed_output_budget_scope', posthoc=True,
        created_at=datetime.now(timezone.utc).isoformat(),
        source_sha256={n:sha(root / n) for n in names}, script_sha256=sha(Path(__file__)),
        all_calls_sha256=sha(output / 'all_855_calls.csv'),
        independent_tasks=4, conditions=48, attempts=855, unknown_terminal_calls=6,
        request_control_groups=[dict(count=n, controls=json.loads(c)) for c,n in Counter(controls).items()],
        by_finish_reason=by_reason,
        at_cap_calls=[x for x in all_calls if x['at_requested_token_cap']],
        reasoning_token_receipts=sum(x['terminal_reasoning_token_count'] is not None for x in all_calls),
        terminal_reasoning_token_split_established=all(x['terminal_reasoning_token_count'] is not None
            for x in all_calls if x['terminal_observed']),
        character_counts_are_token_allocations=False, reasoning_semantically_read=False,
        raw_code_or_reasoning_published=False, new_model_generations=0,
        input_count_requests=0, environment_api_requests=0, evaluations=0,
        reserved_tasks_read=False, changed_budget_quality_or_cost_measured=False,
        analysis_wall_seconds=time.monotonic()-started)
    with (output / 'diagnosis.json').open('x') as f:
        json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print({k: result[k] for k in ('attempts','unknown_terminal_calls','by_finish_reason',
                                'request_control_groups','reasoning_token_receipts','analysis_wall_seconds')})
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('storage-root', 'repo-root', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args(); inspect(a.storage_root.resolve(), a.repo_root.resolve(), a.output.resolve())
