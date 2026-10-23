"""Integration contract for future cells, with no experiment allocation or CLI.

Dispatched requests without terminal usage remain unknown attempts. The adapter's
admission ledger and observed notices are kept separately from terminal usage.
"""
import copy
import re

from api_error_comparison import ARMS, config_for
from budget_observation import POLICIES

PHASE = 'budget_observation_connection'


def worker_config(original, plan, task_id, arm, run_id, time_visibility):
    if plan.get('phase') != PHASE:
        raise ValueError('new_connection_plan_required_preserve_closed_experiments')
    if arm not in ARMS or time_visibility not in POLICIES:
        raise ValueError('explicit_error_and_time_policies_required')
    if type(run_id) is not str or not re.fullmatch(r'BOC_[A-Za-z0-9_-]{1,100}', run_id):
        raise ValueError('new_safe_connection_run_id_required')
    caps = {'max_calls':80, 'max_total_tokens':450000, 'max_wall_seconds':1800,
            'max_setup_seconds':120, 'max_cleanup_seconds':180}
    if any(type(plan.get(k)) is not int or not 0 < plan[k] <= cap for k, cap in caps.items()):
        raise ValueError('finite_connection_limits_required')
    if (plan.get('automatic_retries') != 0 or plan.get('reserved_scenarios_read') != 0
            or plan.get('history_policy') != 'all_returned_reasoning_from_start'
            or type(plan.get('model_seed')) is not int
            or type(plan.get('world_seed')) is not int):
        raise ValueError('explicit_no_retry_history_and_seeds_required')
    config = config_for(original, plan, task_id)
    if (type(config['max_api_requests']) is not int or not 0 < config['max_api_requests'] <= 160
            or type(config['max_output_tokens']) is not int or not 0 < config['max_output_tokens'] <= 4096):
        raise ValueError('finite_API_and_output_limits_required')
    config.update(phase=PHASE, time_visibility=time_visibility, error_presentation=arm)
    return config


def attempt_usage(infer):
    """Materialize unknown dispatches without fabricating a terminal response."""
    if infer is None:
        return []
    terminal = {c['id']: c for c in infer.calls}
    if len(terminal) != len(infer.calls):
        raise ValueError('duplicate_terminal_usage_identity')
    dispatched = [s for s in infer.snapshots if s.get('model_attempted')]
    ids = [s['next_call_id'] for s in dispatched]
    if len(ids) != len(set(ids)) or not set(terminal).issubset(ids):
        raise ValueError('dispatch_terminal_identity_mismatch')
    rows = []
    for notice in dispatched:
        cid = notice['next_call_id']
        if notice.get('terminal_usage_recorded') != (cid in terminal):
            raise ValueError('dispatch_terminal_presence_mismatch')
        if cid in terminal:
            row = copy.deepcopy(terminal[cid])
            if notice.get('usage_unknown') != (row['status'] != 'ok'):
                raise ValueError('dispatch_terminal_usage_status_mismatch')
        else:
            if notice.get('usage_unknown') is not True:
                raise ValueError('missing_terminal_usage_must_stay_unknown')
            row = {'id':cid, 'role':'agent', 'status':'error',
                'input_tokens':None, 'output_tokens':None, 'cached_input_tokens':None,
                'wall_seconds':None, 'finish_reason':None,
                'error_kind':'dispatched_without_terminal_usage',
                'terminal_usage_recorded':False,
                'server_receipt_confirmed':False,
                'usage_record_source':'budget_observation_dispatch_record'}
        rows.append(row)
    return rows
