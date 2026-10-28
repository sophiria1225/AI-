"""Six synthetic P143 transports from the genuine 8k controller, no I/O.

Both initial focus packets, both second packets and both installed actor views
are counted by the finite caller. This module never counts or generates itself.
"""
from copy import deepcopy
import json
from checkpoint_early_threshold_p143 import DeltaEnvelopeCheckpoint, MODES
from protocol_stable_history import StableReferenceConversation
from public_display import CODE_TOOLS
from receipt_reasoning_history import require
from single_checkpoint_history import FIELDS


def synthetic_transport_cases():
    first, second, actors = {}, {}, {}
    require(tuple(MODES) == ('threshold_recursive','threshold_delta_object'), 'fixed_two_P143_modes')
    for mode in MODES:
        conv = StableReferenceConversation('Synthetic transport check only.', {'instruction':'Synthetic task.'})
        control = DeltaEnvelopeCheckpoint(mode)
        serial = 0
        for opportunity in (1,2):
            for _ in range(3):
                serial += 1
                function = {'name':'run_python','arguments':json.dumps({'code':'pass','span_ids':[]})}
                conv.append({'role':'assistant','content':'','reasoning_content':'synthetic text',
                    'tool_calls':[{'id':f'synthetic-{serial}','type':'function','function':function}]},
                    [{'id':f's{serial}','action':function,'observation':{'status':'ok','stdout':'synthetic observation'}}])
            archive, _ = conv.for_model()
            offer = control.begin(archive,8192,repeat_ready=True)
            require(offer is not None, 'genuine_8192_opportunity_required')
            (first if opportunity == 1 else second)[mode] = offer['summary_messages']
            value = {key:[f'synthetic revision {opportunity} {key}'] for key in FIELDS}
            control.close_separate(archive, {'role':'assistant','content':json.dumps(value)}, 'stop', usage_known=True)
            control.decide(12000,6000)
        actors[mode] = control.view(archive)
    require(first[MODES[0]] == first[MODES[1]], 'shared_first_focus_packet')
    require(second[MODES[0]][1] == second[MODES[1]][1] and second[MODES[0]][0] != second[MODES[1]][0],
            'second_focus_same_reference_distinct_representation_prompt')
    values = [('recursive_focus1','focus',first[MODES[0]],MODES[0],1),
        ('object_delta_focus1','focus',first[MODES[1]],MODES[1],1),
        ('recursive_focus2','focus',second[MODES[0]],MODES[0],2),
        ('object_delta_focus2','focus',second[MODES[1]],MODES[1],2),
        ('recursive_actor_after2','agent',actors[MODES[0]],MODES[0],2),
        ('delta_actor_after2','agent',actors[MODES[1]],MODES[1],2)]
    return [dict(name=name,role=role,messages=deepcopy(messages),
        tools=deepcopy(CODE_TOOLS) if role=='agent' else [],synthetic_only=True,
        mode=mode,checkpoint_opportunity=opportunity)
        for name,role,messages,mode,opportunity in values]
