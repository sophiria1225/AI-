"""Task-wide API reservations connected to existing typed dispatch receipts.

This host-side adapter does not implement lazy values or certify API purity.
No running experiment uses it. Callers must share one ledger across programs;
generated code must not receive the ledger or reservation capabilities.
Only request counts are reserved, not wall time, tokens, or eventual success.
"""
from container_api_python import ApiChannel
from public_api_result_transport import PublicResultProgram, PublicResultTransport


class RequestBudgetError(RuntimeError): pass


class RequestBudget:
    def __init__(self, limit):
        if type(limit) is not int or limit < 0:
            raise ValueError('nonnegative_integer_request_limit_required')
        self.limit = limit
        self.spent = 0
        self._pending = {}
        self.events = []
        self.stopped = False
        self.busy = False
        self._next = 0

    @property
    def pending(self):
        return len(self._pending)

    @property
    def available(self):
        return self.limit - self.spent - self.pending

    def _ready(self):
        if self.stopped or self.busy:
            raise RequestBudgetError('stopped_or_reentrant_request_budget')
        if not 0 <= self.spent + self.pending <= self.limit:
            self.stopped = True
            raise RequestBudgetError('request_budget_invariant_failed')

    def reserve(self):
        self._ready()
        if self.available < 1:
            raise RequestBudgetError('future_requests_are_not_spendable')
        token = object()  # Host-only, identity checked; never serialized to code.
        self._pending[token] = self._next
        self.events.append({'kind': 'reserve', 'reservation': self._next})
        self._next += 1
        return token

    def _require(self, token):
        if token not in self._pending:
            raise RequestBudgetError('unknown_or_consumed_reservation')
        return self._pending[token]

    def cancel(self, token):
        self._ready()
        number = self._require(token)
        del self._pending[token]
        self.events.append({'kind': 'cancel_unused', 'reservation': number})

    def snapshot(self):
        return dict(limit=self.limit, spent=self.spent, pending=self.pending,
                    available=self.available, stopped=self.stopped)


class BudgetedApiChannel:
    """One program's ordinary channel, with task-wide future-request admission.

    Dispatch uses the existing catalog validation, typed transport and receipt
    correction. A new channel cannot reset the shared ledger. A host-owned
    reserved call may consume its own reservation when ordinary capacity is 0.
    Invalid requests and proven pre-dispatch failures are never charged as sent.
    Unknown transport outcomes stop the shared ledger without automatic retry.
    This is single-threaded; reentrant dispatch and ledger changes are rejected.
    """
    def __init__(self, base, budget):
        if not isinstance(base, ApiChannel) or not isinstance(base.bridge, PublicResultTransport):
            raise ValueError('fresh_typed_api_channel_required')
        if base.rows or base.last_id or base.fatal or base.complete:
            raise ValueError('cannot_attach_budget_after_program_dispatch')
        budget._ready()
        self.base = base
        self.budget = budget
        self.ceiling = base.remaining
        self.sent_here = 0
        self.receipted = PublicResultProgram(lambda source, observations, wrapped: wrapped)('', [], base)

    def __getattr__(self, name):
        return getattr(self.base, name)

    def exchange(self, packet):
        return self._exchange(packet, None)

    def exchange_reserved(self, packet, token):
        """Host entry point for a previously admitted deferred full request."""
        if token is None:
            raise RequestBudgetError('explicit_reservation_required')
        return self._exchange(packet, token)

    def _exchange(self, packet, token):
        budget = self.budget
        budget._ready()
        reserved = token is not None
        if reserved:
            budget._require(token)
        capacity = min(self.ceiling - self.sent_here, 1 if reserved else budget.available)
        if capacity > 0 and not reserved:
            token = budget.reserve()
        self.base.remaining = max(0, capacity)
        before = len(self.base.rows)
        before_receipts = len(self.base.bridge.receipts)
        budget.busy = True
        try:
            return self.receipted.exchange(packet)
        finally:
            budget.busy = False
            rows = self.base.rows[before:]
            receipts = self.base.bridge.receipts[before_receipts:]
            if len(rows) > 1 or len(receipts) > 1:
                budget.stopped = True
                raise RequestBudgetError('unexpected_multiple_dispatch_rows')
            row = rows[0] if rows else None
            receipt = receipts[0] if receipts else None
            sent = ((row is not None and row.get('api_request_sent') is True)
                    or (receipt is not None and receipt.get('bridge_request_sent') is True))
            if sent:
                # The typed receipt adapter has already corrected pre-send errors.
                if token is None:
                    budget.stopped = True
                    raise RequestBudgetError('dispatch_without_admission')
                number = budget._require(token)
                del budget._pending[token]
                budget.spent += 1
                self.sent_here += 1
                budget.events.append({'kind': 'sent', 'reservation': number,
                    'status': receipt.get('status', 'unknown') if receipt else 'unknown'})
                # KeyboardInterrupt/SystemExit can escape the older channel before
                # it appends a row. Retain the transport's dispatched receipt and
                # stop; never turn interruption after an effect into a free call.
                if row is None or receipt is None or receipt.get('status') == 'unknown':
                    budget.stopped = self.base.fatal = self.base.bridge.fatal = True
            elif token is not None and not reserved:
                # This temporary ordinary-call admission incurred no API request.
                number = budget._pending.pop(token)
                budget.events.append({'kind': 'not_dispatched', 'reservation': number})
            if self.base.fatal or self.base.bridge.fatal:
                budget.stopped = True
            if self.base.complete or self.base.bridge.complete:
                budget.stopped = True
            if not 0 <= budget.spent + budget.pending <= budget.limit:
                budget.stopped = True
                raise RequestBudgetError('request_budget_invariant_failed')
            self.base.remaining = max(0, min(self.ceiling - self.sent_here, budget.available))
