"""Ordinary rolling checkpoints plus one bounded observed-obligation disclosure.

Every mode uses the original P123 initial interface and captures the same typed
evidence. IDs and entity/field modes use the same conservative ID selection.
Notice input is paid by the ordinary actor budget. No query, guide or public
handle is added; no transient notice enters archive/focus.
"""
from copy import deepcopy
import json

from late_obligation_runtime_p136 import LateObligationRuntime
from public_display import CODE_TOOLS
from late_obligation_core_p136 import CheckpointDisclosure, MODES, VERSION, SELECTION_RULE, digest as packet_digest, notice
from inference_cache_control import cache_measurement
from receipt_reasoning_history import digest, require
from rolling_checkpoint_inference import RollingCheckpointInference
from run_context_comparison import write_json
from single_checkpoint_history import closed_turns
from tool_choice_residual import ToolChoiceResidualInference


def boundary_descriptor(normalized, working, *, revision, after_model_calls, decision):
    return dict(checkpoint_revision=revision, after_model_calls=after_model_calls,
        normalized_history_sha256=digest(normalized), checkpoint_view_sha256=digest(working),
        checkpoint_decision_sha256=packet_digest(decision))


class LateObligationInference(RollingCheckpointInference):
    def __init__(self, config, output, *, conversation, obligation_runtime):
        require(config.get('checkpoint_policy') == 'rolling_separate'
                and config.get('obligation_mode') in MODES, 'fixed_obligation_modes_required')
        require(type(obligation_runtime) is LateObligationRuntime, 'exact_obligation_runtime_required')
        scope = config.get('run_id')
        require(type(scope) is str and scope
                and packet_digest(scope) == obligation_runtime.execution_scope_sha256,
                'obligation_and_inference_execution_scope_differs')
        super().__init__(config, output, conversation=conversation)
        self.obligation_runtime = obligation_runtime
        self.disclosure = CheckpointDisclosure(config['obligation_mode'])
        self.obligation_views, self.obligation_boundaries = [], []
        self.obligation_contract_failed = False

    def _resolve(self, normalized, tools):
        before = self.checkpoint.revision
        super()._resolve(normalized, tools)
        revision = self.checkpoint.revision
        if revision == before:
            return
        try:
            require(revision == before + 1, 'one_capture_per_new_checkpoint_installation')
            boundary = boundary_descriptor(normalized, self.checkpoint.view(normalized),
                revision=revision, after_model_calls=len(self.calls), decision=self.checkpoint.events[-1])
            packet = self.obligation_runtime.capture(revision=revision,
                source_boundary_sha256=packet_digest(boundary))
            self.disclosure.prepare_packet(packet, revision, accepted=True)
            self.obligation_boundaries.append(boundary)
        except Exception:
            self.obligation_contract_failed = True
            raise
        finally:
            self._save()

    def _verify_pending_boundary(self, normalized, ordinary_working):
        if self.disclosure.pending is None:
            return
        try:
            captured = self.obligation_runtime.captures[-1]
            boundary = self.obligation_boundaries[-1]
            require(captured['checkpoint_revision'] == self.checkpoint.revision
                    and captured['source_boundary_sha256'] == packet_digest(boundary)
                    and boundary['normalized_history_sha256'] == digest(normalized)
                    and boundary['checkpoint_view_sha256'] == digest(ordinary_working),
                    'obligation_source_boundary_changed')
            require(captured['after_records'] == len(self.obligation_runtime.records)
                    and captured['records_sha256'] == packet_digest(self.obligation_runtime.records),
                    'obligation_record_boundary_changed')
            require(captured['packet'] == self.disclosure.pending
                    and self.obligation_runtime.store.capture() == self.disclosure.pending,
                    'obligation_evidence_changed_before_actor')
        except Exception:
            self.obligation_contract_failed = True
            raise

    def call(self, role, messages, tools):
        require(role == 'agent', 'external_call_must_be_agent')
        require(tools == CODE_TOOLS,
                'fixed_obligation_tool_capabilities_required')
        require(not self._stopped and not self.obligation_contract_failed
                and not self.obligation_runtime.failed, 'obligation_inference_already_stopped')
        require(self._config_digest() == self._fixed_config, 'fixed_rolling_config_changed')
        require(not any(c['status'] != 'ok' for c in self.calls), 'unknown_usage_blocks_continuation')
        normalized, _ = self.conversation.for_model(self.config['observation_page_characters'])
        require(normalized == messages, 'supplied_history_differs_from_full_archive')
        require(len(closed_turns(normalized)) == sum(c['role'] == 'agent' for c in self.calls),
                'one_archived_turn_per_agent_response_required')
        entry = view = None
        self.current_offer = False
        self.config['model']['cache_prompt'] = bool(self.calls)
        try:
            self._resolve(normalized, tools)
            offered = self._maybe_offer(normalized, tools)
            if offered is not None:
                self._summarize_separately(normalized, tools, offered)
            ordinary_working = self.checkpoint.view(normalized)
            self._verify_pending_boundary(normalized, ordinary_working)
            pending = deepcopy(self.disclosure.pending)
            working = self.disclosure.actor_view(ordinary_working)
            require(self.conversation.for_model(self.config['observation_page_characters'])[0] == normalized,
                    'obligation_cannot_mutate_normalized_archive')
            supplied, actual, visible = self._supplied(working)
            body = notice(pending, self.disclosure.mode) if pending else None
            call_id = f'call_{len(self.calls) + 1:03d}'
            view = dict(next_agent_call_id=call_id, checkpoint_revision=self.checkpoint.revision,
                normalized_history_sha256=digest(normalized), checkpoint_view_sha256=digest(ordinary_working),
                obligation_view_sha256=digest(working), supplied_messages_sha256=digest(supplied),
                capture_index=self.obligation_runtime.captures[-1]['index'] if pending else None,
                packet_sha256=pending['sha256'] if pending else None,
                obligation_prepared=pending is not None, obligation_included=body is not None,
                displayed_entities=body['displayed_entities'] if body else 0,
                displayed_field_rows=body['displayed_entities'] if body and self.disclosure.mode == 'entity_fields' else 0,
                notice_sha256=packet_digest(body) if body else None,
                model_attempted=False, terminal_usage_recorded=False, usage_unknown=False,
                raw_archive_modified=False, focus_request_modified=False)
            self.obligation_views.append(view)
            self.projections.append(dict(next_agent_call_id=call_id,
                original_history_sha256=digest(normalized), working_history_sha256=digest(working),
                tools_sha256=digest(tools), inline_offered=False, checkpoint_revision=self.checkpoint.revision,
                checkpoint_used=self.checkpoint.checkpoint is not None, archive_deleted=False, semantics_verified=False))
            before, before_admissions = len(self.calls), len(self.admissions)
            self.config['model']['cache_prompt'] = bool(self.calls)
            entry = dict(next_call_id=call_id, measured_state=actual, visible_state=visible,
                model_messages_sha256=digest(supplied), model_tools_sha256=digest(tools),
                model_attempted=False, cache_prompt=bool(self.calls), time_visibility='not_exposed')
            self.snapshots.append(entry)
            response = ToolChoiceResidualInference.call(self, 'agent', supplied, tools)
            require(digest(supplied) == view['supplied_messages_sha256'], 'count_send_obligation_view_mutated')
            self._verify_pending_boundary(normalized, ordinary_working)
            if before == 0:
                measured = json.loads((self.output / self.calls[0]['id'] / 'response.json').read_text())
                cold = cache_measurement('cold_1', measured, measured['input_tokens'])
                entry['first_input_measurement'] = cold
                require(cold['state_confirmed'], 'first_request_reused_prior_condition_cache')
            entry['status'] = 'returned'
            return response
        except Exception as error:
            self._stopped = True
            if entry is not None:
                entry.update(status='stopped', exception_type=type(error).__name__)
            raise
        finally:
            if entry is not None:
                entry['model_attempted'] = any(a.get('model_request_started') for a in self.admissions[before_admissions:])
                entry['terminal_usage_recorded'] = len(self.calls) != before
                entry['usage_unknown'] = entry['model_attempted'] and (
                    not entry['terminal_usage_recorded'] or self.calls[-1]['status'] != 'ok')
                view.update({k: entry[k] for k in ('model_attempted', 'terminal_usage_recorded', 'usage_unknown')})
                self.disclosure.model_submitted(attempted=entry['model_attempted'])
            self._save()

    def _save(self):
        super()._save()
        if hasattr(self, 'disclosure'):
            self.obligation_runtime.save()
            write_json(self.output / 'obligation_boundaries_private.json', self.obligation_boundaries)
            write_json(self.output / 'obligation_inference_views.json', self.obligation_views)

    def obligation_summary(self):
        runtime = self.obligation_runtime.summary()
        dispatched = [v for v in self.obligation_views if v['model_attempted']]
        exposed = [v for v in dispatched if v['obligation_included']]
        return dict(mode=self.disclosure.mode, live_worker_connected=True, runtime=runtime,
            version=VERSION, selection_rule=SELECTION_RULE, query_interface_exposed=False,
            public_snapshot_handle_exposed=False,
            prepared=self.disclosure.captures, submitted=self.disclosure.submitted,
            pending=self.disclosure.pending is not None,
            contract_failed=self.obligation_contract_failed or self.obligation_runtime.failed,
            counted_actor_views=len(self.obligation_views), dispatched_actor_views=len(dispatched),
            actual_obligation_exposures=len(exposed),
            entity_rows_exposed=sum(v['displayed_entities'] for v in exposed),
            field_rows_exposed=sum(v['displayed_field_rows'] for v in exposed),
            actual_exposed_packet_sha256=[v['packet_sha256'] for v in exposed],
            views_sha256=packet_digest(self.obligation_views),
            boundaries_sha256=packet_digest(self.obligation_boundaries),
            raw_archive_unchanged=True, focus_requests_unchanged=True,
            all_model_roles_and_obligation_input_share_budget=True,
            disclosure_activity_requires_actual_dispatch=True)
