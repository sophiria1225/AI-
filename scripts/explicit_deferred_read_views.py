"""Python ownership adapter over the in-memory deferred-read specification.

This is an explicit read-only Mapping capability, not a replacement for dict.
Both immediate and deferred policies expose this same interface. Real API
contracts, RPC accounting, AppWorld and model prompts are not connected.
"""
from collections.abc import Mapping
import weakref

from deferred_read_obligations import Assumptions, DeferredReadModel


class ClosedReadView(RuntimeError): pass


class ReadView(Mapping):
    """Fields return copies; full iteration, repr and export materialize.

    Python containers and closures keep the view alive normally. A shallow
    copy shares the capability. A deep copy or pickle exports a plain complete
    dictionary. None of these promises transparent native-dict compatibility.
    """
    __slots__ = ('_owner', '_name', '_finalizer', '__weakref__')

    def __init__(self, owner, name):
        self._owner = owner
        self._name = name
        self._finalizer = weakref.finalize(self, owner._release, name)

    def _check(self):
        if self._owner.closed:
            raise ClosedReadView('read_capability_closed')

    def __getitem__(self, key):
        self._check()
        return self._owner.model.field(self._name, key)

    def materialize(self):
        self._check()
        return self._owner.model.materialize(self._name)

    def __iter__(self):
        return iter(self.materialize())

    def __len__(self):
        return len(self.materialize())

    def __repr__(self):
        return 'ReadView(' + repr(self.materialize()) + ')'

    def __copy__(self):
        self._check()
        return self

    def __deepcopy__(self, memo):
        value = self.materialize()
        memo[id(self)] = value
        return value

    def __reduce_ex__(self, protocol):
        return dict, (self.materialize(),)


class ReadViews:
    """Synthetic owner: actual Python references control in-memory leases."""
    def __init__(self, objects, limit, *, defer=True):
        self.model = DeferredReadModel(objects, limit, defer=defer)
        self.closed = False
        self._counter = 0
        self.released_views = 0
        self.task_close_releases = 0

    def read(self, key, partial=None, assumptions=Assumptions()):
        if self.closed:
            raise ClosedReadView('read_capability_closed')
        name = f'view_{self._counter}'
        self.model.bind(name, key, partial if partial is not None else {}, assumptions)
        self._counter += 1
        return ReadView(self, name)

    def _release(self, name):
        # A failed contract remains frozen; GC is never an implicit retry or
        # permission to discard the failed ledger. It must not throw in a finalizer.
        if not self.model.poisoned and name in self.model.bindings:
            self.model.drop(name)
            self.released_views += 1

    def effect(self, changes):
        if self.closed:
            raise ClosedReadView('read_capability_closed')
        self.model.effect(changes)

    def close(self):
        """Invalidate all capabilities, without declaring an application task done."""
        if not self.closed:
            self.closed = True
            if not self.model.poisoned:
                for name in list(self.model.bindings):
                    self.model.drop(name)
                    self.task_close_releases += 1
