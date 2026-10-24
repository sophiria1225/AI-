"""Conventional complete-response reuse for ordinary verified Song reads.

The same opt-in cache applies to eager and coalesced-deferred hosts. Only the
existing provider's complete, same-scope, same-epoch response may replace an
ordinary call. Partial values, new API capabilities, and uncertain effects do
not qualify. This is a stronger control, not a proposed novel cache algorithm.
"""
from copy import deepcopy
import hashlib
import json

from coalesced_contract_read_views import CoalescedContractReadHost
from field_read_contract import canonical
from public_contract_read_views import PublicContractReadHost, PublicContractReadProgram
from shared_api_reservations import BudgetedApiChannel


class OrdinaryCompleteReadCache:
    def __init__(self, *args, **kwargs):
        self.ordinary_complete_reuses = 0
        self.ordinary_cache_events = []
        self._ordinary_request_active = False
        self._ordinary_operation = None
        super().__init__(*args, **kwargs)

    def request(self, packet):
        if self._ordinary_request_active:
            raise RuntimeError('reentrant_ordinary_cache_request')
        self._ordinary_request_active = True
        self._ordinary_operation = packet.get('op') if type(packet) is dict else None
        try:
            # The existing protocol validates all arguments and release names
            # before either dispatch hook below can use this operation marker.
            return super().request(packet)
        finally:
            self._ordinary_request_active = False
            self._ordinary_operation = None

    def _ordinary_complete(self, action):
        if self._ordinary_operation != 'call':
            return None
        decoded = self.channel.catalog.decode(dict(name=action['app']+'__'+action['api'],
            arguments=json.dumps(action['args'], allow_nan=False)))
        if set(decoded) != {'app', 'api', 'args'}:
            raise ValueError('ordinary_public_API_required')
        # PublicReadAuthority admits only the pinned show_song identity, and
        # returns complete only for an unambiguous, actually observed response.
        found = self.provider.lookup(action, self.epoch)
        return found[1] if found is not None and found[0] == 'complete' else None

    def _barrier(self):
        if self._ordinary_complete(self.active_action) is not None:
            # A zero-dispatch hit must not require one unused API slot. It may
            # not bypass a stopped ledger or consume another pending obligation.
            self.channel.budget._ready()
            return
        return super()._barrier()

    def _send(self, action, token=None):
        value = self._ordinary_complete(action) if token is None else None
        if value is not None:
            self.channel.budget._ready()
            self.ordinary_complete_reuses += 1
            self.ordinary_cache_events.append(dict(epoch=self.epoch,
                action_sha256=hashlib.sha256(canonical(action).encode()).hexdigest(),
                value_sha256=hashlib.sha256(canonical(value).encode()).hexdigest(),
                environment_API_requests=0))
            return deepcopy(value)
        return super()._send(action, token)


class OrdinaryCachedReadHost(OrdinaryCompleteReadCache, PublicContractReadHost):
    pass


class OrdinaryCachedCoalescedHost(OrdinaryCompleteReadCache, CoalescedContractReadHost):
    pass


class OrdinaryCachedReadProgram(PublicContractReadProgram):
    """Identical Python interface with the ordinary cache in both policies."""
    def __call__(self, source, observations, channel, **kwargs):
        if self.host is None:
            host = OrdinaryCachedCoalescedHost if self.defer else OrdinaryCachedReadHost
            self.host = host(BudgetedApiChannel(channel, self.budget),
                execution_scope=self.execution_scope, verified_contract=self.verified_contract,
                defer=self.defer)
        return super().__call__(source, observations, channel, **kwargs)
