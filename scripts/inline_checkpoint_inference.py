"""Budgeted ordinary inline-checkpoint adapter; does not launch an experiment.

Every generation is a normal agent call. Offer instructions, the extended tool
schema, metadata output, malformed replies and changed future actions use the
same call/token/time budget. No separate summary or judge call is made here.
"""
from copy import deepcopy
import json
import time

from api_error_comparison import task_snapshot
from budget_observation import notification
from inference_cache_control import cache_measurement
from inline_checkpoint_history import InlineCheckpoint
from protocol_stable_history import StableReferenceConversation
from receipt_reasoning_history import digest, require
from run_context_comparison import BudgetStop, write_json
from single_checkpoint_history import closed_turns
from tool_choice_local_llama import count_input, reasoning_budget, tool_choice
from tool_choice_residual import ToolChoiceResidualInference


class InlineCheckpointInference(ToolChoiceResidualInference):
    def __init__(self, config, output, *, conversation):
        require(type(conversation) is StableReferenceConversation,
                'source_normalized_conversation_required')
        require(config.get('checkpoint_policy') == 'inline_checkpoint',
                'explicit_inline_checkpoint_policy_required')
        require(config.get('read_views_enabled') is False, 'unchanged_eager_API_path_required')
        require(reasoning_budget(config['model']) == -1 and tool_choice(config['model']) == 'auto',
                'unchanged_auto_reasoning_required')
        super().__init__(config, output, 'residual')
        self.conversation = conversation
        self.checkpoint = InlineCheckpoint()
        self.api_requests = 0
        self.snapshots, self.controls, self.projections, self.input_counts = [], [], [], []
        self.current_offer = False
        self._stopped = False
        self._offered_call_id = None
        self._fixed_config = self._config_digest()

    def _config_digest(self):
        value = deepcopy(self.config)
        value['model'].pop('cache_prompt', None)
        return digest(value)

    def _state(self):
        return task_snapshot(self.config, self.calls, self.api_requests,
                             time.monotonic() - self.started)

    def _supplied(self, messages, state=None):
        state = self._state() if state is None else state
        supplied, visible = notification(messages, state, 'not_exposed')
        return supplied, state, visible

    def _count(self, purpose, messages, tools):
        elapsed = time.monotonic() - self.started
        if elapsed >= self.config['max_wall_seconds']:
            raise BudgetStop('wall_limit_before_inline_count')
        cfg = dict(self.config['model'])
        cfg.update(temperature=self.config['agent_temperature'],
                   seed=self.config['seed'] + len(self.calls),
                   num_predict=self.config['max_output_tokens'])
        entry = {'purpose': purpose, 'after_model_calls': len(self.calls),
            'messages_sha256': digest(messages), 'tools_sha256': digest(tools), 'status': 'counting'}
        self.input_counts.append(entry)
        try:
            result = count_input(cfg, messages, tools,
                timeout=min(60, self.config['max_wall_seconds'] - elapsed))
            entry.update(status='complete', **result)
            return result
        except Exception as error:
            entry.update(status='failed', exception_type=type(error).__name__)
            raise
        finally:
            write_json(self.output / 'inline_input_counts.json', self.input_counts)

    def _resolve(self, normalized, tools):
        control = self.checkpoint
        if not control.opportunity_used or control.decision is not None:
            return
        require(control.after is not None and normalized == control.after,
                'offered_turn_must_close_before_next_agent_request')
        state = self._state()
        # Both views use the SAME post-execution remaining budget. Actual
        # admission below recounts the selected request including its notice.
        ordinary, _, _ = self._supplied(control.views['ordinary'], state)
        compacted, _, _ = self._supplied(control.views['compacted'], state)
        a = self._count('ordinary_next_input', ordinary, tools)
        b = self._count('compacted_next_input', compacted, tools)
        decision = control.decide(a['input_tokens'], b['input_tokens'])
        self.controls.append({'status': 'checkpoint_decided', 'after_model_calls': len(self.calls),
                              **decision, 'semantics_verified': False})
        write_json(self.output / 'inline_checkpoint_private.json', {
            'proposal': control.proposal, 'checkpoint': control.split['checkpoint'],
            'transport_binding': control.split['binding'], 'decision': control.decision})

    def call(self, role, messages, tools):
        require(role == 'agent', 'external_call_must_be_agent')
        require(not self._stopped, 'inline_inference_already_stopped')
        require(self._config_digest() == self._fixed_config, 'fixed_inline_config_changed')
        require(not any(c['status'] != 'ok' for c in self.calls), 'unknown_usage_blocks_continuation')
        normalized, _ = self.conversation.for_model(self.config['observation_page_characters'])
        require(normalized == messages, 'supplied_history_differs_from_full_archive')
        require(len(closed_turns(normalized)) == len(self.calls),
                'one_archived_turn_per_agent_response_required')
        before, before_admissions = len(self.calls), len(self.admissions)
        entry = None
        self.current_offer = False
        self.config['model']['cache_prompt'] = bool(self.calls)
        try:
            self._resolve(normalized, tools)
            working = self.checkpoint.view(normalized)
            actual_tools = tools
            if not self.checkpoint.opportunity_used:
                full, _, _ = self._supplied(normalized)
                count = self._count('trigger', full, tools)
                offered = self.checkpoint.begin(normalized, tools, count['input_tokens'])
                self.controls.append({'status': 'inline_offered' if offered else 'below_trigger_or_recent_only',
                    'after_model_calls': len(self.calls), 'trigger_input_tokens': count['input_tokens'],
                    'source_archive_sha256': digest(normalized), 'semantics_verified': False})
                if offered is not None:
                    self.current_offer = True
                    working, actual_tools = offered['messages'], offered['tools']
                    self._offered_call_id = f'call_{len(self.calls) + 1:03d}'
                    write_json(self.output / 'inline_offer_private.json', offered)
            supplied, actual, visible = self._supplied(working)
            call_id = f'call_{len(self.calls) + 1:03d}'
            self.projections.append({'next_agent_call_id': call_id,
                'original_history_sha256': digest(normalized), 'working_history_sha256': digest(working),
                'tools_sha256': digest(actual_tools), 'inline_offered': self.current_offer,
                'checkpoint_used': bool(self.checkpoint.decision and self.checkpoint.decision['accepted']),
                'archive_deleted': False, 'semantics_verified': False})
            entry = {'next_call_id': call_id, 'measured_state': actual, 'visible_state': visible,
                'model_messages_sha256': digest(supplied), 'model_tools_sha256': digest(actual_tools),
                'model_attempted': False, 'cache_prompt': bool(self.calls), 'time_visibility': 'not_exposed'}
            self.snapshots.append(entry)
            response = ToolChoiceResidualInference.call(self, 'agent', supplied, actual_tools)
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
                entry['model_attempted'] = any(a.get('model_request_started')
                    for a in self.admissions[before_admissions:])
                entry['terminal_usage_recorded'] = len(self.calls) != before
                entry['usage_unknown'] = entry['model_attempted'] and (
                    not entry['terminal_usage_recorded'] or self.calls[-1]['status'] != 'ok')
            self._save()

    def close_turn(self, split):
        """Call after the received response and its actual outcomes are archived."""
        require(not self._stopped and self.calls and self.calls[-1]['status'] == 'ok',
                'known_returned_call_required_before_close')
        if not self.current_offer:
            require(split['status'] == 'not_offered_keep_original', 'unoffered_metadata_transformation')
            return
        require(self.calls[-1]['id'] == self._offered_call_id, 'offered_response_identity_changed')
        normalized, _ = self.conversation.for_model(self.config['observation_page_characters'])
        views = self.checkpoint.close(normalized, split)
        self.controls.append({'status': 'offered_turn_closed', 'after_model_calls': len(self.calls),
            'split_status': split['status'], 'ordinary_sha256': views['ordinary_sha256'],
            'compacted_sha256': views['compacted_sha256'],
            'transport_metadata_hidden': views['transport_metadata_hidden'],
            'semantics_verified': False})
        write_json(self.output / 'inline_closed_turn_private.json', {
            'split': split, 'view_hashes': {k: v for k, v in views.items() if k.endswith('_sha256')},
            'decision': self.checkpoint.decision})
        self._save()

    def _save(self):
        write_json(self.output / 'inline_controls.json', self.controls)
        write_json(self.output / 'inline_history_views.json', self.projections)
        write_json(self.output / 'budget_observations.json', self.snapshots)

    def checkpoint_summary(self):
        decision = self.checkpoint.decision
        return {'policy': 'inline_checkpoint', 'opportunity_used': self.checkpoint.opportunity_used,
            'offered_call_id': self._offered_call_id, 'offered_turn_closed': self.checkpoint.after is not None,
            'checkpoint_installed': bool(decision and decision['accepted']),
            'valid_checkpoint_pending_without_next_request': bool(
                self.checkpoint.views and self.checkpoint.views['compacted'] is not None and decision is None),
            'decision': deepcopy(decision), 'separate_summary_calls': 0, 'judge_calls': 0,
            'all_metadata_output_charged_as_agent': True, 'control_cost_included_in_work_wall': True,
            'archive_deleted': False, 'semantic_fidelity_verified': False,
            'task_quality_established': False, 'novel_method_claim': False}
