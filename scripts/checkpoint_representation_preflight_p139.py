"""Six handwritten transport cases; this function never counts or generates.

The supplied fake shorter counts only advance pure checkpoint state. They are
not measurements, and the synthetic outputs are not saved model responses.
"""
from copy import deepcopy
import json

from checkpoint_representation_p139 import RepresentationCheckpoint
from protocol_stable_history import StableReferenceConversation
from public_display import CODE_TOOLS
from receipt_reasoning_history import require
from single_checkpoint_history import FIELDS, TRIGGER_INPUT_TOKENS


def synthetic_transport_cases():
    by_name = {}
    for representation in ('recursive', 'delta'):
        conv = StableReferenceConversation('Synthetic transport check only.',
                                           {'instruction': 'Synthetic task.'})
        control = RepresentationCheckpoint('threshold_'+representation)
        serial = 0
        for opportunity in (1, 2):
            for _ in range(3):
                serial += 1
                function = {'name': 'run_python', 'arguments': json.dumps({'code': 'pass', 'span_ids': []})}
                message = {'role': 'assistant', 'content': '', 'reasoning_content': 'synthetic text',
                           'tool_calls': [{'id': f'synthetic-{serial}', 'type': 'function',
                                           'function': function}]}
                conv.append(message, [{'id': f's{serial}', 'action': function,
                                      'observation': {'status': 'ok', 'stdout': 'synthetic observation'}}])
            archive, _ = conv.for_model()
            offered = control.begin(archive, TRIGGER_INPUT_TOKENS)
            name = f'{representation}_focus{opportunity}'
            by_name[name] = dict(name=name, role='focus', messages=offered['summary_messages'],
                                 tools=[], synthetic_only=True)
            value = {key: [f'synthetic revision {opportunity} {key}'] for key in FIELDS}
            control.close_separate(archive, {'role': 'assistant', 'content': json.dumps(value)},
                                   'stop', usage_known=True)
            control.decide(20000, 15000)  # Handwritten fake counts, no native request.
        name = f'{representation}_actor_after2'
        by_name[name] = dict(name=name, role='agent', messages=control.view(archive),
                             tools=deepcopy(CODE_TOOLS), synthetic_only=True)
    require(by_name['recursive_focus1']['messages'] == by_name['delta_focus1']['messages'],
            'synthetic_first_focus_packet_differs')
    require(by_name['recursive_focus2']['messages'][1] == by_name['delta_focus2']['messages'][1],
            'synthetic_second_focus_reference_packet_differs')
    names = ('recursive_focus1', 'recursive_focus2', 'delta_focus1', 'delta_focus2',
             'recursive_actor_after2', 'delta_actor_after2')
    return [deepcopy(by_name[name]) for name in names]
