"""P141 adapter: honest timing modes sharing the fixed object-delta contract.

P139's constructor and offer hook bind its four-mode controller, so those small
sections are explicit here. All actor/focus transport, counting, admission,
unknown stopping, representation recording and whole-job accounting are shared.
There is no global replacement and no old max-three configuration disguise.
"""
from copy import deepcopy

import rolling_checkpoint_inference as rolling
from checkpoint_representation_inference_p139 import CheckpointRepresentationInference
from checkpoint_object_timing_p141 import (
    MODES, VERSION, MAX_OPPORTUNITIES, DeltaEnvelopeCheckpoint,
    DeltaEnvelopeExposureLedger, base_mode_for, timing_for, representation_for,
    prompt_policy_for, eligible_prefix_views, trigger_decision,
    OBJECT_DELTA_PROMPT_SHA256)
from receipt_reasoning_history import digest, require
from run_context_comparison import write_json
from single_checkpoint_history import closed_turns


class CheckpointDeltaEnvelopeInference(CheckpointRepresentationInference):
    def __init__(self, config, output, *, conversation):
        mode = config.get('checkpoint_representation_mode')
        require(mode in MODES and config.get('object_timing_mode') == mode
                and config.get('checkpoint_policy') == 'rolling_separate',
                'fixed_P141_separate_mode_required')
        require(config.get('checkpoint_timing') == timing_for(mode) and
                config.get('checkpoint_representation') == representation_for(mode),
                'P141_mode_factor_binding_required')
        require(type(conversation) is rolling.StableReferenceConversation,
                'source_normalized_conversation_required')
        require(type(config.get('rolling_checkpoint_max_opportunities')) is int and
                config['rolling_checkpoint_max_opportunities'] == MAX_OPPORTUNITIES == 2 and
                type(config.get('rolling_min_fresh_turns')) is int and
                config['rolling_min_fresh_turns'] == 3, 'fixed_P141_two_opportunities_required')
        require(type(config.get('max_output_tokens')) is int and config['max_output_tokens'] == 4096,
                'unchanged_P141_summary_output_cap_required')
        require(config.get('read_views_enabled') is False and
                config.get('inline_checkpoint_requirement') == 'not_applicable',
                'unchanged_separate_eager_API_path_required')
        require(rolling.reasoning_budget(config['model']) == -1 and
                rolling.tool_choice(config['model']) == 'auto', 'unchanged_auto_reasoning_required')
        rolling.ToolChoiceResidualInference.__init__(self, config, output, 'residual')
        self.conversation = conversation
        self.checkpoint_policy, self.mode = 'rolling_separate', 'separate'
        self.representation_mode = mode
        self.checkpoint = DeltaEnvelopeCheckpoint(mode)
        self.api_requests = 0
        self.snapshots, self.controls, self.projections, self.input_counts = [], [], [], []
        self.offers, self.closed = [], []
        self.current_offer, self._offered_call_id, self._stopped = False, None, False
        self._fixed_config = self._config_digest()
        self.exposure = DeltaEnvelopeExposureLedger(mode)
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

    def representation_summary(self):
        return {**super().representation_summary(), 'version': VERSION}

    def envelope_summary(self):
        attempts = rolling.attempt_usage(self)
        mode = self.representation_mode
        offers = [o for o in self.offers if prompt_policy_for(mode) == 'explicit_delta_object'
                  and o['offer']['delta_requested']]
        dispatched = [attempts[o['after_model_calls']] for o in offers
            if o['after_model_calls'] < len(attempts)
            and attempts[o['after_model_calls']]['role'] == 'focus']
        representation = self.representation_summary()
        return dict(version=VERSION, mode=mode, policy=prompt_policy_for(mode),
            underlying_representation_mode=base_mode_for(mode),
            object_delta_summary_prompt_sha256=OBJECT_DELTA_PROMPT_SHA256,
            object_prompt_offers=len(offers), object_prompt_dispatched_focus_calls=len(dispatched),
            object_prompt_known_focus_calls=sum(c['status'] == 'ok' for c in dispatched),
            object_prompt_unknown_focus_calls=sum(c['status'] != 'ok' for c in dispatched),
            **{k: representation[k] for k in ('actual_delta_actor_calls',
                'actual_delta_known_actor_calls', 'actual_delta_unknown_actor_calls',
                'contract_failed', 'accounting_complete')},
            first_summary_unchanged=True, host_combines_fragments=True,
            parser_and_fragment_limits_unchanged=True, prompt_guarantees_object_output=False,
            novel_method_claim=False)
