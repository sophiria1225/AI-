"""Describe generated-memory format failures without exporting generated content."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from context_preservation import select_focus, validate_ledger


def classify(message, role, visible, previous_ledger=None):
    counts = {'tool_calls': len(message.get('tool_calls') or []),
              'content_characters': len(message.get('content') or ''),
              'reasoning_characters': len(message.get('reasoning_content') or '')}
    calls = message.get('tool_calls') or []
    expected = {'focus': 'submit_selection', 'ledger': 'submit_ledger'}[role]
    if len(calls) != 1:
        return {**counts, 'format': 'missing_or_multiple_submissions'}
    function = calls[0].get('function') or {}
    if function.get('name') != expected:
        return {**counts, 'format': 'unexpected_submission_function'}
    try:
        value = json.loads(function.get('arguments', ''))
    except (ValueError, TypeError):
        return {**counts, 'format': 'invalid_json'}
    if not isinstance(value, dict):
        return {**counts, 'format': 'object_required'}
    allowed = set(visible)
    if role == 'ledger':
        allowed.update(s for item in (previous_ledger or {}).get('items', []) for s in item['source_ids'])
    lists = []
    if role == 'focus':
        if isinstance(value.get('steps'), list):
            lists += [item.get('depends_on') for item in value['steps'] if isinstance(item, dict)]
        lists.append(value.get('rescued'))
    elif isinstance(value.get('items'), list):
        lists += [item.get('source_ids') for item in value['items'] if isinstance(item, dict)]
    ids = [item for group in lists if isinstance(group, list) for item in group if isinstance(item, str)]
    counts.update(cited_ids=len(ids), unavailable_citations=sum(item not in allowed for item in ids),
                  unavailable_plan_step_labels=sum(item not in allowed and bool(re.fullmatch(
                      r'(?i)(step|plan)\s*[a-z0-9]', item)) for item in ids),
                  distinct_valid_citations=len(set(ids) & allowed), visible_spans=len(visible),
                  all_visible_spans_cited=set(visible) <= set(ids))
    try:
        if role == 'focus':
            select_focus([value], list(visible), 0.3)
        else:
            validate_ledger(value, allowed)
    except (ValueError, KeyError, TypeError, AttributeError):
        return {**counts, 'format': 'source_or_schema_invalid'}
    return {**counts, 'format': 'structurally_valid_not_semantically_verified'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-running', action='store_true')
    args = parser.parse_args()
    finished = (args.trial / 'summary.json').exists()
    if not finished and not args.allow_running:
        raise ValueError('request an explicitly partial analysis')
    read = lambda name: json.loads((args.trial / name).read_text())
    usage, events = read('usage.json'), read('generated_memory_events.json')
    rows, names = [], ['usage.json', 'generated_memory_events.json']
    for event in events:
        first = event['first_call_index']
        for call in usage[first:first + event['calls']]:
            if call['role'] not in ('focus', 'ledger'):
                raise ValueError('memory event includes an executor call')
            name = call['id'] + '/response.json'; response = read(name); names.append(name)
            row = {k: call[k] for k in ('id', 'role', 'status', 'input_tokens', 'output_tokens')}
            row.update(done_reason=response.get('done_reason'),
                       recorded_event_status=event['status'])
            if call['status'] == 'ok':
                row.update(classify(response['message'], call['role'], event['visible_before'],
                                    event.get('ledger_before')))
            rows.append(row)
    result = {'run_id': args.trial.name, 'status': 'finished' if finished else 'partial',
              'completed_memory_events': len(events), 'calls': rows,
              'model_calls': 0, 'environment_operations': 0, 'evaluator_accessed': False,
              'source_hashes': {name: hashlib.sha256((args.trial / name).read_bytes()).hexdigest()
                                for name in names},
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'scope': 'Format and source-ID validity of recorded memory submissions; no generated '
                       'text, citation values, arguments or reasoning exported. Character counts '
                       'do not establish reasoning quality or a cause of final task failure.'}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'run_id': result['run_id'], 'status': result['status'],
                      'memory_calls_observed': len(rows),
                      'formats': [row.get('format', 'unknown') for row in rows]}))
