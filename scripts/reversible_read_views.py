"""Conditional old-view reconstruction from caller-certified integer effects.

This is an opt-in host extension, not an automatic AppWorld effect verifier.
The default policy grants no effect certificates. Complete current responses
remain in the ordinary cache; reconstructed old values belong only to old views.
Historical reconstruction is an established technique, not a novelty claim.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
import re

from field_read_contract import canonical
from public_contract_read_views import PublicContractReadHost
from shared_api_reservations import RequestBudgetError


@dataclass(frozen=True)
class IntegerEffect:
    read_app: str
    read_api: str
    identity_argument: str
    identity: int
    field: str
    change: int
    expected_reply: dict
    all_other_read_values_unchanged: bool
    successful_receipt_binds_exact_change: bool
    read_remains_total: bool

    def __post_init__(self):
        labels = (self.read_app, self.read_api, self.identity_argument, self.field)
        if (any(type(s) is not str or not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', s) for s in labels)
                or type(self.identity) is not int or self.identity <= 0
                or type(self.change) is not int or self.change not in (-1, 1)
                or type(self.expected_reply) is not dict
                or any(type(v) is not bool for v in (self.all_other_read_values_unchanged,
                    self.successful_receipt_binds_exact_change, self.read_remains_total))):
            raise ValueError('explicit_bounded_effect_certificate_required')
        canonical(self.expected_reply)

    def permitted(self):
        return (self.all_other_read_values_unchanged
                and self.successful_receipt_binds_exact_change and self.read_remains_total)

    def relation(self, action):
        args = action['args']
        if (action['app'] != self.read_app or action['api'] != self.read_api
                or set(args) != {self.identity_argument}
                or type(args[self.identity_argument]) is not int
                or args[self.identity_argument] <= 0):
            return 'unsupported'
        return 'affected' if args[self.identity_argument] == self.identity else 'unchanged'


class ReversibleReadHost(PublicContractReadHost):
    """Defer across a certified mutation, or use the original full-read barrier.

Each reserved read still costs at most one future API request. Patch depth is
bounded; at the bound we materialize before the next mutation. A failed or
unrecognized mutation receipt freezes the client, preserving its actual charge
and outstanding liabilities. No retry or simulated undo of the real action.
"""
    def __init__(self, channel, *, effect_authority=lambda action, epoch: None,
                 max_patch_depth=32, allow_reversible=True, **kwargs):
        if type(max_patch_depth) is not int or not 1 <= max_patch_depth <= 128:
            raise ValueError('bounded_positive_patch_depth_required')
        if type(allow_reversible) is not bool:
            raise ValueError('explicit_reversible_policy_required')
        self.effect_authority = effect_authority
        self.max_patch_depth = max_patch_depth
        self.allow_reversible = allow_reversible
        self.undo = {}
        self.prepared_effect = None
        self.effect_events = []
        self.reconstruction_steps = 0
        self.exact_materialization_reuses = 0
        super().__init__(channel, **kwargs)

    def request(self, packet):
        try:
            return super().request(packet)
        finally:
            self.undo = {k:v for k,v in self.undo.items() if k in self.records}
            self.prepared_effect = None

    def _barrier(self):
        action = self.active_action
        # Validate the visible capability and shared budget before doing even a
        # protective fetch, matching the original barrier's admission order.
        fn = {'name':action['app']+'__'+action['api'],
              'arguments':json.dumps(action['args'],allow_nan=False)}
        decoded = self.channel.catalog.decode(fn)
        if set(decoded) != {'app','api','args'}:
            raise ValueError('ordinary_public_API_required')
        if self.channel.budget.available < 1:
            raise RequestBudgetError('ordinary_call_cannot_spend_future_reservations')
        effect = (self.effect_authority(deepcopy(action), self.epoch)
                  if self.defer and self.allow_reversible else None)
        if not isinstance(effect, IntegerEffect) or not effect.permitted():
            return super()._barrier()
        effect = deepcopy(effect)
        for name, record in list(self.records.items()):
            if record.token is None:
                continue
            relation = effect.relation(record.action)
            if relation == 'unsupported' or (relation == 'affected'
                    and len(self.undo.get(name, [])) >= self.max_patch_depth):
                self._materialize(name)
        self.prepared_effect = effect

    def _send(self, action, token=None):
        effect = self.prepared_effect if token is None and action == self.active_action else None
        if effect is None:
            return super()._send(action, token)
        self.prepared_effect = None
        try:
            value = super()._send(action)
        except BaseException:
            # Even a known API exception is not an exact state-change receipt.
            self.channel.budget.stopped = True
            self.provider.cache.invalidate()
            raise
        if canonical(value) != canonical(effect.expected_reply):
            self.provider.cache.invalidate()
            self._fail_contract('successful_mutation_reply_not_certified')
        self.epoch += 1
        self.provider.cache.invalidate()
        affected = 0
        for name, record in self.records.items():
            if record.token is not None and effect.relation(record.action) == 'affected':
                self.undo.setdefault(name, []).append((effect.field, effect.change))
                affected += 1
        self.effect_events.append(dict(epoch=self.epoch, affected_pending_views=affected))
        return value

    def _materialize(self, name):
        patches = self.undo.get(name, [])
        record = self.records[name]
        if record.token is None:
            if patches:self._fail_contract('undo_without_reserved_read')
            return deepcopy(record.value)
        current = self.provider.lookup(record.action, self.epoch)
        if current is not None and current[0] == 'complete':
            # The barrier baseline has this identical complete-response reuse.
            # A cache hit discharges a liability without pretending it was sent.
            value = deepcopy(current[1])
            self.channel.budget.cancel(record.token)
            self.exact_materialization_reuses += 1
        else:
            try:
                # The parent caches this CURRENT response under the current epoch.
                # Only the private copy below is reconstructed for the old view.
                value = super()._send(record.action, record.token)
            except BaseException:
                self.channel.budget.stopped = True
                raise
        record.token = None
        if type(value) is not dict:
            self._fail_contract('reconstruction_requires_mapping')
        old = deepcopy(value)
        for field, change in reversed(patches):
            if type(old.get(field)) is not int or old[field] < 0 or old[field]-change < 0:
                self._fail_contract('inverse_integer_effect_not_valid')
            old[field] -= change
            self.reconstruction_steps += 1
        if any(k not in old or canonical(old[k]) != canonical(v) for k,v in record.partial.items()):
            self._fail_contract('reconstructed_partial_snapshot_contract_false')
        record.value = old
        self.undo.pop(name, None)
        return deepcopy(old)
