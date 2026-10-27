"""Six pure transport shapes: four focus checks and two installed actor views.

P142 compares the two threshold methods only. Both initial focus packets are
checked separately, even though their content is equal; the second packets
exercise recursive and explicit object-delta representations. No task/world,
native counter, model, API or evaluator is invoked by this constructor.
"""
from copy import deepcopy
from checkpoint_object_timing_preflight_p141 import synthetic_transport_cases as previous_cases
from receipt_reasoning_history import require


def synthetic_transport_cases():
    prior = {case['name']: case for case in previous_cases()}
    names = [('recursive_focus1', 'shared_focus1', 'threshold_recursive', 1),
             ('object_delta_focus1', 'shared_focus1', 'threshold_delta_object', 1),
             ('recursive_focus2', 'recursive_focus2', 'threshold_recursive', 2),
             ('object_delta_focus2', 'object_delta_focus2', 'threshold_delta_object', 2),
             ('recursive_actor_after2', 'recursive_actor_after2', 'threshold_recursive', 2),
             ('delta_actor_after2', 'delta_actor_after2', 'threshold_delta_object', 2)]
    result = []
    for name, source, mode, opportunity in names:
        case = deepcopy(prior[source])
        case.update(name=name, mode=mode, checkpoint_opportunity=opportunity)
        result.append(case)
    require(result[0]['messages'] == result[1]['messages'], 'same_initial_focus_contract')
    require(result[2]['messages'][1] == result[3]['messages'][1] and
            result[2]['messages'][0] != result[3]['messages'][0],
            'second_focus_same_packet_distinct_representation_prompt')
    require(sum(row['role'] == 'focus' for row in result) == 4 and
            sum(row['role'] == 'agent' for row in result) == 2,
            'four_focus_two_actor_transport_checks')
    return result
