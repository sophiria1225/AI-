"""Count repeated public requests and visible prior receipts without exporting values."""
import argparse
import hashlib
import json
from pathlib import Path

from inspect_appworld_api_schemas import load_public_tools


def repeated_requests(spans, events, views, allowed):
    selected = {v['next_call_id']: set(v['selection']['retained_span_ids']) for v in views}
    prior, rows = {}, []
    for event in events:
        span = spans[event['span_id']]
        function = span.get('action') or {}
        name = function.get('name')
        if not event['api_request_sent']:
            continue
        if name not in allowed:
            raise ValueError('only public schema operation names may be exported')
        try:
            args = json.loads(function['arguments'])
        except (ValueError, TypeError):
            continue
        key = json.dumps([name, args], ensure_ascii=False, sort_keys=True)
        if key in prior:
            old, previous_call = prior[key]
            visible = selected.get(event['call'])
            rows.append({'public_api': name, 'previous_span_id': old['id'],
                         'current_span_id': span['id'], 'current_call_id': event['call'],
                         'previous_call_id': previous_call,
                         'prior_result_predates_current_call': previous_call != event['call'],
                         'previous_span_retained': old['id'] in visible if visible is not None else None,
                         'same_recorded_observation': span['observation'] == old['observation']})
        prior[key] = (span, event['call'])
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-running', action='store_true')
    args = parser.parse_args()
    finished = (args.trial / 'summary.json').exists()
    if not finished and not args.allow_running:
        raise ValueError('request an explicitly partial observation')
    read = lambda name: json.loads((args.trial / name).read_text())
    public_tools, _, _ = load_public_tools(args.data_root)
    allowed = {t['function']['name'] for t in public_tools}
    events = read('events.json')
    source_names = ['events.json', 'spans.json']
    if (args.trial / 'memory_views.json').exists():
        views = read('memory_views.json')
        source_names.append('memory_views.json')
    else:
        if read('provenance.json')['arm'] not in ('native_roles', 'native_guided'):
            raise ValueError('missing memory selection record')
        source_names.append('provenance.json')
        calls = list(dict.fromkeys(e['call'] for e in events))
        views = [{'next_call_id': call, 'selection': {'retained_span_ids': [
            e['span_id'] for e in events if e['call'] in calls[:i]]}}
            for i, call in enumerate(calls)]
    rows = repeated_requests(read('spans.json'), events, views, allowed)
    result = {'run_id': args.trial.name, 'status': 'finished' if finished else 'partial',
              'repeated_requests': rows,
              'count': len(rows),
              'same_call_repeats': sum(not r['prior_result_predates_current_call'] for r in rows),
              'prior_receipt_not_retained': sum(r['previous_span_retained'] is False
                  and r['prior_result_predates_current_call'] for r in rows),
              'same_observation_and_prior_not_retained': sum(r['previous_span_retained'] is False
                  and r['prior_result_predates_current_call'] and r['same_recorded_observation'] for r in rows),
              'source_hashes': {name: hashlib.sha256((args.trial / name).read_bytes()).hexdigest()
                                for name in source_names},
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'model_calls': 0, 'environment_calls': 0, 'evaluator_loaded': False,
              'scope': 'Exactly equal public API name and parsed arguments; receipts compared only for '
                       'equality. No argument values or per-secret hashes exported. Repetition is not '
                       'automatically unnecessary or caused by forgetting: state and validity may change. '
                       'A missing original receipt does not establish that its information is absent '
                       'from other retained turns, a ledger or the accessible archive.'}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('run_id', 'status', 'count', 'prior_receipt_not_retained',
                                          'same_observation_and_prior_not_retained')}))
