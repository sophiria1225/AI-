"""Five handwritten transport shapes, with no native counting or generation."""
from copy import deepcopy
import json
from checkpoint_object_timing_p141 import DeltaEnvelopeCheckpoint, MODES
from protocol_stable_history import StableReferenceConversation
from public_display import CODE_TOOLS
from receipt_reasoning_history import require
from single_checkpoint_history import FIELDS, TRIGGER_INPUT_TOKENS


def synthetic_transport_cases():
    first,second,actors={},{},{}
    for mode in MODES:
        conv=StableReferenceConversation('Synthetic transport check only.',{'instruction':'Synthetic task.'})
        control=DeltaEnvelopeCheckpoint(mode);serial=0
        for opportunity in (1,2):
            for _ in range(3):
                serial+=1
                function={'name':'run_python','arguments':json.dumps({'code':'pass','span_ids':[]})}
                conv.append({'role':'assistant','content':'','reasoning_content':'synthetic text',
                    'tool_calls':[{'id':f'synthetic-{serial}','type':'function','function':function}]},
                    [{'id':f's{serial}','action':function,'observation':{'status':'ok','stdout':'synthetic observation'}}])
            archive,_=conv.for_model()
            offer=control.begin(archive,TRIGGER_INPUT_TOKENS,repeat_ready=True)
            (first if opportunity==1 else second)[mode]=offer['summary_messages']
            value={key:[f'synthetic revision {opportunity} {key}'] for key in FIELDS}
            control.close_separate(archive,{'role':'assistant','content':json.dumps(value)},'stop',usage_known=True)
            control.decide(20000,15000)
        actors[mode]=control.view(archive)
    require(all(first[m]==first[MODES[0]] for m in MODES),'shared_first_focus_packet')
    require(all(second[m][1]==second[MODES[0]][1] for m in MODES),'shared_second_focus_reference_packet')
    require(second[MODES[1]]==second[MODES[2]] and actors[MODES[1]]==actors[MODES[2]],
            'same_object_prompt_both_timings')
    values=[('shared_focus1','focus',first[MODES[0]]),('recursive_focus2','focus',second[MODES[0]]),
        ('object_delta_focus2','focus',second[MODES[2]]),
        ('recursive_actor_after2','agent',actors[MODES[0]]),('delta_actor_after2','agent',actors[MODES[1]])]
    return [dict(name=name,role=role,messages=deepcopy(messages),tools=deepcopy(CODE_TOOLS) if role=='agent' else [],synthetic_only=True)
            for name,role,messages in values]
