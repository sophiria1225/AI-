"""After P40, recount only inputs rejected by the fixed output reservation.

Calls the pinned input-token counter, never a completion or an environment API.
Residual decode capacity is not task feasibility or recoverable savings.
"""
import argparse
import datetime as dt
from pathlib import Path
import json

from budget_signal import add_notification, digest
from code_agent_interface import CODE_TOOLS
from local_llama import count_input
from native_conversation import NativeConversation, recover_turn
from probe_inference_cache import live_identity
from run_handoff_factors import ROOT, read, sha


def residual_capacity(remaining, next_input, reserved_output):
    if any(type(v) is not int or v < 0 for v in (remaining, next_input, reserved_output)):
        raise ValueError('invalid token quantities')
    capacity = remaining - next_input
    if capacity >= reserved_output:
        raise ValueError('fixed reservation would fit; this does not explain the stop')
    return {'remaining_tokens': remaining, 'next_input_tokens': next_input,
            'reserved_output_tokens': reserved_output,
            'positive_output_capacity': max(0, capacity),
            'classification': 'smaller_output_cap_could_admit' if capacity > 0 else 'no_positive_output_fits',
            'completion_possible_claim': False}


def restore(messages):
    view = NativeConversation(messages[0]['content'], json.loads(messages[1]['content'])['task'])
    offset = 2
    while offset < len(messages):
        assistant = messages[offset]
        size = 1 + len(assistant.get('tool_calls') or [None])
        view.append(assistant, recover_turn(messages[offset:offset + size]))
        offset += size
    if view.messages() != messages:
        raise ValueError('saved conversation cannot be reconstructed exactly')
    return view


def inspect(storage, root):
    report = read(root / 'reports/P40_comparison.json')
    status = read(storage / 'records/context_pilot/P40_batch_v01/status.json')
    if (not report['all_eight_reviewed'] or report['audit_errors'] or len(report['rows']) != 8
            or status['status'] != 'complete' or len(status['completed']) != 8):
        raise ValueError('wait for the whole closed and audited cohort')
    activation = read(root / 'reports/P40_activation_v01.json')
    for name in ('scripts/budget_signal.py', 'scripts/native_conversation.py',
                 'scripts/local_llama.py', 'scripts/code_agent_interface.py'):
        if sha(root / name) != activation['source_hashes'][name]:
            raise ValueError('input construction differs from the executed version')
    source = read(root / 'configs/P29_stateful_code_v01.json')
    identity, _ = live_identity(storage, source, 300)
    out = storage / 'records/context_pilot/P40_admission_v01'
    target = root / 'reports/P40_admission.json'
    if out.exists() or target.exists():
        raise FileExistsError('preserve admission audit or failed attempt')
    out.mkdir()
    result = {'phase': 'P40_admission_audit', 'status': 'running', 'rows': [],
              'created_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'model_identity': identity,
              'completion_requests': 0, 'environment_api_requests': 0, 'evaluator_calls': 0,
              'input_count_requests': 0, 'failed_input_count_requests': 0,
              'limits': ['Only the recorded token-reservation stops are recounted.',
                         'Positive output capacity does not establish that a useful or complete response fits.',
                         'No execution is resumed, and no additional budget is granted.',
                         'This is a stopping-policy diagnostic, not a novel method or a task-success result.'],
              'source_sha256': {p: sha(root / p) for p in
                  ('reports/P40_comparison.json', 'scripts/inspect_budget_admission.py')}}
    try:
        for cell in report['rows']:
            if cell['stop_reason'] != 'token_reservation_limit':
                continue
            folder = storage / 'records/context_pilot' / cell['run_id']
            if sha(folder / 'budget_signals.json') != cell['signal_source_sha256']:
                raise ValueError('changed budget signals')
            signal = read(folder / 'budget_signals.json')[-1]
            if signal['model_attempted']:
                raise ValueError('expected the rejected, ungenerated input')
            config = read(folder / 'plan.json')
            view = restore(read(folder / 'conversation_private.json'))
            base, _ = view.for_model(config['observation_page_characters'])
            messages = add_notification(base, signal['state'], cell['arm'])
            if digest(base) != signal['base_messages_sha256'] or digest(messages) != signal['model_messages_sha256']:
                raise ValueError('recounted input differs from the rejected input')
            cfg = {**config['model'], 'temperature': config['agent_temperature'],
                   'seed': config['seed'] + cell['model_calls'], 'num_predict': config['max_output_tokens'],
                   'cache_prompt': bool(cell['model_calls'])}
            result['input_count_requests'] += 1
            try:
                count = count_input(cfg, messages, CODE_TOOLS, timeout=30)
            except Exception:
                result['failed_input_count_requests'] += 1
                raise
            capacity = residual_capacity(signal['state']['remaining']['logical_input_plus_output_tokens'],
                                         count['input_tokens'], config['max_output_tokens'])
            result['rows'].append({'run_id': cell['run_id'], **capacity,
                                   'count_wall_seconds': count['wall_seconds'],
                                   'model_messages_sha256': digest(messages),
                                   'conversation_sha256': sha(folder / 'conversation_private.json')})
        result['status'] = 'complete'
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result['rows']))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT)
    a = p.parse_args()
    inspect(a.storage_root, a.repo_root)
