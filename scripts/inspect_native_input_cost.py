"""Tokenizer-only fixed-trajectory input accounting; removals never drive an agent."""
import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import urllib.request

from context_preservation import compact
from local_llama import post
from model_provenance import check_live_model


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def counterfactuals(payload):
    if [m['role'] for m in payload['messages']] != ['system', 'user']:
        raise ValueError('this accounting is only for the saved P8 JSON baseline')
    user = json.loads(payload['messages'][1]['content'])
    if (set(user) != {'task', 'memory'} or set(user['memory']) != {'available_archive_ids', 'visible_spans'}):
        raise ValueError('unexpected history fields')
    without_history = copy.deepcopy(payload)
    user['memory'] = {'available_archive_ids': [], 'visible_spans': []}
    without_history['messages'][1]['content'] = compact(user)
    def without_tools(value):
        result = copy.deepcopy(value)
        for key in ('tools', 'tool_choice', 'parallel_tool_calls'):
            result.pop(key, None)
        return result
    return {'full': payload, 'no_history': without_history,
            'no_schemas': without_tools(payload), 'task_only': without_tools(without_history)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--private-record', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.private_record.mkdir(parents=True, exist_ok=False)
    storage = args.storage_root
    plan = read(storage / 'records/context_pilot/P8_01_NATIVE/plan.json')
    # A timing probe must not compete even with these small CPU-only requests.
    probe = read(storage / 'records/cache_probe/P9_01/status.json')
    if probe['status'] != 'complete':
        raise ValueError('wait until the fixed P9 timing probe finishes')
    runtime = read(storage / '.runtime/model_server.json')
    with urllib.request.urlopen(plan['model']['base_url'] + '/props', timeout=10) as response:
        props = json.load(response)
    check_live_model(plan['model_selection'], runtime, props, root=storage,
                     expected_ctx=plan['model']['num_ctx'], expected_cache=('q8_0', 'q8_0'))
    (args.private_record / 'runtime.json').write_text(json.dumps(runtime, indent=2) + '\n')
    (args.private_record / 'props.json').write_text(json.dumps(props, indent=2) + '\n')
    rows = []
    result = {'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'model_revision': runtime['model_revision'], 'runtime': runtime['runtime'],
              'model_inference_calls': 0, 'environment_requests': 0,
              'token_count_requests': 0, 'rows': rows,
              'scope': 'Counterfactual rendered lengths on a FIXED saved trajectory. '
                       'No removed-history or removed-schema prompt is used for inference. '
                       'Not achievable savings, a bound on adaptive agent cost, or quality evidence.'}
    for run in ('P8_01_NATIVE', 'P8_02_NATIVE'):
        trial = storage / 'records/context_pilot' / run
        if read(trial / 'summary.json')['arm'] != 'native_full':
            raise ValueError('unexpected baseline')
        for call in read(trial / 'usage.json'):
            if call['status'] != 'ok':
                raise ValueError('this fixed accounting expects complete P8 usage')
            source = trial / call['id'] / 'request.json'
            payload = read(source)
            directory = args.private_record / run / call['id']
            directory.mkdir(parents=True)
            counts, hashes = {}, {}
            for name, value in counterfactuals(payload).items():
                path = directory / (name + '.json')
                path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
                counted = post(plan['model'], '/v1/chat/completions/input_tokens', value, 60)
                counts[name] = counted['input_tokens']; hashes[name] = sha(path)
                result['token_count_requests'] += 1
            if counts['full'] != call['input_tokens']:
                raise ValueError('current tokenizer disagrees with recorded terminal input')
            rows.append({'run_id': run, 'call_id': call['id'], 'counts': counts,
                         'source_request_sha256': sha(source), 'case_payload_hashes': hashes,
                         'schema_increment_after_task_only': counts['no_history'] - counts['task_only'],
                         'history_increment_after_schemas': counts['full'] - counts['no_history'],
                         'interaction_residual': counts['full'] - counts['no_schemas'] - counts['no_history'] + counts['task_only']})
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    result['source_script_sha256'] = sha(Path(__file__))
    result['totals'] = {run: {key: sum(r[key] for r in rows if r['run_id'] == run)
                            for key in ('schema_increment_after_task_only', 'history_increment_after_schemas', 'interaction_residual')}
                        for run in ('P8_01_NATIVE', 'P8_02_NATIVE')}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'count_requests': result['token_count_requests'], 'inference_calls': 0,
                      'totals': result['totals']}))


if __name__ == '__main__':
    main()
