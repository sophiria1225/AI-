"""Explicit time visibility for future comparisons; not an efficiency method.

This adapter does not replace any frozen experiment worker. Both policies use
the real monotonic deadline and the existing token admission/accounting path.
Only the current notification changes; earlier conversation is never rewritten.
"""
import copy
import json
import time

from api_error_comparison import NOTICE, add_notification, task_snapshot
from budget_signal import digest
from inference_cache_control import cache_measurement
from residual_output_budget import ResidualInference
from run_context_comparison import write_json

POLICIES = ('measured', 'not_exposed')
NO_TIME_NOTICE = NOTICE.replace(
    'Wall time continues after this snapshot.',
    'The harness still enforces its real elapsed-time limit. Remaining wall\n'
    'time is not exposed in this notification; do not infer extra time.')


def notification(messages, measured_state, time_visibility):
    if time_visibility not in POLICIES:
        raise ValueError('explicit_time_visibility_policy_required')
    seconds = measured_state['remaining']['wall_seconds_at_snapshot']
    if type(seconds) is not int or seconds < 0:
        raise ValueError('invalid_measured_wall_snapshot')
    visible = copy.deepcopy(measured_state)
    if time_visibility == 'measured':
        return add_notification(messages, visible), visible
    del visible['remaining']['wall_seconds_at_snapshot']
    result = copy.deepcopy(messages)
    result.append({'role': 'user', 'content': NO_TIME_NOTICE +
        json.dumps(visible, sort_keys=True, separators=(',', ':')) +
        '\n</whole_task_budget_v1>'})
    return result, visible


class BudgetObservationInference(ResidualInference):
    """Choose visibility explicitly, retaining real deadlines and full usage."""
    def __init__(self, config, output, *, time_visibility):
        if time_visibility not in POLICIES:
            raise ValueError('explicit_time_visibility_policy_required')
        super().__init__(config, output, 'residual')
        self._time_visibility = time_visibility
        self._stop_reason = None
        self.api_requests = 0
        self.snapshots = []

    @property
    def time_visibility(self):
        return self._time_visibility

    def call(self, role, messages, tools):
        if role != 'agent':
            raise ValueError('one_executor_no_free_controller')
        if self._stop_reason is not None:
            raise RuntimeError('budget_observation_stopped_after_' + self._stop_reason)
        actual = task_snapshot(self.config, self.calls, self.api_requests,
                               time.monotonic() - self.started)
        supplied, visible = notification(messages, actual, self.time_visibility)
        before = len(self.calls)
        admission_before = len(self.admissions)
        self.config['model']['cache_prompt'] = before != 0
        entry = {'next_call_id': f'call_{before + 1:03d}',
            'time_visibility': self.time_visibility, 'measured_state': actual,
            'visible_state': visible, 'base_messages_sha256': digest(messages),
            'model_messages_sha256': digest(supplied), 'cache_prompt': before != 0,
            'model_attempted': False}
        self.snapshots.append(entry)
        try:
            message = super().call(role, supplied, tools)
            if not before:
                measured = json.loads((self.output / self.calls[0]['id'] / 'response.json').read_text())
                check = cache_measurement('cold_1', measured, measured['input_tokens'])
                entry['first_input_measurement'] = check
                if not check['state_confirmed']:
                    raise ValueError('first_request_reused_prior_condition_cache')
            entry['status'] = 'returned'
            return message
        except Exception as error:
            self._stop_reason = type(error).__name__
            entry.update(status='stopped', exception_type=self._stop_reason)
            raise
        finally:
            # A transport failure can occur after dispatch but before usage.json.
            # Preserve that attempt as unknown instead of recording a free call.
            entry['model_attempted'] = (len(self.calls) != before or any(
                a.get('model_request_started') for a in self.admissions[admission_before:]))
            entry['terminal_usage_recorded'] = len(self.calls) != before
            entry['usage_unknown'] = entry['model_attempted'] and (
                not entry['terminal_usage_recorded'] or self.calls[-1]['status'] != 'ok')
            write_json(self.output / 'budget_observations.json', self.snapshots)
