"""Shared-budget rolling inference for the exact receipt-disclosure live adapter.

Both generation roles share calls, admissions, tokens and the work clock. Native
counts and control time are recorded. This module does not launch an experiment.
The previously published one-checkpoint adapters and pure core stay unchanged.
"""
from copy import deepcopy
import json
import time

from api_error_comparison import task_snapshot
from budget_observation import notification
from checkpoint_attempt_usage import attempt_usage
from fixed_budget_local_llama import count_input as count_summary_input
from fixed_budget_residual import FixedBudgetResidualInference
from inference_cache_control import cache_measurement
from receipt_disclosure_live import ReceiptDisclosureLiveConversation
from receipt_reasoning_history import digest, require
from rolling_checkpoint_history import (MAX_OPPORTUNITIES, MIN_NEW_CLOSED_TURNS,
                                         RollingCheckpoint)
from run_context_comparison import BudgetStop, write_json
from single_checkpoint_history import closed_turns
from tool_choice_local_llama import count_input as count_agent_input, reasoning_budget, tool_choice
from tool_choice_residual import ToolChoiceResidualInference

POLICIES = ('rolling_separate',)


class AdmissionAwareRollingCheckpoint(RollingCheckpoint):
    """Cancel a separate opportunity before dispatch without inventing a reply."""
    def skip_unstarted_summary(self, archive, reason):
        self._check(archive)
        require(self.mode == 'separate' and self.pending is not None
                and self.pending['stage'] == 'offered'
                and archive == self.pending['before'], 'unstarted_summary_required')
        require(reason in ('insufficient_shared_call_budget', 'insufficient_shared_token_budget',
                           'summary_context_limit'), 'known_summary_screening_reason_required')
        self._bind(archive)
        self._last_closed_turns = len(closed_turns(archive))
        self.pending.update(stage='closed', close_status='not_dispatched')
        return self._finish(False, reason, None, None)


class ReceiptDisclosureRollingInference(ToolChoiceResidualInference):
    def __init__(self, config, output, *, conversation):
        require(type(conversation) is ReceiptDisclosureLiveConversation,
                'exact_receipt_disclosure_conversation_required')
        require(config.get('receipt_disclosure_policy') == conversation.receipt_policy
                and config.get('observation_page_characters') == conversation.page_limit,
                'receipt_policy_and_page_configuration_disagree')
        require(config.get('checkpoint_policy') in POLICIES, 'explicit_rolling_policy_required')
        require(config.get('rolling_checkpoint_max_opportunities') == MAX_OPPORTUNITIES
                and config.get('rolling_min_fresh_turns') == MIN_NEW_CLOSED_TURNS,
                'fixed_rolling_limits_required')
        require(config.get('read_views_enabled') is False, 'unchanged_eager_API_path_required')
        require(reasoning_budget(config['model']) == -1 and tool_choice(config['model']) == 'auto',
                'unchanged_auto_reasoning_required')
        super().__init__(config, output, 'residual')
        self.conversation = conversation
        self.checkpoint_policy = config['checkpoint_policy']
        self.mode = 'inline' if self.checkpoint_policy == 'rolling_inline' else 'separate'
        require(config.get('inline_checkpoint_requirement') == (
            'required_when_run_python' if self.mode == 'inline' else 'not_applicable'),
            'explicit_rolling_inline_requirement_required')
        self.checkpoint = AdmissionAwareRollingCheckpoint(self.mode)
        self.api_requests = 0
        self.snapshots, self.controls, self.projections, self.input_counts = [], [], [], []
        self.offers, self.closed = [], []
        self.receipt_views = []
        self.current_offer = False
        self._offered_call_id = None
        self._stopped = False
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

    def _count(self, role, purpose, messages, tools):
        elapsed = time.monotonic() - self.started
        if elapsed >= self.config['max_wall_seconds']:
            raise BudgetStop('wall_limit_before_rolling_count')
        cfg = dict(self.config['model'])
        cfg.update(temperature=self.config['draft_temperature'] if role == 'focus'
                   else self.config['agent_temperature'],
                   seed=self.config['seed'] + sum(c['role'] == role for c in self.calls),
                   num_predict=self.config['max_output_tokens'])
        entry = {'role': role, 'purpose': purpose, 'after_model_calls': len(self.calls),
            'messages_sha256': digest(messages), 'tools_sha256': digest(tools), 'status': 'counting'}
        self.input_counts.append(entry)
        counter = count_summary_input if role == 'focus' else count_agent_input
        try:
            result = counter(cfg, messages, tools,
                timeout=min(60, self.config['max_wall_seconds'] - elapsed))
            entry.update(status='complete', **result)
            return result
        except Exception as error:
            entry.update(status='failed', exception_type=type(error).__name__)
            raise
        finally:
            write_json(self.output / 'rolling_input_counts.json', self.input_counts)

    def _resolve(self, normalized, tools):
        pending = self.checkpoint.pending
        if pending is None:
            return
        require(pending['stage'] == 'closed' and pending['value'] is not None,
                'rolling_turn_must_close_before_next_request')
        self.checkpoint._check(normalized)
        require(len(normalized) == self.checkpoint._bound_length,
                'new_turn_before_rolling_resolution')
        state = self._state()
        a = self._count('agent', 'ordinary_next_input',
                        self._supplied(pending['views']['ordinary'], state)[0], tools)
        b = self._count('agent', 'compacted_next_input',
                        self._supplied(pending['views']['compacted'], state)[0], tools)
        decision = self.checkpoint.decide(a['input_tokens'], b['input_tokens'])
        self.controls.append({'status': 'checkpoint_decided', 'after_model_calls': len(self.calls),
                              **decision})

    def _maybe_offer(self, normalized, tools):
        if self.checkpoint.opportunities >= self.checkpoint.max_opportunities:
            return None
        working = self.checkpoint.view(normalized)
        count = self._count('agent', 'trigger', self._supplied(working)[0], tools)
        offered = self.checkpoint.begin(normalized, count['input_tokens'], tools)
        self.controls.append({'status': 'checkpoint_offered' if offered else 'below_trigger_or_not_eligible',
            'after_model_calls': len(self.calls), 'trigger_input_tokens': count['input_tokens'],
            'source_archive_sha256': digest(normalized), 'visible_history_sha256': digest(working),
            'opportunities': self.checkpoint.opportunities, 'semantics_verified': False})
        if offered is not None:
            self.offers.append({'after_model_calls': len(self.calls), 'offer': deepcopy(offered)})
            write_json(self.output / 'rolling_offers_private.json', self.offers)
        return offered

    def _summarize_separately(self, normalized, tools, offered):
        began = time.monotonic()
        before_calls, before_tokens, before_admissions = len(self.calls), self.tokens, len(self.admissions)
        event = {'status': 'separate_summary_started', 'opportunity_index': offered['opportunity_index'],
                 'after_model_calls': len(self.calls), 'model_attempted': False,
                 'summary_calls': 0, 'summary_known_tokens': 0, 'semantics_verified': False}
        self.controls.append(event)
        try:
            count = self._count('focus', 'separate_summary_input', offered['summary_messages'], [])
            reserve = count['input_tokens'] + offered['trigger_input_tokens'] + 2 * self.config['max_output_tokens']
            event.update(summary_input_count=count, screening_tokens_using_current_agent_input=reserve)
            reason = ('insufficient_shared_call_budget' if len(self.calls) + 2 > self.config['max_calls'] else
                      'insufficient_shared_token_budget' if self.tokens + reserve > self.config['max_total_tokens'] else
                      'summary_context_limit' if count['input_tokens'] + self.config['max_output_tokens'] > self.config['model']['num_ctx'] else None)
            if reason is not None:
                decision = self.checkpoint.skip_unstarted_summary(normalized, reason)
                event.update(status='separate_summary_not_dispatched', decision=decision)
                return
            message = FixedBudgetResidualInference.call(self, 'focus', offered['summary_messages'], [])
            views = self.checkpoint.close_separate(normalized, message,
                self.calls[-1]['finish_reason'], usage_known=self.calls[-1]['status'] == 'ok')
            self.closed.append({'mode': 'separate', 'call_id': self.calls[-1]['id'],
                'opportunity_index': offered['opportunity_index'], 'source_archive_sha256': digest(normalized),
                'ordinary_sha256': views['ordinary_sha256'], 'compacted_sha256': views['compacted_sha256']})
            write_json(self.output / 'rolling_closed_private.json', self.closed)
            event['status'] = 'separate_summary_closed'
            self._resolve(normalized, tools)
        except Exception as error:
            event.update(status='separate_summary_aborted', exception_type=type(error).__name__)
            raise
        finally:
            dispatched = sum(bool(a.get('model_request_started')) for a in self.admissions[before_admissions:])
            missing = max(0, dispatched - (len(self.calls) - before_calls))
            event.update(summary_calls=len(self.calls) - before_calls,
                summary_known_tokens=self.tokens - before_tokens, model_attempted=bool(dispatched),
                dispatched_without_terminal_usage=missing,
                unknown_usage_calls=missing + sum(c['status'] != 'ok' for c in self.calls[before_calls:]),
                control_wall_seconds=time.monotonic() - began)
            self._save()

    def call(self, role, messages, tools):
        require(role == 'agent', 'external_call_must_be_agent')
        require(not self._stopped, 'rolling_inference_already_stopped')
        require(self._config_digest() == self._fixed_config, 'fixed_rolling_config_changed')
        require(not any(c['status'] != 'ok' for c in self.calls), 'unknown_usage_blocks_continuation')
        normalized, _ = self.conversation.for_model(self.config['observation_page_characters'])
        require(normalized == messages, 'supplied_history_differs_from_receipt_display')
        receipt_snapshot = self.conversation.disclosure_snapshot()
        require(len(closed_turns(normalized)) == sum(c['role'] == 'agent' for c in self.calls),
                'one_archived_turn_per_agent_response_required')
        entry = None
        self.current_offer = False
        self.config['model']['cache_prompt'] = bool(self.calls)
        try:
            self._resolve(normalized, tools)
            offered = self._maybe_offer(normalized, tools)
            if offered is not None and self.mode == 'separate':
                self._summarize_separately(normalized, tools, offered)
            if offered is not None and self.mode == 'inline':
                working, actual_tools = offered['messages'], offered['tools']
                self.current_offer = True
            else:
                working, actual_tools = self.checkpoint.view(normalized), tools
            supplied, actual, visible = self._supplied(working)
            call_id = f'call_{len(self.calls) + 1:03d}'
            if self.current_offer:
                self._offered_call_id = call_id
            self.receipt_views.append({'next_agent_call_id': call_id,
                'receipt_snapshot_sha256': digest(receipt_snapshot),
                'normalized_history_sha256': digest(normalized),
                'raw_messages_sha256': receipt_snapshot['raw_messages_sha256'],
                'closed_turns': receipt_snapshot['closed_turns'],
                'disclosed_turns': receipt_snapshot['disclosed_turns']})
            self.projections.append({'next_agent_call_id': call_id,
                'original_history_sha256': digest(normalized), 'working_history_sha256': digest(working),
                'tools_sha256': digest(actual_tools), 'inline_offered': self.current_offer,
                'checkpoint_revision': self.checkpoint.revision,
                'checkpoint_used': self.checkpoint.checkpoint is not None,
                'archive_deleted': False, 'semantics_verified': False})
            before, before_admissions = len(self.calls), len(self.admissions)
            self.config['model']['cache_prompt'] = bool(self.calls)
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
        require(self.mode == 'inline' and not self._stopped and self.calls
                and self.calls[-1]['role'] == 'agent' and self.calls[-1]['status'] == 'ok',
                'known_inline_actor_required_before_close')
        if not self.current_offer:
            require(split['status'] == 'not_offered_keep_original', 'unoffered_metadata_transformation')
            return
        require(self.calls[-1]['id'] == self._offered_call_id, 'offered_response_identity_changed')
        normalized, _ = self.conversation.for_model(self.config['observation_page_characters'])
        index = self.checkpoint.pending['opportunity_index']
        views = self.checkpoint.close_inline(normalized, split, usage_known=True)
        self.closed.append({'mode': 'inline', 'call_id': self.calls[-1]['id'],
            'opportunity_index': index, 'source_archive_sha256': digest(normalized),
            'split': deepcopy(split), 'ordinary_sha256': views['ordinary_sha256'],
            'compacted_sha256': views['compacted_sha256']})
        self.controls.append({'status': 'inline_turn_closed', 'opportunity_index': index,
            'after_model_calls': len(self.calls), 'split_status': split['status'],
            'ordinary_sha256': views['ordinary_sha256'], 'compacted_sha256': views['compacted_sha256'],
            'semantics_verified': False})
        write_json(self.output / 'rolling_closed_private.json', self.closed)
        self._save()

    def _save(self):
        write_json(self.output / 'receipt_disclosure_inference_views.json', self.receipt_views)
        write_json(self.output / 'rolling_controls.json', self.controls)
        write_json(self.output / 'rolling_history_views.json', self.projections)
        write_json(self.output / 'budget_observations.json', self.snapshots)

    def checkpoint_summary(self):
        attempts = attempt_usage(self)
        pending = self.checkpoint.pending
        return {'policy': self.checkpoint_policy, 'opportunity_used': self.checkpoint.opportunities > 0,
            'opportunities': self.checkpoint.opportunities, 'max_opportunities': MAX_OPPORTUNITIES,
            'installations': self.checkpoint.revision, 'checkpoint_installed': self.checkpoint.revision > 0,
            'decisions': deepcopy(self.checkpoint.events),
            'pending_stage': pending['stage'] if pending else None,
            'valid_checkpoint_pending_without_next_request': bool(pending
                and pending['stage'] == 'closed' and pending.get('value') is not None),
            'separate_summary_calls': sum(c['role'] == 'focus' for c in attempts),
            'judge_calls': 0, 'all_summary_and_agent_costs_in_shared_budget': True,
            'schema_checkpoint_required': self.mode == 'inline', 'tool_choice_forced': False,
            'control_cost_included_in_work_wall': True, 'archive_deleted': False,
            'semantic_fidelity_verified': False, 'task_quality_established': False,
            'novel_method_claim': False}
