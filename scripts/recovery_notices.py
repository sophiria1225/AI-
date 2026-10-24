"""Ordinary recovery controls over observations already received.

No request is elided. Equality after a receipt is not a permission, freshness,
progress or completion certificate. P96's three comparisons remain visible;
only its simple auth-argument-omission control can trigger a notice.
"""
from collections import Counter
import copy
import json
import time

from auth_origin_observations import MODES, ObservationIndex

POLICIES = ('none', 'generic', 'factual')
GENERIC = ('Review the remaining user requirements and your existing Python variables '
           'before selecting the next action. All tools remain available; choose any '
           'new reads or checks needed to finish correctly.')
FACT = ('In each of the last two completed model turns, every sent API request was '
        'either a monitored Spotify read or a repeated successful Spotify login. '
        'Each read returned the same complete value as its most recent matching '
        'read from an earlier turn, comparing arguments with access_token omitted. '
        'This comparison does not establish completion, lack of local progress, '
        'current authorization, or the validity of a future result. ')
NOTICES = {p: '<recovery_review_v1>\n' + (FACT if p == 'factual' else '')
           + GENERIC + '\n</recovery_review_v1>' for p in ('generic', 'factual')}


class RecoveryMonitor:
    """Online version of the frozen P96 boundary predicate, one offer per trial."""
    def __init__(self, policy):
        if policy not in POLICIES:
            raise ValueError('fixed_recovery_policy_required')
        self.policy = policy
        self.index = ObservationIndex(512, 65536)
        self.requests, self.boundaries, self.offers = [], [], []
        self.streaks = Counter()
        self.active_call, self.current = None, []
        self.pending = None
        self.offered = False
        self.controller_wall_seconds = 0.0

    def begin(self, call_id):
        if self.active_call is not None or call_id != f'call_{len(self.boundaries)+1:03d}':
            raise ValueError('chronological_complete_boundary_required')
        self.active_call, self.current = call_id, []

    def observe(self, row):
        began = time.monotonic()
        try:
            if self.active_call is None or type(row.get('api_request_sent')) is not bool:
                raise ValueError('active_boundary_and_explicit_send_required')
            if not row['api_request_sent']:
                if row.get('effects_unknown'):
                    self.index.unknown_effect()
                return
            receipt = row['api_execution']
            if receipt.get('bridge_request_sent') is not True or receipt.get('automatic_retries') != 0:
                raise ValueError('typed_zero_retry_receipt_required')
            action = row['action']
            args = action['arguments']
            if type(args) is str:
                args = json.loads(args)
            seen = self.index.observe(action['name'], args, receipt['status'], row,
                self.active_call, effects_unknown=bool(row.get('effects_unknown')))
            self.requests.append(seen)
            self.current.append(seen)
        finally:
            self.controller_wall_seconds += time.monotonic() - began

    def finish(self):
        began = time.monotonic()
        try:
            if self.active_call is None:
                raise ValueError('active_boundary_required')
            reads = [q for q in self.current if q['kind'] == 'declared_read']
            logins = [q for q in self.current if q['kind'] == 'spotify_login']
            other = [q for q in self.current if q['kind'] == 'other']
            result = dict(call_id=self.active_call, sent_requests=len(self.current),
                declared_reads=len(reads), spotify_logins=len(logins), other_requests=len(other),
                execution_redundant_established=False)
            for mode in MODES:
                equal = sum(q[mode]['value_equal_in_earlier_boundary'] for q in reads)
                qualifies = bool(reads) and equal == len(reads) and not other and all(
                    q['repeated_successful_login'] for q in logins) and not self.index.poisoned
                self.streaks[mode] = self.streaks[mode]+1 if qualifies else 0
                result[mode] = dict(read_receipts_seen_in_earlier_boundary=equal,
                    all_reads_reobserved_with_only_repeated_logins=qualifies,
                    consecutive_qualifying_boundaries=self.streaks[mode],
                    fixed_two_boundary_candidate=self.streaks[mode] == 2)
            self.boundaries.append(result)
            if result['drop_auth_argument']['fixed_two_boundary_candidate'] and not self.offered:
                self.offered = True
                offer = dict(after_call=self.active_call, policy=self.policy,
                    selected_detector='drop_auth_argument', next_call_id=None,
                    included_in_supplied_messages=False, model_attempted=False)
                self.offers.append(offer)
                if self.policy != 'none':
                    self.pending = offer
            self.active_call, self.current = None, []
            return result
        finally:
            self.controller_wall_seconds += time.monotonic() - began

    def supply(self, messages, next_call_id):
        """Ephemeral input only. The bound conversation is never changed."""
        if self.pending is None:
            return messages, None
        if self.active_call is not None or next_call_id != f'call_{len(self.boundaries)+1:03d}':
            raise ValueError('notice_must_follow_completed_boundary')
        supplied = copy.deepcopy(messages)
        supplied[-1]['content'] += '\n' + NOTICES[self.policy]
        offer = self.pending
        offer.update(next_call_id=next_call_id, included_in_supplied_messages=True,
                     notice_characters=len(NOTICES[self.policy]))
        self.pending = None
        return supplied, offer

    def report(self):
        return dict(policy=self.policy, selected_detector='drop_auth_argument',
            requests=self.requests, model_boundaries=self.boundaries, offers=self.offers,
            active_incomplete_boundary=self.active_call,
            bounds_rejected=dict(self.index.bounds), unknown_effect=self.index.poisoned,
            controller_wall_seconds=self.controller_wall_seconds,
            observation_replacement_count=0, api_elision_count=0,
            full_controller_cost_in_task_wall=True,
            controller_subtimer_excludes_serialization_and_inference=True)
