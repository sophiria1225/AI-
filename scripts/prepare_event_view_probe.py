"""Prepare P16 input cases from public trajectory prefixes, never evaluation files."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from appworld_native_tools import NativeCatalog, dispatch_native_calls
from run_context_comparison import write_json


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_application(name):
    return (isinstance(name, str) and '__' in name
            and not name.startswith(('api_docs__', 'supervisor__')))


class NeverDispatch:
    def __init__(self):
        self.calls = 0

    def request(self, _):
        self.calls += 1
        raise RuntimeError('preparation must never send an API request')


def reject_response(message, tools, parameter):
    """Exercise the normal adapter, with an invalid public parameter on every call."""
    public_tools = [t for t in tools if t['function']['name'] != 'read_span']
    catalog = NativeCatalog(public_tools)
    catalog.visible = set(catalog.catalog)
    faulty = copy.deepcopy(message)
    calls = faulty.get('tool_calls') or []
    if not calls or any(not is_application(c['function']['name']) for c in calls):
        raise ValueError('selected response includes a non-application operation')
    for call in calls:
        fn = call['function']
        decoded = catalog.decode(fn)
        if parameter in catalog.catalog[fn['name']]['function']['parameters']['properties']:
            raise ValueError('reserved probe parameter exists in public schema')
        args = decoded['args']
        if parameter in args:
            raise ValueError('probe parameter already exists')
        fn['arguments'] = json.dumps({**args, parameter: True}, ensure_ascii=False, separators=(',', ':'))
    bridge = NeverDispatch()
    rows = dispatch_native_calls(faulty, catalog, bridge, None,
                                 remaining_api_calls=len(calls))
    if bridge.calls or len(rows) != len(calls) or any(
            r['api_request_sent'] is not False or r.get('effects_unknown', False)
            or r['observation'] != {'format_error': 'unknown API parameter'} for r in rows):
        raise RuntimeError('controlled rejection did not occur strictly before dispatch')
    return faulty, rows


def prepare_source(source, parameter):
    # Do not substitute summary.json for these records: it includes final evaluation.
    events = json.loads((source / 'events.json').read_text())
    spans = json.loads((source / 'spans.json').read_text())
    task = json.loads((source / 'public_task.json').read_text())
    candidates = [e for e in events if is_application(
        (spans[e['span_id']].get('action') or {}).get('name'))]
    if not candidates:
        raise ValueError('no application response in the fixed trajectory')
    call_id = candidates[-1]['call']
    selected = [e for e in events if e['call'] == call_id]
    start = next(i for i, e in enumerate(events) if e['call'] == call_id)
    if events[start:start + len(selected)] != selected:
        raise ValueError('non-contiguous response records')
    if any(not is_application((spans[e['span_id']].get('action') or {}).get('name'))
           for e in selected):
        raise ValueError('selected response contains mixed helper/application calls')
    request = json.loads((source / call_id / 'request.json').read_text())
    response = json.loads((source / call_id / 'response.json').read_text())
    if response.get('status') != 'ok':
        raise ValueError('selected response is incomplete')
    message = response['message']
    tools = request['tools']
    if [c['function'] for c in message['tool_calls']] != [spans[e['span_id']]['action'] for e in selected]:
        raise ValueError('response and recorded action sequence differ')
    faulty, rows = reject_response(message, tools, parameter)
    prefix_events = events[:start + len(selected)]
    prefix_spans = {e['span_id']: copy.deepcopy(spans[e['span_id']]) for e in prefix_events}
    receipts = {e['span_id']: {'span_id': e['span_id'],
                  'api_request_sent': e['api_request_sent'],
                  'effects_unknown': e.get('effects_unknown', False)} for e in prefix_events}
    recorded = {'task': task, 'tools': tools, 'spans': prefix_spans, 'receipts': receipts,
                'selected_span_ids': [e['span_id'] for e in selected], 'source_call_id': call_id}
    rejected = copy.deepcopy(recorded)
    for index, (event, row) in enumerate(zip(selected, rows)):
        sid = event['span_id']
        rejected['spans'][sid] = {
            'id': sid, 'assistant': (faulty.get('content') or '') if index == 0 else '',
            'action': row['action'], 'observation': row['observation']}
        rejected['receipts'][sid] = {'span_id': sid, 'api_request_sent': False, 'effects_unknown': False}
    hashes = {name: sha(source / name) for name in ('events.json', 'spans.json', 'public_task.json')}
    hashes.update({f'{call_id}/{name}': sha(source / call_id / name)
                   for name in ('request.json', 'response.json')})
    return {'recorded': recorded, 'rejected_before_dispatch': rejected}, hashes


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--public-report', type=Path, required=True)
    args = p.parse_args()
    plan = json.loads(args.plan.read_text())
    if plan['run_id'] != 'P16_01' or plan['conditions'] != ['recorded', 'rejected_before_dispatch']:
        raise ValueError('unexpected P16 plan')
    prepared = []
    # Validate every case before publishing a partial prepared suite.
    for number, name in enumerate(plan['source_runs'], 1):
        cases, hashes = prepare_source(args.storage_root / 'records/context_pilot' / name,
                                       plan['unknown_parameter'])
        for condition in plan['conditions']:
            case = cases[condition]
            case.update(case_id=f'case_{number:02d}_{condition}', source_run=name,
                        condition=condition, source_hashes=hashes)
            prepared.append(case)
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for case in prepared:
        path = args.output / (case['case_id'] + '.json')
        write_json(path, case)
        rows.append({'case_id': case['case_id'], 'source_run': case['source_run'],
                     'condition': case['condition'], 'source_call_id': case['source_call_id'],
                     'span_count': len(case['spans']), 'selected_span_ids': case['selected_span_ids'],
                     'case_sha256': sha(path), 'source_hashes': case['source_hashes']})
    manifest = {'plan_sha256': sha(args.plan), 'cases': rows,
                'model_calls': 0, 'environment_api_requests': 0, 'evaluator_files_accessed': False,
                'independent_source_tasks': len(plan['source_runs']),
                'scope': 'Controlled input preparation only; no restored environment or new task success.'}
    write_json(args.output / 'manifest.json', manifest)
    write_json(args.public_report, manifest)
    print(json.dumps({'cases': len(rows), 'api_requests': 0, 'model_calls': 0}))


if __name__ == '__main__':
    main()
