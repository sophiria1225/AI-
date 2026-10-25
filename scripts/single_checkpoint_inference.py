"""Shared-cost ordinary one-checkpoint comparator; no experiment is launched.

The existing agent and text-only transports operate on one calls/admissions
ledger, clock and token budget. Frozen historical adapters are left unchanged.
"""
import json
import time

from api_error_comparison import task_snapshot
from budget_observation import notification
from fixed_budget_local_llama import count_input as count_summary_input
from fixed_budget_residual import FixedBudgetResidualInference
from inference_cache_control import cache_measurement
from protocol_stable_history import StableReferenceConversation
from receipt_reasoning_history import digest, require
from run_context_comparison import BudgetStop, write_json
from single_checkpoint_history import SingleCheckpoint, closed_turns, parse_checkpoint, project
from tool_choice_local_llama import count_input as count_agent_input, reasoning_budget, tool_choice
from tool_choice_residual import ToolChoiceResidualInference

POLICIES = ('full', 'single_checkpoint')


class SingleCheckpointInference(ToolChoiceResidualInference):
    def __init__(self, config, output, *, conversation):
        require(type(conversation) is StableReferenceConversation, 'source_normalized_conversation_required')
        require(config.get('checkpoint_policy') in POLICIES, 'explicit_checkpoint_policy_required')
        require(config.get('read_views_enabled') is False, 'unchanged_eager_API_path_required')
        require(reasoning_budget(config['model']) == -1 and tool_choice(config['model']) == 'auto',
                'unchanged_auto_reasoning_required')
        super().__init__(config, output, 'residual')
        self.conversation = conversation
        self.checkpoint_policy = config['checkpoint_policy']
        self.checkpoint = SingleCheckpoint()
        self.api_requests = 0
        self.snapshots = []
        self.controls = []
        self.projections = []
        self.input_counts = []
        self._stopped = False
        self._fixed_config = self._config_digest()

    def _config_digest(self):
        value = {**self.config, 'model': dict(self.config['model'])}
        value['model'].pop('cache_prompt', None)
        return digest(value)

    def _count(self, role, messages, tools):
        elapsed = time.monotonic() - self.started
        if elapsed >= self.config['max_wall_seconds']:
            raise BudgetStop('wall_limit_before_checkpoint_count')
        cfg = dict(self.config['model'])
        cfg.update(temperature=self.config['draft_temperature'] if role == 'focus'
                   else self.config['agent_temperature'],
                   seed=self.config['seed'] + sum(c['role'] == role for c in self.calls),
                   num_predict=self.config['max_output_tokens'])
        counter = count_summary_input if role == 'focus' else count_agent_input
        entry = {'role': role, 'after_model_calls': len(self.calls),
                 'messages_sha256': digest(messages), 'tools_sha256': digest(tools), 'status': 'counting'}
        self.input_counts.append(entry)
        try:
            result = counter(cfg, messages, tools, timeout=min(60, self.config['max_wall_seconds'] - elapsed))
            entry.update(status='complete', **result)
            return result
        except Exception as error:
            entry.update(status='failed', exception_type=type(error).__name__)
            raise
        finally:
            write_json(self.output / 'checkpoint_input_counts.json', self.input_counts)

    def _supplied(self, messages):
        state = task_snapshot(self.config, self.calls, self.api_requests, time.monotonic() - self.started)
        supplied, visible = notification(messages, state, 'not_exposed')
        return supplied, state, visible

    def _maybe_checkpoint(self, normalized, tools):
        if self.checkpoint.opportunity_used:
            return
        supplied, _, _ = self._supplied(normalized)
        count = self._count('agent', supplied, tools)
        proposal = self.checkpoint.begin(normalized, count['input_tokens'])
        if proposal is None:
            self.controls.append({'status': 'below_trigger_or_recent_only',
                'after_model_calls': len(self.calls), 'count': count})
            return
        event = {k: v for k, v in proposal.items() if k != 'summary_messages'}
        event.update(status='started', after_model_calls=len(self.calls),
                     trigger_input_tokens=count['input_tokens'], model_attempted=False,
                     summary_calls=0, summary_known_tokens=0, semantics_verified=False)
        self.controls.append(event)
        if self.checkpoint_policy == 'full':
            event['status'] = 'full_control_retains_archive'
            return
        started = time.monotonic()
        before_calls, before_tokens, before_admissions = len(self.calls), self.tokens, len(self.admissions)
        try:
            summary_count = self._count('focus', proposal['summary_messages'], [])
            event['summary_input_count'] = summary_count
            # Screen using the CURRENT ordinary input and two output caps. The
            # budget notice changes after summarization; the actual next request
            # is counted and admitted again. This does not guarantee its full
            # configured output cap, time to execute it, or task quality.
            reserve = (summary_count['input_tokens'] + count['input_tokens'] +
                       2 * self.config['max_output_tokens'])
            event['screening_tokens_using_current_agent_input'] = reserve
            if len(self.calls) + 2 > self.config['max_calls']:
                event['status'] = 'insufficient_shared_call_budget'
                return
            if self.tokens + reserve > self.config['max_total_tokens']:
                event['status'] = 'insufficient_shared_token_budget'
                return
            if summary_count['input_tokens'] + self.config['max_output_tokens'] > self.config['model']['num_ctx']:
                event['status'] = 'summary_context_limit'
                return
            # Both inherited methods append to this SAME self.calls ledger and
            # use self.started, self.tokens, and self.admissions. No second budget.
            message = FixedBudgetResidualInference.call(self, 'focus', proposal['summary_messages'], [])
            try:
                checkpoint = parse_checkpoint(message, self.calls[-1]['finish_reason'])
            except (ValueError, TypeError, RecursionError) as error:
                event.update(status='invalid_summary_keep_original', validation_error=type(error).__name__)
                return
            proposed = project(normalized, proposal, checkpoint)
            ordinary, _, _ = self._supplied(normalized)
            compacted, _, _ = self._supplied(proposed)
            ordinary_count = self._count('agent', ordinary, tools)
            compacted_count = self._count('agent', compacted, tools)
            event.update(ordinary_next_input_tokens=ordinary_count['input_tokens'],
                         checkpoint_next_input_tokens=compacted_count['input_tokens'])
            if compacted_count['input_tokens'] >= ordinary_count['input_tokens']:
                event['status'] = 'not_shorter_keep_original'
                return
            self.checkpoint.install(normalized, proposal, checkpoint)
            write_json(self.output / 'checkpoint_private.json', {
                'proposal': self.checkpoint.proposal, 'checkpoint': checkpoint})
            event.update(status='checkpoint_installed', checkpoint_sha256=digest(checkpoint))
        except Exception as error:
            event.update(status='aborted', exception_type=type(error).__name__)
            raise
        finally:
            dispatched = sum(bool(a.get('model_request_started'))
                             for a in self.admissions[before_admissions:])
            missing = max(0, dispatched - (len(self.calls) - before_calls))
            event.update(summary_calls=len(self.calls) - before_calls,
                         summary_known_tokens=self.tokens - before_tokens,
                         model_attempted=bool(dispatched),
                         dispatched_without_terminal_usage=missing,
                         unknown_usage_calls=missing + sum(c['status'] != 'ok'
                             for c in self.calls[before_calls:]),
                         control_wall_seconds=time.monotonic() - started)
            write_json(self.output / 'checkpoint_controls.json', self.controls)

    def call(self, role, messages, tools):
        require(role == 'agent', 'external_call_must_be_agent')
        require(not self._stopped, 'checkpoint_inference_already_stopped')
        require(self._config_digest() == self._fixed_config, 'fixed_checkpoint_config_changed')
        require(not any(c['status'] != 'ok' for c in self.calls), 'unknown_usage_blocks_continuation')
        normalized, _ = self.conversation.for_model(self.config['observation_page_characters'])
        require(normalized == messages, 'supplied_history_differs_from_full_archive')
        require(len(closed_turns(normalized)) == sum(c['role'] == 'agent' for c in self.calls),
                'one_archived_turn_per_agent_response_required')
        entry = None
        before, before_admissions = len(self.calls), len(self.admissions)
        self.config['model']['cache_prompt'] = bool(self.calls)
        try:
            self._maybe_checkpoint(normalized, tools)
            working = self.checkpoint.view(normalized)
            supplied, actual, visible = self._supplied(working)
            call_id = f'call_{len(self.calls) + 1:03d}'
            self.projections.append({'next_agent_call_id': call_id,
                'original_history_sha256': digest(normalized),
                'working_history_sha256': digest(working),
                'checkpoint_used': self.checkpoint.proposal is not None,
                'archive_deleted': False, 'semantics_verified': False})
            before, before_admissions = len(self.calls), len(self.admissions)
            self.config['model']['cache_prompt'] = bool(self.calls)
            entry = {'next_call_id': call_id, 'measured_state': actual, 'visible_state': visible,
                     'model_messages_sha256': digest(supplied), 'model_attempted': False,
                     'cache_prompt': bool(self.calls), 'time_visibility': 'not_exposed'}
            self.snapshots.append(entry)
            response = ToolChoiceResidualInference.call(self, 'agent', supplied, tools)
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
            write_json(self.output / 'checkpoint_controls.json', self.controls)
            write_json(self.output / 'checkpoint_history_views.json', self.projections)
            write_json(self.output / 'budget_observations.json', self.snapshots)

    def checkpoint_summary(self):
        roles = {}
        for role in ('agent', 'focus'):
            rows = [c for c in self.calls if c['role'] == role]
            known = [c for c in rows if c['status'] == 'ok']
            roles[role] = {'calls': len(rows), 'unknown_usage': len(rows) - len(known),
                          'input_tokens': sum(c['input_tokens'] for c in known),
                          'output_tokens': sum(c['output_tokens'] for c in known)}
        return {'policy': self.checkpoint_policy, 'terminal_usage_by_role': roles,
                'opportunity_used': self.checkpoint.opportunity_used,
                'checkpoint_installed': self.checkpoint.proposal is not None,
                'control_cost_included_in_work_wall': True, 'archive_deleted': False,
                'semantic_fidelity_verified': False, 'task_quality_established': False,
                'novel_method_claim': False}
