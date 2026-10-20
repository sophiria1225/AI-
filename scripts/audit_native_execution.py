"""Check saved native API dispatch records without exposing operations or replaying them."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from summarize_context_pilot import summarize_trial
from native_conversation import NativeConversation


def inspect_history(task, prompt, usage, records, spans, payloads, responses, page_limit):
    """Check every supplied history against preceding recorded responses/results."""
    conversation = NativeConversation(prompt, task)
    by_call = defaultdict(list)
    for event in records:
        by_call[event['call']].append(spans[event['span_id']])
    errors, formatting = [], {}
    for call in usage:
        cid = call['id']
        expected, formatting = conversation.for_model(page_limit)
        if payloads[cid]['messages'] != expected:
            errors.append(cid + ': supplied history differs from preceding recorded turns')
        if call['status'] == 'ok':
            try:
                conversation.append(responses[cid]['message'], by_call[cid])
            except (KeyError, ValueError, TypeError) as error:
                errors.append(cid + ': cannot reconstruct recorded turn: ' + type(error).__name__)
                break
    return {'history_audit_errors': errors, 'last_input_formatting': formatting}


def read(path):
    return json.loads(path.read_text())


def inspect_operations(usage, records, spans, payloads, responses, summary):
    errors, counts, by_call, seen = [], Counter(), defaultdict(list), set()
    for event in records:
        sid = event['span_id']
        if sid in seen or sid not in spans:
            errors.append('duplicate or missing operation span')
            continue
        seen.add(sid)
        span = spans[sid]
        if span['id'] != sid:
            errors.append('span key disagrees with span ID')
        by_call[event['call']].append((event, span))
        counts['recorded_operations'] += 1
        obs, sent = span['observation'], event['api_request_sent']
        counts['api_requests_sent'] += int(sent)
        counts['unknown_effect_requests'] += int(event.get('effects_unknown', False))
        if 'transport_error_type' in obs:
            counts['transport_errors'] += 1
            if not sent or not event.get('effects_unknown'):
                errors.append('transport failure incorrectly treated as unexecuted or certain')
        elif 'not_executed' in obs:
            counts['skipped_operations'] += 1
            if sent:
                errors.append('skipped operation marked sent')
        elif 'format_error' in obs:
            counts['format_rejections'] += 1
            if sent:
                errors.append('format rejection marked sent')
        elif 'api_error' in obs:
            counts['outer_api_errors'] += 1
            if not sent:
                errors.append('API error without an API request')
        elif sent:
            if isinstance(obs.get('observation'), str) and obs['observation'].startswith('Execution failed.'):
                counts['inner_execution_errors'] += 1
            else:
                # Accepted transport is not a claim of task or semantic success.
                counts['returned_api_results_without_detected_error'] += 1
        else:
            counts['local_archive_results'] += 1
            if (span.get('action') or {}).get('name') != 'read_span':
                errors.append('non-API result is not a local archive read')
        counts['public_schemas_added'] += len(event['new_tools'])
    if seen != set(spans):
        errors.append('span/event coverage differs')
    if len(records) != summary['tool_turns']:
        errors.append('operation count disagrees with summary')
    if counts['api_requests_sent'] != summary['api_requests']:
        errors.append('sent count disagrees with summary')
    if counts['unknown_effect_requests'] != summary['unknown_effect_requests']:
        errors.append('unknown-effect count disagrees with summary')
    call_rows = []
    for call in usage:
        cid = call['id']
        events = by_call.pop(cid, [])
        if call['status'] != 'ok':
            if events:
                errors.append(cid + ': unknown model result has dispatched operations')
            counts['unknown_model_usage_calls'] += 1
            continue
        requested = responses[cid]['message'].get('tool_calls') or []
        if not isinstance(requested, list):
            errors.append(cid + ': tool-call list is malformed')
            continue
        expected = [c.get('function') if isinstance(c, dict) else None for c in requested] or [None]
        if expected != [span.get('action') for _, span in events]:
            errors.append(cid + ': requested operations and ordered records differ')
        supplied = {tool['function']['name'] for tool in payloads[cid]['tools']}
        completed, uncertain = False, False
        for event, span in events:
            obs = span['observation']
            if (completed or uncertain) and event['api_request_sent']:
                errors.append(cid + ': operation dispatched after completion or unknown effects')
            name = (span.get('action') or {}).get('name')
            if event['api_request_sent'] and name not in supplied:
                errors.append(cid + ': dispatched tool was absent from the supplied schema')
            completed |= bool(obs.get('declared_complete'))
            uncertain |= bool(event.get('effects_unknown'))
        counts['multiple_call_responses'] += int(len(requested) > 1)
        call_rows.append({'call_id': cid, 'requested_tool_calls': len(requested),
                          'recorded_operations': len(events), 'supplied_schemas': len(supplied),
                          'api_requests_sent': sum(e['api_request_sent'] for e, _ in events)})
    if by_call:
        errors.append('operation refers to unknown model call')
    return {'counts': dict(counts), 'calls': call_rows, 'dispatch_audit_errors': errors}


def audit(directory):
    result = summarize_trial(directory)
    if result['arm'] not in ('native_full', 'native_roles'):
        raise ValueError('requires a completed native full-history trial')
    usage = read(directory / 'usage.json')
    records, spans = read(directory / 'events.json'), read(directory / 'spans.json')
    payloads = {c['id']: read(directory / c['id'] / 'request.json') for c in usage}
    responses = {c['id']: read(directory / c['id'] / 'response.json') for c in usage}
    result.update(inspect_operations(usage, records, spans, payloads, responses,
                                     read(directory / 'summary.json')))
    if result['arm'] == 'native_roles':
        from run_native_appworld import NATIVE_PROMPT
        hashes = read(directory / 'summary.json')['source_hashes']
        matched = all(hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                      == hashes[name] for name in ('native_conversation.py', 'run_native_appworld.py'))
        if not matched:
            result['history_audit_errors'] = ['history renderer source differs from frozen execution']
        else:
            result.update(inspect_history(read(directory / 'public_task.json'), NATIVE_PROMPT,
                                         usage, records, spans, payloads, responses,
                                         read(directory / 'plan.json')['observation_page_characters']))
    result['source_hashes'].update({name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                                    for name in ('events.json', 'spans.json', 'plan.json')})
    result['scope'] = ('Saved model requests, schemas and ordered dispatch metadata. '
                       'Transport acceptance is not semantic or final task success. '
                       'No environment execution or model inference; no payload text exported.')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.trial)
    result['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'run': result['run_id'], 'usage_audit_errors': result['audit_errors'],
                      'dispatch_audit_errors': result['dispatch_audit_errors'],
                      'history_audit_errors': result.get('history_audit_errors')}))


if __name__ == '__main__':
    main()
