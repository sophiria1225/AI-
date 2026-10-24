"""Explicit read views across a JSON control boundary, with host-owned budgets.

The authority callback is a trusted assumption, not a learned API contract.
This module does not launch a container, call a model, or certify AppWorld APIs.
Control messages are not API invocations; every underlying API uses the existing
typed channel and one shared ledger. A future runner must record control costs,
install the client in its isolated interpreter, and flush releases before done.
"""
from copy import deepcopy
from dataclasses import dataclass

from deferred_read_obligations import Assumptions, ContractViolation
from explicit_deferred_read_views import ReadView, ClosedReadView
from shared_api_reservations import BudgetedApiChannel, RequestBudgetError


@dataclass(frozen=True)
class ReadAuthority:
    epoch: int
    partial: dict
    assumptions: Assumptions


@dataclass
class PendingRead:
    action: dict
    partial: dict
    token: object | None
    value: dict | None = None


class DeferredReadHost:
    """All unknown-effect API calls materialize surviving snapshots first.

    A resolver may return ReadAuthority only from trusted, already-observed
    information at the supplied epoch. Unknown authority falls back to immediate
    execution. The conservative barrier applies even to reads without authority;
    it can eliminate savings. No task success, hidden state or future reply may
    be used to manufacture the partial values.
    """
    def __init__(self, channel, *, authority=lambda action, epoch: None,
                 defer=True, on_record=lambda row: None):
        if not isinstance(channel, BudgetedApiChannel):
            raise ValueError('shared_budget_channel_required')
        self.channel = channel
        self.authority = authority
        self.defer = defer
        self.on_record = on_record
        self.epoch = 0
        self.records = {}
        self.next_view = 0
        self.last_id = 0
        self.control_events = []

    def attach(self, channel):
        if (not isinstance(channel, BudgetedApiChannel)
                or channel.budget is not self.channel.budget
                or channel.bridge is not self.channel.bridge):
            raise ValueError('same_task_budget_and_transport_required')
        self.channel = channel

    def _fail_contract(self, reason):
        self.channel.budget.stopped = True
        raise ContractViolation(reason)

    def _send(self, action, token=None):
        packet = dict(kind='api', id=self.channel.last_id+1,
                      app=action['app'], api=action['api'], arguments=action['args'])
        before = len(self.channel.rows)
        try:
            reply = (self.channel.exchange(packet) if token is None
                     else self.channel.exchange_reserved(packet, token))
        finally:
            for row in self.channel.rows[before:]:
                self.on_record(deepcopy(row))
        if not reply['ok']:
            raise RuntimeError(reply['error'])
        return deepcopy(reply['value'])

    def _materialize(self, name):
        record = self.records[name]
        if record.token is not None:
            try:
                value = self._send(record.action, record.token)
            except BaseException:
                # A deferred read was assumed pure and total. Preserve its exact
                # dispatch accounting and invalidate trust instead of retrying.
                self.channel.budget.stopped = True
                raise
            record.token = None
            if (type(value) is not dict
                    or any(k not in value or value[k] != v for k,v in record.partial.items())):
                self._fail_contract('partial_snapshot_contract_false')
            record.value = value
        return deepcopy(record.value)

    def _barrier(self):
        # Admission precedes the barrier: do not fetch merely for a call that
        # already cannot fit. Reserved fetches do not change available capacity.
        if self.channel.budget.available < 1:
            raise RequestBudgetError('ordinary_call_cannot_spend_future_reservations')
        for name in list(self.records):
            self._materialize(name)
        self.epoch += 1

    def _read(self, action):
        grant = self.authority(deepcopy(action), self.epoch)
        trusted = (isinstance(grant, ReadAuthority) and type(grant.epoch) is int
                   and grant.epoch == self.epoch and type(grant.partial) is dict
                   and isinstance(grant.assumptions, Assumptions)
                   and grant.assumptions.permit_deferral() and bool(grant.partial))
        token = None
        if self.defer and trusted:
            token = self.channel.budget.reserve()
            value = None
            partial = deepcopy(grant.partial)
        else:
            if not trusted:
                self._barrier()
            value = self._send(action)
            if type(value) is not dict:
                raise TypeError('read_view_requires_a_mapping_response')
            partial = deepcopy(value)
        name = f'view_{self.next_view}'
        self.next_view += 1
        self.records[name] = PendingRead(deepcopy(action), partial, token, value)
        return {'name': name, 'partial': deepcopy(partial)}

    def request(self, packet):
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
        self.control_events.append({'id': self.last_id, 'op': op,
                                    'released': len(packet['releases'])})
        reply = {'id': self.last_id, 'ok': False}
        try:
            self.channel.budget._ready()
            for name in packet['releases']:
                record = self.records[name]
                if record.token is not None:
                    self.channel.budget.cancel(record.token)
                del self.records[name]
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
        reply['fatal'] = self.channel.budget.stopped
        return reply


class RemoteReadViews:
    """Interpreter-side capabilities; finalizers queue releases without I/O.

    The supplied exchange must carry JSON, not shared Python objects. Queued
    releases are attached to the next control request, or explicitly flushed
    before a program's done marker. Cycles keep reservations until collected.
    A lost control reply is never automatically retried.
    """
    def __init__(self, exchange):
        self.exchange = exchange
        self.model = self  # Reuse the exact existing ReadView interface.
        self.closed = False
        self.records = {}
        self.releases = []
        self.counter = 0

    def _rpc(self, op, args):
        if self.closed:
            raise ClosedReadView('read_capability_closed')
        self.counter += 1
        pending = self.releases
        self.releases = []
        try:
            reply = self.exchange(dict(id=self.counter, op=op, args=args, releases=pending))
            if (type(reply) is not dict or reply.get('id') != self.counter
                    or type(reply.get('ok')) is not bool or type(reply.get('fatal')) is not bool
                    or (reply['ok'] and 'value' not in reply)
                    or (not reply['ok'] and type(reply.get('error')) is not str)):
                raise ValueError('invalid_view_control_reply')
        except BaseException:
            self.closed = True
            # No retry of possibly consumed releases, read reservations, or APIs.
            raise
        self.closed |= reply['fatal']
        if not reply['ok']:
            raise RuntimeError(reply['error'])
        return reply['value']

    def read(self, app, api, **args):
        value = self._rpc('read', dict(app=app, api=api, args=args))
        if (type(value) is not dict or set(value) != {'name','partial'}
                or type(value['name']) is not str or value['name'] in self.records
                or type(value['partial']) is not dict):
            self.closed = True
            raise ValueError('invalid_view_creation_reply')
        name = value['name']
        self.records[name] = {'partial': deepcopy(value['partial']), 'full': None}
        return ReadView(self, name)

    def call(self, app, api, **args):
        return self._rpc('call', dict(app=app, api=api, args=args))

    def field(self, name, field):
        record = self.records[name]
        if record['full'] is not None:
            return deepcopy(record['full'][field])
        if field in record['partial']:
            return deepcopy(record['partial'][field])
        return self.materialize(name)[field]

    def materialize(self, name):
        record = self.records[name]
        if record['full'] is None:
            value = self._rpc('materialize', {'name': name})
            if type(value) is not dict:
                self.closed = True
                raise ValueError('invalid_view_materialization_reply')
            record['full'] = deepcopy(value)
        return deepcopy(record['full'])

    def _release(self, name):
        # Never dispatch while GC is running or throw from a finalizer.
        if not self.closed and name in self.records:
            del self.records[name]
            self.releases.append(name)

    def flush_releases(self):
        if self.releases and not self.closed:
            self._rpc('flush', {})
