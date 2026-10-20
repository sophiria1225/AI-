"""Count public-operation shapes without exporting task, arguments or data values."""
import argparse
import collections
import datetime
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observation_shape(span, public_methods):
    name = (span.get('action') or {}).get('name', '')
    if name != 'read_span' and name not in public_methods:
        raise ValueError('operation name is not in the public schema allowlist')
    value = span['observation'].get('observation')
    parsed = None
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            pass
    return {'span_id': span['id'], 'public_api': name,
            'documented_http_method': public_methods.get(name),
            'response_characters': len(value) if isinstance(value, str) else None,
            'parsed_top_type': type(parsed).__name__,
            'top_level_list_items': len(parsed) if isinstance(parsed, list) else None}


def inspect(directory, methods):
    spans = json.loads((directory / 'spans.json').read_text())
    rows = [observation_shape(s, methods) for s in spans.values()]
    return {'run_id': directory.name, 'operations': rows,
            'operation_counts': dict(collections.Counter(r['public_api'] for r in rows)),
            'max_response_characters': max((r['response_characters'] or 0 for r in rows), default=0),
            'source_spans_sha256': digest(directory / 'spans.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--runs', nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    methods, sources = {}, {}
    for path in sorted((args.data_root / 'api_docs/standard').glob('*.json')):
        if path.stem == 'admin':
            continue
        for api, doc in json.loads(path.read_text()).items():
            methods[path.stem + '__' + api] = doc['method']
        sources[path.name] = digest(path)
    result = {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'trials': [inspect(args.storage_root / 'records/context_pilot' / name, methods)
                         for name in args.runs],
              'schema_sha256': sources, 'script_sha256': digest(Path(__file__)),
              'model_calls': 0, 'tokenizer_requests': 0, 'environment_requests': 0,
              'evaluator_loaded': False,
              'scope': 'Observed operation and response sizes only. List counts can include duplicate '
                       'items and documentation; no unique target count or completeness claim. '
                       'HTTP methods do not prove actual semantic side effects. '
                       'No task text, arguments, response values or hidden state exported.'}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'trials': len(result['trials']), 'model_calls': 0}))
