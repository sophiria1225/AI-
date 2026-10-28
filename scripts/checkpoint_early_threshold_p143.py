"""P143 early-threshold coverage controller, explicitly fixed at 8,192 tokens.

Only first/repeat timing differs from the P142 controller; P141's object prompt,
immutable first note, parser, host combination and fragment limits are reused.
This is a post-P142 development cohort, not a retrospective threshold change.
"""
from copy import deepcopy
import json
from checkpoint_prefix_exposure import integer
from checkpoint_object_timing_p141 import (
    MAX_OPPORTUNITIES, MIN_NEW_CLOSED_TURNS, SUMMARY_PROMPT, DELTA_SUMMARY_PROMPT,
    OBJECT_DELTA_SUMMARY_PROMPT, OBJECT_DELTA_PROMPT_SHA256,
    DeltaEnvelopeCheckpoint as _PriorCheckpoint,
    DeltaEnvelopeExposureLedger as _PriorLedger,
    summary_note, delta_note, eligible_prefix_views, serialize_fragment_body,
    validate_fragment_budget)
from receipt_reasoning_history import digest, require
from single_checkpoint_history import candidate, RECENT_TURNS

MODES = ('threshold_recursive', 'threshold_delta_object')
VERSION = 'checkpoint_early_threshold_object_p143_v1'
TRIGGER_INPUT_TOKENS = 8192


def base_mode_for(mode):
    require(mode in MODES, 'fixed_P143_threshold_modes_required')
    return 'threshold_recursive' if mode == MODES[0] else 'threshold_delta'


def timing_for(mode):
    base_mode_for(mode)
    return 'threshold'


def representation_for(mode):
    return base_mode_for(mode).split('_', 1)[1]


def prompt_policy_for(mode):
    base_mode_for(mode)
    return 'original' if mode == MODES[0] else 'explicit_delta_object'


def trigger_decision(*, mode, opportunities, fresh_turns, eligible_raw,
                     measured_input_tokens, accumulated_exposure, previous_focus_cost):
    timing, representation = timing_for(mode), representation_for(mode)
    integer(opportunities, 'opportunities')
    integer(fresh_turns, 'fresh_turns')
    integer(measured_input_tokens, 'measured_input_tokens', 1)
    integer(accumulated_exposure, 'accumulated_exposure')
    require(type(eligible_raw) is bool, 'typed_eligible_raw_required')
    if previous_focus_cost is not None:
        integer(previous_focus_cost, 'previous_focus_cost', 1)
    common = opportunities < MAX_OPPORTUNITIES and fresh_turns >= MIN_NEW_CLOSED_TURNS and eligible_raw
    first = opportunities == 0
    threshold = common and measured_input_tokens >= TRIGGER_INPUT_TOKENS
    exposure = threshold if first else (common and previous_focus_cost is not None
                                       and accumulated_exposure >= previous_focus_cost)
    reason = ('opportunity_limit' if opportunities >= MAX_OPPORTUNITIES else
              'insufficient_fresh_turns' if fresh_turns < MIN_NEW_CLOSED_TURNS else
              'no_new_eligible_raw' if not eligible_raw else
              'first_native_threshold' if first else
              'ordinary_native_threshold' if timing == 'threshold' else
              'no_paid_focus_cost' if previous_focus_cost is None else
              'paid_raw_exposure_threshold')
    return dict(version=VERSION, mode=mode, timing=timing, representation=representation,
                opportunities=opportunities, fresh_turns=fresh_turns, eligible_raw=eligible_raw,
                measured_input_tokens=measured_input_tokens, accumulated_exposure=accumulated_exposure,
                previous_focus_cost=previous_focus_cost, threshold_would_offer=threshold,
                exposure_would_offer=exposure, offer=threshold if timing == 'threshold' else exposure,
                reason=reason, first_opportunity=first, future_horizon_used=False,
                realizable_savings_established=False)


class DeltaEnvelopeExposureLedger(_PriorLedger):
    def __init__(self, mode):
        base_mode_for(mode)
        super().__init__(mode)

    def summary(self):
        return {**super().summary(), 'version': VERSION}


class DeltaEnvelopeCheckpoint(_PriorCheckpoint):
    def __init__(self, mode):
        base_mode_for(mode)
        super().__init__(mode)

    def begin(self, archive, measured_input_tokens, tools=None, *, repeat_ready=False):
        require(type(repeat_ready) is bool, 'typed_repeat_trigger_required')
        turns = self._check(archive)
        require(self.pending is None, 'rolling_opportunity_already_pending')
        integer(measured_input_tokens, 'measured_input_tokens', 1)
        self._bind(archive)
        ready = measured_input_tokens >= TRIGGER_INPUT_TOKENS if (
            self.opportunities == 0 or self.timing == 'threshold') else repeat_ready
        if (self.opportunities >= self.max_opportunities or
                len(turns)-self._last_closed_turns < MIN_NEW_CLOSED_TURNS or not ready):
            return None
        cutoff = turns[-RECENT_TURNS][0]
        if cutoff <= self.cutoff:
            return None
        clean = self._clean(archive)
        use_delta = self.representation == 'delta' and self.opportunities == 1 and self.revision == 1
        if not self._values:
            messages = candidate(clean)['summary_messages']
        else:
            require(len(self._values) == 1, 'no_third_summary_opportunity')
            packet = dict(original_instructions_and_task=deepcopy(clean[:2]),
                          previous_checkpoint=deepcopy(self._values[0]),
                          previous_checkpoint_semantics_verified=False,
                          older_history=deepcopy(clean[self.cutoff:cutoff]),
                          recent_context=deepcopy(clean[cutoff:]))
            messages = [{'role': 'system', 'content': OBJECT_DELTA_SUMMARY_PROMPT if use_delta else SUMMARY_PROMPT},
                        {'role': 'user', 'content': json.dumps(packet, ensure_ascii=False,
                         separators=(',', ':'), allow_nan=False)}]
        result = dict(mode='separate', opportunity_index=self.opportunities+1,
                      source_archive_sha256=digest(archive), cutoff=cutoff, previous_cutoff=self.cutoff,
                      fresh_closed_turns=len(turns)-self._last_closed_turns,
                      trigger_input_tokens=measured_input_tokens, summary_messages=messages,
                      delta_requested=use_delta, prior_fragment_count=self.fragment_count,
                      prior_summary_notes_sha256=digest(self._notes))
        self.opportunities += 1
        self.pending = dict(before=deepcopy(archive), cutoff=cutoff, opportunity_index=self.opportunities,
                            stage='offered', delta_requested=use_delta, prior_notes=deepcopy(self._notes))
        return deepcopy(result)
