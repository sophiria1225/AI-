"""P97 one-shot ordinary recovery, derived from the source-normalized clock wrapper."""
import json
import time

from api_error_comparison import task_snapshot
from budget_observation import notification
from budget_signal import digest
from protocol_stable_history import StableReferenceConversation
from inference_cache_control import cache_measurement
from fixed_budget_residual import FixedBudgetResidualInference
from fixed_budget_local_llama import reasoning_budget
from recovery_notices import RecoveryMonitor
from run_context_comparison import write_json

class RecoveryNoticeInference(FixedBudgetResidualInference):
    def __init__(self, config, output, *, conversation, time_visibility, monitor):
        if time_visibility != 'not_exposed':
            raise ValueError('explicit_late_clock_policy_required')
        if type(conversation) is not StableReferenceConversation:
            raise ValueError('source_normalized_conversation_required')
        if type(monitor) is not RecoveryMonitor or monitor.policy != config['notice_policy']:
            raise ValueError('fixed_matching_recovery_monitor_required')
        if reasoning_budget(config['model']) != -1:
            raise ValueError('ordinary_unlimited_reasoning_required')
        self.monitor = monitor
        self.conversation = conversation
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
        if reasoning_budget(self.config['model']) != -1:
            raise ValueError('reasoning_budget_changed_during_task')
        if role != 'agent':
            raise ValueError('one_executor_no_free_controller')
        if self._stop_reason is not None:
            raise RuntimeError('late_clock_stopped_after_' + self._stop_reason)
        if self.config['max_wall_seconds'] != self._wall_limit:
            raise ValueError('original_wall_limit_must_not_change')
        normalized, _ = self.conversation.for_model(self.config['observation_page_characters'])
        if normalized != messages:
            raise ValueError('supplied_history_differs_from_bound_source')
        self.reference_views.append({'next_call_id': f'call_{len(self.calls)+1:03d}',
            'original_messages_sha256': digest(self.conversation.messages()), 'canonical_messages_sha256': digest(normalized),
            'policy': 'source_protocol_fields_before_rendering'})
        write_json(self.output / 'protocol_reference_views.json', self.reference_views)
        actual = task_snapshot(self.config, self.calls, self.api_requests,
                               time.monotonic() - self.started)
        effective = 'not_exposed'
        supplied, visible = notification(normalized, actual, effective)
        before_recovery = digest(supplied)
        supplied, offer = self.monitor.supply(supplied, f'call_{len(self.calls)+1:03d}')
        before, admission_before = len(self.calls), len(self.admissions)
        self.config['model']['cache_prompt'] = before != 0
        entry = {'next_call_id': f'call_{before+1:03d}', 'time_visibility': self.time_visibility,
            'effective_time_visibility': effective, 'original_wall_limit_seconds': self._wall_limit,
            'measured_state': actual, 'visible_state': visible,
            'base_messages_sha256': digest(normalized), 'model_messages_sha256': digest(supplied),
            'cache_prompt': before != 0, 'model_attempted': False,
            'recovery_notice_policy': self.monitor.policy, 'recovery_notice_supplied': offer is not None,
            'before_recovery_messages_sha256': before_recovery}
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
            if offer is not None:
                offer['model_attempted'] = entry['model_attempted']
            write_json(self.output / 'budget_observations.json', self.snapshots)
