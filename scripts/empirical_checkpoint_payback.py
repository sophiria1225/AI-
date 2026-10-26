"""Ordinary empirical repeat-summary admission, not guaranteed amortization.

P6 already documented ceil(C/d): docs/P6_memory_update_costs.md. This controller
uses past measurements only. It does not establish future savings or quality.
"""
import math
from receipt_reasoning_history import digest, require

MODES = ('rolling_separate', 'empirical_payback')
VERSION = 'empirical_checkpoint_payback_v1'
REJECT_REASONS = ('payback_missing_prior_accepted', 'payback_nonpositive_prior_delta',
                  'payback_insufficient_call_horizon', 'payback_insufficient_wall_horizon')


def integer(value, name, minimum=0):
    require(type(value) is int and value >= minimum, 'invalid_' + name)
    return value


def finite(value, name):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            'invalid_' + name)
    return value


def evaluate_payback(*, mode, opportunity_index, calls, controls,
                     summary_input_tokens, output_cap, remaining_calls, remaining_wall_seconds):
    """Return a deterministic, value-free ledger entry from a closed prefix.

    The ordinary mode records the same hypothetical gate but does not apply it.
    Unknown usage or malformed histories are errors, never fabricated zeros.
    """
    require(mode in MODES, 'fixed_payback_mode_required')
    integer(opportunity_index, 'opportunity_index', 1)
    require(opportunity_index <= 3, 'fixed_maximum_opportunities_required')
    integer(summary_input_tokens, 'summary_input_tokens', 1)
    integer(output_cap, 'output_cap', 1)
    integer(remaining_calls, 'remaining_calls')
    finite(remaining_wall_seconds, 'remaining_wall_seconds')
    require(type(calls) is list and type(controls) is list, 'closed_prefix_lists_required')
    ids = set()
    for c in calls:
        require(type(c) is dict and c.get('role') in ('agent', 'focus')
                and c.get('status') == 'ok', 'known_closed_model_usage_required')
        require(type(c.get('id')) is str and c['id'] not in ids, 'unique_call_ids_required')
        ids.add(c['id'])
        integer(c.get('input_tokens'), 'past_input_tokens')
        integer(c.get('output_tokens'), 'past_output_tokens')
        finite(c.get('wall_seconds'), 'past_wall_seconds')
    require(all(type(x) is dict and type(x.get('status')) is str for x in controls),
            'well_formed_control_prefix_required')
    decided = [x for x in controls if x['status'] == 'checkpoint_decided']
    require(all(type(x.get('accepted')) is bool for x in decided), 'typed_checkpoint_decisions_required')
    accepted = [x for x in decided if x['accepted']]
    previous_index = 0
    for revision, entry in enumerate(accepted, 1):
        index = integer(entry.get('after_model_calls'), 'accepted_after_model_calls', 1)
        require(previous_index < index <= len(calls) and calls[index-1]['role'] == 'focus'
                and type(entry.get('revision')) is int and entry['revision'] == revision,
                'accepted_checkpoint_history_contradiction')
        previous_index = index
    require(len(accepted) < opportunity_index, 'accepted_count_exceeds_prior_opportunities')
    actors = [c for c in calls if c['role'] == 'agent'][-3:]
    focuses = [c for c in calls if c['role'] == 'focus']
    event = dict(version=VERSION, mode=mode, opportunity_index=opportunity_index,
        after_model_calls=len(calls), past_calls_sha256=digest(calls),
        past_controls_sha256=digest(controls), summary_input_tokens=summary_input_tokens,
        output_cap=output_cap, remaining_calls=remaining_calls,
        remaining_wall_seconds=remaining_wall_seconds,
        actor_wall_samples=[{'call_id':c['id'], 'wall_seconds':c['wall_seconds']} for c in actors],
        prior_focus_wall_samples=[{'call_id':c['id'], 'wall_seconds':c['wall_seconds']} for c in focuses],
        prior_revision=None, prior_checkpoint_sha256=None, prior_accepted_focus_call_id=None,
        prior_delta=None, prior_focus_paid_tokens=None, predicted_focus_token_cost=None,
        predicted_actor_horizon=None, actor_wall_estimate=None, focus_wall_estimate=None,
        required_wall_seconds=None, prediction_guaranteed=False, task_quality_established=False,
        novel_method_claim=False)
    if opportunity_index == 1:
        require(not focuses and not accepted, 'first_opportunity_has_prior_focus_or_checkpoint')
        reason, predicted = 'first_opportunity_ordinary', True
    elif not accepted:
        reason, predicted = 'payback_missing_prior_accepted', False
    else:
        prior = accepted[-1]
        index = integer(prior.get('after_model_calls'), 'accepted_after_model_calls', 1)
        require(index <= len(calls) and calls[index-1]['role'] == 'focus',
                'accepted_checkpoint_must_bind_prior_focus')
        revision = integer(prior.get('revision'), 'prior_revision', 1)
        ordinary = integer(prior.get('ordinary_input_tokens'), 'prior_ordinary_input', 1)
        compacted = integer(prior.get('compacted_input_tokens'), 'prior_compacted_input', 1)
        require(actors and focuses, 'repeat_requires_actor_and_focus_measurements')
        paid = calls[index-1]['input_tokens'] + calls[index-1]['output_tokens']
        delta = ordinary - compacted
        event.update(prior_revision=revision, prior_checkpoint_sha256=digest(prior),
            prior_accepted_focus_call_id=calls[index-1]['id'], prior_delta=delta,
            prior_focus_paid_tokens=paid)
        if delta <= 0:
            reason, predicted = 'payback_nonpositive_prior_delta', False
        else:
            cost = max(paid, summary_input_tokens + output_cap)
            horizon = (cost + delta - 1) // delta
            actor_wall = max(c['wall_seconds'] for c in actors)
            focus_wall = max(c['wall_seconds'] for c in focuses)
            required_wall = focus_wall + horizon * actor_wall
            finite(required_wall, 'required_wall_seconds')
            event.update(predicted_focus_token_cost=cost, predicted_actor_horizon=horizon,
                actor_wall_estimate=actor_wall, focus_wall_estimate=focus_wall,
                required_wall_seconds=required_wall)
            reason = ('payback_insufficient_call_horizon' if remaining_calls < 1 + horizon else
                      'payback_insufficient_wall_horizon' if remaining_wall_seconds < required_wall else
                      'empirical_horizon_fits')
            predicted = reason == 'empirical_horizon_fits'
    event.update(predicted_admit=predicted, predicted_reason=reason,
        applied=mode == 'empirical_payback',
        admitted=predicted if mode == 'empirical_payback' else True,
        reason=reason if mode == 'empirical_payback' else 'ordinary_baseline_unchanged')
    return event
