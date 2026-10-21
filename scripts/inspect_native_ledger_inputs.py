"""Tokenizer-only preflight at four saved full-history terminal input prefixes."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import urllib.request

from context_preservation import LEDGER_TOOL
from local_llama import count_input
from model_provenance import check_live_model
from native_ledger_memory import draft_messages


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan = read(args.plan)
    prerequisite = plan['wait_for_native_batch']
    if prerequisite not in ('P13_batch_v01', 'P13_recovery_v01'):
        raise ValueError('unexpected P13 completion prerequisite')
    if read(args.storage_root / 'records/context_pilot' / prerequisite / 'status.json')['status'] != 'complete':
        raise ValueError('wait for P13 completion before additional tokenizer requests')
    runtime = read(args.storage_root / '.runtime/model_server.json')
    with urllib.request.urlopen(plan['model']['base_url'] + '/props', timeout=10) as response:
        props = json.load(response)
    check_live_model(plan['model_selection'], runtime, props, root=args.storage_root,
                     expected_ctx=plan['model']['num_ctx'], expected_cache=('q8_0', 'q8_0'))
    private = args.storage_root / 'records/native_history/P14_ledger_input_v01'
    private.mkdir(parents=True, exist_ok=False)
    rows = []
    for i, (task_id, _, _) in enumerate(plan['run_order'], 1):
        trial = args.storage_root / f'records/context_pilot/P11_{i:02d}_ROLES'
        provenance = read(trial / 'provenance.json')
        if provenance['task_id'] != task_id:
            raise ValueError('task order changed')
        usage = read(trial / 'usage.json'); target = usage[-1]['id']
        prefix_ids = {c['id'] for c in usage[:-1]}
        events, all_spans = read(trial / 'events.json'), read(trial / 'spans.json')
        spans = {e['span_id']: all_spans[e['span_id']] for e in events if e['call'] in prefix_ids}
        payload = read(trial / target / 'request.json')
        messages = draft_messages(read(trial / 'public_task.json'), spans, list(spans), None,
                                  payload['tools'], plan['observation_page_characters'])
        record = private / f'task_{i}.json'
        record.write_text(json.dumps({'messages': messages, 'tools': [LEDGER_TOOL]}, ensure_ascii=False) + '\n')
        config = dict(plan['model'], temperature=plan['draft_temperature'], seed=plan['seed'],
                      num_predict=plan['max_output_tokens'])
        n = count_input(config, messages, [LEDGER_TOOL], timeout=60)['input_tokens']
        rows.append({'task_number': i, 'source_run': trial.name, 'source_next_call': target,
                     'input_tokens': n, 'reserved_output': plan['max_output_tokens'],
                     'fits_context': n + plan['max_output_tokens'] <= plan['model']['num_ctx'],
                     'request_sha256': sha(record), 'source_usage_sha256': sha(trial / 'usage.json')})
    result = {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'cases': rows,
              'token_count_requests': len(rows), 'model_calls': 0, 'environment_requests': 0,
              'evaluator_accessed': False, 'plan_sha256': sha(args.plan),
              'source_hashes': {name: sha(Path(__file__).parent / name) for name in (
                  'inspect_native_ledger_inputs.py', 'native_ledger_memory.py', 'context_preservation.py')},
              'scope': 'Four saved full-history input prefixes. No selected-memory generation, '
                       'continuation, measured savings or proof every future input will fit.'}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'cases': rows, 'model_calls': 0}))
