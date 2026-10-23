"""Bounded metadata-only inspection of the fixed P29/P71 history population."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import signal
import subprocess
import time

from reasoning_history import public_assistant, reasoning_shape, with_recorded_reasoning

ROOT = Path(__file__).resolve().parents[1]
PLAN = 'configs/P75_reasoning_history_v01.json'
ZERO_KEYS = ('model_generations', 'environment_api_requests', 'evaluator_calls',
             'tokenizer_calls', 'saved_code_executions', 'task_databases_read', 'reserved_scenarios_read')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def inspect_attempt(request, response, previous, expected_status):
    if response.get('status') != expected_status or expected_status not in ('ok', 'error'):
        raise ValueError('recorded_response_status_disagrees')
    messages = request.get('messages')
    if not isinstance(messages, list) or any(not isinstance(m, dict) for m in messages):
        raise ValueError('invalid_saved_messages')
    assistants = [m for m in messages if m.get('role') == 'assistant']
    if len(assistants) != len(previous):
        raise ValueError('causal_prefix_length_disagrees')
    if any(public_assistant(a) != public_assistant(b)
           for a, b in zip(assistants, previous, strict=True)):
        raise ValueError('causal_public_assistant_values_disagree')
    shapes = [reasoning_shape(m) for m in assistants]
    old_shapes = [reasoning_shape(m) for m in previous]
    no_overwrite = all(m == public_assistant(m) for m in assistants)
    restored_characters = None
    if no_overwrite:
        restored = with_recorded_reasoning(messages, previous)
        restored_characters = sum(reasoning_shape(m)['characters'] for m in restored
                                  if m.get('role') == 'assistant')
        if restored_characters != sum(s['characters'] for s in old_shapes):
            raise ValueError('restoration_character_accounting_disagrees')
    result = {'recorded_status': expected_status, 'public_prefix_matches': True,
        'input_assistant_messages': len(assistants),
        'input_reasoning_fields': sum(s['field_present'] for s in shapes),
        'input_nonempty_reasoning_messages': sum(s['nonempty'] for s in shapes),
        'input_reasoning_characters': sum(s['characters'] for s in shapes),
        'input_inline_think_marker_messages': sum(s['inline_think_begin'] or s['inline_think_end'] for s in shapes),
        'preceding_nonempty_reasoning_responses': sum(s['nonempty'] for s in old_shapes),
        'preceding_reasoning_characters': sum(s['characters'] for s in old_shapes),
        'reasoning_fields_exactly_match_preceding': all(
            ('reasoning_content' in a) == ('reasoning_content' in b)
            and a.get('reasoning_content') == b.get('reasoning_content')
            for a, b in zip(assistants, previous, strict=True)),
        'restorable_without_overwrite': no_overwrite,
        'restored_reasoning_characters': restored_characters,
        'known_output_reasoning': None}
    if expected_status == 'ok':
        result['known_output_reasoning'] = reasoning_shape(response['message'])
    return result


def run(storage, expected_sha, ci_path):
    output = ROOT / 'reports/P75_reasoning_history.json'
    if output.exists():
        raise FileExistsError('preserve_existing_P75_result')
    started = time.monotonic()
    result = {'phase': 'P75', 'status': 'stopped', 'rows': [], 'groups': [],
              **{k: 0 for k in ZERO_KEYS}, 'novel_method_claim': False,
              'quality_improvement_established': False, 'measured_savings': None}
    def timed_out(*_):
        raise TimeoutError('metadata_inspection_deadline')
    previous_handler = signal.signal(signal.SIGALRM, timed_out)
    signal.setitimer(signal.ITIMER_REAL, 120)
    try:
        actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        if not re.fullmatch(r'[0-9a-f]{40}', expected_sha) or actual != expected_sha:
            raise ValueError('fixed_commit_changed')
        if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
            raise ValueError('worktree_not_clean_before_inspection')
        ci = read(ci_path)
        if (len(ci) != 2 or {r['event'] for r in ci} != {'push', 'pull_request'}
                or any(r['head_sha'] != actual or r['status'] != 'completed' or r['conclusion'] != 'success'
                       or r['job_head_sha'] != actual or r['job_conclusion'] != 'success'
                       or r['job_name'] != 'accounting-and-syntax' for r in ci)):
            raise ValueError('both_exact_commit_workflows_and_jobs_required')
        plan = read(ROOT / PLAN)
        if (plan['phase'] != 'P75' or [plan[k] for k in (
                'known_tasks', 'planned_calls', 'prefix_calls', 'continuation_calls',
                'known_usage_calls', 'unknown_usage_calls', 'max_wall_seconds', 'max_file_bytes')]
                != [4, 105, 32, 73, 103, 2, 120, 8388608]
                or len(plan['groups']) != 16 or any(plan[k] for k in ZERO_KEYS)):
            raise ValueError('fixed_population_or_budget_changed')
        for path, expected in plan['source_sha256'].items():
            if sha(ROOT / path) != expected:
                raise ValueError('historical_source_changed')
        if sha(storage / plan['template_relative_path']) != plan['template_sha256']:
            raise ValueError('pinned_template_changed')
        result.update(git_commit=actual, ci=ci, plan_sha256=sha(ROOT / PLAN),
            source_sha256=plan['source_sha256'], template_sha256=plan['template_sha256'],
            protocol_sha256=sha(ROOT / 'docs/experiments/P75_reasoning_history.md'),
            implementation_sha256={p: sha(ROOT / p) for p in (
                'scripts/reasoning_history.py', 'scripts/inspect_reasoning_history.py',
                'tests/test_reasoning_history.py', 'tests/test_reasoning_history_inspection.py')})
        completed_prefixes = {}
        for group in plan['groups']:
            run_id = group['run_id']
            if not re.fullmatch(r'(P29_0[1-4]_CODE|P71_0[1-4]_(FULL_KEEP|DETAILS_OMITTED_KEEP|DETAILS_AND_LISTINGS_OMITTED_KEEP))', run_id):
                raise ValueError('unapproved_run_identity')
            folder = storage / 'records/context_pilot' / run_id
            folder.resolve().relative_to(storage.resolve())
            if sha(folder / 'usage.json') != group['usage_sha256']:
                raise ValueError('usage_inventory_changed')
            previous = list(completed_prefixes[group['prefix_run']]) if group['prefix_run'] else []
            start = len(result['rows'])
            for index, call in enumerate(group['calls'], 1):
                if call['call_id'] != f'call_{index:03d}':
                    raise ValueError('call_order_changed')
                packets = {}
                if set(call['files']) != {'request.json', 'response.json'}:
                    raise ValueError('unapproved_packet_names')
                for name, expected in call['files'].items():
                    path = folder / call['call_id'] / name
                    path.resolve().relative_to(storage.resolve())
                    if path.stat().st_size > plan['max_file_bytes'] or sha(path) != expected:
                        raise ValueError('saved_packet_hash_or_size_changed')
                    packets[name] = read(path)
                inspected = inspect_attempt(packets['request.json'], packets['response.json'],
                                            previous, call['recorded_status'])
                result['rows'].append({'run_id': run_id, 'source': group['source'],
                    'call_id': call['call_id'], 'source_sha256': call['files'], **inspected})
                if call['recorded_status'] == 'ok':
                    previous.append(packets['response.json']['message'])
                elif index != len(group['calls']):
                    raise ValueError('unknown_response_has_later_generation')
            rows = result['rows'][start:]
            if len(rows) != group['call_count']:
                raise ValueError('group_population_changed')
            counts = Counter(r['recorded_status'] for r in rows)
            result['groups'].append({'run_id': run_id, 'source': group['source'],
                'attempts': len(rows), 'known_output_responses': counts['ok'],
                'unknown_usage_attempts': counts['error'],
                'nonempty_known_output_reasoning': sum((r['known_output_reasoning'] or {}).get('nonempty', False) for r in rows),
                'known_output_reasoning_characters': sum((r['known_output_reasoning'] or {}).get('characters', 0) for r in rows),
                'requests_containing_nonempty_reasoning': sum(r['input_nonempty_reasoning_messages'] > 0 for r in rows),
                'requests_omitting_nonempty_preceding_reasoning': sum(
                    r['preceding_nonempty_reasoning_responses'] > 0 and r['input_nonempty_reasoning_messages'] == 0 for r in rows)})
            if group['source'] == 'prefix':
                if len(previous) != 8: raise ValueError('fixed_prefix_not_fully_known')
                completed_prefixes[run_id] = previous
        result['totals'] = {k: sum(g[k] for g in result['groups']) for k in (
            'attempts', 'known_output_responses', 'unknown_usage_attempts', 'nonempty_known_output_reasoning',
            'known_output_reasoning_characters', 'requests_containing_nonempty_reasoning',
            'requests_omitting_nonempty_preceding_reasoning')}
        if [result['totals'][k] for k in ('attempts', 'known_output_responses', 'unknown_usage_attempts')] != [105, 103, 2]:
            raise ValueError('complete_population_disagrees')
        result['status'] = 'complete'
    except Exception as exc:
        result['error_type'] = type(exc).__name__
        # Never serialize exception payloads or saved message text.
        result['error_reason'] = str(exc) if type(exc) in (ValueError, TimeoutError) else 'inspect_local_exception_type'
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous_handler)
        result['accounted_attempts'] = len(result['rows'])
        result['unprocessed_attempts'] = 105 - len(result['rows'])
        result['wall_seconds'] = time.monotonic() - started
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'totals', 'wall_seconds')}))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--expected-sha', required=True)
    p.add_argument('--ci-evidence', type=Path, required=True)
    args = p.parse_args(); run(args.storage_root.resolve(), args.expected_sha, args.ci_evidence.resolve())
