"""Share one pending fetch among identical, same-state explicit read views.

An opt-in successor of the frozen PublicContractReadHost. This is ordinary
request coalescing, not a novel method or a demonstrated task improvement.
The original eager policy and complete-response cache remain available.
"""
from copy import deepcopy
import json

from field_read_contract import canonical
from public_contract_read_views import PublicContractReadHost, PublicContractReadProgram
from shared_api_reservations import BudgetedApiChannel


class CoalescedContractReadHost(PublicContractReadHost):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pending_groups = {}
        self.coalesced_reuses = 0
        self.materialization_cache_reuses = 0

    def _forget_group(self, record):
        for key in [key for key, value in self.pending_groups.items() if value is record]:
            del self.pending_groups[key]

    def _read(self, action):
        # Reusing a pending record must not bypass current public capabilities.
        decoded = self.channel.catalog.decode({'name': action['app']+'__'+action['api'],
            'arguments': json.dumps(action['args'], allow_nan=False)})
        if set(decoded) != {'app', 'api', 'args'}:
            raise ValueError('ordinary_public_API_required')
        found = self.provider.lookup(action, self.epoch)
        key = (self.provider.scope, self.epoch, canonical(action))
        if self.defer and found is not None and found[0] == 'partial':
            shared = self.pending_groups.get(key)
            if shared is not None:
                if shared.token is None or shared.partial != found[1]:
                    self._fail_contract('pending_group_authority_changed')
                name = f'view_{self.next_view}'
                self.next_view += 1
                self.records[name] = shared
                self.coalesced_reuses += 1
                return {'name': name, 'partial': deepcopy(shared.partial)}
        result = super()._read(action)
        record = self.records[result['name']]
        if record.token is not None:
            self.pending_groups[key] = record
        return result

    def _use_cached(self, record):
        if record.token is not None:
            # A separately charged ordinary read may already have supplied the
            # complete value at this same epoch. Do not spend the reservation twice.
            key = (self.provider.scope, self.epoch, canonical(record.action))
            found = self.provider.lookup(record.action, self.epoch)
            if (self.pending_groups.get(key) is record and found is not None
                    and found[0] == 'complete'):
                value = found[1]
                if any(k not in value or value[k] != v for k,v in record.partial.items()):
                    self._fail_contract('partial_snapshot_contract_false')
                self.channel.budget.cancel(record.token)
                record.token = None
                record.value = deepcopy(value)
                self.materialization_cache_reuses += 1
                self._forget_group(record)

    def _send(self, action, token=None):
        value = super()._send(action, token)
        # Resolve already-satisfied obligations before the next budget admission.
        # Skip the reservation this send consumed: the parent materializer still
        # has to check and commit its returned value, without a second cancel.
        for record in list(self.pending_groups.values()):
            if record.token is not token:
                self._use_cached(record)
        return value

    def _materialize(self, name):
        record = self.records[name]
        self._use_cached(record)
        value = super()._materialize(name)
        self._forget_group(record)
        return value

    def _release(self, name):
        record = self.records[name]
        # Each view has its own client finalizer. Only the last host name can
        # cancel the group's reservation; completed groups have no reservation.
        if not any(other is record for key,other in self.records.items() if key != name):
            if record.token is not None:
                self.channel.budget.cancel(record.token)
            self._forget_group(record)
        del self.records[name]

    def request(self, packet):
        # Preserve the frozen protocol's validation and dispatch order. The only
        # lifecycle difference is group-aware release instead of per-name cancel.
        if (type(packet) is not dict or set(packet) != {'id','op','args','releases'}
                or type(packet['id']) is not int or packet['id'] != self.last_id+1
                or packet['op'] not in ('read','call','materialize','flush')
                or type(packet['args']) is not dict or type(packet['releases']) is not list
                or any(type(n) is not str for n in packet['releases'])
                or len(set(packet['releases'])) != len(packet['releases'])
                or any(n not in self.records for n in packet['releases'])):
            raise ValueError('invalid_view_control_request')
        op, args = packet['op'], packet['args']
        if op in ('read','call'):
            if (set(args) != {'app','api','args'} or type(args['app']) is not str
                    or type(args['api']) is not str or type(args['args']) is not dict):
                raise ValueError('invalid_view_api_action')
        elif op == 'materialize':
            if set(args) != {'name'} or type(args['name']) is not str:
                raise ValueError('invalid_view_materialization')
        elif args:
            raise ValueError('flush_takes_no_arguments')
        self.last_id = packet['id']
        self.control_events.append({'id': self.last_id, 'op': op, 'released': len(packet['releases'])})
        reply = {'id': self.last_id, 'ok': False}
        self.active_action = args if op in ('read','call') else None
        try:
            self.channel.budget._ready()
            for name in packet['releases']:
                self._release(name)
            if op == 'read':
                value = self._read(args)
            elif op == 'call':
                self._barrier()
                value = self._send(args)
            elif op == 'materialize':
                value = self._materialize(args['name'])
            else:
                value = None
            reply.update(ok=True, value=value)
        except Exception as error:
            reply.update(error=type(error).__name__+': '+str(error))
        finally:
            self.active_action = None
        reply['fatal'] = self.channel.budget.stopped
        return reply


class CoalescedContractReadProgram(PublicContractReadProgram):
    """Same isolated client and control accounting; a separate host implementation."""
    def __call__(self, source, observations, channel, **kwargs):
        if self.host is None:
            self.host = CoalescedContractReadHost(BudgetedApiChannel(channel, self.budget),
                execution_scope=self.execution_scope, verified_contract=self.verified_contract, defer=self.defer)
        return super().__call__(source, observations, channel, **kwargs)
