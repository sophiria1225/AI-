"""Past paid raw-prefix exposure, not measured savings or a ski-rental guarantee.

Pure bounded controller and rolling-view construction. No model, native count,
API, generated-code execution, or task-value interpretation occurs here.
"""
from copy import deepcopy
import json

from receipt_reasoning_history import digest, require
from rolling_checkpoint_history import (MAX_OPPORTUNITIES, MIN_NEW_CLOSED_TURNS,
                                        SUMMARY_PROMPT, RollingCheckpoint)
from single_checkpoint_history import RECENT_TURNS, TRIGGER_INPUT_TOKENS, candidate, closed_turns

MODES = ('rolling_separate', 'fixed_interval', 'prefix_exposure')
VERSION = 'paid_raw_prefix_exposure_v1'


def integer(value, name, minimum=0):
    require(type(value) is int and value >= minimum, 'invalid_' + name)
    return value


def trigger_decision(*, mode, opportunities, fresh_turns, eligible_raw,
                     measured_input_tokens, accumulated_exposure, previous_focus_cost):
    require(mode in MODES, 'fixed_prefix_exposure_mode_required')
    integer(opportunities, 'opportunities')
    integer(fresh_turns, 'fresh_turns')
    integer(measured_input_tokens, 'measured_input_tokens', 1)
    integer(accumulated_exposure, 'accumulated_exposure')
    require(type(eligible_raw) is bool, 'typed_eligible_raw_required')
    if previous_focus_cost is not None:
        integer(previous_focus_cost, 'previous_focus_cost', 1)
    common = (opportunities < MAX_OPPORTUNITIES and
              fresh_turns >= MIN_NEW_CLOSED_TURNS and eligible_raw)
    ordinary = common and measured_input_tokens >= TRIGGER_INPUT_TOKENS
    first = opportunities == 0
    exposure = common and (measured_input_tokens >= TRIGGER_INPUT_TOKENS if first else
                           previous_focus_cost is not None and accumulated_exposure >= previous_focus_cost)
    interval = ordinary if first else common
    selected = {'rolling_separate': ordinary, 'fixed_interval': interval,
                'prefix_exposure': exposure}[mode]
    reason = ('opportunity_limit' if opportunities >= MAX_OPPORTUNITIES else
              'insufficient_fresh_turns' if fresh_turns < MIN_NEW_CLOSED_TURNS else
              'no_new_eligible_raw' if not eligible_raw else
              'first_native_threshold' if first else
              'ordinary_native_threshold' if mode == 'rolling_separate' else
              'fixed_fresh_turn_interval' if mode == 'fixed_interval' else
              'no_paid_focus_cost' if previous_focus_cost is None else
              'paid_raw_exposure_threshold')
    return dict(version=VERSION, mode=mode, opportunities=opportunities,
                fresh_turns=fresh_turns, eligible_raw=eligible_raw,
                measured_input_tokens=measured_input_tokens,
                accumulated_exposure=accumulated_exposure, previous_focus_cost=previous_focus_cost,
                ordinary_would_offer=ordinary, interval_would_offer=interval,
                exposure_would_offer=exposure, offer=selected, reason=reason,
                first_opportunity=first, future_horizon_used=False,
                realizable_savings_established=False)


class PrefixExposureLedger:
    """Only known paid actor terminals contribute; every known paid focus resets.

    Raw negative deltas are retained. Their positive parts form the indicator.
    Count-only/admission-rejected requests never purchase exposure or a focus.
    """
    def __init__(self, mode):
        require(mode in MODES, 'fixed_prefix_exposure_mode_required')
        self.mode = mode
        self.accumulated_exposure = 0
        self.previous_focus_cost = None
        self.events = []
        self.blocked = False
        self._paid_ids = set()

    def _begin(self, role, call_id, model_attempted, usage_known):
        require(not self.blocked, 'unknown_or_failed_exposure_blocks_continuation')
        require(type(model_attempted) is bool and type(usage_known) is bool,
                'typed_dispatch_and_usage_required')
        require(type(call_id) is str and call_id, 'call_identity_required')
        if model_attempted:
            require(call_id not in self._paid_ids, 'duplicate_paid_call')
            self._paid_ids.add(call_id)
        return dict(role=role, call_id=call_id, model_attempted=model_attempted,
                    usage_known=usage_known, exposure_before=self.accumulated_exposure,
                    focus_cost_before=self.previous_focus_cost)

    def record_focus(self, *, call_id, model_attempted, usage_known,
                     input_tokens=None, output_tokens=None):
        event = self._begin('focus', call_id, model_attempted, usage_known)
        if not model_attempted:
            require(not usage_known and input_tokens is None and output_tokens is None,
                    'unstarted_focus_cannot_have_usage')
            event['status'] = 'not_dispatched'
        elif not usage_known:
            event['status'] = 'unknown_terminal'
            self.blocked = True
        else:
            cost = integer(input_tokens, 'focus_input_tokens', 1) + integer(output_tokens, 'focus_output_tokens')
            self.previous_focus_cost = cost
            self.accumulated_exposure = 0
            event.update(status='known_paid_focus', input_tokens=input_tokens,
                         output_tokens=output_tokens, paid_focus_tokens=cost)
        event.update(exposure_after=self.accumulated_exposure, focus_cost_after=self.previous_focus_cost)
        self.events.append(event)
        return deepcopy(event)

    def record_actor(self, *, call_id, model_attempted, usage_known,
                     input_tokens=None, without_raw_input_tokens=None, bindings=None):
        event = self._begin('agent', call_id, model_attempted, usage_known)
        event.update(raw_delta=None, positive_part=None, added_exposure=0,
                     bindings=deepcopy(bindings))
        if not model_attempted:
            require(not usage_known and input_tokens is None and without_raw_input_tokens is None,
                    'unstarted_actor_cannot_have_usage')
            event['status'] = 'not_dispatched'
        elif not usage_known:
            event['status'] = 'unknown_terminal'
            self.blocked = True
        else:
            integer(input_tokens, 'actor_input_tokens', 1)
            event['input_tokens'] = input_tokens
            if self.previous_focus_cost is None:
                require(without_raw_input_tokens is None, 'no_exposure_count_before_paid_focus')
                event['status'] = 'known_actor_before_first_paid_focus'
            else:
                integer(without_raw_input_tokens, 'without_raw_input_tokens', 1)
                raw = input_tokens - without_raw_input_tokens
                positive = max(0, raw)
                self.accumulated_exposure += positive
                event.update(status='known_paid_actor', without_raw_input_tokens=without_raw_input_tokens,
                             raw_delta=raw, positive_part=positive, added_exposure=positive)
        event.update(exposure_after=self.accumulated_exposure, focus_cost_after=self.previous_focus_cost)
        self.events.append(event)
        return deepcopy(event)

    def fail(self, reason):
        self.blocked = True
        self.events.append({'role': 'control', 'status': 'contract_failed', 'reason': reason,
                            'exposure_after': self.accumulated_exposure,
                            'focus_cost_after': self.previous_focus_cost})

    def record_actor_measurement_failure(self, *, call_id, input_tokens, reason):
        event = self._begin('agent', call_id, True, True)
        integer(input_tokens, 'known_actor_input_tokens', 1)
        event.update(status='known_paid_actor_measurement_failed', input_tokens=input_tokens,
                     raw_delta=None, positive_part=None, added_exposure=0,
                     action_returned_to_worker=False, reason=reason,
                     exposure_after=self.accumulated_exposure, focus_cost_after=self.previous_focus_cost)
        self.blocked = True
        self.events.append(event)
        return deepcopy(event)

    def summary(self):
        return dict(version=VERSION, mode=self.mode, accumulated_exposure=self.accumulated_exposure,
                    previous_focus_cost=self.previous_focus_cost, blocked=self.blocked,
                    event_count=len(self.events), events_sha256=digest(self.events),
                    known_paid_actor_exposures=sum(e['status'] == 'known_paid_actor' for e in self.events),
                    known_paid_focuses=sum(e['status'] == 'known_paid_focus' for e in self.events),
                    incomplete_paid_actor_measurements=sum(e['status'] == 'known_paid_actor_measurement_failed'
                                                          for e in self.events),
                    negative_raw_deltas=sum(e.get('raw_delta', 0) is not None and e.get('raw_delta', 0) < 0
                                            for e in self.events),
                    positive_part_indicator=True, realizable_savings_established=False,
                    future_horizon_used=False)


def eligible_prefix_views(checkpoint, archive):
    """Remove only whole new raw turns; preserve the complete prior checkpoint.

    Returned without_raw is exclusively for counting, never a model input.
    """
    require(checkpoint.mode == 'separate', 'separate_checkpoint_required')
    working = checkpoint.view(archive)
    clean = checkpoint._clean(archive)
    turns = closed_turns(clean)
    start = checkpoint.cutoff
    end = max(start, turns[-RECENT_TURNS][0]) if len(turns) >= RECENT_TURNS else start
    require(2 <= start <= end <= len(clean), 'invalid_raw_prefix_bounds')
    head = 3 if checkpoint.checkpoint is not None else 2
    require(working[head:] == clean[start:], 'working_raw_suffix_mismatch')
    without_raw = deepcopy(working[:head] + clean[end:])
    return dict(working=working, without_raw=without_raw,
                source_archive_sha256=digest(archive), working_history_sha256=digest(working),
                without_raw_history_sha256=digest(without_raw),
                eligible_raw_sha256=digest(clean[start:end]),
                raw_start=start, raw_end=end, eligible_raw_messages=end-start,
                checkpoint_revision=checkpoint.revision, count_only=True)


class PrefixExposureCheckpoint(RollingCheckpoint):
    """Unchanged first offer; repeat predicate selected without forging a count."""
    def __init__(self, mode):
        require(mode in MODES, 'fixed_prefix_exposure_mode_required')
        super().__init__('separate')
        self.exposure_mode = mode

    def begin(self, archive, measured_input_tokens, tools=None, *, repeat_ready=False):
        require(type(repeat_ready) is bool, 'typed_repeat_trigger_required')
        if self.exposure_mode == 'rolling_separate' or self.opportunities == 0:
            return super().begin(archive, measured_input_tokens, tools)
        turns = self._check(archive)
        require(self.pending is None, 'rolling_opportunity_already_pending')
        integer(measured_input_tokens, 'measured_input_tokens', 1)
        self._bind(archive)
        if (self.opportunities >= self.max_opportunities or
                len(turns)-self._last_closed_turns < MIN_NEW_CLOSED_TURNS or not repeat_ready):
            return None
        cutoff = turns[-RECENT_TURNS][0]
        if cutoff <= self.cutoff:
            return None
        clean = self._clean(archive)
        packet = dict(original_instructions_and_task=deepcopy(clean[:2]),
                      previous_checkpoint=deepcopy(self.checkpoint),
                      previous_checkpoint_semantics_verified=False,
                      older_history=deepcopy(clean[self.cutoff:cutoff]),
                      recent_context=deepcopy(clean[cutoff:]))
        messages = (candidate(clean)['summary_messages'] if self.checkpoint is None else
                    [{'role': 'system', 'content': SUMMARY_PROMPT},
                     {'role': 'user', 'content': json.dumps(packet, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False)}])
        result = dict(mode='separate', opportunity_index=self.opportunities+1,
                      source_archive_sha256=digest(archive), cutoff=cutoff, previous_cutoff=self.cutoff,
                      fresh_closed_turns=len(turns)-self._last_closed_turns,
                      trigger_input_tokens=measured_input_tokens, summary_messages=messages)
        self.opportunities += 1
        self.pending = dict(before=deepcopy(archive), cutoff=cutoff,
                            opportunity_index=self.opportunities, stage='offered')
        return deepcopy(result)
