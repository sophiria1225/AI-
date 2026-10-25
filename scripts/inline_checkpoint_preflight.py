"""Three synthetic native-template inputs; never a task or model-output trial."""
import json

from inline_checkpoint_history import InlineCheckpoint
from inline_checkpoint_protocol import split_inline_response
from protocol_stable_history import StableReferenceConversation
from public_display import CODE_TOOLS
from single_checkpoint_history import FIELDS, TRIGGER_INPUT_TOKENS


def synthetic_transport_cases():
    conv = StableReferenceConversation('Synthetic transport check only.', {'instruction': 'Synthetic task.'})
    for number in range(3):
        message = {'role': 'assistant', 'content': '', 'reasoning_content': 'synthetic text',
            'tool_calls': [{'id': f'synthetic-{number}', 'type': 'function',
                           'function': {'name': 'run_python', 'arguments': '{"code":"pass","span_ids":[]}'}}]}
        conv.append(message, [{'id': f's{number + 1}', 'action': message['tool_calls'][0]['function'],
                               'observation': {'status': 'ok', 'stdout': 'synthetic observation'}}])
    before, _ = conv.for_model()
    control = InlineCheckpoint()
    offer = control.begin(before, CODE_TOOLS, TRIGGER_INPUT_TOKENS)
    checkpoint = {key: ['synthetic ' + key] for key in FIELDS}
    message = {'role': 'assistant', 'content': '', 'reasoning_content': 'synthetic current reasoning',
        'tool_calls': [{'id': 'synthetic-inline', 'type': 'function', 'function': {'name': 'run_python',
            'arguments': json.dumps({'code': 'pass', 'span_ids': [], 'checkpoint': checkpoint})}}]}
    split = split_inline_response(message, offered=True, finish_reason='tool_calls', usage_known=True)
    conv.append(message, [{'id': 's4', 'action': message['tool_calls'][0]['function'],
                          'observation': {'status': 'ok', 'stdout': 'synthetic current observation'}}])
    after, _ = conv.for_model()
    views = control.close(after, split)
    return [{'name': 'inline_offer', 'messages': offer['messages'], 'tools': offer['tools']},
            {'name': 'ordinary_after_inline', 'messages': views['ordinary'], 'tools': CODE_TOOLS},
            {'name': 'compacted_after_inline', 'messages': views['compacted'], 'tools': CODE_TOOLS}]
