"""Descriptive P141 predecision identity, before the first timing divergence.

Inputs come from the independent saved-wire trace replay. Only validated transport
IDs can differ. No equal second-focus cutoff is required after timing diverges.
The first observed predicate divergence is retained even if its focus is unsent;
such a boundary is not counted as an actual timing intervention and is not
skipped to search for a more favorable later boundary. This is a metadata
comparison, not a causal guarantee or an adoption criterion.
"""
from checkpoint_prefix_identity_p140 import VERSION as IDENTITY_VERSION, valid_hash
from receipt_reasoning_history import digest

VERSION = 'P141_first_timing_dispatch_prefix_v1'
STATE_FIELDS = ('opportunities', 'revision', 'cutoff', 'last_closed_turns',
                'prior_summary_notes_sha256', 'accumulated_exposure',
                'previous_focus_cost', 'measured_input_tokens',
                'count_messages_sha256', 'count_tools_sha256', 'budget_state_sha256',
                'first_checkpoint_sha256')


def _require(value, reason):
    if not value:
        raise ValueError(reason)


def _valid(entry):
    _require(type(entry) is dict, 'decision_record_required')
    n = entry.get('after_model_calls')
    _require(type(n) is int and n >= 0 and type(entry.get('offer')) is bool,
             'typed_decision_required')
    state = entry.get('state')
    _require(type(state) is dict and set(state) == set(STATE_FIELDS), 'complete_state_required')
    for k in ('opportunities', 'revision', 'cutoff', 'last_closed_turns',
              'accumulated_exposure', 'measured_input_tokens'):
        _require(type(state[k]) is int and state[k] >= 0, 'typed_state_count_required')
    _require(state['previous_focus_cost'] is None or
             type(state['previous_focus_cost']) is int and state['previous_focus_cost'] >= 0,
             'typed_prior_cost_required')
    for k in STATE_FIELDS:
        if k.endswith('_sha256'):
            _require(valid_hash(state[k]), 'state_hash_required')
    identity = entry.get('identity')
    _require(type(identity) is dict and identity.get('version') == IDENTITY_VERSION
             and identity.get('validation_status') == 'valid', 'validated_identity_required')
    for k in ('record_count', 'agent_calls', 'focus_calls', 'protocol_call_count'):
        _require(type(identity.get(k)) is int and identity[k] >= 0, 'identity_count_type')
    seq = identity.get('sequence')
    _require(type(seq) is list and len(seq) == identity['record_count'] == n,
             'complete_prior_dispatch_sequence_required')
    _require(all(valid_hash(identity.get(k)) for k in
                 ('raw_archive_sha256', 'canonical_archive_sha256')), 'archive_hash_required')
    for i, item in enumerate(seq, 1):
        _require(type(item) is dict and set(item) == {'call_id', 'role', 'status',
                 'request_sha256', 'raw_assistant_message_sha256',
                 'canonical_assistant_message_sha256'}, 'sequence_fields')
        _require(item['call_id'] == f'call_{i:03d}' and item['role'] in ('agent', 'focus')
                 and item['status'] == 'ok', 'known_prior_sequence_required')
        _require(all(valid_hash(item[k]) for k in ('request_sha256',
                 'raw_assistant_message_sha256','canonical_assistant_message_sha256')), 'sequence_hashes')
    _require(identity['agent_calls'] == sum(s['role'] == 'agent' for s in seq)
             and identity['focus_calls'] == sum(s['role'] == 'focus' for s in seq), 'identity_counts')
    dispatch = entry.get('next_dispatch')
    _require(dispatch is None or type(dispatch) is dict and set(dispatch) == {'call_id','role','status'}
             and dispatch['call_id'] == f'call_{n+1:03d}' and dispatch['role'] in ('agent','focus')
             and type(dispatch['status']) is str, 'next_dispatch_binding')
    return identity


def timing_prefix_comparison(left, right):
    """Compare TDO to EDO only, with fail-closed malformed/unknown evidence."""
    result = dict(version=VERSION, boundary_present=False, after_model_calls=None,
                  strict_match=None, canonical_match=None, actual_dispatch_diverged=False,
                  both_dispatches_known=False, reason='timing_boundary_absent')
    try:
        _require(left.get('checkpoint_representation_mode') == 'threshold_delta_object'
                 and right.get('checkpoint_representation_mode') == 'exposure_delta_object',
                 'fixed_timing_pair_required')
        a, b = left.get('timing_decision_prefixes'), right.get('timing_decision_prefixes')
        _require(type(a) is list and type(b) is list, 'timing_evidence_required')
        strict = canonical = True
        last = -1
        for x, y in zip(a, b):
            ix, iy = _valid(x), _valid(y)
            _require(x['after_model_calls'] == y['after_model_calls'] > last, 'decision_alignment')
            last = x['after_model_calls']
            common = digest(x['state']) == digest(y['state'])
            raw_equal = digest(ix) == digest(iy)
            def normalized(evidence):
                return {k: v for k,v in evidence.items() if k not in ('raw_archive_sha256','sequence')} | {
                    'sequence': [{k:v for k,v in item.items() if k != 'raw_assistant_message_sha256'}
                                 for item in evidence['sequence']]}
            strict &= common and raw_equal
            canonical &= common and digest(normalized(ix)) == digest(normalized(iy))
            if x['offer'] != y['offer']:
                dx, dy = x['next_dispatch'], y['next_dispatch']
                actual = bool(dx and dy and dx['role'] == ('focus' if x['offer'] else 'agent')
                              and dy['role'] == ('focus' if y['offer'] else 'agent')
                              and dx['role'] != dy['role'])
                return result | dict(boundary_present=True, after_model_calls=last,
                    strict_match=bool(strict), canonical_match=bool(canonical),
                    actual_dispatch_diverged=actual,
                    both_dispatches_known=bool(actual and dx['status'] == dy['status'] == 'ok'),
                    reason='first_observed_timing_decision_divergence')
            # Earlier identical offers must have matched actual dispatch/terminal metadata.
            strict &= digest(x['next_dispatch']) == digest(y['next_dispatch'])
            canonical &= digest(x['next_dispatch']) == digest(y['next_dispatch'])
        return result
    except (ValueError, KeyError, TypeError, AttributeError):
        return result | dict(strict_match=False, canonical_match=False, reason='invalid_or_unaligned_prefix')
