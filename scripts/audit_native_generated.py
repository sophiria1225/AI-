"""Replay generated-memory control decisions from saved outputs, never inference."""
import argparse
import hashlib
import json
from pathlib import Path

from appworld_native_tools import NativeCatalog
from audit_native_execution import inspect_operations
from inspect_appworld_api_schemas import load_public_tools
from native_conversation import NativeConversation
from run_context_comparison import BudgetStop
from run_native_generated import NATIVE_PROMPT, make_memory
from summarize_context_pilot import summarize_trial


class AuditMismatch(RuntimeError):
    pass


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def audit(directory, data_root):
    result = summarize_trial(directory)
    summary, plan = read(directory / 'summary.json'), read(directory / 'plan.json')
    if result['arm'] not in ('native_focus', 'native_ledger', 'native_ledger_aligned'):
        raise ValueError('expected completed generated-memory adaptation')
    provenance = read(directory / 'provenance.json')
    sources = ['run_native_generated.py', 'native_focus_memory.py', 'native_memory_view.py',
               'native_conversation.py', 'analyze_focus_shortcircuit.py', 'context_preservation.py']
    if result['arm'] in ('native_ledger', 'native_ledger_aligned'):
        sources.append('native_ledger_memory.py')
    if result['arm'] == 'native_ledger_aligned':
        sources += ['aligned_ledger_memory.py', 'ledger_contract.py']
    for name in sources:
        if hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest() != provenance['sources'][name]:
            raise ValueError('use the frozen memory implementation')
    tools, source_hashes, _ = load_public_tools(data_root)
    if source_hashes != provenance['public_schema_hashes']:
        raise ValueError('public schema sources differ from execution')
    catalog = NativeCatalog(tools)
    usage, events, spans = (read(directory / n) for n in ('usage.json', 'events.json', 'spans.json'))
    payloads = {c['id']: read(directory / c['id'] / 'request.json') for c in usage}
    responses = {c['id']: read(directory / c['id'] / 'response.json') for c in usage}
    result.update(inspect_operations([c for c in usage if c['role'] == 'agent'],
                                     events, spans, payloads, responses, summary))
    views, counts = read(directory / 'memory_views.json', []), read(directory / 'memory_counting.json', [])
    memory_events = read(directory / 'generated_memory_events.json', [])
    errors, count_index, view_index, attempted = [], 0, 0, 0

    class Replay:
        def __init__(self):
            self.calls, self.tokens = [], 0

        def consume(self, role, messages, supplied):
            if len(self.calls) == len(usage):
                # No inference was sent: verify the recorded terminal disposition,
                # not a fresh wall-clock or preflight-budget decision.
                raise BudgetStop(summary['stop_reason'])
            row = usage[len(self.calls)]
            payload = payloads[row['id']]
            if row['role'] != role or payload['messages'] != messages or payload['tools'] != supplied:
                raise AuditMismatch('replayed input or role differs at ' + row['id'])
            self.calls.append(row)
            if row['status'] != 'ok':
                raise BudgetStop(summary['stop_reason'])
            self.tokens += row['input_tokens'] + row['output_tokens']
            return responses[row['id']]['message']

        call = consume

    def recorded_count(content):
        nonlocal count_index
        if count_index == len(counts):
            raise BudgetStop(summary['stop_reason'])
        record = counts[count_index]; count_index += 1
        if (record['content_sha256'] != hashlib.sha256(content.encode()).hexdigest()
                or record['characters'] != len(content)):
            raise AuditMismatch('tokenizer input differs')
        if record['status'] != 'ok':
            raise BudgetStop(summary['stop_reason'])
        return record['tokens']

    task = read(directory / 'public_task.json')
    conversation, controller, replay = NativeConversation(NATIVE_PROMPT, task), make_memory(result['arm']), Replay()
    try:
        while attempted < summary['memory_selection_attempts']:
            attempted += 1
            start = count_index
            messages, selection = controller.prepare(
                conversation, task, catalog.tools(), replay, recorded_count, plan, lambda events: None)
            if view_index >= len(views):
                raise AuditMismatch('missing completed memory decision')
            view = views[view_index]; view_index += 1
            expected = {'next_call_id': f'call_{len(replay.calls)+1:03d}',
                        'known_tokens_before': replay.tokens, 'selection': selection,
                        'counting_start_index': start, 'counting_end_index': count_index}
            different = [k for k, v in expected.items() if view.get(k) != v]
            if different:
                if 'selection' in different:
                    different += ['selection.' + k for k, v in selection.items()
                                  if view.get('selection', {}).get(k) != v]
                raise AuditMismatch('saved memory view differs: ' + ','.join(different))
            message = replay.consume('agent', messages, catalog.tools())
            cid = replay.calls[-1]['id']
            current = [e for e in events if e['call'] == cid]
            conversation.append(message, [spans[e['span_id']] for e in current])
            for e in current:
                if not set(e['new_tools']) <= set(catalog.catalog):
                    raise AuditMismatch('unknown public schema exposure')
                catalog.visible.update(e['new_tools'])
            if any(e['declared_complete'] for e in current):
                break
    except BudgetStop:
        if summary['stop_reason'] == 'agent_declared_complete':
            errors.append('unexpected replay termination')
    except (AuditMismatch, ValueError, KeyError, TypeError, IndexError) as error:
        errors.append(type(error).__name__ + ': ' + str(error) if isinstance(error, AuditMismatch)
                      else 'cannot replay saved control decisions: ' + type(error).__name__)
    if replay.calls != usage:
        errors.append('not all model costs were consumed by replay')
    if count_index != len(counts) or view_index != len(views) or attempted != summary['memory_selection_attempts']:
        errors.append('memory attempt/count/view coverage differs')
    if controller.events != memory_events:
        errors.append('generated-memory events differ from replay')
    if len(counts) != summary['memory_token_count_requests']:
        errors.append('tokenizer request accounting differs')
    result.update(memory_audit_errors=errors, memory_events=len(memory_events),
                  all_retained_early_exits=summary['all_retained_early_exits'],
                  memory_selection_seconds=summary['memory_selection_seconds'],
                  memory_token_count_requests=len(counts),
                  model_calls_by_auditor=0, environment_operations=0, final_evaluations=0,
                  scope='Replay of recorded drafts, trigger counts, selection, public schema and executor '
                        'inputs. Recorded preflight/time stop is a disposition, not remeasured runtime. '
                        'Memory semantics and final truth are not certified by structural replay.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.trial, args.data_root)
    result['auditor_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'run_id': result['run_id'], 'usage_errors': result['audit_errors'],
                      'dispatch_errors': result['dispatch_audit_errors'], 'memory_errors': result['memory_audit_errors']}))
