"""Host/client JSON isolation with handwritten fixture API, no task data."""
import copy
import gc
import json
from pathlib import Path
import pickle
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from container_api_python import ApiChannel
from deferred_read_obligations import Assumptions
from deferred_view_protocol import DeferredReadHost, ReadAuthority, RemoteReadViews
from explicit_deferred_read_views import ClosedReadView
from public_api_result_transport import PublicResultTransport
from shared_api_reservations import BudgetedApiChannel, RequestBudget
from test_public_api_result_transport import FixtureTransport, catalog

TRUSTED = Assumptions(True, True, True)
VALUE = {'title': 'alpha', 'rating': 1}


def setup(*, limit=5, defer=True, authority=None, raw=None):
    b = RequestBudget(limit)
    raw = raw or FixtureTransport()
    transport = PublicResultTransport(raw)
    channel = BudgetedApiChannel(ApiChannel(catalog(), transport, limit), b)
    if authority is None:
        authority = lambda action, epoch: (ReadAuthority(epoch, {'title': action['args']['value']['title']}, TRUSTED)
            if action['api'] == 'echo' and type(action['args'].get('value')) is dict else None)
    rows = []
    host = DeferredReadHost(channel, authority=authority, defer=defer, on_record=rows.append)
    wire = []
    def exchange(packet):
        serialized = json.dumps(packet, allow_nan=False)
        wire.append(serialized)
        return json.loads(json.dumps(host.request(json.loads(serialized)), allow_nan=False))
    client = RemoteReadViews(exchange)
    return b, raw, host, client, wire, rows


class DeferredViewProtocolTests(unittest.TestCase):
    def test_known_field_uses_no_api_unknown_field_consumes_reserved_full_read(self):
        b, raw, host, client, wire, rows = setup(limit=1)
        v = client.read('fixture', 'echo', value=VALUE)
        self.assertEqual(v['title'], 'alpha'); self.assertEqual(len(wire), 1)
        self.assertEqual(b.spent, 0); self.assertEqual(b.pending, 1)
        self.assertEqual(v['rating'], 1); self.assertEqual(len(wire), 2)
        self.assertEqual(b.spent, 1); self.assertEqual(b.pending, 0)
        self.assertEqual(dict(v), VALUE); self.assertEqual(len(raw.commands), 1)
        self.assertEqual(sum(row['api_request_sent'] for row in rows), b.spent)

    def test_finalizer_queues_no_io_and_release_precedes_next_ordinary_admission(self):
        b, raw, host, client, wire, rows = setup(limit=1)
        v = client.read('fixture', 'echo', value=VALUE)
        container = {'saved': v}; del v; gc.collect()
        self.assertEqual(b.pending, 1); self.assertEqual(len(wire), 1)
        del container; gc.collect()
        self.assertEqual(b.pending, 1); self.assertEqual(len(wire), 1)
        self.assertEqual(client.call('fixture', 'echo', value=9), 9)
        self.assertEqual(b.spent, 1); self.assertEqual(b.pending, 0)
        self.assertEqual(raw.world.effects, [('echo', 9)])

    def test_surviving_alias_materializes_before_unknown_effect_and_keeps_snapshot(self):
        b, raw, host, client, wire, rows = setup(limit=3)
        v = client.read('fixture', 'echo', value=VALUE)
        retain = lambda held=v: held
        del v
        self.assertEqual(client.call('fixture', 'echo', value={'mutation_marker': 9}), {'mutation_marker': 9})
        self.assertEqual(raw.world.effects, [('echo', VALUE), ('echo', {'mutation_marker': 9})])
        self.assertEqual(retain()['rating'], 1)
        self.assertEqual(b.spent, 2); self.assertEqual(b.pending, 0); self.assertEqual(host.epoch, 1)

    def test_eager_and_deferred_have_identical_explicit_copy_export_interface(self):
        observed = []
        for defer in (False, True):
            b, raw, host, client, wire, rows = setup(defer=defer)
            v = client.read('fixture', 'echo', value=VALUE)
            self.assertIs(copy.copy(v), v)
            observed.append((v['title'], dict(v), copy.deepcopy(v), pickle.loads(pickle.dumps(v))))
            with self.assertRaises(TypeError): v['title'] = 'changed'
            self.assertEqual(b.spent, 1)
        self.assertEqual(observed[0], observed[1])

    def test_absent_or_stale_authority_falls_back_and_false_partial_stops(self):
        for authority in (lambda action, epoch: None,
                          lambda action, epoch: ReadAuthority(epoch-1, {'title': 'alpha'}, TRUSTED)):
            b, raw, host, client, wire, rows = setup(authority=authority)
            v = client.read('fixture', 'echo', value=VALUE)
            self.assertEqual(b.spent, 1); self.assertEqual(b.pending, 0); self.assertEqual(v['rating'], 1)
        b, raw, host, client, wire, rows = setup(authority=lambda a,e: ReadAuthority(e, {'title': 'wrong'}, TRUSTED))
        v = client.read('fixture', 'echo', value=VALUE)
        self.assertEqual(v['title'], 'wrong')  # False trust already exposes a wrong answer.
        with self.assertRaises(RuntimeError): dict(v)
        self.assertTrue(b.stopped); self.assertEqual(b.spent, 1)
        with self.assertRaises(ClosedReadView): v['title']

    def test_reserved_failure_prevents_following_effect_and_is_never_retried(self):
        b, raw, host, client, wire, rows = setup(authority=lambda a,e: ReadAuthority(e, {'title': 'alpha'}, TRUSTED))
        v = client.read('fixture', 'fail', value=7)
        with self.assertRaises(RuntimeError): client.call('fixture', 'echo', value='must not run')
        self.assertEqual(raw.world.effects, [('fail', 7)]); self.assertEqual(b.spent, 1)
        self.assertTrue(b.stopped); self.assertEqual(rows[0]['api_execution']['status'], 'raised')
        with self.assertRaises(ClosedReadView): v['title']
        self.assertEqual(len(raw.commands), 1)

    def test_cycle_and_program_change_keep_the_same_lease_and_budget(self):
        b, raw, host, client, wire, rows = setup(limit=2)
        v = client.read('fixture', 'echo', value=VALUE)
        cycle = [v]; cycle.append(cycle); del v
        base = ApiChannel(catalog(), host.channel.bridge, b.limit-b.spent)
        host.attach(BudgetedApiChannel(base, b))
        self.assertEqual(cycle[0]['rating'], 1); self.assertEqual(b.spent, 1)
        del cycle; gc.collect(); client.flush_releases()
        self.assertEqual(host.records, {}); self.assertEqual(b.spent, 1)

    def test_budget_refusal_does_not_perform_a_pointless_barrier(self):
        b, raw, host, client, wire, rows = setup(limit=1)
        v = client.read('fixture', 'echo', value=VALUE)
        with self.assertRaises(RuntimeError): client.call('fixture', 'echo', value='does not fit')
        self.assertEqual(b.spent, 0); self.assertEqual(b.pending, 1); self.assertEqual(raw.commands, [])
        self.assertEqual(v['rating'], 1); self.assertEqual(b.spent, 1)

    def test_lost_control_reply_stops_client_without_repeating_an_admitted_read(self):
        b, raw, host, original, wire, rows = setup()
        def lost(packet):
            host.request(json.loads(json.dumps(packet)))
            raise TimeoutError('fixture lost control reply')
        client = RemoteReadViews(lost)
        with self.assertRaises(TimeoutError): client.read('fixture', 'echo', value=VALUE)
        self.assertTrue(client.closed); self.assertEqual(b.pending, 1); self.assertEqual(b.spent, 0)
        with self.assertRaises(ClosedReadView): client.read('fixture', 'echo', value=VALUE)
        self.assertEqual(len(host.control_events), 1)


if __name__ == '__main__': unittest.main()
