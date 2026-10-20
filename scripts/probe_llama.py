"""Bounded model integration probes, separate from benchmark task scores."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import signal
import time
import urllib.request
import uuid

import local_llama
from model_provenance import LEGACY_SELECTION, check_live_model
from run_e0_pilot import alarm_handler, save_json

ROOT = Path(__file__).resolve().parents[1]
TOOL = {'type': 'function', 'function': {'name': 'lookup_record',
        'description': 'Read the requested calibration record. The return value is not known until the tool returns.',
        'parameters': {'type': 'object', 'properties': {'key': {'type': 'string'}}, 'required': ['key']}}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['enabled', 'disabled', 'adaptive'], default='enabled')
    parser.add_argument('--base-url', default='http://127.0.0.1:8011')
    parser.add_argument('--selection', default=LEGACY_SELECTION)
    args = parser.parse_args()
    with urllib.request.urlopen(args.base_url + '/props', timeout=10) as response:
        props = json.load(response)
    runtime = json.loads((ROOT / '.runtime/model_server.json').read_text())
    selection, _, _ = check_live_model(args.selection, runtime, props)
    config = {'backend': 'llama.cpp', 'base_url': args.base_url, 'model': selection['model_alias'],
              'model_selection': args.selection, 'model_revision': selection['revision'],
              'quantization': selection['quantization'],
              'num_ctx': runtime['ctx_size'], 'num_predict': 2048, 'temperature': 1.0,
              'top_p': 0.95, 'top_k': 0, 'min_p': 0.0, 'repeat_penalty': 1.0,
              'seed': 7, 'thinking_mode': args.mode, 'call_timeout_seconds': 360}
    out = ROOT / 'records/p2_probes' / (datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + args.mode)
    out.mkdir(parents=True)
    save_json(out / 'config.json', config)
    save_json(out / 'server_props.json', props)
    save_json(out / 'server_runtime.json', runtime)
    save_json(out / 'model_selection.json', selection)
    source_hashes = {}
    for source in ('probe_llama.py', 'local_llama.py', 'model_provenance.py'):
        content = (ROOT / 'scripts' / source).read_bytes()
        (out / source).write_bytes(content)
        source_hashes[source] = hashlib.sha256(content).hexdigest()
    save_json(out / 'source_hashes.json', source_hashes)
    results = []
    assertions = {}
    total = 0
    started = time.monotonic()

    def call(name, messages, tools=None, num_predict=None):
        nonlocal total
        cfg = config if num_predict is None else config | {'num_predict': num_predict}
        directory = out / name
        directory.mkdir()
        count = local_llama.count_input(cfg, messages, tools)
        save_json(directory / 'preflight.json', count)
        if count['input_tokens'] + cfg['num_predict'] > min(cfg['num_ctx'], 20000 - total):
            raise RuntimeError('probe token/context guard')
        result = local_llama.model_call(cfg, messages, directory, 900 - (time.monotonic() - started), tools)
        result['name'] = name
        results.append({k: v for k, v in result.items() if k != 'message'})
        if result['status'] != 'ok':
            raise RuntimeError('probe usage unknown; inspect raw record')
        total += result['input_tokens'] + result['output_tokens']
        assertions[name + '_count_matches'] = result['input_tokens'] == count['input_tokens']
        print(json.dumps({'probe': name, 'tokens': total, 'done_reason': result['done_reason'],
                          'count_matches': assertions[name + '_count_matches']}), flush=True)
        if not assertions[name + '_count_matches']:
            raise RuntimeError('server input counting differs from generation')
        return result

    error = None
    try:
        first = call('json', [{'role': 'user', 'content': 'Return only a JSON object with key value and integer value 19 times 17.'}])
        try:
            assertions['json_value'] = json.loads(first['message'].get('content', '')) == {'value': 323}
        except (ValueError, TypeError):
            assertions['json_value'] = False
        messages = [{'role': 'user', 'content': 'Call lookup_record for key calibration-01. After its result, return its nonce exactly. Do not invent the value.'}]
        tool_response = call('tool_request', messages, [TOOL])
        calls = tool_response['message'].get('tool_calls', [])
        assertions['valid_tool_request'] = False
        if len(calls) == 1 and tool_response['done_reason'] != 'length':
            function = calls[0].get('function', {})
            arguments = function.get('arguments', '{}')
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            assertions['valid_tool_request'] = (function.get('name') == 'lookup_record' and
                                                arguments == {'key': 'calibration-01'})
        if assertions['valid_tool_request']:
            nonce = uuid.uuid4().hex
            messages += [tool_response['message'], {'role': 'tool', 'tool_call_id': calls[0]['id'],
                          'content': json.dumps({'nonce': nonce})}]
            second = call('tool_result', messages, [TOOL])
            assertions['tool_result_used'] = nonce in (second['message'].get('content') or '')
        else:
            assertions['tool_result_used'] = False
        truncated = call('intentional_length', [{'role': 'user', 'content': 'List the integers from 1 to 1000, one per line.'}], num_predict=1)
        assertions['length_detected'] = truncated['done_reason'] == 'length'
    except Exception as exception:
        error = repr(exception)
    finally:
        summary = {'scope': 'connection/calibration fixtures, not task performance', 'config': config,
                   'calls': results, 'assertions': assertions, 'known_total_tokens': total,
                   'usage_complete': all(r['status'] == 'ok' for r in results), 'error': error,
                   'wall_seconds': time.monotonic() - started}
        save_json(out / 'summary.json', summary)
        print(json.dumps({'path': str(out), 'assertions': assertions, 'error': error}), flush=True)
    return not error and bool(assertions) and all(assertions.values())


if __name__ == '__main__':
    signal.signal(signal.SIGALRM, alarm_handler)
    raise SystemExit(0 if main() else 1)
