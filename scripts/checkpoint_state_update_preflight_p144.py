"""Nine synthetic P144 transports from the genuine controller, without I/O.

Three identical first focus packets, three distinct second focus prompts and
three installed actor views are counted by the finite caller; no generation.
"""
from copy import deepcopy
import json
from checkpoint_state_update_p144 import StateUpdateCheckpoint, MODES
from protocol_stable_history import StableReferenceConversation
from public_display import CODE_TOOLS
from receipt_reasoning_history import require
from single_checkpoint_history import FIELDS


def synthetic_transport_cases():
    first, second, actors = {}, {}, {}
    require(tuple(MODES) == ('threshold_recursive','threshold_delta_object','threshold_delta_update'),
            'fixed_three_P144_modes')
    for mode in MODES:
        conv = StableReferenceConversation('Synthetic transport check only.', {'instruction':'Synthetic task.'})
        control = StateUpdateCheckpoint(mode)
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
            if opportunity == 2 and mode == MODES[2]:
                value = {key:dict(keep=[],update=[dict(index=0,text=value[key][0])],delete=[],add=[]) for key in FIELDS}
            control.close_separate(archive, {'role':'assistant','content':json.dumps(value)}, 'stop', usage_known=True)
            control.decide(12000,6000)
        actors[mode] = control.view(archive)
    require(all(first[m] == first[MODES[0]] for m in MODES), 'shared_first_focus_packet')
    require(all(second[m][1] == second[MODES[0]][1] for m in MODES), 'shared_second_reference_packet')
    require(len({second[m][0]['content'] for m in MODES}) == 3, 'distinct_second_system_prompts')
    values = [(f'{mode}_focus{opportunity}', 'focus', packets[mode], mode, opportunity)
              for opportunity, packets in ((1,first),(2,second)) for mode in MODES]
    values += [(f'{mode}_actor_after2','agent',actors[mode],mode,2) for mode in MODES]
    return [dict(name=name,role=role,messages=deepcopy(messages),
        tools=deepcopy(CODE_TOOLS) if role=='agent' else [],synthetic_only=True,
        mode=mode,checkpoint_opportunity=opportunity)
        for name,role,messages,mode,opportunity in values]
