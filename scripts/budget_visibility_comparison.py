"""P80: fixed whole-task comparison of measured versus unexposed wall time.

Protocol references are renamed before token counting in both conditions.
Text, arguments, observations and opaque reasoning are never rewritten.
This is an ordinary control ablation, not a claim of a new efficiency method.
"""
import copy

from budget_observation import BudgetObservationInference, POLICIES
from budget_observation_worker import PHASE, worker_config
from budget_signal import digest
from run_context_comparison import write_json

ERROR_POLICY = 'error_exception'


def canonical_messages(messages):
    result, references, returned = copy.deepcopy(messages), {}, set()
    for message in result:
        for call in message.get('tool_calls') or []:
            ident = call.get('id')
            if type(ident) is not str or not ident or ident in references:
                raise ValueError('unique_nonempty_protocol_reference_required')
            references[ident] = f'transport_reference_{len(references) + 1}'
            call['id'] = references[ident]
        if 'tool_call_id' in message:
            ident = message['tool_call_id']
            if type(ident) is not str or ident not in references or ident in returned:
                raise ValueError('one_result_per_prior_protocol_call_required')
            returned.add(ident)
            message['tool_call_id'] = references[ident]
    if set(references) != returned:
        raise ValueError('all_prior_protocol_calls_require_results')
    return result


class CanonicalBudgetInference(BudgetObservationInference):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reference_views = []

    def call(self, role, messages, tools):
        normalized = canonical_messages(messages)
        self.reference_views.append({
            'next_call_id': f'call_{len(self.calls) + 1:03d}',
            'original_messages_sha256': digest(messages),
            'canonical_messages_sha256': digest(normalized),
            'policy': 'protocol_fields_only_first_appearance_order',
        })
        write_json(self.output / 'protocol_reference_views.json', self.reference_views)
        return super().call(role, normalized, tools)


def run_order():
    return [(number, policy) for number in range(1, 5)
            for policy in (POLICIES if number % 2 else POLICIES[::-1])]


def cell_id(number, policy):
    if type(number) is not int or number not in range(1, 5) or policy not in POLICIES:
        raise ValueError('outside_fixed_P80_comparison')
    return f'BOC_P80_{number:02d}_{policy.upper()}'


def config_for(original, plan, task_id, policy):
    number = [t['task_id'] for t in plan['known_tasks']].index(task_id) + 1
    return worker_config(original, plan, task_id, ERROR_POLICY, cell_id(number, policy), policy)


def validate_plan(plan):
    expected = {'phase': PHASE, 'experiment': 'P80', 'batch_id': 'P80_batch_v01',
        'time_policies': list(POLICIES), 'error_policy': ERROR_POLICY,
        'max_cells': 8, 'max_calls': 80, 'max_total_tokens': 450000,
        'max_wall_seconds': 1800, 'max_model_calls': 640, 'max_reserved_tokens': 3600000,
        'max_setup_seconds': 120, 'max_cleanup_seconds': 180,
        'max_idle_wait_seconds': 60, 'max_evaluation_seconds': 180,
        'server_max_lifetime_seconds': 21600, 'world_seed': 42, 'model_seed': 57,
        'reserved_scenarios_read': 0, 'automatic_retries': 0,
        'history_policy': 'all_returned_reasoning_from_start',
        'protocol_references': 'canonical_in_both_before_counting', 'novel_method_claim': False}
    if any(type(plan.get(k)) is not type(v) or plan[k] != v for k, v in expected.items()):
        raise ValueError('fixed_P80_plan_changed')
    if [t['task_id'] for t in plan['known_tasks']] != [
            '34d9492_1', '3c13f5a_1', '60d0b5b_1', '6104387_1']:
        raise ValueError('exactly_the_four_previously_known_tasks_required')
