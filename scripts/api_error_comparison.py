"""P78: matched ordinary API contracts, differing only on confirmed exceptions.

Both arms use the same typed bridge. The value arm is an explicit diagnostic
ablation, not an exact replay of the historical untyped/traceback interface.
Business failure values, transport uncertainty and completion stay unchanged.
"""
import copy
import json
import time

from budget_signal import digest, snapshot
from inference_cache_control import cache_measurement
from public_api_result_transport import PublicResultProgram
from public_display import capability_prompt
from reasoning_history import ReasoningConversation
from residual_output_budget import ResidualInference
from run_context_comparison import write_json
from stateful_code_prompts import stateful_system_prompt

ARMS = ('error_value', 'error_exception')
NOTICE = '''<whole_task_budget_v1>
This is an authoritative resource snapshot for the task from its first action.
All task requirements still apply. Every model call's full input and output,
including reasoning and this notice, counts toward the logical token limit.
All discovery, read, write and completion API calls count toward the API limit.
Before each model call, the full input is counted; the output limit is the
smaller of the configured maximum and tokens left after that input. No call
is made if no output fits or input plus output cap exceeds the context limit.
Wall time continues after this snapshot. Finish and verify the requested work
within these limits. Do not declare success while requirements are unmet.
'''


class ErrorPresentationProgram:
    def __init__(self, program, arm):
        if arm not in ARMS:
            raise ValueError('unknown_error_presentation')
        self.program, self.arm = program, arm

    def __call__(self, source, observations, channel, **kwargs):
        def run(source, observations, wrapped, **kwargs):
            return self.program(source, observations, _PresentationChannel(wrapped, self.arm), **kwargs)
        return PublicResultProgram(run)(source, observations, channel, **kwargs)


class _PresentationChannel:
    def __init__(self, base, arm):
        self.base, self.arm = base, arm

    def __getattr__(self, name):
        return getattr(self.base, name)

    def exchange(self, packet):
        reply = self.base.exchange(packet)
        row = self.base.rows[-1]
        if self.arm == 'error_value' and row.get('api_execution', {}).get('status') == 'raised':
            if reply.get('ok') is not False or type(reply.get('error')) is not str:
                raise ValueError('confirmed_exception_response_changed')
            # Convert only after the common channel recorded the invocation error.
            # Failed documentation calls expose no new schemas in either arm.
            value = reply['error']
            row['observation'] = {'observation': json.dumps(value, ensure_ascii=False, allow_nan=False),
                                  'declared_complete': self.base.complete}
            reply = {'id': reply['id'], 'ok': True, 'value': value, 'new_schemas': {}}
        return reply


def initial_conversation(original, public_task):
    return ReasoningConversation(capability_prompt(stateful_system_prompt(original)), public_task)


def task_snapshot(config, calls, api_requests, elapsed):
    state = snapshot(config, calls, 0, api_requests, elapsed)
    old = state['used']
    state['used'] = {'api_calls': old['api_calls_including_prefix'],
                     'model_calls': old['continuation_model_calls'],
                     'logical_input_plus_output_tokens': old['continuation_logical_tokens']}
    return state


def add_notification(messages, state):
    result = copy.deepcopy(messages)
    result.append({'role': 'user', 'content': NOTICE +
                   json.dumps(state, sort_keys=True, separators=(',', ':')) +
                   '\n</whole_task_budget_v1>'})
    return result


class FromStartInference(ResidualInference):
    """Common whole-task notice, exact admission and a cold first request."""
    def __init__(self, config, output):
        super().__init__(config, output, 'residual')
        self.api_requests = 0
        self.snapshots = []

    def call(self, role, messages, tools):
        if role != 'agent':
            raise ValueError('one_executor_no_free_controller')
        state = task_snapshot(self.config, self.calls, self.api_requests,
                              time.monotonic() - self.started)
        supplied = add_notification(messages, state)
        before = len(self.calls)
        self.config['model']['cache_prompt'] = before != 0
        entry = {'next_call_id': f'call_{before + 1:03d}', 'state': state,
                 'base_messages_sha256': digest(messages), 'model_messages_sha256': digest(supplied),
                 'cache_prompt': before != 0, 'model_attempted': False}
        self.snapshots.append(entry)
        if not before:
            write_json(self.output / 'initial_messages_private.json', messages)
        try:
            message = super().call(role, supplied, tools)
            if not before:
                measured = json.loads((self.output / self.calls[0]['id'] / 'response.json').read_text())
                check = cache_measurement('cold_1', measured, measured['input_tokens'])
                entry['first_input_measurement'] = check
                if not check['state_confirmed']:
                    raise ValueError('first_request_reused_prior_condition_cache')
            return message
        finally:
            entry['model_attempted'] = len(self.calls) != before
            write_json(self.output / 'budget_signals.json', self.snapshots)


def config_for(original, plan, task_id):
    config = copy.deepcopy(original)
    for key in ('max_calls', 'max_total_tokens', 'max_wall_seconds'):
        config[key] = plan[key]
    config.update(phase='P78', seed=plan['model_seed'],
                  max_api_requests=original['api_budget_by_task'][task_id])
    return config


def run_order():
    return [(number, arm) for number in range(1, 5)
            for arm in (ARMS if number % 2 else ARMS[::-1])]


def cell_id(number, arm):
    if type(number) is not int or number not in range(1, 5) or arm not in ARMS:
        raise ValueError('outside_fixed_four_task_comparison')
    return f'P78_{number:02d}_{arm.upper()}'


def disposition(summary):
    if (summary['setup']['status'] != 'initial_public_state_matched'
            or summary['unknown_effect_requests']
            or not summary['cleanup_confirmed']
            or summary['stop_reason'] in ('runtime_error', 'cleanup_error', 'setup_failure', 'user_stop')):
        return 'stop_batch'
    if summary['unknown_usage_calls']:
        return ('evaluate_unknown_usage' if summary['stop_reason'] in
                ('wall_limit_during_model_call', 'model_usage_unknown') else 'stop_batch')
    return 'evaluate'


def validate_plan(plan):
    expected = {'phase': 'P78', 'batch_id': 'P78_batch_v01', 'arms': list(ARMS),
        'source_plan': 'configs/P29_stateful_code_v01.json',
        'source_runs': [f'P29_{n:02d}_CODE' for n in range(1, 5)],
        'max_calls': 80, 'max_total_tokens': 450000, 'max_wall_seconds': 1800,
        'max_setup_seconds': 120, 'max_cleanup_seconds': 180,
        'max_idle_wait_seconds': 60, 'max_evaluation_seconds': 180,
        'server_max_lifetime_seconds': 21600, 'max_cells': 8,
        'max_model_calls': 640, 'max_reserved_tokens': 3600000,
        'world_seed': 42, 'model_seed': 51, 'reserved_scenarios_read': 0,
        'novel_method_claim': False, 'history_policy': 'all_returned_reasoning_from_start',
        'catalog_policy': 'public_names', 'automatic_retries': 0}
    if any(plan.get(k) != value for k, value in expected.items()):
        raise ValueError('fixed_P78_comparison_or_budget_changed')
