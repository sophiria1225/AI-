"""Executable specification of deferred reads, not a live Python/API adapter.

All objects and effects belong to a handwritten in-memory world. A caller must
explicitly describe bindings, aliases, escapes and effects. The trust flags are
assumptions supplied by the fixture; this module does not infer API semantics.
No saved experiment, model, network, filesystem or task evaluator is accessed.
"""
from copy import deepcopy
from dataclasses import dataclass


class BudgetExhausted(RuntimeError): pass
class ContractViolation(RuntimeError): pass


@dataclass(frozen=True)
class Assumptions:
    pure_total_read: bool = False
    partial_matches_snapshot: bool = False
    all_changes_intercepted: bool = False

    def __post_init__(self):
        if any(type(v) is not bool for v in (self.pure_total_read,
                self.partial_matches_snapshot, self.all_changes_intercepted)):
            raise ValueError('explicit_boolean_assumptions_required')

    def permit_deferral(self):
        return self.pure_total_read and self.partial_matches_snapshot and self.all_changes_intercepted


@dataclass
class Record:
    key: str
    epoch: int
    partial: dict
    value: dict | None = None
    pending: bool = True


class DeferredReadModel:
    """Keep one future fetch reserved for each live partial response.

    The invariant is spent + pending <= limit. Reserved cost is a liability,
    not an incurred request. The object is materialized before an unknown use
    or intercepted mutation. Last-alias death cancels its pending liability.
    Complete objects retain their original snapshot across later mutations.
    """
    def __init__(self, objects, limit, *, defer=True):
        if type(limit) is not int or limit < 0:
            raise ValueError('nonnegative_integer_limit_required')
        self.objects = deepcopy(objects)
        self.limit = limit
        self.defer = defer
        self.epoch = 0
        self.spent = 0
        self.bindings = {}
        self.records = {}
        self.next_id = 0
        self.events = []
        self.poisoned = False
        self.fail_next_fetch = False

    @property
    def pending(self):
        return sum(r.pending for r in self.records.values())

    @property
    def available(self):
        return self.limit - self.spent - self.pending

    def _ready(self):
        if self.poisoned:
            raise ContractViolation('preserve_failed_state_no_retry')
        assert 0 <= self.spent + self.pending <= self.limit

    def _violation(self, reason):
        self.poisoned = True
        self.events.append({'kind':'contract_violation','reason':reason})
        raise ContractViolation(reason)

    def _fetch(self, record, *, reserved):
        self._ready()
        if record.epoch != self.epoch:
            self._violation('snapshot_changed_without_barrier')
        if not reserved and self.available < 1:
            raise BudgetExhausted('future_fetch_reservations_are_not_spendable')
        if reserved:
            assert record.pending
            record.pending = False
        self.spent += 1
        self.events.append({'kind':'fetch','key':record.key,'epoch':self.epoch})
        if self.fail_next_fetch:
            self.fail_next_fetch = False
            if reserved:
                self._violation('trusted_total_read_failed')
            raise RuntimeError('modelled_immediate_fetch_failure')
        try:
            value = deepcopy(self.objects[record.key])
        except KeyError:
            if reserved:
                self._violation('trusted_object_missing')
            raise
        if type(value) is not dict or any(k not in value or value[k] != v for k,v in record.partial.items()):
            self._violation('partial_snapshot_contract_false')
        record.value = value
        record.pending = False
        return deepcopy(value)

    def _unbind(self, name):
        if name not in self.bindings:
            return
        identifier = self.bindings.pop(name)
        if identifier not in self.bindings.values():
            record = self.records.pop(identifier)
            if record.pending:
                self.events.append({'kind':'cancel_unused_fetch','key':record.key,'epoch':record.epoch})

    def bind(self, name, key, partial, assumptions=Assumptions()):
        self._ready()
        if type(partial) is not dict:
            raise ValueError('explicit_partial_mapping_required')
        eligible = self.defer and assumptions.permit_deferral() and bool(partial)
        # Do not kill the old binding before the new read has been admitted.
        if self.available < 1:
            raise BudgetExhausted('read_not_admitted')
        record = Record(key, self.epoch, deepcopy(partial) if eligible else {}, pending=eligible)
        if not eligible:
            self._fetch(record, reserved=False)
        identifier = self.next_id
        self.next_id += 1
        self.records[identifier] = record
        self._unbind(name)
        self.bindings[name] = identifier
        self.events.append({'kind':'bind','key':key,'deferred':eligible})
        self._ready()

    def alias(self, destination, source):
        self._ready()
        identifier = self.bindings[source]
        if destination == source or self.bindings.get(destination) == identifier:
            return
        self._unbind(destination)
        self.bindings[destination] = identifier

    def drop(self, name):
        self._ready()
        self._unbind(name)

    def materialize(self, name):
        self._ready()
        record = self.records[self.bindings[name]]
        if record.pending:
            self._fetch(record, reserved=True)
        return deepcopy(record.value)

    def field(self, name, field):
        self._ready()
        record = self.records[self.bindings[name]]
        if record.value is not None:
            return deepcopy(record.value[field])
        if record.epoch != self.epoch:
            self._violation('snapshot_changed_without_barrier')
        if field in record.partial:
            return deepcopy(record.partial[field])
        return self.materialize(name)[field]

    def effect(self, changes):
        """A modelled one-request mutation, including the pre-mutation barrier."""
        self._ready()
        for record in list(self.records.values()):
            if record.pending:
                self._fetch(record, reserved=True)
        if self.available < 1:
            raise BudgetExhausted('effect_not_admitted')
        self.spent += 1
        self.objects.update(deepcopy(changes))
        self.epoch += 1
        self.events.append({'kind':'effect','epoch':self.epoch})
        self._ready()

    def snapshot(self):
        self._ready()
        return dict(spent=self.spent, pending=self.pending, available=self.available,
                    live_objects=len(self.records), live_names=len(self.bindings))
