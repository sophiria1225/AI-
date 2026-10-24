"""Ordinary cache control fixtures; no model, AppWorld or task evaluation."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from container_api_python import ApiChannel
from coalesced_live_sequences import PROGRAMS
from deferred_view_protocol import RemoteReadViews
from field_read_contract import CONTRACT_ID
from ordinary_complete_read_cache import (OrdinaryCachedReadHost,
    OrdinaryCachedCoalescedHost, OrdinaryCachedReadProgram)
from public_api_result_transport import PublicResultTransport
from shared_api_reservations import BudgetedApiChannel, RequestBudget
from test_public_contract_read_views import setup as old_setup, SONG
from test_public_read_views_live_probe import Fixture, catalog
from test_persistent_read_view_python import TrustedSubprocessSession


def setup(*, defer=False, limit=8):
    raw, budget, old, _ = old_setup(defer=defer, limit=limit)
    cls = OrdinaryCachedCoalescedHost if defer else OrdinaryCachedReadHost
    host = cls(old.channel, execution_scope='ordinary-cache-fixture',
               verified_contract=CONTRACT_ID, defer=defer)
    client = RemoteReadViews(lambda packet: json.loads(json.dumps(host.request(json.loads(json.dumps(packet))))))
    return raw, budget, host, client


class OrdinaryCompleteCacheTests(unittest.TestCase):
    def test_ordinary_hit_after_view_fetch_is_free_at_exhausted_budget(self):
        raw, b, h, c = setup(limit=1)
        view = c.read('spotify', 'show_song', song_id=1)
        full = c.call('spotify', 'show_song', song_id=1)
        self.assertEqual(full, dict(view)); self.assertEqual(full, SONG)
        self.assertEqual((b.spent, b.pending, h.ordinary_complete_reuses), (1, 0, 1))
        self.assertEqual(len(raw.calls), 1)
        full['artists'][0]['name'] = 'changed local copy'
        self.assertEqual(c.call('spotify', 'show_song', song_id=1), SONG)

    def test_partial_is_never_returned_as_a_complete_ordinary_response(self):
        raw, b, h, c = setup(defer=True, limit=3)
        c.call('spotify', 'show_song_library', access_token='fixture-token')
        first = c.read('spotify', 'show_song', song_id=1)
        second = c.read('spotify', 'show_song', song_id=1)
        self.assertEqual((b.spent, b.pending), (1, 1))
        full = c.call('spotify', 'show_song', song_id=1)
        self.assertEqual(full, SONG); self.assertEqual(dict(first), dict(second))
        self.assertEqual((b.spent, b.pending, h.ordinary_complete_reuses), (2, 0, 0))
        self.assertEqual(h.materialization_cache_reuses, 1)

    def test_free_hit_preserves_an_unrelated_pending_obligation_at_full_budget(self):
        raw = Fixture(); budget = RequestBudget(3)
        channel = BudgetedApiChannel(ApiChannel(catalog(), PublicResultTransport(raw), 3), budget)
        host = OrdinaryCachedCoalescedHost(channel, execution_scope='pending-fixture',
                                           verified_contract=CONTRACT_ID, defer=True)
        c = RemoteReadViews(lambda packet: json.loads(json.dumps(host.request(json.loads(json.dumps(packet))))))
        c.call('spotify', 'show_song_library', access_token='fixture-token', page_index=0, page_limit=3)
        first = c.call('spotify', 'show_song', song_id=10)
        pending = c.read('spotify', 'show_song', song_id=11)
        self.assertEqual((budget.spent, budget.pending, budget.available), (2, 1, 0))
        self.assertEqual(c.call('spotify', 'show_song', song_id=10), first)
        self.assertEqual((budget.spent, budget.pending, budget.available), (2, 1, 0))
        self.assertEqual(dict(pending)['song_id'], 11)
        self.assertEqual((budget.spent, budget.pending), (3, 0))

    def test_mutation_invalidates_ordinary_cache_but_preserves_old_view(self):
        for defer in (False, True):
            raw, b, h, c = setup(defer=defer)
            view = c.read('spotify', 'show_song', song_id=1)
            c.call('spotify', 'show_song', song_id=1)
            c.call('spotify', 'like_song', song_id=1, access_token='fixture-token')
            after = c.call('spotify', 'show_song', song_id=1)
            self.assertEqual((view['like_count'], after['like_count']), (0, 1))
            self.assertEqual([x['api'] for x in raw.calls], ['show_song', 'like_song', 'show_song'])
            self.assertEqual((b.spent, h.ordinary_complete_reuses), (3, 1))

    def test_cache_does_not_restore_a_revoked_API_capability(self):
        raw, b, h, c = setup()
        c.call('spotify', 'show_song', song_id=1)
        h.channel.catalog.visible.remove('spotify__show_song')
        with self.assertRaises(RuntimeError):
            c.call('spotify', 'show_song', song_id=1)
        self.assertEqual((b.spent, h.ordinary_complete_reuses), (1, 0))

    def test_invalid_arguments_and_non_target_reads_cannot_hit(self):
        raw, b, h, c = setup()
        c.call('spotify', 'show_song', song_id=1)
        with self.assertRaises(RuntimeError):
            c.call('spotify', 'show_song', song_id=1, extra=True)
        c.call('spotify', 'show_album', album_id=1)
        c.call('spotify', 'show_album', album_id=1)
        self.assertEqual((b.spent, h.ordinary_complete_reuses), (3, 0))

    def test_different_task_does_not_inherit_complete_cache(self):
        for _ in range(2):
            raw, b, h, c = setup()
            c.call('spotify', 'show_song', song_id=1)
            self.assertEqual((b.spent, h.ordinary_complete_reuses), (1, 0))

    def test_stopped_ledger_cannot_be_bypassed_by_a_known_complete_value(self):
        raw, b, h, c = setup()
        c.call('spotify', 'show_song', song_id=1)
        b.stopped = True
        with self.assertRaises(RuntimeError):
            c.call('spotify', 'show_song', song_id=1)
        self.assertEqual((b.spent, h.ordinary_complete_reuses), (1, 0))

    def test_same_seven_handwritten_programs_tie_with_shared_ordinary_cache(self):
        for liked in (False, True):
            outputs = []
            for defer in (False, True):
                with tempfile.TemporaryDirectory() as tmp:
                    folder = Path(tmp); raw = Fixture(liked=liked)
                    bridge = PublicResultTransport(raw); b = RequestBudget(20)
                    session = TrustedSubprocessSession(folder); cat = catalog()
                    program = OrdinaryCachedReadProgram(session, b, execution_scope='same-fixture',
                                                        verified_contract=CONTRACT_ID, defer=defer)
                    rows, results = [], []
                    try:
                        for n, source in enumerate(PROGRAMS, 1):
                            result = program(source, {}, ApiChannel(cat, bridge, b.limit-b.spent),
                                storage_root=folder, record_dir=folder/f'p{n}', timeout=5, on_record=rows.append)
                            self.assertEqual(result['status'], 'ok')
                            results.append(result)
                        expected = [6, 0, 1, 0, 0, 1, 4] if defer else [6, 1, 0, 1, 0, 1, 3]
                        self.assertEqual([x['api_requests'] for x in results], expected)
                        self.assertEqual((b.spent, b.pending), (12, 0))
                        self.assertFalse(program.host.records)
                        self.assertEqual(len(raw.calls), 12)
                        self.assertEqual(sum(x['api_request_sent'] for x in rows), 12)
                        self.assertEqual(program.host.ordinary_complete_reuses, 0 if defer else 1)
                        outputs.append([x['stdout'] for x in results])
                    finally:
                        session.close()
            self.assertEqual(outputs[0], outputs[1])


if __name__ == '__main__':
    unittest.main()
