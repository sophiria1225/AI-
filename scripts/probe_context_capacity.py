"""Synthetic context-capacity calibration, not evidence of real-task ability."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import random
import signal
import time
import urllib.request

import local_llama
from run_e0_pilot import alarm_handler, save_json

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target-tokens', type=int, required=True)
    parser.add_argument('--seed', type=int, default=17)
    args = parser.parse_args()
    runtime = json.loads((ROOT / '.runtime/model_server.json').read_text())
    if runtime['status'] != 'ready' or args.target_tokens > runtime['ctx_size'] - 1024:
        raise ValueError('target requires a ready server and 1024 tokens of reserve')
    config = {'backend': 'llama.cpp', 'base_url': 'http://127.0.0.1:8011',
              'model': 'minimax-m3-q3kl', 'num_ctx': runtime['ctx_size'],
              'num_predict': 512, 'temperature': 1.0, 'top_p': 0.95,
              'top_k': 0, 'min_p': 0.0, 'repeat_penalty': 1.0,
              'seed': args.seed, 'thinking_mode': 'disabled', 'call_timeout_seconds': 900}
    out = ROOT / 'records/p2_capacity' / (datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + str(args.target_tokens))
    out.mkdir(parents=True)
    save_json(out / 'config.json', config)
    with urllib.request.urlopen(config['base_url'] + '/props', timeout=10) as response:
        props = json.load(response)
    save_json(out / 'server_props.json', props)
    save_json(out / 'server_runtime.json', runtime)
    source_hashes = {}
    for source in ('probe_context_capacity.py', 'local_llama.py'):
        content = (ROOT / 'scripts' / source).read_bytes()
        (out / source).write_bytes(content)
        source_hashes[source] = hashlib.sha256(content).hexdigest()
    save_json(out / 'source_hashes.json', source_hashes)
    rng = random.Random(args.seed)
    rows = [f'asset-{i:06d}: token={rng.getrandbits(64):016x}; batch={rng.randrange(1000000)}; zone={rng.randrange(64)}'
            for i in range(args.target_tokens)]
    special = 'asset-424242: token=calibration-target-8f32; batch=71024; zone=7'

    def messages_for(n):
        records = rows[:n]
        records.insert(n // 2, special)
        text = ('The following are distinct synthetic records for a capacity test.\n' +
                '\n'.join(records) + '\nReturn only the token value for asset-424242.')
        return [{'role': 'user', 'content': text}]

    low, high = 0, len(rows)
    counts = []
    while low < high:
        middle = (low + high + 1) // 2
        count = local_llama.count_input(config, messages_for(middle), None)
        counts.append({'records': middle, **count})
        if count['input_tokens'] <= args.target_tokens:
            low = middle
        else:
            high = middle - 1
    messages = messages_for(low)
    count = local_llama.count_input(config, messages, None)
    save_json(out / 'input_sizing.json', counts)
    save_json(out / 'preflight.json', count)
    result = local_llama.model_call(config, messages, out, config['call_timeout_seconds'], tools=None)
    summary = {'scope': 'distinct synthetic records for memory/API calibration only',
               'target_tokens': args.target_tokens, 'preflight_tokens': count['input_tokens'],
               'source_records': low + 1,
               'count_matches': result.get('input_tokens') == count['input_tokens'],
               'retrieved_exact_value': (result['message'].get('content') or '').strip() == 'calibration-target-8f32',
               'response': {k: v for k, v in result.items() if k != 'message'},
               'server_record': runtime['record_directory']}
    save_json(out / 'summary.json', summary)
    print(json.dumps(summary), flush=True)
    return result['status'] == 'ok' and summary['count_matches'] and summary['retrieved_exact_value']


if __name__ == '__main__':
    signal.signal(signal.SIGALRM, alarm_handler)
    raise SystemExit(0 if main() else 1)
