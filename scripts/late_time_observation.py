"""Ordinary half-deadline visibility control, separate from frozen experiments.

Before each model attempt, expose the real integer wall snapshot only when it
is at most half the original work budget. Existing floor rounding is retained.
An in-flight call cannot be notified.
No threshold search, deadline extension, historical rewrite, or novelty claim.
"""
import json
import time

from api_error_comparison import task_snapshot
from budget_observation import notification
from budget_signal import digest
from budget_visibility_comparison import canonical_messages
from inference_cache_control import cache_measurement
from residual_output_budget import ResidualInference
from run_context_comparison import write_json

POLICIES = ('measured', 'late_half')


def effective_visibility(policy, state, wall_limit):
    seconds = state['remaining']['wall_seconds_at_snapshot']
    if (policy not in POLICIES or type(wall_limit) is not int or wall_limit <= 0
            or type(seconds) is not int or not 0 <= seconds <= wall_limit):
        raise ValueError('valid_fixed_policy_and_real_wall_snapshot_required')
    return 'measured' if policy == 'measured' or 2 * seconds <= wall_limit else 'not_exposed'


class LateClockInference(ResidualInference):
    def __init__(self, config, output, *, time_visibility):
        if time_visibility not in POLICIES:
            raise ValueError('explicit_late_clock_policy_required')
        wall_limit = config['max_wall_seconds']
        if type(wall_limit) is not int or wall_limit <= 0:
            raise ValueError('positive_fixed_integer_wall_limit_required')
        super().__init__(config, output, 'residual')
        self._time_visibility = time_visibility
        self._wall_limit = wall_limit
        self._stop_reason = None
        self.api_requests = 0
        self.snapshots = []
        self.reference_views = []

    @property
    def time_visibility(self):
        return self._time_visibility

    def call(self, role, messages, tools):
        if role != 'agent':
            raise ValueError('one_executor_no_free_controller')
        if self._stop_reason is not None:
            raise RuntimeError('late_clock_stopped_after_' + self._stop_reason)
        if self.config['max_wall_seconds'] != self._wall_limit:
            raise ValueError('original_wall_limit_must_not_change')
        normalized = canonical_messages(messages)
        self.reference_views.append({'next_call_id': f'call_{len(self.calls)+1:03d}',
            'original_messages_sha256': digest(messages), 'canonical_messages_sha256': digest(normalized),
            'policy': 'protocol_fields_only_first_appearance_order'})
        write_json(self.output / 'protocol_reference_views.json', self.reference_views)
        actual = task_snapshot(self.config, self.calls, self.api_requests,
                               time.monotonic() - self.started)
        effective = effective_visibility(self.time_visibility, actual, self._wall_limit)
        supplied, visible = notification(normalized, actual, effective)
        before, admission_before = len(self.calls), len(self.admissions)
        self.config['model']['cache_prompt'] = before != 0
        entry = {'next_call_id': f'call_{before+1:03d}', 'time_visibility': self.time_visibility,
            'effective_time_visibility': effective, 'original_wall_limit_seconds': self._wall_limit,
            'measured_state': actual, 'visible_state': visible,
            'base_messages_sha256': digest(normalized), 'model_messages_sha256': digest(supplied),
            'cache_prompt': before != 0, 'model_attempted': False}
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
            entry['model_attempted'] = (len(self.calls) != before or any(
                a.get('model_request_started') for a in self.admissions[admission_before:]))
            entry['terminal_usage_recorded'] = len(self.calls) != before
            entry['usage_unknown'] = entry['model_attempted'] and (
                not entry['terminal_usage_recorded'] or self.calls[-1]['status'] != 'ok')
            write_json(self.output / 'budget_observations.json', self.snapshots)
