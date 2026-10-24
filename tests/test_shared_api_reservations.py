"""Real host channel/typed-envelope path; handwritten fixture, no environment."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from container_api_python import ApiChannel
from public_api_result_transport import PublicResultTransport
from shared_api_reservations import BudgetedApiChannel, RequestBudget, RequestBudgetError
from test_public_api_result_transport import FixtureTransport, catalog


def packet(ch, api='echo', value=None):
    return dict(kind='api', id=ch.last_id + 1, app='fixture', api=api, arguments={'value': value})


def channel(budget, raw=None, *, may_continue=lambda: True):
    transport = PublicResultTransport(raw if raw is not None else FixtureTransport())
    return BudgetedApiChannel(ApiChannel(catalog(), transport, budget.limit-budget.spent,
                                        may_continue), budget)


class SharedApiReservationTests(unittest.TestCase):
    def test_ordinary_dispatch_cannot_spend_future_fetch_and_reserved_fetch_can(self):
        b = RequestBudget(2); future = b.reserve(); raw = FixtureTransport(); ch = channel(b, raw)
        self.assertTrue(ch.exchange(packet(ch, value='ordinary'))['ok'])
        self.assertFalse(ch.exchange(packet(ch, value='must not run'))['ok'])
        self.assertFalse(ch.rows[-1]['api_request_sent'])
        self.assertEqual(len(raw.commands), 1)
        self.assertEqual(b.snapshot(), dict(limit=2, spent=1, pending=1, available=0, stopped=False))
        self.assertEqual(ch.exchange_reserved(packet(ch, value='full'), future)['value'], 'full')
        self.assertEqual(b.spent, 2); self.assertEqual(b.pending, 0)
        self.assertEqual(len(raw.commands), 2)
        with self.assertRaises(RequestBudgetError): ch.exchange_reserved(packet(ch), future)

    def test_release_restores_capacity_but_does_not_invent_an_incurred_saving(self):
        b = RequestBudget(1); token = b.reserve(); ch = channel(b)
        self.assertFalse(ch.exchange(packet(ch))['ok'])
        b.cancel(token)
        self.assertEqual(b.spent, 0)
        self.assertTrue(ch.exchange(packet(ch, value=7))['ok'])
        self.assertEqual(b.spent, 1)
        with self.assertRaises(RequestBudgetError): b.cancel(token)

    def test_new_program_cannot_reset_shared_budget_or_consume_another_ledgers_token(self):
        b = RequestBudget(2); token = b.reserve(); first = channel(b)
        first.exchange(packet(first))
        second = channel(b)
        self.assertFalse(second.exchange(packet(second))['ok'])
        foreign = RequestBudget(1).reserve()
        with self.assertRaises(RequestBudgetError): second.exchange_reserved(packet(second), foreign)
        self.assertTrue(second.exchange_reserved(packet(second), token)['ok'])
        self.assertEqual(b.spent, 2)

    def test_catalog_and_packet_rejection_do_not_charge_or_consume_future_reservation(self):
        b = RequestBudget(2); token = b.reserve(); raw = FixtureTransport(); ch = channel(b, raw)
        self.assertFalse(ch.exchange(packet(ch, api='undiscovered'))['ok'])
        self.assertFalse(ch.exchange_reserved(packet(ch, api='undiscovered'), token)['ok'])
        with self.assertRaises(ValueError): ch.exchange({'kind': 'not a request'})
        self.assertEqual(b.spent, 0); self.assertEqual(b.pending, 1)
        self.assertEqual(raw.commands, [])
        self.assertTrue(ch.exchange_reserved(packet(ch), token)['ok'])

    def test_confirmed_exception_is_charged_and_effects_are_not_rolled_back(self):
        b = RequestBudget(2); token = b.reserve(); raw = FixtureTransport(); ch = channel(b, raw)
        self.assertFalse(ch.exchange_reserved(packet(ch, api='fail', value=9), token)['ok'])
        self.assertEqual(raw.world.effects, [('fail', 9)])
        self.assertEqual(ch.rows[-1]['api_execution']['status'], 'raised')
        self.assertEqual(b.spent, 1); self.assertFalse(b.stopped)
        # Semantic trust in a deferred total read must be invalidated by a higher layer.
        self.assertTrue(ch.exchange(packet(ch))['ok'])

    def test_unknown_transport_is_charged_once_and_stops_future_dispatch(self):
        class LostReply(FixtureTransport):
            def request(self, command):
                super().request(command)
                raise TimeoutError('fixture reply lost after effect')
        b = RequestBudget(3); token = b.reserve(); other = b.reserve()
        raw = LostReply(); ch = channel(b, raw)
        self.assertFalse(ch.exchange_reserved(packet(ch, value=8), token)['ok'])
        self.assertEqual(b.spent, 1); self.assertEqual(b.pending, 1); self.assertTrue(b.stopped)
        self.assertEqual(ch.rows[-1]['api_execution']['status'], 'unknown')
        for action in (lambda: ch.exchange(packet(ch)), lambda: b.cancel(other), lambda: channel(b)):
            with self.assertRaises(RequestBudgetError): action()
        self.assertEqual(len(raw.commands), 1)

    def test_proven_nonce_failure_precedes_dispatch_and_retains_reserved_liability(self):
        b = RequestBudget(2); token = b.reserve(); raw = FixtureTransport(); ch = channel(b, raw)
        with patch('public_api_result_transport.uuid.uuid4', side_effect=RuntimeError('fixture nonce')):
            self.assertFalse(ch.exchange_reserved(packet(ch), token)['ok'])
        self.assertFalse(ch.rows[-1]['api_request_sent'])
        self.assertEqual(ch.rows[-1]['api_execution']['status'], 'not_dispatched')
        self.assertEqual(b.spent, 0); self.assertEqual(b.pending, 1); self.assertTrue(b.stopped)
        self.assertEqual(raw.commands, [])

    def test_interrupt_after_send_is_retained_even_before_channel_row_exists(self):
        class Interrupted(FixtureTransport):
            def request(self, command):
                super().request(command)
                raise KeyboardInterrupt('fixture stop after effect')
        b = RequestBudget(2); future = b.reserve(); raw = Interrupted(); ch = channel(b, raw)
        with self.assertRaises(KeyboardInterrupt): ch.exchange(packet(ch, value=5))
        self.assertEqual(ch.rows, [])
        self.assertEqual(raw.world.effects, [('echo', 5)])
        self.assertEqual(b.spent, 1); self.assertEqual(b.pending, 1); self.assertTrue(b.stopped)
        self.assertEqual(b.events[-1]['status'], 'unknown')
        with self.assertRaises(RequestBudgetError): ch.exchange_reserved(packet(ch), future)

    def test_deadline_refusal_and_completion_never_create_a_retry_path(self):
        b = RequestBudget(2); token = b.reserve(); ch = channel(b, may_continue=lambda: False)
        self.assertFalse(ch.exchange_reserved(packet(ch), token)['ok'])
        self.assertEqual(b.spent, 0); self.assertEqual(b.pending, 1)
        end = channel(b)
        self.assertTrue(end.exchange(packet(end, api='finish'))['ok'])
        self.assertTrue(b.stopped); self.assertEqual(b.spent, 1); self.assertEqual(b.pending, 1)
        with self.assertRaises(RequestBudgetError): end.exchange_reserved(packet(end), token)

    def test_reentrant_dispatch_cannot_overspend_or_release_inflight_reservation(self):
        b = RequestBudget(2); future = b.reserve()
        class Reentrant(FixtureTransport):
            def request(self, command):
                with self_test.assertRaises(RequestBudgetError): ch.exchange(packet(ch))
                with self_test.assertRaises(RequestBudgetError): b.cancel(future)
                return super().request(command)
        self_test = self; raw = Reentrant(); ch = channel(b, raw)
        self.assertTrue(ch.exchange(packet(ch))['ok'])
        self.assertEqual(len(raw.commands), 1); self.assertEqual(b.spent, 1); self.assertEqual(b.pending, 1)


if __name__ == '__main__': unittest.main()
