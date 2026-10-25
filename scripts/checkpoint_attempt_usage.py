"""Account for both actor and summary dispatches, including lost responses."""
from copy import deepcopy

from receipt_reasoning_history import require


def attempt_usage(infer):
    if infer is None:
        return []
    terminal = {c['id']: c for c in infer.calls}
    require(len(terminal) == len(infer.calls), 'duplicate_terminal_usage_identity')
    dispatched = [a for a in infer.admissions if a.get('model_request_started')]
    ids = [a['next_call_id'] for a in dispatched]
    require(len(ids) == len(set(ids)) and set(terminal).issubset(ids),
            'dispatch_terminal_identity_mismatch')
    result = []
    for entry in dispatched:
        cid, role = entry['next_call_id'], entry['role']
        require(role in ('agent', 'focus'), 'known_checkpoint_role_required')
        if cid in terminal:
            row = deepcopy(terminal[cid])
            require(row['role'] == role, 'dispatch_terminal_role_mismatch')
        else:
            row = {'id': cid, 'role': role, 'status': 'error',
                   'input_tokens': None, 'output_tokens': None, 'cached_input_tokens': None,
                   'wall_seconds': None, 'finish_reason': None,
                   'error_kind': 'dispatched_without_terminal_usage',
                   'terminal_usage_recorded': False, 'server_receipt_confirmed': False,
                   'usage_record_source': 'shared_checkpoint_admission_dispatch'}
        require(not result or result[-1]['status'] == 'ok', 'no_dispatch_after_unknown_usage')
        result.append(row)
    return result
