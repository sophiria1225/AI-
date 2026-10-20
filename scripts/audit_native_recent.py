"""Replay recorded memory-selection calculations offline, never the environment."""
import argparse
import hashlib
import json
from pathlib import Path

from audit_native_execution import inspect_operations
from native_conversation import NativeConversation
from native_recent_window import recent_window
from run_native_recent import NATIVE_PROMPT
from summarize_context_pilot import summarize_trial


def read(path):
    return json.loads(path.read_text())


def replay_selection(conversation, decision, counts, plan):
    position = 0

    def recorded_count(content):
        nonlocal position
        if position >= len(counts):
            raise ValueError('missing count record')
        record = counts[position]; position += 1
        if (record['status'] != 'ok' or record['characters'] != len(content)
                or record['content_sha256'] != hashlib.sha256(content.encode()).hexdigest()):
            raise ValueError('count record does not match the reconstructed history')
        return record['tokens']

    messages, selected = recent_window(conversation, recorded_count,
                                       plan['history_budget_tokens'], plan['observation_page_characters'])
    if selected != decision['selection'] or position != len(counts):
        raise ValueError('selection differs from the recorded calculations')
    return messages


def audit(directory):
    result = summarize_trial(directory)
    if result['arm'] != 'native_recent':
        raise ValueError('requires a finished recent-history trial')
    plan, provenance = read(directory / 'plan.json'), read(directory / 'provenance.json')
    for name in ('run_native_recent.py', 'native_conversation.py', 'native_recent_window.py', 'native_memory_view.py'):
        if hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest() != provenance['sources'][name]:
            raise ValueError('audit must use the frozen memory-selection implementation')
    usage = read(directory / 'usage.json')
    events, spans = read(directory / 'events.json'), read(directory / 'spans.json')
    payloads = {c['id']: read(directory / c['id'] / 'request.json') for c in usage}
    responses = {c['id']: read(directory / c['id'] / 'response.json') for c in usage}
    summary = read(directory / 'summary.json')
    result.update(inspect_operations(usage, events, spans, payloads, responses, summary))
    views, counts = read(directory / 'memory_views.json'), read(directory / 'memory_counting.json')
    by_call = {v['next_call_id']: v for v in views}
    errors, before_tokens = [], 0
    if len(by_call) != len(views):
        errors.append('duplicated selection decision')
    end = 0
    for decision in views:
        if decision['counting_start_index'] != end or not end <= decision['counting_end_index'] <= len(counts):
            errors.append('selection count ranges overlap or omit recorded requests')
        end = decision['counting_end_index']
    if summary['stop_reason'] == 'agent_declared_complete' and end != len(counts):
        errors.append('completed execution has unassigned count requests')
    conversation = NativeConversation(NATIVE_PROMPT, read(directory / 'public_task.json'))
    for row in usage:
        cid = row['id']; decision = by_call.get(cid)
        if decision is None:
            errors.append(cid + ': missing memory decision')
            break
        if decision['known_tokens_before'] != before_tokens:
            errors.append(cid + ': pre-decision cost differs from previous calls')
        try:
            expected = replay_selection(conversation, decision, counts[
                decision['counting_start_index']:decision['counting_end_index']], plan)
            if payloads[cid]['messages'] != expected:
                errors.append(cid + ': model input differs from selected original turns')
        except (ValueError, KeyError, IndexError, TypeError) as error:
            errors.append(cid + ': cannot replay selection: ' + type(error).__name__)
        if row['status'] == 'ok':
            before_tokens += row['input_tokens'] + row['output_tokens']
            conversation.append(responses[cid]['message'], [spans[e['span_id']] for e in events if e['call'] == cid])
    if len(counts) != summary['memory_token_count_requests']:
        errors.append('count request accounting differs')
    if len(views) != summary['memory_selections_completed']:
        errors.append('completed selection accounting differs')
    if not len(views) <= summary['memory_selection_attempts'] <= len(views) + 1:
        errors.append('selection attempts must include at most one failed terminal attempt')
    if sum(r['status'] != 'ok' for r in counts) != summary['memory_token_count_failures']:
        errors.append('failed count accounting differs')
    result.update(memory_audit_errors=errors,
                  memory_selection_attempts=summary['memory_selection_attempts'],
                  memory_selection_seconds=summary['memory_selection_seconds'],
                  memory_token_count_requests=len(counts),
                  memory_token_count_failures=summary['memory_token_count_failures'],
                  memory_budget_overflows=summary['memory_budget_overflows'],
                  model_calls_by_auditor=0, environment_operations=0, final_evaluations=0,
                  scope='Deterministic replay of recorded history selections, tokenizer-input hashes, '
                        'actual model inputs, operations and costs. No hidden task state or replayed actions.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.trial)
    result['auditor_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'run_id': result['run_id'], 'usage_errors': result['audit_errors'],
                      'dispatch_errors': result['dispatch_audit_errors'], 'memory_errors': result['memory_audit_errors']}))
