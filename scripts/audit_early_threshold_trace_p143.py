"""P143 max-two timing/representation and whole-job costs from closed records.

The ordinary rolling audit is copied, never patched. Native counts are not
rerun: their values are trusted recorder measurements bound to reconstructed
messages, tools, sampling configuration and the known paid actor. The summary
parser/checkpoint formatter is shared; exposure arithmetic and scheduling are
independently recomputed here. No savings or ski-rental guarantee is inferred.

No model, tokenizer, program, API, evaluator or semantic judge is invoked.
Recorded native counts are bound to reconstructed inputs. This proves neither
summary truthfulness nor preservation of task quality.
"""
from collections import Counter
from copy import deepcopy
import json
import math
from types import SimpleNamespace

from api_error_comparison import task_snapshot
from audit_budget_visibility import budget_before_calls
from audit_documentation_comparison import validate_admission
from audit_single_checkpoint_trace import audit_trace as audit_single
from budget_observation import notification
from checkpoint_attempt_usage import attempt_usage
from fixed_budget_local_llama import payload_for as summary_payload
from inference_cache_control import cache_measurement
from inline_checkpoint_protocol import split_inline_response
from local_llama import parse_response
from native_data_compute import selected_receipts
from public_display import CODE_TOOLS
from receipt_reasoning_history import digest, require
from checkpoint_early_threshold_p143 import (MODES, VERSION, SUMMARY_PROMPT, DELTA_SUMMARY_PROMPT,
    summary_note, delta_note, OBJECT_DELTA_SUMMARY_PROMPT, OBJECT_DELTA_PROMPT_SHA256,
    timing_for, representation_for, base_mode_for, prompt_policy_for)
from single_checkpoint_history import closed_turns, candidate, parse_checkpoint, FIELDS
from checkpoint_prefix_identity_p140 import canonical_prefix_evidence, PrefixIdentityError, VERSION as IDENTITY_VERSION
from run_handoff_factors import read, sha
from tool_choice_local_llama import payload_for as agent_payload


def _audit_fragment_budget(values):
    require(type(values) is list and len(values) in (1, 2), 'audit_fragment_count')
    require(all(type(value) is dict and set(value) == set(FIELDS) for value in values),
            'audit_fragment_fields')
    totals = {field: 0 for field in FIELDS}
    for value in values:
        for field in FIELDS:
            items = value[field]
            require(type(items) is list and all(type(item) is str and 0 < len(item) <= 2048
                                              for item in items), 'audit_fragment_items')
            totals[field] += len(items)
    require(max(totals.values()) <= 32, 'audit_combined_field_cap')
    body = json.dumps(values[0] if len(values) == 1 else values, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False)
    require(len(body) <= 8192, 'audit_combined_character_cap')
    return dict(fragment_count=len(values), body_characters=len(body),
                body_sha256=digest(body), field_item_counts=totals)


class AuditRepresentationCheckpoint:
    """Separately instantiated audit state replay, never the live controller.

    Packet prompts/formatters and the old parser/turn grammar are shared.
    Budget/view/cutoff/acceptance/transition checks below run in this new module.

    Budget/context admission and whole-view native counting remain the caller's
    responsibility. This class never treats structural validity as truth.
    """
    def __init__(self, mode):
        require(mode in MODES, 'fixed_P143_audit_mode_required')
        self.timing, self.representation = timing_for(mode), representation_for(mode)
        self.representation_mode = mode
        self.mode = 'separate'
        self.max_opportunities = 2
        self.opportunities = self.revision = 0
        self.cutoff = 2
        self.pending = None
        self.events = []
        self._values, self._notes = [], []
        self._bound_length, self._last_closed_turns = 0, 0
        self._bound_sha256 = None
        self._blocked = False

    @property
    def checkpoint(self):
        return deepcopy(self._values[-1]) if self._values else None

    @property
    def summary_notes(self):
        return deepcopy(self._notes)

    @property
    def fragment_count(self):
        return len(self._notes)

    @property
    def delta_applied(self):
        return self.fragment_count == 2

    def _check(self, archive):
        require(not self._blocked, 'unknown_usage_blocks_rolling_continuation')
        turns = closed_turns(archive)
        require(len(archive) >= self._bound_length and (self._bound_sha256 is None or
                digest(archive[:self._bound_length]) == self._bound_sha256),
                'rolling_archive_changed_or_rewound')
        return turns

    def _bind(self, archive):
        self._bound_length, self._bound_sha256 = len(archive), digest(archive)

    def _clean(self, archive):
        return deepcopy(archive)

    def _render(self, archive):
        clean = self._clean(archive)
        return clean[:2] + self.summary_notes + clean[self.cutoff:]

    def view(self, archive):
        self._check(archive)
        require(self.pending is None, 'rolling_opportunity_must_close_and_resolve')
        return self._render(archive)

    def begin(self, archive, measured_input_tokens, tools=None, *, repeat_ready=False):
        require(type(repeat_ready) is bool, 'typed_repeat_trigger_required')
        turns = self._check(archive)
        require(self.pending is None, 'rolling_opportunity_already_pending')
        _positive(measured_input_tokens, 'measured_input_tokens', 1)
        self._bind(archive)
        ready = measured_input_tokens >= 8192 if (
            self.opportunities == 0 or self.timing == 'threshold') else repeat_ready
        if (self.opportunities >= self.max_opportunities or
                len(turns)-self._last_closed_turns < 3 or not ready):
            return None
        cutoff = turns[-2][0]
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
            focus_prompt = (OBJECT_DELTA_SUMMARY_PROMPT if use_delta and prompt_policy_for(self.representation_mode) == 'explicit_delta_object'
                            else DELTA_SUMMARY_PROMPT if use_delta else SUMMARY_PROMPT)
            messages = [{'role': 'system', 'content': focus_prompt},
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

    def close_separate(self, archive, message, finish_reason, *, usage_known):
        if usage_known is not True:
            self._blocked = True
            raise ValueError('unknown_usage_blocks_rolling_continuation')
        self._check(archive)
        require(self.pending is not None and self.pending['stage'] == 'offered',
                'separate_rolling_offer_required')
        require(archive == self.pending['before'], 'archive_changed_during_summary')
        value, status = None, 'invalid_summary'
        try:
            value = parse_checkpoint(message, finish_reason)
            status = 'structurally_valid'
        except (ValueError, TypeError, RecursionError):
            pass
        return self._close(archive, value, status)

    def _close(self, archive, value, status):
        self._bind(archive)
        self._last_closed_turns = len(closed_turns(archive))
        ordinary = self._render(archive)
        values, notes, compacted = None, None, None
        if value is not None:
            values = deepcopy(self._values)+[deepcopy(value)] if self.pending['delta_requested'] else [deepcopy(value)]
            try:
                _audit_fragment_budget(values)
            except (ValueError, TypeError, RecursionError):
                value, values, status = None, None, 'combined_summary_budget'
            else:
                notes = (deepcopy(self.pending['prior_notes'])+[delta_note(value)]
                         if self.pending['delta_requested'] else [summary_note(value)])
                compacted = deepcopy(archive[:2])+deepcopy(notes)+deepcopy(archive[self.pending['cutoff']:])
        views = dict(ordinary=ordinary, compacted=compacted, ordinary_sha256=digest(ordinary),
                     compacted_sha256=digest(compacted) if compacted is not None else None,
                     archive_deleted=False, semantics_verified=False,
                     delta_requested=self.pending['delta_requested'],
                     candidate_fragment_count=len(notes) if notes is not None else None)
        self.pending.update(stage='closed', value=deepcopy(value), values=values, notes=notes,
                            views=deepcopy(views), close_status=status)
        if value is None:
            self._finish(False, 'fragment_budget_exceeded' if status == 'combined_summary_budget'
                         else 'no_structurally_valid_checkpoint', None, None)
        return deepcopy(views)

    def decide(self, ordinary_input_tokens, compacted_input_tokens):
        require(not self._blocked, 'unknown_usage_blocks_rolling_continuation')
        require(self.pending is not None and self.pending['stage'] == 'closed'
                and self.pending['value'] is not None, 'unresolved_rolling_views_required')
        _positive(ordinary_input_tokens, 'ordinary_next_input', 1)
        _positive(compacted_input_tokens, 'compacted_next_input', 1)
        accepted = compacted_input_tokens < ordinary_input_tokens
        if accepted and self.pending['delta_requested']:
            require(self.pending['notes'][:1] == self.pending['prior_notes'] and
                    len(self.pending['notes']) == 2, 'prior_note_must_remain_exact')
        if accepted:
            self._values, self._notes = deepcopy(self.pending['values']), deepcopy(self.pending['notes'])
            self.cutoff = self.pending['cutoff']
            self.revision += 1
        return self._finish(accepted, 'shorter_native_input' if accepted else 'not_shorter',
                            ordinary_input_tokens, compacted_input_tokens)

    def skip_unstarted_summary(self, archive, reason):
        self._check(archive)
        require(self.pending is not None and self.pending['stage'] == 'offered'
                and archive == self.pending['before'], 'unstarted_summary_required')
        require(reason in ('insufficient_shared_call_budget', 'insufficient_shared_token_budget',
                           'summary_context_limit'), 'known_summary_screening_reason_required')
        self._bind(archive)
        self._last_closed_turns = len(closed_turns(archive))
        self.pending.update(stage='closed', close_status='not_dispatched')
        return self._finish(False, reason, None, None)

    def _finish(self, accepted, reason, ordinary, compacted):
        event = dict(opportunity_index=self.pending['opportunity_index'], mode='separate',
                     accepted=accepted, reason=reason, close_status=self.pending['close_status'],
                     revision=self.revision, cutoff=self.cutoff, ordinary_input_tokens=ordinary,
                     compacted_input_tokens=compacted, semantics_verified=False, archive_deleted=False,
                     delta_requested=self.pending['delta_requested'], delta_applied=self.delta_applied,
                     fragment_count=self.fragment_count, summary_notes_sha256=digest(self._notes),
                     preserved_first_note_sha256=digest(self._notes[0]) if self.delta_applied else None)
        self.events.append(deepcopy(event))
        self.pending = None
        return deepcopy(event)


def eligible_prefix_views(checkpoint, archive):
    """Count-only deletion of new raw turns; keep every prior summary note."""
    require(checkpoint.mode == 'separate', 'separate_checkpoint_required')
    working = checkpoint.view(archive)
    clean = checkpoint._clean(archive)
    turns = closed_turns(clean)
    start = checkpoint.cutoff
    end = max(start, turns[-2][0]) if len(turns) >= 2 else start
    require(2 <= start <= end <= len(clean), 'invalid_raw_prefix_bounds')
    head = 2+checkpoint.fragment_count
    require(working[:2] == clean[:2] and working[2:head] == checkpoint.summary_notes
            and working[head:] == clean[start:], 'working_raw_suffix_mismatch')
    without_raw = deepcopy(working[:head]+clean[end:])
    return dict(working=working, without_raw=without_raw, source_archive_sha256=digest(archive),
                working_history_sha256=digest(working), without_raw_history_sha256=digest(without_raw),
                eligible_raw_sha256=digest(clean[start:end]), raw_start=start, raw_end=end,
                eligible_raw_messages=end-start, checkpoint_revision=checkpoint.revision,
                fragment_count=checkpoint.fragment_count, summary_notes_sha256=digest(checkpoint.summary_notes),
                count_only=True)


class TraceStopped(Exception):
    def __init__(self, exception_type):
        self.exception_type = exception_type



def _positive(value, name, minimum=0):
    require(type(value) is int and value >= minimum, 'invalid_exposure_' + name)
    return value


def dispatched_difference_counts(decisions, usage):
    """Observed dispatch after a differing predicate, not a second-policy rollout.

    A skipped offer may have failed screening in a counterfactual policy; this
    count makes no claim that its missing focus would actually have dispatched.
    """
    result = {}
    for reference, field in (('threshold', 'threshold_would_offer'),
                             ('exposure', 'exposure_would_offer')):
        count = 0
        for decision in decisions:
            index = decision['after_model_calls']
            role = 'focus' if decision['offer'] else 'agent'
            if (decision['offer'] != decision[field] and index < len(usage)
                    and usage[index]['role'] == role):
                count += 1
        result['actual_decision_differences_from_' + reference] = count
    return result


class RepresentationExposureAudit:
    """Independent arithmetic replay; recorded timings are bounded observations."""
    def __init__(self, folder, config, summary, usage, saved):
        self.config, self.summary, self.usage = config, summary, usage
        self.mode = config['checkpoint_representation_mode']
        self.timing, self.representation = timing_for(self.mode), representation_for(self.mode)
        self.saved_events = saved('prefix_exposure_events', [])
        self.saved_decisions = saved('prefix_exposure_decisions', [])
        self.counts = saved('prefix_exposure_counts', [])
        require(all(type(x) is list for x in (self.saved_events, self.saved_decisions, self.counts)),
                'exposure_sidecars_must_be_lists')
        self.events, self.decisions = [], []
        self.exposure, self.cost, self.count_index = 0, None, 0
        self.blocked, self.contract_failed = False, False
        self.paid_ids = set()

    def _event(self, role, cid, attempted, known):
        require(not self.blocked, 'exposure_event_after_sticky_stop')
        if attempted:
            require(cid not in self.paid_ids, 'duplicate_exposure_paid_call')
            self.paid_ids.add(cid)
        return dict(role=role, call_id=cid, model_attempted=attempted, usage_known=known,
                    exposure_before=self.exposure, focus_cost_before=self.cost)

    def _append(self, event):
        event.update(exposure_after=self.exposure, focus_cost_after=self.cost)
        self.events.append(event)

    def decision(self, control, base, measured, index):
        require(not self.blocked, 'exposure_decision_after_stop')
        views = eligible_prefix_views(control, base)
        fresh = len(closed_turns(base)) - control._last_closed_turns
        n = control.opportunities
        common = n < 2 and fresh >= 3 and views['eligible_raw_messages'] > 0
        first = n == 0
        ordinary = common and measured >= 8192
        proposed = common and (measured >= 8192 if first else
                                self.cost is not None and self.exposure >= self.cost)
        selected = ordinary if self.timing == 'threshold' else proposed
        reason = ('opportunity_limit' if n >= 2 else 'insufficient_fresh_turns' if fresh < 3 else
                  'no_new_eligible_raw' if not views['eligible_raw_messages'] else
                  'first_native_threshold' if first else
                  'ordinary_native_threshold' if self.timing == 'threshold' else
                  'no_paid_focus_cost' if self.cost is None else 'paid_raw_exposure_threshold')
        decision = dict(version=VERSION, mode=self.mode, timing=self.timing, representation=self.representation, opportunities=n, fresh_turns=fresh,
                        eligible_raw=views['eligible_raw_messages'] > 0, measured_input_tokens=measured,
                        accumulated_exposure=self.exposure, previous_focus_cost=self.cost,
                        threshold_would_offer=ordinary,
                        exposure_would_offer=proposed, offer=selected, reason=reason,
                        first_opportunity=first, future_horizon_used=False,
                        realizable_savings_established=False, after_model_calls=index,
                        source_archive_sha256=digest(base), exposure_events_sha256=digest(self.events))
        self.decisions.append(decision)
        return decision

    def focus(self, relevant, cid):
        require(len(relevant) <= 1 and all(c['role'] == 'focus' for c in relevant),
                'one_focus_per_exposure_opportunity')
        call = relevant[0] if relevant else None
        event = self._event('focus', cid, call is not None, bool(call and call['status'] == 'ok'))
        if call is None:
            event['status'] = 'not_dispatched'
        elif call['status'] != 'ok':
            require(call['input_tokens'] is None and call['output_tokens'] is None,
                    'unknown_focus_cannot_have_numeric_usage')
            event['status'] = 'unknown_terminal'
            self.blocked = True
        else:
            self.cost = _positive(call['input_tokens'], 'focus_input', 1) + _positive(call['output_tokens'], 'focus_output')
            self.exposure = 0
            event.update(status='known_paid_focus', input_tokens=call['input_tokens'],
                         output_tokens=call['output_tokens'], paid_focus_tokens=self.cost)
        self._append(event)

    def unknown_actor(self, call):
        require(call['input_tokens'] is None and call['output_tokens'] is None,
                'unknown_actor_cannot_have_numeric_usage')
        event = self._event('agent', call['id'], True, False)
        event.update(status='unknown_terminal', raw_delta=None, positive_part=None,
                     added_exposure=0, bindings=None)
        self.blocked = True
        self._append(event)

    def _count(self, call, without, tools, index):
        require(self.count_index < len(self.counts), 'prefix_native_count_missing')
        count = self.counts[self.count_index]
        self.count_index += 1
        cfg = deepcopy(self.config['model'])
        cfg.update(temperature=self.config['agent_temperature'],
                   seed=self.config['seed']+sum(c['role']=='agent' for c in self.usage[:index])-1,
                   num_predict=call['output_cap'], cache_prompt=index > 1)
        require(count.get('call_id') == call['id'] and count.get('count_only') is True
                and count.get('model_generation_allowed') is False
                and count.get('messages_sha256') == digest(without)
                and count.get('tools_sha256') == digest(tools)
                and count.get('model_config_sha256') == digest(cfg),
                'prefix_count_not_bound_to_paid_actor_and_projection')
        wall = count.get('control_wall_seconds')
        require(type(wall) in (int, float) and math.isfinite(wall)
                and 0 <= wall <= self.summary['wall_seconds'], 'invalid_exposure_control_wall')
        if count['status'] == 'failed':
            require(index == len(self.usage) and self.count_index == len(self.counts)
                    and type(count.get('exception_type')) is str, 'failed_exposure_count_must_stop')
            return None, count['exception_type']
        require(count['status'] == 'complete', 'incomplete_exposure_count')
        return _positive(count.get('input_tokens'), 'native_count', 1), None

    def actor(self, control, base, signal, call, tools, index, selected_events):
        views = eligible_prefix_views(control, base)
        actual = notification(views['working'], signal['measured_state'], 'not_exposed')[0]
        without = notification(views['without_raw'], signal['measured_state'], 'not_exposed')[0]
        require(digest(actual) == signal['model_messages_sha256']
                and call['input_tokens'] == call['predicted_input_tokens'],
                'exposure_requires_actual_native_input_equality')
        bindings = {k: v for k, v in views.items() if k not in ('working', 'without_raw')}
        bindings.update(actual_supplied_sha256=digest(actual), count_only_supplied_sha256=digest(without),
                        budget_state_sha256=digest(signal['measured_state']))
        candidate = self.saved_events[len(self.events)] if len(self.events) < len(self.saved_events) else {}
        failed = candidate.get('status') == 'known_paid_actor_measurement_failed'
        value, reason = None, None
        perform = self.cost is not None and bool(views['eligible_raw_messages'])
        has_count = self.count_index < len(self.counts) and self.counts[self.count_index].get('call_id') == call['id']
        if perform and (has_count or not failed):
            value, reason = self._count(call, without, tools, index)
        elif self.cost is not None:
            value = call['input_tokens']
        if failed:
            require(index == len(self.usage) and not selected_events
                    and candidate.get('action_returned_to_worker') is False,
                    'failed_paid_measurement_cannot_execute_or_continue')
            reason = reason or candidate.get('reason')
            require(type(reason) is str and reason and candidate.get('reason') == reason,
                    'measurement_failure_reason_changed')
            # A stop before the extra count has no count record. It remains
            # incomplete, never a certified zero exposure or free generation.
            require(has_count or self.summary['stop_reason'] in ('wall_limit', 'runtime_error',
                    'wall_limit_before_prefix_exposure_count', 'wall_limit_during_prefix_exposure_count'),
                    'unrecorded_measurement_failure_not_terminal')
            event = self._event('agent', call['id'], True, True)
            event.update(status='known_paid_actor_measurement_failed', input_tokens=call['input_tokens'],
                         raw_delta=None, positive_part=None, added_exposure=0,
                         action_returned_to_worker=False, reason=reason)
            self.blocked = True
            self.contract_failed = reason != 'BudgetStop'
            self._append(event)
            raise TraceStopped(reason)
        require(reason is None, 'failed_count_cannot_accrue_exposure')
        event = self._event('agent', call['id'], True, True)
        event.update(input_tokens=call['input_tokens'], raw_delta=None, positive_part=None,
                     added_exposure=0, bindings=bindings)
        bindings['native_count_performed'] = perform
        if self.cost is None:
            event['status'] = 'known_actor_before_first_paid_focus'
        else:
            delta = call['input_tokens'] - value
            self.exposure += max(0, delta)
            event.update(status='known_paid_actor', without_raw_input_tokens=value, raw_delta=delta,
                         positive_part=max(0, delta), added_exposure=max(0, delta))
        self._append(event)

    def stopped(self, exception_type):
        if exception_type != 'BudgetStop' and not self.blocked:
            self.contract_failed = self.blocked = True
            self.events.append(dict(role='control', status='contract_failed', reason=exception_type,
                                    exposure_after=self.exposure, focus_cost_after=self.cost))

    def finish(self):
        require(digest(self.events) == digest(self.saved_events), 'prefix_exposure_ledger_changed')
        require(digest(self.decisions) == digest(self.saved_decisions), 'prefix_exposure_decisions_changed')
        require(self.count_index == len(self.counts), 'unreplayed_exposure_count')
        expected = dict(version=VERSION, mode=self.mode, timing=self.timing, representation=self.representation, accumulated_exposure=self.exposure,
            previous_focus_cost=self.cost, blocked=self.blocked, event_count=len(self.events),
            events_sha256=digest(self.events),
            known_paid_actor_exposures=sum(e['status']=='known_paid_actor' for e in self.events),
            known_paid_focuses=sum(e['status']=='known_paid_focus' for e in self.events),
            incomplete_paid_actor_measurements=sum(e['status']=='known_paid_actor_measurement_failed' for e in self.events),
            negative_raw_deltas=sum(e.get('raw_delta') is not None and e['raw_delta'] < 0 for e in self.events),
            positive_part_indicator=True, realizable_savings_established=False, future_horizon_used=False,
            contract_failed=self.contract_failed, accounting_complete=not self.contract_failed and not self.blocked
                and all(c['status']=='complete' for c in self.counts), decision_count=len(self.decisions),
            decisions_sha256=digest(self.decisions),
            decision_differences_from_threshold=sum(d['offer'] != d['threshold_would_offer'] for d in self.decisions),
            decision_differences_from_exposure=sum(d['offer'] != d['exposure_would_offer'] for d in self.decisions),
            extra_native_counts=len(self.counts), count_only_generation_calls=0, all_count_time_in_shared_wall=True)
        actual = dispatched_difference_counts(self.decisions, self.usage)
        expected.update(actual)
        require(digest(self.summary.get('prefix_exposure_control')) == digest(expected),
                'prefix_exposure_summary_changed')
        return dict(**actual, prefix_exposure_contract_failed=self.contract_failed,
                    prefix_exposure_accounting_complete=expected['accounting_complete'],
                    prefix_exposure_control=expected,
                    decision_differences_from_threshold=expected['decision_differences_from_threshold'],
                    decision_differences_from_exposure=expected['decision_differences_from_exposure'],
                    exposure_native_count_recomputed=False, exposure_native_counts_bound_to_inputs=True,
                    exposure_shared_checkpoint_formatter=True)


def audit_trace(folder, config, conversation):
    require(type(config.get('checkpoint_trigger_input_tokens')) is int and
            config['checkpoint_trigger_input_tokens'] == 8192, 'fixed_P143_audit_8192_threshold')
    require(config['checkpoint_policy'] == 'rolling_separate'
            and config.get('checkpoint_representation_mode') in MODES,
            'explicit_separate_prefix_exposure_audit_required')
    mode = 'separate'
    axis_timing, axis_representation = timing_for(config['checkpoint_representation_mode']), representation_for(config['checkpoint_representation_mode'])
    require(config.get('checkpoint_timing') == axis_timing and
            config.get('checkpoint_representation') == axis_representation,
            'P143_factor_configuration_changed')
    require(type(config.get('rolling_checkpoint_max_opportunities')) is int and
            config.get('rolling_checkpoint_max_opportunities') == 2
            and type(config.get('rolling_min_fresh_turns')) is int
            and config.get('rolling_min_fresh_turns') == 3
            and config.get('inline_checkpoint_requirement') == (
                'required_when_run_python' if mode == 'inline' else 'not_applicable'),
            'fixed_rolling_audit_limits_required')

    def saved(name, default=None):
        path = folder / (name + '.json')
        return read(path) if path.exists() else deepcopy(default)

    summary, usage, terminal, admissions, events, spans = [saved(n) for n in (
        'summary', 'usage', 'terminal_usage', 'admissions', 'events', 'spans')]
    admissions = admissions or []
    representation_views = saved('checkpoint_representation_views', [])
    require(type(representation_views) is list, 'P143_representation_views_required')
    signals, views, controls, counts, offers, closed = [saved(n, []) for n in (
        'budget_observations', 'rolling_history_views', 'rolling_controls',
        'rolling_input_counts', 'rolling_offers_private', 'rolling_closed_private')]
    require(attempt_usage(SimpleNamespace(calls=terminal, admissions=admissions)) == usage,
            'shared_dispatch_accounting_changed')
    budgets, total = budget_before_calls(usage, events, 0, config)
    require(summary['model_calls'] == len(usage)
            and summary['known_total_tokens'] == total['known_total_tokens']
            and summary['unknown_usage_calls'] == total['unknown_usage_calls']
            and summary['api_requests'] == total['suffix_api_requests'], 'worker_accounting_changed')
    require(len(usage) <= config['max_calls']
            and total['known_total_tokens'] <= config['max_total_tokens']
            and total['suffix_api_requests'] <= config['max_api_requests'], 'shared_budget_exceeded')
    require(all(c['role'] in ('agent', 'focus') for c in usage)
            and (mode != 'inline' or all(c['role'] == 'agent' for c in usage)),
            'unplanned_model_role')
    ids = [e['span_id'] for e in events]
    require(len(ids) == len(set(ids)) and set(ids) == set(spans), 'event_archive_mismatch')
    receipts = [e['api_execution'] for e in events if 'api_execution' in e]
    require(receipts == summary['api_execution_receipts'], 'invocation_receipts_changed')
    require(sum(e['effects_unknown'] for e in events if e['api_request_sent']) ==
            summary['unknown_effect_requests'], 'unknown_effect_accounting_changed')
    for event in events:
        if event['api_request_sent']:
            receipt = event.get('api_execution')
            require(receipt and receipt['bridge_request_sent'] and not receipt['automatic_retries'],
                    'sent_API_requires_one_typed_receipt')
            if receipt['status'] == 'raised':
                require(not event['new_tools'] and 'api_error' in spans[event['span_id']]['observation'],
                        'confirmed_exception_presentation_changed')
        elif event['stage'] == 'model_tool':
            require('api_execution' not in event, 'outer_tool_cannot_send_API')
        require('inline_transport' not in event or (mode == 'inline' and event['stage'] == 'model_tool'),
                'unexpected_inline_transport')
    dispatches = [a for a in admissions if a.get('model_request_started')]
    require([a['next_call_id'] for a in dispatches] == [c['id'] for c in usage],
            'all_shared_attempts_required')
    signal_map = {s['next_call_id']: s for s in signals}
    view_map = {v['next_agent_call_id']: v for v in views}
    require(len(signal_map) == len(signals) and len(view_map) == len(views)
            and set(signal_map) == set(view_map), 'unique_actor_signal_and_view_required')
    require([s['next_call_id'] for s in signals if s['model_attempted']] ==
            [c['id'] for c in usage if c['role'] == 'agent'], 'actor_signal_attempts_changed')
    control = AuditRepresentationCheckpoint(config['checkpoint_representation_mode'])
    exposure = RepresentationExposureAudit(folder, config, summary, usage, saved)

    expected_controls, expected_offers, expected_closed, checks = [], [], [], []
    expected_representation_views = []
    prefix_records = []
    timing_decision_prefixes = []
    first_checkpoint = None
    second_opportunity = None
    prior, index, count_index = {}, 0, 0
    last_wall = config['max_wall_seconds']
    seen_signals = []

    def api_before():
        prefix = {c['id'] for c in usage[:index]}
        return sum(e['api_request_sent'] for e in events if e['call'] in prefix)

    def supplied(base):
        return notification(base, task_snapshot(config, usage[:index], api_before(), 0),
                            'not_exposed')[0]

    def take_count(role, purpose, messages, tools):
        nonlocal count_index
        if count_index == len(counts) and index == len(usage) and 'wall_limit' in summary['stop_reason']:
            raise TraceStopped('BudgetStop')
        require(count_index < len(counts), 'expected_native_count_missing')
        count = counts[count_index]
        count_index += 1
        require(count['role'] == role and count['after_model_calls'] == index
                and count['purpose'] == purpose and count['messages_sha256'] == digest(messages)
                and count['tools_sha256'] == digest(tools), 'native_count_not_bound_to_exact_input')
        if count['status'] == 'failed':
            require(index == len(usage) and count_index == len(counts), 'failed_count_must_stop')
            raise TraceStopped(count['exception_type'])
        require(count['status'] == 'complete' and type(count['input_tokens']) is int
                and count['input_tokens'] > 0, 'positive_native_count_required')
        return count

    def resolve(base):
        nonlocal first_checkpoint
        if control.pending is None:
            return
        pending = control.pending
        require(pending['stage'] == 'closed' and pending.get('value') is not None,
                'rolling_turn_must_close_before_next_request')
        control._check(base)
        require(len(base) == control._bound_length, 'new_turn_before_resolution')
        a = take_count('agent', 'ordinary_next_input', supplied(pending['views']['ordinary']), CODE_TOOLS)
        b = take_count('agent', 'compacted_next_input', supplied(pending['views']['compacted']), CODE_TOOLS)
        decision = control.decide(a['input_tokens'], b['input_tokens'])
        if decision['accepted'] and control.revision == 1:
            first_checkpoint = dict(opportunity_index=decision['opportunity_index'], cutoff=control.cutoff, summary_note_sha256=digest(control.summary_notes[0]),
                summary_notes_sha256=digest(control.summary_notes), after_model_calls=index,
                fragment_budget=_audit_fragment_budget(control._values))
        expected_controls.append({'status': 'checkpoint_decided', 'after_model_calls': index, **decision})

    def reject_unstarted(role):
        cid = f'call_{index + 1:03d}'
        pending = [a for a in admissions if a['next_call_id'] == cid]
        require(index == len(usage) and len(pending) <= 1
                and all(not a.get('model_request_started') and a['role'] == role for a in pending),
                'unattempted_admission_changed')
        if pending:
            if 'admitted' in pending[0]:
                validate_admission(pending[0], config['max_total_tokens'] - total['known_total_tokens'], config)
            return pending[0].get('exception_type', 'BudgetStop')
        require(summary['stop_reason'] in ('call_limit', 'wall_limit', 'user_stop'),
                'missing_unattempted_admission')
        return 'BudgetStop'

    def consume(role, messages, tools, offered=False):
        nonlocal index
        if index == len(usage):
            raise TraceStopped(reject_unstarted(role))
        call, admission, budget = usage[index], dispatches[index], budgets[index]
        cid = f'call_{index + 1:03d}'
        require(call['id'] == cid and call['role'] == role and admission['role'] == role,
                'sequential_shared_role_identity_required')
        choice = validate_admission(admission, budget['remaining_tokens_before'], config)
        require(choice['admitted'], 'generation_after_budget_rejection')
        cfg = {**config['model'], 'temperature': config['agent_temperature'] if role == 'agent'
               else config['draft_temperature'],
               'seed': config['seed'] + sum(c['role'] == role for c in usage[:index]),
               'num_predict': choice['selected_output_cap'], 'cache_prompt': index > 0}
        transport = agent_payload if role == 'agent' else summary_payload
        request_path, response_path = folder / cid / 'request.json', folder / cid / 'response.json'
        request = read(request_path) if request_path.exists() else None
        response = read(response_path) if response_path.exists() else None
        missing = call.get('error_kind') == 'dispatched_without_terminal_usage'
        require(request is None or request == transport(cfg, messages, tools), 'actual_rolling_request_differs')
        if missing:
            require(response is None and call['server_receipt_confirmed'] is False,
                    'missing_terminal_cannot_gain_receipt')
        else:
            require(request is not None and response is not None
                    and call['predicted_input_tokens'] == choice['input_tokens']
                    and call['output_cap'] == choice['selected_output_cap'], 'terminal_reservation_changed')
        selected_events = [e for e in events if e['call'] == cid]
        require(role == 'agent' or not selected_events, 'summary_cannot_execute_API')
        checks.append({'call_id': cid, 'role': role, 'status': call['status'],
            **{k: call.get(k) for k in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'finish_reason')},
            'request_sha256': sha(request_path) if request_path.exists() else None,
            'response_sha256': sha(response_path) if response_path.exists() else None,
            'API_requests': sum(e['api_request_sent'] for e in selected_events),
            'inline_offered': offered if role == 'agent' else False,
            'known_assistant_message_sha256': None})
        index += 1
        if call['status'] != 'ok':
            require(index == len(usage) and not selected_events and all(call[k] is None and
                (response is None or response[k] is None) for k in ('input_tokens', 'output_tokens')),
                'unknown_usage_executed_or_imputed')
            raise TraceStopped(admission['exception_type'])
        parsed = parse_response(read(folder / cid / 'raw_response.json'))
        require(all(parsed[k] == response[k] for k in parsed), 'raw_terminal_normalization_changed')
        require(all(call.get(k) == response.get(k) for k in (
            'input_tokens', 'output_tokens', 'cached_input_tokens'))
            and call['finish_reason'] == response['done_reason'], 'terminal_usage_changed')
        require(response['input_tokens'] == choice['input_tokens']
                and response['output_tokens'] <= choice['selected_output_cap'], 'terminal_exceeded_admission')
        checks[-1]['known_assistant_message_sha256'] = digest(response['message'])
        prefix_records.append(dict(call_id=cid,role=role,status=call['status'],
            request_sha256=checks[-1]['request_sha256'],message=deepcopy(response['message'])))
        if index == 1:
            cold = cache_measurement('cold_1', response, response['input_tokens'])
            require(role == 'agent' and signal_map[cid].get('first_input_measurement') == cold,
                    'first_cache_measurement_changed')
            require(cold['state_confirmed'] or (index == len(usage) and not selected_events),
                    'execution_after_non_cold_first_request')
        return call, response, selected_events

    while True:
        if index and usage[index-1]['status'] != 'ok':
            break
        cid = f'call_{index+1:03d}'
        if cid not in signal_map and not any(c['after_model_calls'] == index for c in counts[count_index:]):
            break
        base, _ = conversation.for_model(config['observation_page_characters'])
        offered = None
        try:
            resolve(base)
            if control.opportunities < control.max_opportunities:
                working = control.view(base)
                count = take_count('agent', 'trigger', supplied(working), CODE_TOOLS)
                decision = exposure.decision(control, base, count['input_tokens'], index)
                try:
                    if index:
                        identity = canonical_prefix_evidence(prefix_records, conversation.messages())
                    else:
                        archive = conversation.messages()
                        require(len(archive) == 2 and [m['role'] for m in archive] == ['system','user'],
                                'initial_prefix_archive_required')
                        identity = dict(version=IDENTITY_VERSION, validation_status='valid', record_count=0,
                            agent_calls=0, focus_calls=0, protocol_call_count=0,
                            raw_archive_sha256=digest(archive), canonical_archive_sha256=digest(archive), sequence=[])
                except PrefixIdentityError as error:
                    identity = {'status':'invalid','error_type':type(error).__name__}
                next_call = usage[index] if index < len(usage) else None
                timing_decision_prefixes.append(dict(after_model_calls=index, offer=decision['offer'],
                    identity=identity, state=dict(opportunities=control.opportunities, revision=control.revision,
                        cutoff=control.cutoff, last_closed_turns=control._last_closed_turns,
                        prior_summary_notes_sha256=digest(control.summary_notes),
                        accumulated_exposure=exposure.exposure, previous_focus_cost=exposure.cost,
                        measured_input_tokens=count['input_tokens'], count_messages_sha256=count['messages_sha256'],
                        count_tools_sha256=count['tools_sha256'],
                        budget_state_sha256=digest(task_snapshot(config, usage[:index], api_before(), 0)),
                        first_checkpoint_sha256=digest(first_checkpoint)),
                    next_dispatch=None if next_call is None else dict(call_id=next_call['id'],
                        role=next_call['role'],status=next_call['status'])))
                offered = control.begin(base, count['input_tokens'], CODE_TOOLS,
                                        repeat_ready=decision['offer'])
                require((offered is not None) == decision['offer'], 'exposure_offer_disagrees')
                expected_controls.append({'status': 'checkpoint_offered' if offered else 'below_trigger_or_not_eligible',
                    'after_model_calls': index, 'trigger_input_tokens': count['input_tokens'],
                    'source_archive_sha256': digest(base), 'visible_history_sha256': digest(working),
                    'opportunities': control.opportunities, 'semantics_verified': False})
                if offered is not None:
                    expected_offers.append({'after_model_calls': index, 'offer': deepcopy(offered)})
                    if offered['opportunity_index'] == 2:
                        require(second_opportunity is None, 'one_second_opportunity_only')
                        second_opportunity = dict(after_model_calls=index, delta_requested=offered['delta_requested'],
                            previous_cutoff=offered['previous_cutoff'], candidate_cutoff=offered['cutoff'],
                            accumulated_exposure=exposure.exposure, previous_focus_cost=exposure.cost,
                            first_checkpoint=deepcopy(first_checkpoint),
                            prior_request_output_sequence=[{k:c[k] for k in ('call_id','role','status','request_sha256',
                                'known_assistant_message_sha256')} for c in checks],
                            all_prior_terminal_usage_known=all(c['status']=='ok' for c in checks),
                            candidate_focus_messages_sha256=digest(offered['summary_messages']),
                            prior_summary_notes_sha256=digest(control.summary_notes))
                        try:
                            identity=canonical_prefix_evidence(prefix_records,conversation.messages())
                        except PrefixIdentityError as error:
                            identity={'status':'invalid','error_type':type(error).__name__}
                        second_opportunity['protocol_prefix_identity']=identity
            if offered is not None and mode == 'separate':
                before = index
                event = {'status': 'separate_summary_started', 'opportunity_index': offered['opportunity_index'],
                    'after_model_calls': index, 'model_attempted': False, 'summary_calls': 0,
                    'summary_known_tokens': 0, 'semantics_verified': False}
                position = len(expected_controls)
                expected_controls.append(event)
                try:
                    count = take_count('focus', 'separate_summary_input', offered['summary_messages'], [])
                    # The control log stores the counter result, without its envelope.
                    result = {k: v for k, v in count.items() if k not in (
                        'role', 'purpose', 'after_model_calls', 'messages_sha256', 'tools_sha256', 'status')}
                    reserve = count['input_tokens'] + offered['trigger_input_tokens'] + 2 * config['max_output_tokens']
                    event.update(summary_input_count=result, screening_tokens_using_current_agent_input=reserve)
                    spent = sum(c['input_tokens']+c['output_tokens'] for c in usage[:index] if c['status']=='ok')
                    reason = ('insufficient_shared_call_budget' if index + 2 > config['max_calls'] else
                              'insufficient_shared_token_budget' if spent + reserve > config['max_total_tokens'] else
                              'summary_context_limit' if count['input_tokens']+config['max_output_tokens'] > config['model']['num_ctx'] else None)
                    if reason:
                        event.update(status='separate_summary_not_dispatched',
                                     decision=control.skip_unstarted_summary(base, reason))
                    else:
                        call, response, _ = consume('focus', offered['summary_messages'], [])
                        projected = control.close_separate(base, response['message'], response['done_reason'], usage_known=True)
                        expected_closed.append({'mode': 'separate', 'call_id': call['id'],
                            'opportunity_index': offered['opportunity_index'], 'source_archive_sha256': digest(base),
                            'ordinary_sha256': projected['ordinary_sha256'], 'compacted_sha256': projected['compacted_sha256']})
                        event['status'] = 'separate_summary_closed'
                        resolve(base)
                except TraceStopped as error:
                    event.update(status='separate_summary_aborted', exception_type=error.exception_type)
                    raise
                finally:
                    relevant = usage[before:index]
                    missing = sum(c.get('terminal_usage_recorded') is False for c in relevant)
                    require(position < len(controls), 'summary_control_record_missing')
                    wall = controls[position].get('control_wall_seconds')
                    require(type(wall) in (int, float) and math.isfinite(wall) and
                            0 <= wall <= summary['wall_seconds'], 'invalid_summary_control_time')
                    event.update(summary_calls=len(relevant)-missing,
                        summary_known_tokens=sum(c['input_tokens']+c['output_tokens'] for c in relevant if c['status']=='ok'),
                        model_attempted=bool(relevant), dispatched_without_terminal_usage=missing,
                        unknown_usage_calls=sum(c['status']!='ok' for c in relevant), control_wall_seconds=wall)
                    exposure.focus(relevant, f'call_{before+1:03d}')
            inline = offered is not None and mode == 'inline'
            working, tools = (offered['messages'], offered['tools']) if inline else (control.view(base), CODE_TOOLS)
            cid = f'call_{index+1:03d}'
            signal = signal_map.get(cid)
            require(signal is not None, 'missing_actor_signal')
            seen_signals.append(cid)
            state = signal['measured_state']
            expected_state = task_snapshot(config, usage[:index], api_before(), 0)
            wall = state['remaining']['wall_seconds_at_snapshot']
            expected_state['remaining']['wall_seconds_at_snapshot'] = wall
            require(state == expected_state and 0 <= wall <= last_wall, 'actor_shared_budget_notice_changed')
            last_wall = wall
            messages, visible = notification(working, state, 'not_exposed')
            require(signal['visible_state'] == visible and signal['time_visibility'] == 'not_exposed'
                and signal['model_messages_sha256'] == digest(messages)
                and signal['model_tools_sha256'] == digest(tools)
                and signal['cache_prompt'] == (index > 0), 'actor_notice_or_schema_changed')
            require(view_map[cid] == {'next_agent_call_id': cid,
                'original_history_sha256': digest(base), 'working_history_sha256': digest(working),
                'tools_sha256': digest(tools), 'inline_offered': inline,
                'checkpoint_revision': control.revision, 'checkpoint_used': control.checkpoint is not None,
                'archive_deleted': False, 'semantics_verified': False}, 'rolling_projection_changed')
            expected_representation_views.append(dict(next_call_id=cid, checkpoint_revision=control.revision,
                fragment_count=control.fragment_count, summary_notes_sha256=digest(control.summary_notes),
                delta_view=control.delta_applied, model_messages_sha256=digest(messages),
                model_tools_sha256=digest(tools), model_attempted=signal['model_attempted'],
                terminal_usage_recorded=signal['terminal_usage_recorded'], usage_unknown=signal['usage_unknown']))
            if not signal['model_attempted']:
                reject_unstarted('agent')
                break
            call, response, selected_events = consume('agent', messages, tools, inline)
            exposure.actor(control, base, signal, call, tools, index, selected_events)
        except TraceStopped as stopped:
            if index and usage[index-1]['role'] == 'agent' and usage[index-1]['status'] != 'ok':
                exposure.unknown_actor(usage[index-1])
            exposure.stopped(stopped.exception_type)
            break
        outer_events = [e for e in selected_events if e['stage'] == 'model_tool']
        if outer_events:
            split = split_inline_response(response['message'], offered=inline,
                finish_reason=response['done_reason'], usage_known=True) if mode == 'inline' else None
            outer = [spans[e['span_id']] for e in outer_events]
            execution = split['execution_message'] if split else response['message']
            for i, event in enumerate(outer_events):
                binding = None if split is None else split['binding']
                if binding is not None:
                    expected_binding = {'version': 'inline_checkpoint_transport_v01',
                        'original_payload_sha256': split['original_payload_sha256'], **binding,
                        'status': split['status'], 'execution_success_verified': False, 'semantics_verified': False}
                    require(len(outer_events) == 1 and event.get('inline_transport') == expected_binding,
                            'inline_execution_binding_changed')
                else:
                    require('inline_transport' not in event, 'unexpected_inline_transport_binding')
                path = folder / 'programs' / f'{cid}_{i+1:02d}' / 'input_private.json'
                calls = execution.get('tool_calls') or []
                fn = calls[i]['function'] if calls else None
                needs_program = fn and fn['name'] == 'run_python' and 'status' in outer[i]['observation']
                require(not needs_program or path.exists(), 'submitted_program_source_missing')
                if path.exists():
                    args, payload = json.loads(fn['arguments']), read(path)
                    require(set(args) == {'code', 'span_ids'} and payload['code'] == args['code']
                        and payload['observations'] == selected_receipts(args['span_ids'], prior),
                        'submitted_program_or_receipt_selection_changed')
            conversation.append(response['message'], outer)
            if inline:
                after, _ = conversation.for_model(config['observation_page_characters'])
                projected = control.close_inline(after, split, usage_known=True)
                expected_closed.append({'mode': 'inline', 'call_id': cid,
                    'opportunity_index': offered['opportunity_index'], 'source_archive_sha256': digest(after),
                    'split': split, 'ordinary_sha256': projected['ordinary_sha256'],
                    'compacted_sha256': projected['compacted_sha256']})
                expected_controls.append({'status': 'inline_turn_closed', 'opportunity_index': offered['opportunity_index'],
                    'after_model_calls': index, 'split_status': split['status'],
                    'ordinary_sha256': projected['ordinary_sha256'], 'compacted_sha256': projected['compacted_sha256'],
                    'semantics_verified': False})
        else:
            require(index == len(usage) and not selected_events and summary['stop_reason'] in (
                'runtime_error', 'wall_limit', 'api_request_limit', 'user_stop', 'cleanup_error'),
                'known_response_without_execution_record')
        prior.update({e['span_id']: spans[e['span_id']] for e in selected_events})

    require(index == len(usage) and count_index == len(counts) and digest(controls) == digest(expected_controls),
            'control_timeline_changed')
    require(digest(offers) == digest(expected_offers) and digest(closed) == digest(expected_closed),
            'private_checkpoint_state_changed')
    require(seen_signals == [s['next_call_id'] for s in signals], 'unreplayed_actor_signal')
    require(saved('conversation_private', conversation.messages()) == conversation.messages(), 'archive_replay_changed')
    terminals = {c['id']: c for c in terminal}
    for signal in signals:
        if signal['model_attempted']:
            call = terminals.get(signal['next_call_id'])
            require(signal['terminal_usage_recorded'] == (call is not None)
                and signal['usage_unknown'] == (call is None or call['status'] != 'ok'),
                'actor_signal_terminal_status_changed')
    known = [c for c in usage if c['status'] == 'ok']
    by_role = {role: {'calls': sum(c['role']==role for c in usage),
        'unknown_usage': sum(c['role']==role and c['status']!='ok' for c in usage),
        'input_tokens': sum(c['input_tokens'] for c in known if c['role']==role),
        'output_tokens': sum(c['output_tokens'] for c in known if c['role']==role)} for role in ('agent','focus')}
    require(summary['usage_by_role'] == by_role, 'role_totals_changed')
    pending = control.pending
    expected_summary = {'policy': config['checkpoint_policy'], 'opportunity_used': control.opportunities > 0,
        'opportunities': control.opportunities, 'max_opportunities': 2,
        'installations': control.revision, 'checkpoint_installed': control.revision > 0,
        'decisions': control.events, 'pending_stage': pending['stage'] if pending else None,
        'valid_checkpoint_pending_without_next_request': bool(pending and pending['stage']=='closed' and pending.get('value') is not None),
        'separate_summary_calls': by_role['focus']['calls'], 'judge_calls': 0,
        'all_summary_and_agent_costs_in_shared_budget': True,
        'schema_checkpoint_required': mode == 'inline', 'tool_choice_forced': False,
        'control_cost_included_in_work_wall': True, 'archive_deleted': False,
        'semantic_fidelity_verified': False, 'task_quality_established': False, 'novel_method_claim': False}
    require(digest(summary['checkpoint_control']) == digest(expected_summary), 'rolling_summary_disposition_changed')
    exposure_result = exposure.finish()
    require(digest(representation_views) == digest(expected_representation_views), 'P143_actor_representation_view_changed')
    shown = [v for v in expected_representation_views if v['delta_view'] and v['model_attempted']]
    representation_summary = dict(version=VERSION, mode=config['checkpoint_representation_mode'],
        timing=axis_timing, representation=axis_representation, max_opportunities=2,
        fragment_count=control.fragment_count,
        delta_installations=sum(e['accepted'] and e.get('delta_applied',False) for e in control.events),
        actual_delta_actor_calls=len(shown),
        actual_delta_known_actor_calls=sum(v['terminal_usage_recorded'] and not v['usage_unknown'] for v in shown),
        actual_delta_unknown_actor_calls=sum(v['usage_unknown'] for v in shown),
        actor_view_count=len(expected_representation_views), actor_views_sha256=digest(expected_representation_views),
        contract_failed=exposure_result['prefix_exposure_contract_failed'],
        accounting_complete=exposure_result['prefix_exposure_accounting_complete'],
        first_summary_contract_unchanged=True, initial_actor_interface_unchanged=True,
        full_actor_native_count_required=True, archive_deleted=False,
        semantic_preservation_established=False, novel_method_claim=False)
    require(digest(summary.get('checkpoint_representation_control')) == digest(representation_summary),
            'P143_representation_summary_changed')
    envelope_offers = [o for o in expected_offers if prompt_policy_for(config['checkpoint_representation_mode'])=='explicit_delta_object'
                       and o['offer']['delta_requested']]
    envelope_dispatches = [usage[o['after_model_calls']] for o in envelope_offers
        if o['after_model_calls'] < len(usage) and usage[o['after_model_calls']]['role']=='focus']
    envelope_summary = dict(version=VERSION, mode=config['checkpoint_representation_mode'],
        policy=prompt_policy_for(config['checkpoint_representation_mode']),
        underlying_representation_mode=base_mode_for(config['checkpoint_representation_mode']),
        object_delta_summary_prompt_sha256=OBJECT_DELTA_PROMPT_SHA256,
        object_prompt_offers=len(envelope_offers),object_prompt_dispatched_focus_calls=len(envelope_dispatches),
        object_prompt_known_focus_calls=sum(c['status']=='ok' for c in envelope_dispatches),
        object_prompt_unknown_focus_calls=sum(c['status']!='ok' for c in envelope_dispatches),
        **{k:representation_summary[k] for k in ('actual_delta_actor_calls','actual_delta_known_actor_calls',
            'actual_delta_unknown_actor_calls','contract_failed','accounting_complete')},
        first_summary_unchanged=True,host_combines_fragments=True,parser_and_fragment_limits_unchanged=True,
        prompt_guarantees_object_output=False,novel_method_claim=False)
    require(digest(summary.get('delta_envelope_control'))==digest(envelope_summary),'P143_envelope_summary_changed')
    prefix_evidence = dict(second_opportunity_offered=second_opportunity is not None,
        first_checkpoint=first_checkpoint, second_opportunity=second_opportunity,
        no_same_seed_prefix_equivalence_assumed=True, strict_opaque_output_identifiers_not_normalized=True,
        validated_transport_reference_identity_reported=True,
        absence_of_second_opportunity_is_not_equal_prefix=True)
    return {**total, **exposure_result, 'checkpoint_representation_control': representation_summary,
        'delta_envelope_control':envelope_summary,
        'delta_envelope_contract_failed':envelope_summary['contract_failed'],
        'delta_envelope_accounting_complete':envelope_summary['accounting_complete'],
        **{k:envelope_summary[k] for k in ('object_prompt_offers','object_prompt_dispatched_focus_calls',
            'object_prompt_known_focus_calls','object_prompt_unknown_focus_calls')},
        'checkpoint_representation_contract_failed': representation_summary['contract_failed'],
        'checkpoint_representation_accounting_complete': representation_summary['accounting_complete'],
        'actual_delta_actor_calls': representation_summary['actual_delta_actor_calls'],
        'actual_delta_known_actor_calls': representation_summary['actual_delta_known_actor_calls'],
        'actual_delta_unknown_actor_calls': representation_summary['actual_delta_unknown_actor_calls'],
        'delta_installations': representation_summary['delta_installations'],
        'fragment_count': representation_summary['fragment_count'],
        'representation_second_opportunity': second_opportunity,
        'timing_decision_prefixes': timing_decision_prefixes,
        'representation_prefix_evidence': prefix_evidence,
        'representation_state_reconstructed_in_auditor': True,
        'shared_summary_parser_turn_grammar_and_note_formatters': True,
        'model_calls': len(usage), 'usage_by_role': by_role, 'request_checks': checks,
        'checkpoint_installed': control.revision > 0, 'checkpoint_installations': control.revision,
        'checkpoint_opportunity': control.opportunities, 'checkpoint_controls': controls,
        'input_count_records': len(counts), 'invocation_status_counts': dict(Counter(r['status'] for r in receipts)),
        'additional_model_calls': 0, 'additional_API_requests': 0, 'additional_tokenizer_calls': 0,
        'summary_semantics_verified': False}
