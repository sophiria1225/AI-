"""Compare recorded observations, never replace an authenticated request.

An origin group means the same earlier successful login request, including all
credential arguments. It is NOT a principal, permission, freshness or state
equivalence certificate. Every comparison is made after the current receipt.
"""
from collections import Counter
import json

from field_read_contract import READ_ONLY_APIS
from recorded_request_repetition import digest, returned_payload

MODES = ('exact', 'drop_auth_argument', 'login_request_origin')
LOGIN = 'spotify__login'
AUTH_READS = frozenset(('spotify__show_song_library', 'spotify__show_album_library',
                        'spotify__show_playlist_library', 'spotify__show_playlist'))


class ObservationIndex:
    """Bounded, historical equality counters with explicit authentication origin."""
    def __init__(self, max_entries=512, max_value_bytes=65536):
        if (type(max_entries) is not int or max_entries < 1
                or type(max_value_bytes) is not int or max_value_bytes < 1):
            raise ValueError('positive_bounds_required')
        self.max_entries = max_entries
        self.max_value_bytes = max_value_bytes
        self.groups, self.tokens, self.ambiguous = {}, {}, set()
        self.history = {m: {} for m in MODES}
        self.poisoned = False
        self.ordinal = 0
        self.bounds = Counter()

    def unknown_effect(self):
        # Old origin remains an historical fact, but is not used after an
        # unknown effect. The stripped-argument baseline stays descriptive.
        self.poisoned = True

    def observe(self, name, args, status, span, call_id, *, effects_unknown=False):
        if (type(name) is not str or type(args) is not dict
                or status not in ('returned', 'raised', 'unknown')):
            raise ValueError('typed_request_and_receipt_required')
        self.ordinal += 1
        if effects_unknown or status == 'unknown':
            self.unknown_effect()
        confirmed = status == 'returned' and not effects_unknown
        value_hash, value_bytes = None, None
        if confirmed:
            _, value_hash, value_bytes = returned_payload(span)
        row = dict(request_ordinal=self.ordinal, call_id=call_id, api_name=name,
                   receipt_status=status, effects_unknown=bool(effects_unknown),
                   kind='other', login_origin_group=None, repeated_successful_login=False,
                   auth_origin_known=False, origin_suppressed_by_unknown=self.poisoned,
                   online_replacement_permission=False, task_progress_established=False)
        if name == LOGIN:
            row['kind'] = 'spotify_login'
            if confirmed and not self.poisoned:
                raw = span['observation']['observation']
                try:
                    value = json.loads(raw) if isinstance(raw, str) else raw
                except ValueError:
                    value = None
                valid = (type(value) is dict and set(value) == {'access_token', 'token_type'}
                         and value['token_type'] == 'Bearer'
                         and type(value['access_token']) is str and bool(value['access_token']))
                if valid:
                    request_key = digest({'name': name, 'arguments': args})
                    repeated = request_key in self.groups
                    if not repeated and len(self.groups) < self.max_entries:
                        self.groups[request_key] = len(self.groups) + 1
                    group = self.groups.get(request_key)
                    token = value['access_token']
                    row['repeated_successful_login'] = repeated
                    row['login_origin_group'] = group
                    if group is not None and len(token.encode()) <= self.max_value_bytes:
                        if token in self.tokens and self.tokens[token] != group:
                            if len(self.ambiguous) < self.max_entries:
                                self.ambiguous.add(token)
                            else:
                                self.unknown_effect()
                                self.bounds['ambiguous_tokens'] += 1
                            self.tokens.pop(token, None)
                        elif token not in self.ambiguous:
                            if token in self.tokens or len(self.tokens) < self.max_entries:
                                self.tokens[token] = group
                            else:
                                self.bounds['token_bindings'] += 1
                    else:
                        self.bounds['login_origins'] += 1
                else:
                    row['login_shape_supported'] = False
            return row
        if name not in READ_ONLY_APIS:
            return row
        row['kind'] = 'declared_read'
        token = args.get('access_token') if name in AUTH_READS else None
        group = (self.tokens.get(token) if type(token) is str and token not in self.ambiguous
                 and not self.poisoned else None)
        row['auth_origin_known'] = group is not None
        row['login_origin_group'] = group
        exact = {'name': name, 'arguments': args}
        keys = {m: digest(exact) for m in MODES}
        if name in AUTH_READS and 'access_token' in args:
            others = {k: v for k, v in args.items() if k != 'access_token'}
            keys['drop_auth_argument'] = digest({'name': name, 'arguments': others,
                                                 'auth_comparison': 'omitted'})
            if group is not None:
                keys['login_request_origin'] = digest({'name': name, 'arguments': others,
                                                       'login_origin_group': group})
        usable = confirmed and value_bytes <= self.max_value_bytes
        row['current_returned_value_bytes'] = value_bytes
        row['value_comparison_available'] = usable
        if confirmed and not usable:
            self.bounds['value_bytes'] += 1
        for mode, key in keys.items():
            previous = self.history[mode].get(key)
            comparable = bool(previous and previous['returned']) and usable
            equal = comparable and previous['value_hash'] == value_hash
            row[mode] = dict(previous_request_ordinal=previous['ordinal'] if previous else None,
                previous_call_id=previous['call_id'] if previous else None,
                both_returned=comparable, value_equal=bool(equal) if comparable else None,
                value_equal_in_earlier_boundary=bool(equal and previous['call_id'] != call_id),
                different_auth_value=bool(previous and previous['token'] != token),
                comparison_only=True)
            entry = dict(ordinal=self.ordinal, call_id=call_id, returned=usable,
                         value_hash=value_hash if usable else None, token=token)
            if previous or len(self.history[mode]) < self.max_entries:
                self.history[mode][key] = entry
            else:
                self.bounds['query_entries_' + mode] += 1
        row['new_equal_observation_from_origin'] = (row['login_request_origin']['value_equal'] is True
                                                   and row['exact']['value_equal'] is not True)
        return row


def analyze(events, spans, usage, fixed_requests, *, max_entries=512, max_value_bytes=65536):
    if len(events) > 4000 or len(usage) > 80:
        raise ValueError('fixed_record_bounds_exceeded')
    ids = [u['id'] for u in usage]
    positions = {c: i for i, c in enumerate(ids)}
    ranks = [positions.get(e.get('call'), -1) for e in events]
    if (ids != [f'call_{i:03d}' for i in range(1, len(usage)+1)] or -1 in ranks
            or ranks != sorted(ranks) or len({e['span_id'] for e in events}) != len(events)
            or {e['span_id'] for e in events} != set(spans)):
        raise ValueError('complete_chronological_records_required')
    index = ObservationIndex(max_entries, max_value_bytes)
    rows = []
    for event in events:
        if type(event.get('api_request_sent')) is not bool:
            raise ValueError('explicit_send_status_required')
        if not event['api_request_sent']:
            if event.get('effects_unknown'):
                index.unknown_effect()
            continue
        span = spans[event['span_id']]
        action = span['action']; args = action['arguments']
        if type(args) is str:
            args = json.loads(args)
        receipt = event['api_execution']; fixed = fixed_requests[len(rows)]
        if (event.get('stage') != 'python_api' or receipt.get('bridge_request_sent') is not True
                or receipt.get('automatic_retries') != 0
                or fixed['request_ordinal'] != len(rows)+1 or fixed['call_id'] != event['call']
                or fixed['api_name'] != action['name']
                or fixed['request_sha256'] != digest({'name': action['name'], 'arguments': args})
                or fixed['receipt_status'] != receipt['status']
                or fixed['effects_unknown'] != bool(event.get('effects_unknown'))):
            raise ValueError('closed_P95_request_mismatch')
        rows.append(index.observe(action['name'], args, receipt['status'], span, event['call'],
                                   effects_unknown=bool(event.get('effects_unknown'))))
    if len(rows) != len(fixed_requests):
        raise ValueError('complete_request_cohort_required')
    calls = []
    streaks = Counter()
    for cid in ids:
        current = [q for q in rows if q['call_id'] == cid]
        reads = [q for q in current if q['kind'] == 'declared_read']
        logins = [q for q in current if q['kind'] == 'spotify_login']
        other = [q for q in current if q['kind'] == 'other']
        call = dict(call_id=cid, sent_requests=len(current), declared_reads=len(reads),
                    spotify_logins=len(logins), other_requests=len(other),
                    execution_redundant_established=False, intervention_performed=False)
        for mode in MODES:
            equal = sum(q[mode]['value_equal_in_earlier_boundary'] for q in reads)
            qualifies = bool(reads) and equal == len(reads) and not other and all(
                q['repeated_successful_login'] for q in logins) and not any(
                q['origin_suppressed_by_unknown'] for q in current)
            streaks[mode] = streaks[mode]+1 if qualifies else 0
            call[mode] = dict(read_receipts_seen_in_earlier_boundary=equal,
                all_reads_reobserved_with_only_repeated_logins=qualifies,
                consecutive_qualifying_boundaries=streaks[mode],
                fixed_two_boundary_candidate=streaks[mode] == 2)
        calls.append(call)
    return dict(requests=rows, model_boundaries=calls, bounds_rejected=dict(index.bounds),
                origin_groups=len(index.groups), ambiguous_token_count=len(index.ambiguous),
                final_unknown_effect=index.poisoned,
                online_replacement_permission=False, task_progress_established=False,
                measured_savings=None, intervention_performed=False,
                comparison_scope='Historical receipts grouped by exact arguments, omitted auth argument, or earlier successful identical login requests. No principal or state equivalence is asserted.')
