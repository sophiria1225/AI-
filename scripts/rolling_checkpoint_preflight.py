"""Twelve synthetic template inputs covering all three rolling opportunities.

The synthetic comparison counts below only advance pure control state. Actual
native counts are performed by the finite preflight, never by this constructor.
No generated response, task API, or evaluation is used.
"""
import json

from inline_checkpoint_protocol import split_inline_response
from protocol_stable_history import StableReferenceConversation
from public_display import CODE_TOOLS
from rolling_checkpoint_history import RollingCheckpoint
from single_checkpoint_history import FIELDS, TRIGGER_INPUT_TOKENS


def synthetic_transport_cases():
    cases = []
    for mode in ('separate', 'inline'):
        conv = StableReferenceConversation('Synthetic transport check only.', {'instruction': 'Synthetic task.'})
        control, serial = RollingCheckpoint(mode), 0

        def append(checkpoint=None):
            nonlocal serial
            serial += 1
            args = {'code': 'pass', 'span_ids': []}
            if checkpoint is not None:
                args['checkpoint'] = checkpoint
            message = {'role': 'assistant', 'content': '', 'reasoning_content': 'synthetic text',
                'tool_calls': [{'id': f'synthetic-{serial}', 'type': 'function',
                    'function': {'name': 'run_python', 'arguments': json.dumps(args)}}]}
            conv.append(message, [{'id': f's{serial}', 'action': message['tool_calls'][0]['function'],
                'observation': {'status': 'ok', 'stdout': 'synthetic observation'}}])
            return message

        for opportunity in range(1, 4):
            for _ in range(3):
                append()
            before, _ = conv.for_model()
            offer = control.begin(before, TRIGGER_INPUT_TOKENS, CODE_TOOLS)
            checkpoint = {key: [f'synthetic revision {opportunity} {key}'] for key in FIELDS}
            if mode == 'separate':
                cases.append({'name': f'separate_{opportunity}_summary', 'role': 'focus',
                              'messages': offer['summary_messages'], 'tools': []})
                control.close_separate(before, {'role': 'assistant', 'content': json.dumps(checkpoint)},
                                       'stop', usage_known=True)
            else:
                cases.append({'name': f'inline_{opportunity}_offer', 'role': 'agent',
                              'messages': offer['messages'], 'tools': offer['tools']})
                message = append(checkpoint)
                split = split_inline_response(message, offered=True, finish_reason='tool_calls', usage_known=True)
                after, _ = conv.for_model()
                views = control.close_inline(after, split, usage_known=True)
                cases.extend({'name': f'inline_{opportunity}_{name}', 'role': 'agent',
                    'messages': views[name], 'tools': CODE_TOOLS} for name in ('ordinary','compacted'))
            control.decide(20000, 15000)  # Synthetic state advancement, not a native measurement.
    return cases
