"""Audit already closed development traces; no generation, world, or evaluator.

This checks explicit controller messages, not whether a model internally knows a
budget. Public task text and generated reasoning are never exported.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def budget_before_calls(usage, events, prefix_api, limits):
    ids = [row['id'] for row in usage]
    if len(ids) != len(set(ids)) or any(e['call'] not in ids for e in events):
        raise ValueError('call/event correspondence changed')
    known_tokens = sent = 0
    rows = []
    for index, call in enumerate(usage):
        rows.append({'call_id': call['id'],
                     'remaining_api_before': limits['max_api_requests'] - prefix_api - sent,
                     'remaining_calls_before': limits['max_calls'] - index,
                     'remaining_tokens_before': limits['max_total_tokens'] - known_tokens,
                     'known_tokens_before': known_tokens})
        selected = [e for e in events if e['call'] == call['id']]
        sent += sum(int(e['api_request_sent']) for e in selected)
        if call['status'] != 'ok':
            if index != len(usage) - 1 or selected:
                raise ValueError('execution continued after unknown usage')
            rows[-1]['terminal_usage_known'] = False
        else:
            for key in ('input_tokens', 'output_tokens'):
                if type(call[key]) is not int or call[key] < 0:
                    raise ValueError('invalid terminal usage')
            known_tokens += call['input_tokens'] + call['output_tokens']
            rows[-1]['terminal_usage_known'] = True
    if any(row['remaining_api_before'] < 0 or row['remaining_tokens_before'] < 0
           or row['remaining_calls_before'] < 1 for row in rows):
        raise ValueError('started a call outside an accounted budget')
    return rows, {'known_total_tokens': known_tokens, 'suffix_api_requests': sent,
                  'unknown_usage_calls': sum(c['status'] != 'ok' for c in usage)}


def run(storage, root):
    target = root / 'reports/P40_budget_visibility.json'
    if target.exists():
        raise FileExistsError('preserve the original audit')
    reports = [read(root / f'reports/{phase}_comparison.json') for phase in ('P33', 'P38')]
    expected = ([f'P33_{i:02d}_{arm}' for i in range(1, 5) for arm in
                 ('FULL_KEEP', 'STDOUT_MASK_KEEP', 'STDOUT_MASK_INDEX_KEEP')]
                + [f'P38_04_{arm}_KEEP' for arm in ('NONE', 'EXACT', 'CONTRACT')])
    cells = {r['run_id']: r for report in reports for r in report['rows']}
    if set(cells) != set(expected):
        raise ValueError('only the fifteen closed development cells are eligible')
    rows = []
    for rid in expected:
        folder = storage / 'records/context_pilot' / rid
        cell = cells[rid]
        names = ('usage.json', 'summary.json', 'events.json', 'spans.json')
        if any(sha(folder / n) != cell['source_hashes'][n] for n in names):
            raise ValueError('closed source changed: ' + rid)
        usage, events = read(folder / 'usage.json'), read(folder / 'events.json')
        limits = read(folder / 'plan.json')
        calls, total = budget_before_calls(usage, events, cell['prefix_api_requests'], limits)
        if (total['known_total_tokens'] != cell['known_total_tokens']
                or total['suffix_api_requests'] != cell['api_requests']
                or total['unknown_usage_calls'] != cell['unknown_usage_calls']):
            raise ValueError('independent accounting disagrees: ' + rid)
        first_system = None
        user_shape_counts = {}
        for call in calls:
            p = folder / call['call_id'] / 'request.json'
            request = read(p)
            messages = request['messages']
            systems = [m for m in messages if m['role'] == 'system']
            if len(systems) != 1:
                raise ValueError('review a new system-message topology')
            system = systems[0]['content']
            if first_system is None:
                first_system = system
            if system != first_system:
                raise ValueError('review a changing system instruction')
            # Inspect the envelope, without exporting task/receipt contents.
            for message in messages:
                if message['role'] != 'user':
                    continue
                obj = json.loads(message['content'])
                shape = ','.join(sorted(obj)) if isinstance(obj, dict) else 'not_object'
                user_shape_counts[shape] = user_shape_counts.get(shape, 0) + 1
                if shape not in ('task', 'observation,span_id'):
                    raise ValueError('review a new user/controller message shape: ' + shape)
            call.update(request_sha256=sha(p), system_unchanged=True,
                        explicit_budget_block='<harness_budget_v1>' in system,
                        request_cache_prompt=request.get('cache_prompt'))
        rows.append({'run_id': rid, 'calls': calls, **total,
                     'prefix_api_requests': cell['prefix_api_requests'],
                     'limits': {k: limits[k] for k in
                                ('max_api_requests', 'max_calls', 'max_total_tokens', 'max_wall_seconds')},
                     'system_sha256': hashlib.sha256((first_system or '').encode()).hexdigest(),
                     'user_envelope_shapes': user_shape_counts,
                     'source_sha256': {n: sha(folder / n) for n in names}})
    result = {'phase': 'P40_budget_visibility_audit', 'rows': rows,
              'cells_reviewed': len(rows), 'calls_reviewed': sum(len(r['calls']) for r in rows),
              'model_calls_added': 0, 'environment_api_requests_added': 0,
              'final_evaluator_calls_added': 0, 'reserved_scenarios_read': 0,
              'source_sha256': {str(p.relative_to(root)): sha(p) for p in
                               [Path(__file__), root / 'reports/P33_comparison.json',
                                root / 'reports/P38_comparison.json']},
              'limits': ['Message envelopes and fixed controller source establish absence of an explicit running budget feed.',
                         'An API count in a receipt is not the same as a disclosed total/remaining budget.',
                         'The model may infer constraints or mention budgets itself; this does not measure internal awareness.',
                         'No causal claim that missing budget signals caused the recorded failures.']}
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('cells_reviewed', 'calls_reviewed', 'model_calls_added')}))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT)
    a = p.parse_args()
    run(a.storage_root, a.repo_root)
