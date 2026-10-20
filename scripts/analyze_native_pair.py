"""Compare observed prefixes, without replay or claims of deterministic causality."""
import argparse
import copy
import hashlib
import json
from pathlib import Path


def canonical_transport_ids(payload):
    result, mapping = copy.deepcopy(payload), {}
    for message in result.get('messages', []):
        for call in message.get('tool_calls') or []:
            original = call['id']
            if original in mapping:
                raise ValueError('duplicate transport call ID')
            mapping[original] = f'CANONICAL_{len(mapping)}'
            call['id'] = mapping[original]
        if 'tool_call_id' in message:
            if message['tool_call_id'] not in mapping:
                raise ValueError('unpaired transport receipt')
            message['tool_call_id'] = mapping[message['tool_call_id']]
    return result


def public_actions(message):
    result = []
    for call in message.get('tool_calls') or []:
        function = call['function']
        try:
            arguments = json.loads(function['arguments'])
        except (TypeError, ValueError):
            arguments = {'unparsed': function['arguments']}
        result.append((function['name'], arguments))
    return result


def read(path):
    return json.loads(path.read_text())


def compare(left, right):
    ls, rs = read(left / 'summary.json'), read(right / 'summary.json')
    if ls['task_id'] != rs['task_id']:
        raise ValueError('comparison must use the same task')
    plan_l, plan_r = read(left / 'plan.json'), read(right / 'plan.json')
    for key in ('model', 'seed', 'agent_temperature', 'max_calls', 'max_total_tokens',
                'max_wall_seconds', 'max_api_requests', 'max_output_tokens', 'discovery_policy'):
        if plan_l[key] != plan_r[key]:
            raise ValueError('comparison condition differs: ' + key)
    lu, ru = read(left / 'usage.json'), read(right / 'usage.json')
    views = {v['next_call_id']: v for v in read(right / 'memory_views.json')}
    rows = []
    for a, b in zip(lu, ru):
        if a['id'] != b['id'] or a['role'] != 'agent' or b['role'] != 'agent':
            raise ValueError('only sequential native executor comparisons are supported')
        cid = a['id']
        pa, pb = read(left / cid / 'request.json'), read(right / cid / 'request.json')
        ra, rb = read(left / cid / 'response.json'), read(right / cid / 'response.json')
        rows.append({'call_id': cid, 'exact_request_equal': pa == pb,
                     'request_equal_ignoring_transport_ids': canonical_transport_ids(pa) == canonical_transport_ids(pb),
                     'public_actions_equal': public_actions(ra['message']) == public_actions(rb['message']),
                     'right_uses_partial_history': views[cid]['selection']['memory_note_added']})
    first = lambda key, value: next((r['call_id'] for r in rows if r[key] == value), None)
    return {'left_run': ls['run_id'], 'right_run': rs['run_id'], 'task_id': ls['task_id'],
            'shared_positions': rows, 'left_model_calls': len(lu), 'right_model_calls': len(ru),
            'first_exact_input_difference': first('exact_request_equal', False),
            'first_input_difference_beyond_transport_ids': first('request_equal_ignoring_transport_ids', False),
            'first_different_public_action_position': first('public_actions_equal', False),
            'first_partial_history_position': first('right_uses_partial_history', True),
            'source_hashes': {label: {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                                    for name in ('summary.json', 'plan.json', 'usage.json')}
                              for label, directory in (('left', left), ('right', right))},
            'model_calls_by_analysis': 0, 'environment_calls': 0,
            'scope': 'Descriptive alignment until and after traces diverge. Transport IDs are '
                     'canonicalized only for offline comparison; actual inputs and costs are unchanged. '
                     'Equal seed does not guarantee equal samples. No same-state intervention or '
                     'quality-equivalence inference from this single pair.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--left', type=Path, required=True)
    parser.add_argument('--right', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.left, args.right)
    result['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k.startswith('first_')}))
