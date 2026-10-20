"""Four tokenizer-only checks on a saved public prefix; never execute removals."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import urllib.request

from local_llama import post
from model_provenance import check_live_model
from native_conversation import NativeConversation
from native_memory_view import recorded_turns, retained_view


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--private-record', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.private_record.mkdir(parents=True, exist_ok=False)
    trial = args.storage_root / 'records/context_pilot/P10_01_ROLES'
    plan, usage = read(trial / 'plan.json'), read(trial / 'usage.json')
    # Before the final response: no completion output or evaluator input is used.
    target = usage[-1]
    payload = read(trial / target['id'] / 'request.json')
    events, spans = read(trial / 'events.json'), read(trial / 'spans.json')
    conversation = NativeConversation(payload['messages'][0]['content'], read(trial / 'public_task.json'))
    for call in usage[:-1]:
        response = read(trial / call['id'] / 'response.json')['message']
        ordered = [spans[e['span_id']] for e in events if e['call'] == call['id']]
        conversation.append(response, ordered)
    turns = recorded_turns(conversation)
    all_ids = [s['id'] for _, group in turns for s in group]
    multi = next(group for _, group in turns if len(group) > 1)
    cases = [('all', all_ids, None), ('recent_two_spans', all_ids[-2:], None),
             ('partial_multi_call', [multi[0]['id']], None),
             ('empty_with_empty_ledger', [], {'items': [], 'constraints': [], 'unresolved': []})]
    runtime = read(args.storage_root / '.runtime/model_server.json')
    with urllib.request.urlopen(plan['model']['base_url'] + '/props', timeout=10) as response:
        props = json.load(response)
    check_live_model(plan['model_selection'], runtime, props, root=args.storage_root,
                     expected_ctx=plan['model']['num_ctx'], expected_cache=('q8_0', 'q8_0'))
    (args.private_record / 'runtime.json').write_text(json.dumps(runtime, indent=2) + '\n')
    (args.private_record / 'props.json').write_text(json.dumps(props, indent=2) + '\n')
    rows = []
    for name, selected, ledger in cases:
        messages, detail = retained_view(conversation, selected, ledger, plan['observation_page_characters'])
        value = copy.deepcopy(payload); value['messages'] = messages
        if name == 'all' and value != payload:
            raise ValueError('all-retained input differs from the recorded baseline')
        path = args.private_record / (name + '.json')
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        counted = post(plan['model'], '/v1/chat/completions/input_tokens', value, 60)['input_tokens']
        if name == 'all' and counted != target['input_tokens']:
            raise ValueError('all-retained input count differs from recorded usage')
        rows.append({'case': name, 'input_tokens': counted, 'requested_spans': len(selected),
                     'retained_spans': len(detail['retained_span_ids']),
                     'retained_turns': detail['retained_turns'],
                     'extra_spans_for_complete_turn': detail['additional_spans_to_preserve_call_result_pairs'],
                     'request_sha256': sha(path)})
    result = {'source_run_id': trial.name, 'source_call_id': target['id'],
              'source_request_sha256': sha(trial / target['id'] / 'request.json'),
              'source_script_sha256': sha(Path(__file__)),
              'memory_view_sha256': sha(Path(__file__).parent / 'native_memory_view.py'),
              'cases': rows, 'token_count_requests': len(rows), 'model_calls': 0,
              'environment_requests': 0, 'final_evaluations': 0, 'all_retained_exact_match': True,
              'scope': 'Template/count conformance on one saved prefix. No removed-history '
                       'prompt is used for generation; not a savings or quality result.'}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'cases': rows, 'model_calls': 0}))


if __name__ == '__main__':
    main()
