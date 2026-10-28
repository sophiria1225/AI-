"""P144R1 maps only the ten unstarted P144 slots to fresh output identities.

Scientific configuration is returned unchanged from the frozen P144 adapter.
The run ID is an output identity, not an input to the actor or summarizer.
Completed/evaluated P144 slots cannot be allocated by this continuation.
"""
from whole_task_state_update_p144 import (
    ERROR_POLICY, TASKS, cell_id as original_cell_id, run_order,
    validate_plan as validate_original_plan, worker_config as original_worker_config,
)

REMAINING = tuple(run_order()[2:])


def cell_id(number, mode):
    if type(number) is not int or (number, mode) not in REMAINING:
        raise ValueError('only_ten_unstarted_P144R1_slots_permitted')
    return f'BOC_P144R1_{number:02d}_{mode.upper()}'


def remaining_ids():
    return tuple(cell_id(number, mode) for number, mode in REMAINING)


def validate_remaining_ids(identities):
    if type(identities) not in (list, tuple) or tuple(identities) != remaining_ids():
        raise ValueError('exact_ordered_ten_remaining_P144R1_slots_required')


def worker_config(original, plan, task_id, arm, run_id, object_timing_mode):
    validate_original_plan(plan)
    if task_id not in TASKS or arm != ERROR_POLICY:
        raise ValueError('fixed_P144R1_task_and_error_policy_required')
    number = TASKS.index(task_id) + 1
    expected = cell_id(number, object_timing_mode)
    if type(run_id) is not str or run_id != expected:
        raise ValueError('fixed_P144R1_remaining_slot_identity_required')
    config = original_worker_config(original, plan, task_id, arm,
        original_cell_id(number, object_timing_mode), object_timing_mode)
    if 'run_id' in config:
        raise ValueError('unexpected_P144_run_identity_in_scientific_configuration')
    return config
