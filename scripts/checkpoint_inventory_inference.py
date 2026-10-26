"""One transient actor inventory after each accepted rolling checkpoint.

The ordinary checkpoint decision, raw conversation, focus request and shared
model budget remain unchanged. Both arms capture; only the display arm adds the
same immutable packet to the next actor's counted and dispatched messages.
"""
from copy import deepcopy
import hashlib
import json

from checkpoint_inventory_runtime import CheckpointInventoryRuntime
from checkpoint_runtime_inventory import CheckpointInventory, MODES, digest as packet_digest
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


class CheckpointInventoryInference(RollingCheckpointInference):
    def __init__(self, config, output, *, conversation, inventory_runtime):
        require(config.get('checkpoint_policy') == 'rolling_separate'
                and config.get('checkpoint_inventory_policy') in MODES
                and config.get('output_grounding_policy') == 'feedback'
                and config.get('projection_policy') == 'explicit_joined_fields',
                'fixed_inventory_comparison_and_shared_runtime_required')
        require(type(inventory_runtime) is CheckpointInventoryRuntime,
                'exact_inventory_runtime_required')
        scope = config.get('run_id')
        require(type(scope) is str and scope
                and hashlib.sha256(scope.encode()).hexdigest() == inventory_runtime.scope_sha256,
                'inventory_and_inference_execution_scope_differs')
        super().__init__(config, output, conversation=conversation)
        self.inventory_runtime = inventory_runtime
        self.inventory = CheckpointInventory(mode=config['checkpoint_inventory_policy'], execution_scope=scope)
        self.inventory_views, self.inventory_packets, self.inventory_boundaries = [], [], []
        self.inventory_contract_failed = False

    def _resolve(self, normalized, tools):
        before = self.checkpoint.revision
        super()._resolve(normalized, tools)
        revision = self.checkpoint.revision
        if revision == before:
            return
        require(revision == before + 1 and self.inventory.needs_snapshot(accepted=True, revision=revision),
                'one_inventory_per_new_checkpoint_installation')
        boundary = boundary_descriptor(normalized, self.checkpoint.view(normalized),
            revision=revision, after_model_calls=len(self.calls), decision=self.checkpoint.events[-1])
        try:
            captured = self.inventory_runtime.capture(revision=revision,
                source_boundary_sha256=packet_digest(boundary), deadline=self.started + self.config['max_wall_seconds'])
            packet = self.inventory.prepare(captured['inventory'], accepted=True, revision=revision,
                program_index=captured['program_index'], source_boundary_sha256=packet_digest(boundary))
            self.inventory_boundaries.append(boundary)
            self.inventory_packets.append(packet)
        except Exception:
            self.inventory_contract_failed = True
            raise
        finally:
            self._save()

    def call(self, role, messages, tools):
        require(role == 'agent', 'external_call_must_be_agent')
        require(not self._stopped and not self.inventory_contract_failed
                and not self.inventory_runtime.contract_failed, 'inventory_inference_already_stopped')
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
            revision = self.checkpoint.revision
            pending = deepcopy(self.inventory.pending)
            working = self.inventory.view(ordinary_working, revision=revision, role='agent')
            require(self.conversation.for_model(self.config['observation_page_characters'])[0] == normalized,
                    'inventory_cannot_mutate_normalized_archive')
            supplied, actual, visible = self._supplied(working)
            call_id = f'call_{len(self.calls) + 1:03d}'
            view = dict(next_agent_call_id=call_id, checkpoint_revision=revision,
                normalized_history_sha256=digest(normalized), checkpoint_view_sha256=digest(ordinary_working),
                inventory_view_sha256=digest(working), supplied_messages_sha256=digest(supplied),
                packet_sha256=pending['packet_sha256'] if pending else None,
                inventory_prepared=pending is not None,
                inventory_included=pending is not None and self.inventory.mode == 'checkpoint_inventory',
                model_attempted=False, terminal_usage_recorded=False, usage_unknown=False,
                raw_archive_modified=False, focus_request_modified=False)
            self.inventory_views.append(view)
            self.projections.append(dict(next_agent_call_id=call_id,
                original_history_sha256=digest(normalized), working_history_sha256=digest(working),
                tools_sha256=digest(tools), inline_offered=False, checkpoint_revision=revision,
                checkpoint_used=self.checkpoint.checkpoint is not None, archive_deleted=False, semantics_verified=False))
            before, before_admissions = len(self.calls), len(self.admissions)
            self.config['model']['cache_prompt'] = bool(self.calls)
            entry = dict(next_call_id=call_id, measured_state=actual, visible_state=visible,
                model_messages_sha256=digest(supplied), model_tools_sha256=digest(tools),
                model_attempted=False, cache_prompt=bool(self.calls), time_visibility='not_exposed')
            self.snapshots.append(entry)
            # Ordinary residual admission counts and sends this exact supplied list.
            response = ToolChoiceResidualInference.call(self, 'agent', supplied, tools)
            require(digest(supplied) == view['supplied_messages_sha256'], 'count_send_inventory_view_mutated')
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
                if entry['model_attempted'] and view['inventory_prepared']:
                    try:
                        self.inventory.submitted(revision=view['checkpoint_revision'], call_id=view['next_agent_call_id'])
                    except Exception:
                        self.inventory_contract_failed = self._stopped = True
                        raise
            self._save()

    def _save(self):
        super()._save()
        if hasattr(self, 'inventory'):
            self.inventory_runtime.save()
            write_json(self.output / 'checkpoint_inventory_events_private.json', self.inventory.events)
            write_json(self.output / 'checkpoint_inventory_packets_private.json', self.inventory_packets)
            write_json(self.output / 'checkpoint_inventory_boundaries_private.json', self.inventory_boundaries)
            write_json(self.output / 'checkpoint_inventory_inference_views.json', self.inventory_views)

    def inventory_summary(self):
        value = self.inventory.summary()
        captures = self.inventory_runtime.summary()
        dispatched = [v for v in self.inventory_views if v['model_attempted']]
        exposed = [v for v in dispatched if v['inventory_included']]
        return dict(value, live_worker_connected=True, capture=captures,
            contract_failed=self.inventory_contract_failed or self.inventory_runtime.contract_failed,
            counted_actor_views=len(self.inventory_views), dispatched_actor_views=len(dispatched),
            actual_inventory_exposures=len(exposed), actual_exposed_packet_sha256=[v['packet_sha256'] for v in exposed],
            views_sha256=packet_digest(self.inventory_views), packets_sha256=packet_digest(self.inventory_packets),
            boundaries_sha256=packet_digest(self.inventory_boundaries),
            raw_archive_unchanged=True, focus_requests_unchanged=True,
            all_model_roles_and_inventory_input_share_budget=True,
            disclosure_activity_requires_actual_dispatch=True)
