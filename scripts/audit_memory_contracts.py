"""Audit frozen memory submissions; export only counts, classes and hashes.

This diagnoses our adapter contract, not memory truth or counterfactual task success.
Original messages, reasoning, credentials and source IDs are never exported.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from context_preservation import parse_submission, validate_ledger
from inspect_memory_submissions import classify


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(response, request, role, visible, previous=None):
    row = {k: response.get(k) for k in
           ('status', 'input_tokens', 'output_tokens', 'done_reason', 'timeout_scope')}
    row['output_cap'] = request.get('max_tokens')
    row['output_at_cap'] = (response.get('output_tokens') == row['output_cap']
                            if response.get('output_tokens') is not None else None)
    if response['status'] != 'ok':
        row['format'] = 'no_completed_response'
        return row
    message = response['message']
    row.update(classify(message, role, visible, previous))
    if role != 'ledger':
        return row
    try:
        value = parse_submission(message, 'submit_ledger')
    except (ValueError, KeyError, TypeError):
        return row
    tool, = [t for t in request['tools'] if t['function']['name'] == 'submit_ledger']
    source_spec = tool['function']['parameters']['properties']['items']['items']['properties']['source_ids']
    row['advertised_source_min_items'] = source_spec.get('minItems', 0)
    row['advertised_source_enum'] = 'enum' in source_spec.get('items', {})
    allowed = set(visible)
    allowed.update(s for item in (previous or {}).get('items', []) for s in item['source_ids'])
    issues = Counter()
    affected = []
    for index, item in enumerate(value.get('items', [])):
        if not isinstance(item, dict):
            issues['nonobject_item'] += 1
            continue
        found = []
        sources = item.get('source_ids')
        if sources == []:
            found.append('empty_sources')
        elif isinstance(sources, list) and all(isinstance(s, str) for s in sources):
            if len(set(sources)) != len(sources):
                found.append('duplicate_sources')
            if set(sources) - allowed:
                found.append('unavailable_sources')
            if 'task' in sources and 'task' not in allowed:
                found.append('unregistered_task_reference')
        else:
            found.append('invalid_sources_type')
        status = item.get('status')
        if status not in ('pending', 'done', 'uncertain', 'excluded'):
            found.append('invalid_status')
        if found:
            issues.update(found)
            affected.append({'index': index,
                             'status_class': status if status in ('pending', 'done', 'uncertain', 'excluded')
                             else 'outside_declared_enum', 'issues': found})
    row.update(item_count=len(value.get('items', [])), issue_counts=dict(issues), affected_items=affected)
    try:
        validate_ledger(value, allowed)
        row['receiver_accepts'] = True
    except (ValueError, TypeError, KeyError, AttributeError):
        row['receiver_accepts'] = False
    return row


def collect(storage):
    rows, sources = [], {}

    def load(path):
        sources[str(path.relative_to(storage))] = sha(path)
        return read(path)

    base = storage / 'records/context_pilot'
    runs = [('P13', f'P13_{i:02d}_FOCUS' + ('_RECOVERY01' if i == 3 else ''))
            for i in range(1, 5)]
    runs += [('P14', f'P14_{i:02d}_LEDGER') for i in range(1, 5)]
    runs += [('P13_interrupted', 'P13_03_FOCUS')]
    for phase, name in runs:
        run = base / name
        usage = load(run / 'usage.json')
        events = load(run / 'generated_memory_events.json')
        for event_index, event in enumerate(events):
            first = event['first_call_index']
            for call in usage[first:first + event['calls']]:
                if call['role'] not in ('focus', 'ledger'):
                    raise ValueError('non-memory call inside recorded memory event')
                request = load(run / call['id'] / 'request.json')
                response = load(run / call['id'] / 'response.json')
                rows.append({'phase': phase, 'run_id': name, 'call_id': call['id'],
                             'event_index': event_index, 'event_status': event['status'],
                             **inspect(response, request, call['role'], event['visible_before'],
                                       event.get('ledger_before'))})
    base = storage / 'records/event_view_probe'
    run = base / 'P16_01'
    for result in load(run / 'results.json'):
        case = load(base / 'P16_inputs_v01' / (result['case_id'] + '.json'))
        response = load(run / result['call_id'] / 'response.json')
        request = load(run / result['call_id'] / 'request.json')
        detail = inspect(response, request, 'ledger', case['spans'])
        if detail.get('receiver_accepts') is not result['schema_valid']:
            raise ValueError('audit must reproduce original P16 validity')
        rows.append({'phase': 'P16', 'run_id': run.name, 'call_id': result['call_id'],
                     'case_id': result['case_id'], 'variant': result['variant'], **detail})
    groups = []
    for phase in ('P13', 'P13_interrupted', 'P14', 'P16'):
        selected = [r for r in rows if r['phase'] == phase]
        groups.append({'phase': phase, 'calls': len(selected),
                       'format_counts': dict(Counter(r['format'] for r in selected)),
                       'known_tokens': sum((r.get('input_tokens') or 0) +
                                           (r.get('output_tokens') or 0) for r in selected),
                       'unknown_usage_calls': sum(r['status'] != 'ok' for r in selected),
                       'issue_counts': dict(sum((Counter(r.get('issue_counts', {})) for r in selected), Counter()))})
    return {'rows': rows, 'groups': groups, 'source_sha256': sources,
            'script_sha256': sha(Path(__file__)), 'new_model_calls': 0,
            'environment_operations': 0, 'evaluator_accessed': False,
            'scope': 'Post-hoc diagnosis of our frozen memory submission interface. '
                     'Issue counts are not semantic errors. No amended outcomes or counterfactual success.'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = collect(args.storage_root)
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(result['groups']))


if __name__ == '__main__':
    main()
