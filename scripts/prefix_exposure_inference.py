"""Paid-prefix scheduler prototype over the existing strong rolling control.

All three modes take identical shadow measurements. The incomplete projection
is counted only after a known actor terminal and never sent for generation.
An added count failure keeps that paid response but prevents its action.
"""
from copy import deepcopy
import time

import rolling_checkpoint_inference as rolling
from checkpoint_prefix_exposure import (MODES, PrefixExposureCheckpoint, PrefixExposureLedger,
                                       eligible_prefix_views, trigger_decision)
from receipt_reasoning_history import digest, require
from run_context_comparison import BudgetStop, write_json
from single_checkpoint_history import closed_turns


class AdmissionAwareExposureCheckpoint(PrefixExposureCheckpoint, rolling.AdmissionAwareRollingCheckpoint):
    pass


class PrefixExposureInference(rolling.RollingCheckpointInference):
    def __init__(self, config, output, *, conversation):
        mode = config.get('prefix_exposure_mode')
        require(config.get('checkpoint_policy') == 'rolling_separate' and mode in MODES,
                'fixed_separate_prefix_exposure_mode_required')
        super().__init__(config, output, conversation=conversation)
        self.checkpoint = AdmissionAwareExposureCheckpoint(mode)
        self.exposure = PrefixExposureLedger(mode)
        self.exposure_decisions = []
        self.exposure_counts = []
        self.exposure_contract_failed = False

    def _maybe_offer(self, normalized, tools):
        require(not self.exposure.blocked, 'exposure_continuation_blocked')
        if self.checkpoint.opportunities >= self.checkpoint.max_opportunities:
            return None
        views = eligible_prefix_views(self.checkpoint, normalized)
        count = self._count('agent', 'trigger', self._supplied(views['working'])[0], tools)
        decision = trigger_decision(mode=self.exposure.mode, opportunities=self.checkpoint.opportunities,
            fresh_turns=len(closed_turns(normalized))-self.checkpoint._last_closed_turns,
            eligible_raw=views['eligible_raw_messages'] > 0, measured_input_tokens=count['input_tokens'],
            accumulated_exposure=self.exposure.accumulated_exposure,
            previous_focus_cost=self.exposure.previous_focus_cost)
        decision.update(after_model_calls=len(self.calls), source_archive_sha256=digest(normalized),
                        exposure_events_sha256=digest(self.exposure.events))
        self.exposure_decisions.append(decision)
        offered = self.checkpoint.begin(normalized, count['input_tokens'], tools,
                                        repeat_ready=decision['offer'])
        require((offered is not None) == decision['offer'], 'checkpoint_trigger_disagreement')
        self.controls.append({'status': 'checkpoint_offered' if offered else 'below_trigger_or_not_eligible',
            'after_model_calls': len(self.calls), 'trigger_input_tokens': count['input_tokens'],
            'source_archive_sha256': digest(normalized),
            'visible_history_sha256': views['working_history_sha256'],
            'opportunities': self.checkpoint.opportunities, 'semantics_verified': False})
        if offered is not None:
            self.offers.append({'after_model_calls': len(self.calls), 'offer': deepcopy(offered)})
            write_json(self.output / 'rolling_offers_private.json', self.offers)
        return offered

    def _summarize_separately(self, normalized, tools, offered):
        before_calls, before_admissions = len(self.calls), len(self.admissions)
        try:
            return super()._summarize_separately(normalized, tools, offered)
        finally:
            new = self.calls[before_calls:]
            admitted = self.admissions[before_admissions:]
            sent = [a for a in admitted if a.get('model_request_started')]
            require(len(new) <= 1 and len(sent) <= 1, 'one_focus_attempt_per_opportunity')
            if new:
                call = new[0]
                require(call['role'] == 'focus' and len(sent) == 1,
                        'focus_usage_dispatch_binding_required')
                self.exposure.record_focus(call_id=call['id'], model_attempted=True,
                    usage_known=call['status'] == 'ok', input_tokens=call.get('input_tokens'),
                    output_tokens=call.get('output_tokens'))
            else:
                self.exposure.record_focus(call_id=f'call_{before_calls+1:03d}',
                    model_attempted=bool(sent), usage_known=False)
            self._save()

    def _count_without_raw(self, messages, tools, call):
        elapsed = time.monotonic()-self.started
        if elapsed >= self.config['max_wall_seconds']:
            raise BudgetStop('wall_limit_before_prefix_exposure_count')
        cfg = dict(self.config['model'])
        cfg.update(temperature=self.config['agent_temperature'],
                   seed=self.config['seed']+sum(c['role'] == 'agent' for c in self.calls)-1,
                   num_predict=call['output_cap'])
        entry = dict(call_id=call['id'], status='counting', count_only=True,
                     messages_sha256=digest(messages), tools_sha256=digest(tools),
                     model_config_sha256=digest(cfg), model_generation_allowed=False)
        self.exposure_counts.append(entry)
        began = time.monotonic()
        try:
            result = rolling.count_agent_input(cfg, messages, tools,
                timeout=min(60, self.config['max_wall_seconds']-elapsed))
            entry.update(status='complete', **result)
            if time.monotonic()-self.started >= self.config['max_wall_seconds']:
                raise BudgetStop('wall_limit_during_prefix_exposure_count')
            return result['input_tokens']
        except Exception as error:
            entry.update(status='failed', exception_type=type(error).__name__)
            raise
        finally:
            entry['control_wall_seconds'] = time.monotonic()-began
            self._save()

    def call(self, role, messages, tools):
        before_calls, before_admissions = len(self.calls), len(self.admissions)
        recorded = False
        try:
            response = super().call(role, messages, tools)
            call = self.calls[-1]
            require(call['role'] == 'agent' and call['status'] == 'ok'
                    and call['input_tokens'] == call['predicted_input_tokens'],
                    'known_actor_terminal_and_native_count_required')
            snapshot = self.snapshots[-1]
            require(snapshot['next_call_id'] == call['id'] and snapshot['model_attempted']
                    and snapshot['terminal_usage_recorded'] and not snapshot['usage_unknown'],
                    'actor_snapshot_usage_binding_required')
            normalized, _ = self.conversation.for_model(self.config['observation_page_characters'])
            require(normalized == messages, 'archive_changed_before_actor_action')
            views = eligible_prefix_views(self.checkpoint, normalized)
            supplied = self._supplied(views['working'], snapshot['measured_state'])[0]
            without = self._supplied(views['without_raw'], snapshot['measured_state'])[0]
            require(digest(supplied) == snapshot['model_messages_sha256']
                    and digest(tools) == snapshot['model_tools_sha256'],
                    'exposure_must_bind_actual_actor_request')
            bindings = {k: v for k, v in views.items() if k not in ('working', 'without_raw')}
            bindings.update(actual_supplied_sha256=digest(supplied),
                            count_only_supplied_sha256=digest(without),
                            budget_state_sha256=digest(snapshot['measured_state']))
            count = None
            if self.exposure.previous_focus_cost is not None:
                count = (self._count_without_raw(without, tools, call)
                         if views['eligible_raw_messages'] else call['input_tokens'])
                bindings['native_count_performed'] = bool(views['eligible_raw_messages'])
            else:
                bindings['native_count_performed'] = False
            self.exposure.record_actor(call_id=call['id'], model_attempted=True, usage_known=True,
                input_tokens=call['input_tokens'], without_raw_input_tokens=count, bindings=bindings)
            recorded = True
            return response
        except Exception as error:
            self._stopped = True
            new_actors = [c for c in self.calls[before_calls:] if c['role'] == 'agent']
            sent = [a for a in self.admissions[before_admissions:]
                    if a['role'] == 'agent' and a.get('model_request_started')]
            if not recorded and not self.exposure.blocked and sent and (
                    not new_actors or new_actors[-1]['status'] != 'ok'):
                self.exposure.record_actor(call_id=sent[-1]['next_call_id'],
                                           model_attempted=True, usage_known=False)
            # A paid known response followed by a failed count remains in the raw
            # usage files; its action is not returned to the worker for execution.
            if not recorded and not self.exposure.blocked and new_actors and new_actors[-1]['status'] == 'ok':
                call = new_actors[-1]
                self.exposure.record_actor_measurement_failure(call_id=call['id'],
                    input_tokens=call['input_tokens'], reason=type(error).__name__)
                self.exposure_contract_failed = not isinstance(error, BudgetStop)
            elif not isinstance(error, BudgetStop) and not self.exposure.blocked:
                self.exposure_contract_failed = True
                self.exposure.fail(type(error).__name__)
            raise
        finally:
            self._save()

    def _save(self):
        super()._save()
        if hasattr(self, 'exposure'):
            write_json(self.output / 'prefix_exposure_events.json', self.exposure.events)
            write_json(self.output / 'prefix_exposure_decisions.json', self.exposure_decisions)
            write_json(self.output / 'prefix_exposure_counts.json', self.exposure_counts)

    def exposure_summary(self):
        attempts = rolling.attempt_usage(self)
        dispatched_decisions = [d for d in self.exposure_decisions
            if d['after_model_calls'] < len(attempts)
            and attempts[d['after_model_calls']]['role'] == ('focus' if d['offer'] else 'agent')]
        return {**self.exposure.summary(), 'contract_failed': self.exposure_contract_failed,
                'accounting_complete': not self.exposure_contract_failed and not self.exposure.blocked
                    and all(c['status'] == 'complete' for c in self.exposure_counts),
                'decision_count': len(self.exposure_decisions),
                'decisions_sha256': digest(self.exposure_decisions),
                'decision_differences_from_rolling_separate': sum(
                    d['offer'] != d['ordinary_would_offer'] for d in self.exposure_decisions),
                'decision_differences_from_fixed_interval': sum(
                    d['offer'] != d['interval_would_offer'] for d in self.exposure_decisions),
                'actual_decision_differences_from_rolling_separate': sum(
                    d['offer'] != d['ordinary_would_offer'] for d in dispatched_decisions),
                'actual_decision_differences_from_fixed_interval': sum(
                    d['offer'] != d['interval_would_offer'] for d in dispatched_decisions),
                'extra_native_counts': len(self.exposure_counts),
                'count_only_generation_calls': 0, 'all_count_time_in_shared_wall': True}
