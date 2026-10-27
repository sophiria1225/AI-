"""P139 max-two checkpoint representation adapter over shared residual admission.

The old rolling constructor hard-codes three opportunities, so initialization
is explicit here with the honest max-two contract. Shared counting, focus
transport, budget admission, archive and cleanup semantics remain inherited.
The P138 actor wrapper is copied only because its prefix-view helper is bound
to the old single-note module; no globals or frozen sources are modified.
"""
from copy import deepcopy

import rolling_checkpoint_inference as rolling
from prefix_exposure_inference import PrefixExposureInference
from checkpoint_representation_p139 import (MODES, MAX_OPPORTUNITIES, VERSION,
    RepresentationCheckpoint, RepresentationExposureLedger, eligible_prefix_views,
    trigger_decision)
from receipt_reasoning_history import digest, require
from run_context_comparison import BudgetStop, write_json
from single_checkpoint_history import closed_turns


class CheckpointRepresentationInference(PrefixExposureInference):
    def __init__(self, config, output, *, conversation):
        mode = config.get('checkpoint_representation_mode')
        require(mode in MODES and config.get('checkpoint_policy') == 'rolling_separate',
                'fixed_P139_separate_mode_required')
        timing, representation = mode.split('_', 1)
        require(config.get('checkpoint_timing') == timing and
                config.get('checkpoint_representation') == representation,
                'P139_mode_factor_binding_required')
        require(type(conversation) is rolling.StableReferenceConversation,
                'source_normalized_conversation_required')
        require(type(config.get('rolling_checkpoint_max_opportunities')) is int and
                config['rolling_checkpoint_max_opportunities'] == MAX_OPPORTUNITIES == 2 and
                type(config.get('rolling_min_fresh_turns')) is int and
                config['rolling_min_fresh_turns'] == 3, 'fixed_P139_two_opportunities_required')
        require(config.get('read_views_enabled') is False and
                config.get('inline_checkpoint_requirement') == 'not_applicable',
                'unchanged_separate_eager_API_path_required')
        require(rolling.reasoning_budget(config['model']) == -1 and
                rolling.tool_choice(config['model']) == 'auto', 'unchanged_auto_reasoning_required')
        rolling.ToolChoiceResidualInference.__init__(self, config, output, 'residual')
        self.conversation = conversation
        self.checkpoint_policy, self.mode = 'rolling_separate', 'separate'
        self.representation_mode = mode
        self.checkpoint = RepresentationCheckpoint(mode)
        self.api_requests = 0
        self.snapshots, self.controls, self.projections, self.input_counts = [], [], [], []
        self.offers, self.closed = [], []
        self.current_offer, self._offered_call_id, self._stopped = False, None, False
        self._fixed_config = self._config_digest()
        self.exposure = RepresentationExposureLedger(mode)
        self.exposure_decisions, self.exposure_counts, self.representation_views = [], [], []
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

    def call(self, role, messages, tools):
        before_calls, before_admissions = len(self.calls), len(self.admissions)
        before_snapshots = len(self.snapshots)
        recorded = False
        try:
            response = rolling.RollingCheckpointInference.call(self, role, messages, tools)
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
            self._record_representation_view(before_snapshots)
            self._save()

    def _record_representation_view(self, before_snapshots):
        rows = self.snapshots[before_snapshots:]
        require(len(rows) <= 1, 'one_actor_view_per_external_call')
        for snapshot in rows:
            projection = self.projections[-1]
            require(projection['next_agent_call_id'] == snapshot['next_call_id'],
                    'representation_projection_snapshot_binding_required')
            self.representation_views.append(dict(
                next_call_id=snapshot['next_call_id'],
                checkpoint_revision=projection['checkpoint_revision'],
                fragment_count=self.checkpoint.fragment_count,
                summary_notes_sha256=digest(self.checkpoint.summary_notes),
                delta_view=self.checkpoint.delta_applied,
                model_messages_sha256=snapshot['model_messages_sha256'],
                model_tools_sha256=snapshot['model_tools_sha256'],
                model_attempted=snapshot['model_attempted'],
                terminal_usage_recorded=snapshot['terminal_usage_recorded'],
                usage_unknown=snapshot['usage_unknown']))

    def _save(self):
        super()._save()
        if hasattr(self, 'representation_views'):
            write_json(self.output / 'checkpoint_representation_views.json', self.representation_views)

    def checkpoint_summary(self):
        attempts = rolling.attempt_usage(self)
        pending = self.checkpoint.pending
        return dict(policy=self.checkpoint_policy, opportunity_used=self.checkpoint.opportunities > 0,
            opportunities=self.checkpoint.opportunities, max_opportunities=self.checkpoint.max_opportunities,
            installations=self.checkpoint.revision, checkpoint_installed=self.checkpoint.revision > 0,
            decisions=deepcopy(self.checkpoint.events), pending_stage=pending['stage'] if pending else None,
            valid_checkpoint_pending_without_next_request=bool(pending and pending['stage'] == 'closed'
                and pending.get('value') is not None),
            separate_summary_calls=sum(c['role'] == 'focus' for c in attempts), judge_calls=0,
            all_summary_and_agent_costs_in_shared_budget=True, schema_checkpoint_required=False,
            tool_choice_forced=False, control_cost_included_in_work_wall=True, archive_deleted=False,
            semantic_fidelity_verified=False, task_quality_established=False, novel_method_claim=False)

    def exposure_summary(self):
        attempts = rolling.attempt_usage(self)
        dispatched = [d for d in self.exposure_decisions if d['after_model_calls'] < len(attempts)
            and attempts[d['after_model_calls']]['role'] == ('focus' if d['offer'] else 'agent')]
        result = dict(self.exposure.summary(), contract_failed=self.exposure_contract_failed,
            accounting_complete=not self.exposure_contract_failed and not self.exposure.blocked
                and all(c['status'] == 'complete' for c in self.exposure_counts),
            decision_count=len(self.exposure_decisions), decisions_sha256=digest(self.exposure_decisions),
            extra_native_counts=len(self.exposure_counts), count_only_generation_calls=0,
            all_count_time_in_shared_wall=True)
        for timing in ('threshold', 'exposure'):
            key = timing + '_would_offer'
            result['decision_differences_from_' + timing] = sum(d['offer'] != d[key] for d in self.exposure_decisions)
            result['actual_decision_differences_from_' + timing] = sum(d['offer'] != d[key] for d in dispatched)
        return result

    def representation_summary(self):
        exposure = self.exposure_summary()
        shown = [v for v in self.representation_views if v['delta_view'] and v['model_attempted']]
        return dict(version=VERSION, mode=self.representation_mode,
            timing=self.config['checkpoint_timing'], representation=self.config['checkpoint_representation'],
            max_opportunities=self.checkpoint.max_opportunities,
            fragment_count=self.checkpoint.fragment_count,
            delta_installations=sum(e['accepted'] and e.get('delta_applied', False) for e in self.checkpoint.events),
            actual_delta_actor_calls=len(shown),
            actual_delta_known_actor_calls=sum(v['terminal_usage_recorded'] and not v['usage_unknown'] for v in shown),
            actual_delta_unknown_actor_calls=sum(v['usage_unknown'] for v in shown),
            actor_view_count=len(self.representation_views),
            actor_views_sha256=digest(self.representation_views),
            contract_failed=exposure['contract_failed'], accounting_complete=exposure['accounting_complete'],
            first_summary_contract_unchanged=True, initial_actor_interface_unchanged=True,
            full_actor_native_count_required=True, archive_deleted=False,
            semantic_preservation_established=False, novel_method_claim=False)
