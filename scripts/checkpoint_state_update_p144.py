"""Bounded second-checkpoint edits, with unchanged recursive/append controls.

Only saved summary strings are edited. Keep means byte-preserved text, not a
verified fact. This module does no semantic validation or task execution.
"""
from copy import deepcopy
import hashlib
import json

from checkpoint_early_threshold_p143 import (
    DeltaEnvelopeCheckpoint as _PriorCheckpoint, MAX_OPPORTUNITIES,
    MIN_NEW_CLOSED_TURNS, TRIGGER_INPUT_TOKENS, SUMMARY_PROMPT,
    DELTA_SUMMARY_PROMPT, OBJECT_DELTA_SUMMARY_PROMPT, OBJECT_DELTA_PROMPT_SHA256,
    summary_note, delta_note, eligible_prefix_views, serialize_fragment_body,
    validate_fragment_budget)
from checkpoint_prefix_exposure import PrefixExposureLedger, integer
from receipt_reasoning_history import digest, require
from single_checkpoint_history import FIELDS, _unique_pairs, closed_turns

MODES = ('threshold_recursive', 'threshold_delta_object', 'threshold_delta_update')
VERSION = 'checkpoint_state_update_p144_v1'
UPDATE_SUMMARY_PROMPT = '''Update the previous fallible checkpoint using the new older_history.
Return exactly one JSON object with the four keys completed, usable_state,
remaining, uncertainties. Each value must have exactly these four keys:
{"keep":[0],"update":[{"index":1,"text":"replacement text"}],"delete":[2],"add":["new text"]}.
The example is a schema, not an instruction to use those indices. Indices are
zero-based positions in that same field of previous_checkpoint. Cover EVERY
old index exactly once across keep, update and delete; never duplicate indices.
For an empty old field all three index lists must be empty. Use keep to preserve
an old item's text exactly, update to replace it, delete to explicitly remove
it, and add for new items. Keep useful facts and unresolved uncertainties;
previous_checkpoint is fallible, not verified truth. Do not silently drop old
items. The host applies these operations atomically: retained/updated old items
stay in their original relative order, followed by adds in their given order.
The host supplies the resulting SINGLE checkpoint, not this edit program, to
the actor. Do not output an array, the old checkpoint, Markdown, or commentary.
Every replacement/add must be a nonempty string of at most 2048 characters.
Your entire JSON output must be at most 8192 characters. The resulting compact
JSON checkpoint must also be at most 8192 characters, with at most 32 items in
EACH field. The original task and recent_context are context only; summarize
new older_history while preserving or explicitly revising the old state.'''
UPDATE_PROMPT_SHA256 = hashlib.sha256(UPDATE_SUMMARY_PROMPT.encode()).hexdigest()


def base_mode_for(mode):
    require(mode in MODES, 'fixed_P144_threshold_modes_required')
    return {'threshold_recursive': 'threshold_recursive',
            'threshold_delta_object': 'threshold_delta',
            'threshold_delta_update': 'threshold_update'}[mode]


def timing_for(mode):
    base_mode_for(mode)
    return 'threshold'


def representation_for(mode):
    return base_mode_for(mode).split('_', 1)[1]


def prompt_policy_for(mode):
    base_mode_for(mode)
    return dict(zip(MODES, ('original', 'explicit_delta_object', 'explicit_state_update')))[mode]


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
              'first_native_threshold' if first else 'ordinary_native_threshold')
    return dict(version=VERSION, mode=mode, timing=timing, representation=representation,
                opportunities=opportunities, fresh_turns=fresh_turns, eligible_raw=eligible_raw,
                measured_input_tokens=measured_input_tokens, accumulated_exposure=accumulated_exposure,
                previous_focus_cost=previous_focus_cost, threshold_would_offer=threshold,
                exposure_would_offer=exposure, offer=threshold, reason=reason,
                first_opportunity=first, future_horizon_used=False,
                realizable_savings_established=False)


def _text(value):
    require(type(value) is str and 0 < len(value) <= 2048, 'invalid_update_text')
    return value


def apply_update_patch(old_state, patch):
    """Pure simultaneous application; rejects incomplete/ambiguous old-index edits.

    Returns (new_state, scalar_counts), never mutating either argument.
    """
    validate_fragment_budget([old_state])
    require(type(patch) is dict and set(patch) == set(FIELDS), 'invalid_update_fields')
    result = {}
    counts = dict(kept_old_items=0, update_operations=0, unchanged_update_operations=0,
                  updated_old_items=0, deleted_old_items=0, added_items=0,
                  changed_old_items=0, final_items=0)
    for field in FIELDS:
        operations, old = patch[field], old_state[field]
        require(type(operations) is dict and set(operations) == {'keep', 'update', 'delete', 'add'},
                'invalid_update_operations')
        require(all(type(operations[key]) is list for key in operations), 'update_lists_required')
        seen, updates = set(), {}
        for action in ('keep', 'update', 'delete'):
            for item in operations[action]:
                if action == 'update':
                    require(type(item) is dict and set(item) == {'index', 'text'}, 'invalid_update_entry')
                    index = item['index']
                    text = _text(item['text'])
                else:
                    index = item
                require(type(index) is int and 0 <= index < len(old), 'invalid_update_index')
                require(index not in seen, 'duplicate_update_index')
                seen.add(index)
                if action == 'update':
                    updates[index] = text
                    counts['update_operations'] += 1
                    counts['unchanged_update_operations'] += int(text == old[index])
                    counts['updated_old_items'] += int(text != old[index])
        require(seen == set(range(len(old))), 'incomplete_old_item_coverage')
        additions = [_text(text) for text in operations['add']]
        deleted = set(operations['delete'])
        result[field] = [updates.get(i, text) for i, text in enumerate(old) if i not in deleted] + additions
        counts['kept_old_items'] += len(operations['keep'])
        counts['deleted_old_items'] += len(deleted)
        counts['added_items'] += len(additions)
        counts['final_items'] += len(result[field])
    counts['changed_old_items'] = counts['updated_old_items'] + counts['deleted_old_items']
    validate_fragment_budget([result])
    return deepcopy(result), counts


def parse_update_patch(message, finish_reason, old_state):
    require(type(message) is dict and message.get('role') == 'assistant', 'update_assistant_required')
    require(finish_reason == 'stop', 'update_finish_stop_required')
    require(not message.get('tool_calls'), 'update_tool_calls_forbidden')
    content = message.get('content')
    require(type(content) is str and 0 < len(content) <= 8192, 'update_output_character_budget')
    patch = json.loads(content, object_pairs_hook=_unique_pairs)
    # Validation includes the materialized-state limits, not just the edit size.
    apply_update_patch(old_state, patch)
    return patch


class StateUpdateExposureLedger(PrefixExposureLedger):
    def __init__(self, mode):
        timing_for(mode)
        super().__init__('rolling_separate')
        self.mode = mode

    def summary(self):
        return {**super().summary(), 'version': VERSION, 'mode': self.mode,
                'timing': timing_for(self.mode), 'representation': representation_for(self.mode)}


class StateUpdateCheckpoint(_PriorCheckpoint):
    def __init__(self, mode):
        base_mode_for(mode)
        if mode != 'threshold_delta_update':
            super().__init__(mode)
        else:
            # Honest third representation: no old enum/max-opportunity disguise.
            self.timing, self.representation = 'threshold', 'update'
            self.representation_mode, self.envelope_policy = mode, prompt_policy_for(mode)
            self.mode, self.max_opportunities = 'separate', MAX_OPPORTUNITIES
            self.opportunities = self.revision = 0
            self.cutoff, self.pending, self.events = 2, None, []
            self._values, self._notes = [], []
            self._bound_length = self._last_closed_turns = 0
            self._bound_sha256, self._blocked = None, False
        self._update_installed = False
        self._installed_update_counts = None
        self._installed_update_state_changed = False

    @property
    def update_applied(self):
        return self._update_installed

    @property
    def installed_update_counts(self):
        return deepcopy(self._installed_update_counts)

    @property
    def installed_update_state_changed(self):
        return self._installed_update_state_changed

    def begin(self, archive, measured_input_tokens, tools=None, *, repeat_ready=False):
        offered = super().begin(archive, measured_input_tokens, tools, repeat_ready=repeat_ready)
        if offered is None or self.representation_mode != 'threshold_delta_update':
            return offered
        requested = offered['opportunity_index'] == 2 and self.revision == 1
        offered['update_requested'] = requested
        offered['update_prior_state_sha256'] = digest(self._values[0]) if requested else None
        self.pending.update(update_requested=requested)
        if requested:
            require(len(self._values) == len(self._notes) == 1, 'one_old_state_required')
            self.pending.update(update_prior_state=deepcopy(self._values[0]),
                update_prior_state_sha256=digest(self._values[0]),
                update_prior_notes_sha256=digest(self._notes))
            offered['summary_messages'][0] = {'role': 'system', 'content': UPDATE_SUMMARY_PROMPT}
        return offered

    def _update_state_matches(self):
        return (len(self._values) == 1 and
                digest(self._values[0]) == self.pending['update_prior_state_sha256'] and
                digest(self._notes) == self.pending['update_prior_notes_sha256'])

    def close_separate(self, archive, message, finish_reason, *, usage_known):
        if not (self.pending and self.pending.get('update_requested')):
            return super().close_separate(archive, message, finish_reason, usage_known=usage_known)
        if usage_known is not True:
            self._blocked = True
            raise ValueError('unknown_usage_blocks_rolling_continuation')
        self._check(archive)
        require(self.pending['stage'] == 'offered' and archive == self.pending['before'],
                'update_offer_archive_binding_required')
        value, status = None, 'invalid_update_patch'
        if not self._update_state_matches():
            status = 'stale_update_state'
        else:
            try:
                patch = parse_update_patch(message, finish_reason, self.pending['update_prior_state'])
                value, counts = apply_update_patch(self.pending['update_prior_state'], patch)
                self.pending.update(update_patch_sha256=digest(patch),
                    update_result_state_sha256=digest(value), update_operation_counts=counts,
                    update_state_changed=digest(value) != self.pending['update_prior_state_sha256'])
                status = 'structurally_valid_update'
            except (ValueError, TypeError, RecursionError):
                # Fixed reason labels only; never leak arbitrary parser/content errors.
                status = ('update_finish_not_stop' if finish_reason != 'stop' else 'invalid_update_patch')
        return self._close(archive, value, status)

    def decide(self, ordinary_input_tokens, compacted_input_tokens):
        if self.pending and self.pending.get('update_requested') and not self._update_state_matches():
            self.pending['close_status'] = 'stale_update_state'
            return self._finish(False, 'stale_update_state', ordinary_input_tokens, compacted_input_tokens)
        return super().decide(ordinary_input_tokens, compacted_input_tokens)

    def _finish(self, accepted, reason, ordinary, compacted):
        pending = deepcopy(self.pending)
        requested = bool(pending.get('update_requested'))
        if requested and not accepted and pending['close_status'] in (
                'stale_update_state', 'invalid_update_patch', 'update_finish_not_stop'):
            reason = pending['close_status']
        if requested and accepted:
            self._update_installed = True
            self._installed_update_counts = deepcopy(pending['update_operation_counts'])
            self._installed_update_state_changed = pending['update_state_changed']
        event = super()._finish(accepted, reason, ordinary, compacted)
        if requested:
            event.update(update_requested=True, update_applied=accepted,
                update_prior_state_sha256=pending['update_prior_state_sha256'],
                update_patch_sha256=pending.get('update_patch_sha256'),
                update_result_state_sha256=pending.get('update_result_state_sha256'),
                update_state_changed=bool(pending.get('update_state_changed', False)),
                update_operation_counts=deepcopy(pending.get('update_operation_counts')))
            self.events[-1] = deepcopy(event)
        return event


DeltaEnvelopeCheckpoint = StateUpdateCheckpoint
DeltaEnvelopeExposureLedger = StateUpdateExposureLedger
