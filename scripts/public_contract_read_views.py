"""Connect the existing P37 field contract to explicit deferred read views.

Only already-returned public responses enter this cache. Both policies reuse
identical complete responses; only the deferred policy may postpone completion
of a partial response. The existing six audited read handlers may preserve the
revision. Every other API requires the conservative snapshot barrier.
No new cross-application effect exemption, model run, or task result is claimed.
"""
from copy import deepcopy
import json

from deferred_read_obligations import Assumptions
from deferred_view_protocol import DeferredReadHost, PendingRead, ReadAuthority
from field_read_contract import (CONTRACT_ID, FIELDS, READ_ONLY_APIS, FieldReadCache,
                                  ReadContext, canonical, target_identity)
from persistent_read_view_python import ReadViewProgram
from shared_api_reservations import BudgetedApiChannel, RequestBudgetError


class PublicReadAuthority:
    def __init__(self, execution_scope, *, verified_contract):
        if type(execution_scope) is not str or not execution_scope:
            raise ValueError('nonempty_task_scope_required')
        if verified_contract != CONTRACT_ID:
            raise ValueError('pinned_public_implementation_must_be_verified')
        self.scope = execution_scope
        self.cache = FieldReadCache('contract',verified_contract=verified_contract)

    def context(self, epoch):
        return ReadContext(self.scope,str(epoch),CONTRACT_ID)

    def observe(self, action, value, epoch):
        self.cache.observe(action['app']+'__'+action['api'],action['args'],value,self.context(epoch))

    def lookup(self, action, epoch):
        api = action['app']+'__'+action['api'];args = action['args'];context = self.context(epoch)
        partial = self.cache.lookup(api,args,sorted(FIELDS),context)
        if partial is None or target_identity(api,args) is None:
            return None
        versions = self.cache.exact.get(canonical(args),{})
        if len(versions)==1:
            full = next(iter(versions.values()))
            complete = self.cache.lookup(api,args,list(full),context)
            if complete is not None and complete.source=='exact':
                return 'complete',complete.value
        if partial.source=='cross_api':
            return 'partial',partial.value
        return None

    def grant(self, action, epoch):
        found = self.lookup(action,epoch)
        if found is None:return None
        # Conditional on the existing pinned public serializer/read contract,
        # task isolation, and barriers on every operation outside its read set.
        # An actual fallback error still invalidates this premise and stops.
        return ReadAuthority(epoch,deepcopy(found[1]),Assumptions(True,True,True))


class PublicContractReadHost(DeferredReadHost):
    def __init__(self, channel, *, execution_scope, verified_contract, defer=True):
        self.provider = PublicReadAuthority(execution_scope,verified_contract=verified_contract)
        self.active_action = None
        self.exact_reuses = 0
        super().__init__(channel,authority=self.provider.grant,defer=defer)

    def request(self, packet):
        if self.active_action is not None:
            raise RuntimeError('reentrant_public_contract_request')
        # The inherited request validates shape before using the action.
        self.active_action = (packet.get('args') if type(packet) is dict
                              and packet.get('op') in ('read','call') else None)
        try:return super().request(packet)
        finally:self.active_action = None

    def _barrier(self):
        action = self.active_action
        # Rejected catalog operations cannot mutate state and must not trigger
        # speculative full fetches. Validation is repeated at actual dispatch.
        fn = {'name':action['app']+'__'+action['api'],
              'arguments':json.dumps(action['args'],allow_nan=False)}
        decoded = self.channel.catalog.decode(fn)
        if set(decoded) != {'app','api','args'}:
            raise ValueError('ordinary_public_API_required')
        if self.channel.budget.available < 1:
            raise RequestBudgetError('ordinary_call_cannot_spend_future_reservations')
        if fn['name'] in READ_ONLY_APIS:
            return
        super()._barrier()
        self.provider.cache.invalidate()

    def _send(self, action, token=None):
        value = super()._send(action,token)
        self.provider.observe(action,value,self.epoch)
        return value

    def _read(self, action):
        # Reuse does not grant a new API capability or bypass its visible schema.
        decoded = self.channel.catalog.decode({'name':action['app']+'__'+action['api'],
            'arguments':json.dumps(action['args'],allow_nan=False)})
        if set(decoded) != {'app','api','args'}:
            raise ValueError('ordinary_public_API_required')
        # A cached complete response is available to the eager baseline too.
        found = self.provider.lookup(action,self.epoch)
        if found is not None and found[0]=='complete':
            value = deepcopy(found[1]);name = f'view_{self.next_view}';self.next_view += 1
            self.records[name] = PendingRead(deepcopy(action),value,None,value)
            self.exact_reuses += 1
            return {'name':name,'partial':deepcopy(value)}
        return super()._read(action)


class PublicContractReadProgram(ReadViewProgram):
    """Opt-in adapter; caller verifies fixed source hashes before construction."""
    def __init__(self, session, budget, *, execution_scope, verified_contract, defer=True):
        super().__init__(session,budget,authority=None,defer=defer)
        # Validate contract identifiers immediately, without touching task state.
        PublicReadAuthority(execution_scope,verified_contract=verified_contract)
        self.execution_scope,self.verified_contract = execution_scope,verified_contract

    def __call__(self, source, observations, channel, **kwargs):
        if self.host is None:
            self.host = PublicContractReadHost(BudgetedApiChannel(channel,self.budget),
                execution_scope=self.execution_scope,verified_contract=self.verified_contract,defer=self.defer)
        return super().__call__(source,observations,channel,**kwargs)
