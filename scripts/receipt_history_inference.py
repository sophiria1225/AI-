"""Apply frozen P110 display rules before counting/admission in a new live run."""
import json
import time

from api_error_comparison import task_snapshot
from budget_observation import notification
from inference_cache_control import cache_measurement
from protocol_stable_history import StableReferenceConversation
from receipt_reasoning_history import POLICIES, digest, execution_evidence, project, require
from run_context_comparison import write_json
from tool_choice_local_llama import reasoning_budget, tool_choice
from tool_choice_residual import ToolChoiceResidualInference


class ReceiptHistoryInference(ToolChoiceResidualInference):
    def __init__(self, config, output, *, conversation, time_visibility='not_exposed'):
        require(type(conversation) is StableReferenceConversation, 'source_normalized_conversation_required')
        require(time_visibility == 'not_exposed', 'fixed_hidden_wall_time_required')
        require(config['reasoning_display_policy'] in POLICIES, 'explicit_receipt_history_policy_required')
        require(config['read_views_enabled'] is False, 'eager_API_path_has_no_pending_read_views')
        require(reasoning_budget(config['model']) == -1 and tool_choice(config['model']) == 'auto',
                'fixed_auto_unlimited_reasoning_required')
        super().__init__(config, output, 'residual')
        self.conversation = conversation
        self.display_policy = config['reasoning_display_policy']
        self._wall_limit = config['max_wall_seconds']
        self._stop_reason = None
        self.api_requests = 0
        self.snapshots = []
        self.reference_views = []
        self.history_views = []
        self.execution_records = []

    def record_execution(self, call_id, events, spans):
        """Called only after that actual response's tool execution is recorded."""
        started = time.monotonic()
        require(self.calls and self.calls[-1]['status'] == 'ok' and self.calls[-1]['id'] == call_id,
                'latest_known_model_response_required')
        require(len(self.execution_records) == len(self.calls)-1, 'one_execution_record_per_response')
        require(all(e['call'] == call_id for e in events), 'execution_call_identity_changed')
        entry = execution_evidence(events, spans, pending_reads=0)
        self.execution_records.append(dict(call_id=call_id, evidence=entry,
            evidence_wall_seconds=time.monotonic()-started))
        write_json(self.output / 'reasoning_execution_records.json', self.execution_records)

    def call(self, role, messages, tools):
        require(role == 'agent', 'one_executor_no_extra_selector_model')
        require(self._stop_reason is None, 'receipt_history_already_stopped')
        require(self.config['max_wall_seconds'] == self._wall_limit and
                self.config['reasoning_display_policy'] == self.display_policy and
                self.config['read_views_enabled'] is False and
                reasoning_budget(self.config['model']) == -1 and
                tool_choice(self.config['model']) == 'auto', 'fixed_history_runtime_policy_changed')
        started = time.monotonic()
        normalized, _ = self.conversation.for_model(self.config['observation_page_characters'])
        require(normalized == messages, 'supplied_history_differs_from_full_archive')
        projected, metadata = project(normalized, [e['evidence'] for e in self.execution_records], self.display_policy)
        call_id = f'call_{len(self.calls)+1:03d}'
        previous_removed = set(self.history_views[-1]['projection']['removed_reasoning_turns']) if self.history_views else set()
        metadata['redisplayed_reasoning_turns'] = sorted(previous_removed-set(metadata['removed_reasoning_turns']))
        self.history_views.append(dict(next_call_id=call_id, projection=metadata,
            projection_wall_seconds=time.monotonic()-started))
        write_json(self.output / 'reasoning_history_views.json', self.history_views)
        self.reference_views.append(dict(next_call_id=call_id,
            original_messages_sha256=digest(self.conversation.messages()),
            canonical_messages_sha256=digest(normalized), projected_messages_sha256=digest(projected),
            policy='source_protocol_fields_before_rendering'))
        write_json(self.output / 'protocol_reference_views.json', self.reference_views)
        actual = task_snapshot(self.config, self.calls, self.api_requests, time.monotonic()-self.started)
        supplied, visible = notification(projected, actual, 'not_exposed')
        before, admission_before = len(self.calls), len(self.admissions)
        self.config['model']['cache_prompt'] = before != 0
        entry = dict(next_call_id=call_id, time_visibility='not_exposed',
            effective_time_visibility='not_exposed', original_wall_limit_seconds=self._wall_limit,
            measured_state=actual, visible_state=visible, base_messages_sha256=digest(projected),
            model_messages_sha256=digest(supplied), cache_prompt=before != 0, model_attempted=False)
        self.snapshots.append(entry)
        try:
            message = super().call(role, supplied, tools)
            if not before:
                measured = json.loads((self.output/self.calls[0]['id']/'response.json').read_text())
                check = cache_measurement('cold_1', measured, measured['input_tokens'])
                entry['first_input_measurement'] = check
                require(check['state_confirmed'], 'first_request_reused_prior_condition_cache')
            entry['status'] = 'returned'
            return message
        except Exception as error:
            self._stop_reason = type(error).__name__
            entry.update(status='stopped', exception_type=self._stop_reason)
            raise
        finally:
            entry['model_attempted'] = len(self.calls) != before or any(
                a.get('model_request_started') for a in self.admissions[admission_before:])
            entry['terminal_usage_recorded'] = len(self.calls) != before
            entry['usage_unknown'] = entry['model_attempted'] and (
                not entry['terminal_usage_recorded'] or self.calls[-1]['status'] != 'ok')
            write_json(self.output/'budget_observations.json', self.snapshots)

    def history_summary(self):
        return dict(policy=self.display_policy, execution_records=len(self.execution_records),
            eligible_executions=sum(e['evidence']['eligible'] for e in self.execution_records),
            projections=len(self.history_views),
            projections_hiding_reasoning=sum(bool(v['projection']['removed_reasoning_turns']) for v in self.history_views),
            projections_redisplaying_reasoning=sum(bool(v['projection']['redisplayed_reasoning_turns']) for v in self.history_views),
            measured_projection_wall_seconds=sum(v['projection_wall_seconds'] for v in self.history_views),
            measured_evidence_wall_seconds=sum(e['evidence_wall_seconds'] for e in self.execution_records),
            control_cost_included_in_work_wall=True, archive_deleted=False,
            semantic_redundancy_certified=False, task_quality_established=False)
