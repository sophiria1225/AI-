"""Execute an inline-checkpoint action and retain its exact original envelope.

The existing executor sees only ordinary code/span_ids arguments. The archive
records the original model response, with a separate transport binding. This
binding proves the removal of metadata, not execution success or summary truth.
The caller must account for the entire original model response before dispatch.
"""
from copy import deepcopy

from code_agent_interface import execute_response
from container_api_python import run_program
from inline_checkpoint_protocol import split_inline_response
from receipt_reasoning_history import require


def execute_inline_response(message, catalog, bridge, prior, record, *, offered,
                            finish_reason, usage_known, out, storage, call_id,
                            remaining_api, may_continue, remaining_wall,
                            read_archive, program=run_program):
    split = split_inline_response(message, offered=offered,
        finish_reason=finish_reason, usage_known=usage_known)
    binding = split['binding']
    restored = 0

    def archival_record(row, display=True):
        nonlocal restored
        if display and binding is not None:
            action = split['execution_message']['tool_calls'][0]['function']
            require(restored == 0 and row['action'] == action,
                    'one_matching_inline_outer_record_required')
            # Replace the function object instead of mutating the sanitized
            # response used by the executor. NativeConversation checks exact
            # argument-string equality with the received model response.
            row['action'] = deepcopy(message['tool_calls'][0]['function'])
            row['inline_transport'] = {
                'version': 'inline_checkpoint_transport_v01',
                'original_payload_sha256': split['original_payload_sha256'],
                **deepcopy(binding), 'status': split['status'],
                'execution_success_verified': False, 'semantics_verified': False}
            restored += 1
        return record(row, display=display)

    rows = execute_response(split['execution_message'], catalog, bridge, prior,
        archival_record, out=out, storage=storage, call_id=call_id,
        remaining_api=remaining_api, may_continue=may_continue,
        remaining_wall=remaining_wall, read_archive=read_archive, program=program)
    require(binding is None or restored == 1, 'inline_outer_record_missing')
    return rows, split
