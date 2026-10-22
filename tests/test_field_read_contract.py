import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from field_read_contract import (CONTRACT_ID, SOURCE, TARGET, FieldReadCache,
                                ReadContext, verify_public_implementation)
from probe_field_contract import process
import json


class FieldReadContractTests(unittest.TestCase):
    def setUp(self):
        self.ctx = ReadContext("one-execution-and-audience", "revision-1", CONTRACT_ID)
        self.song = {"song_id": 7, "title": "Example", "album_id": None,
                     "duration": 120, "artists": [{"id": 3, "name": "Artist"}]}
        self.detail = self.song | {"genre": "test"}
        self.calls = []

    def fetch(self, api, arguments):
        self.calls.append((api, arguments))
        return copy.deepcopy(self.detail)

    def cache(self, mode="contract", **options):
        c = FieldReadCache(mode, verified_contract=CONTRACT_ID, **options)
        c.observe(SOURCE, {"access_token": "fixture-only"},
                  [self.song | {"added_at": "private-fixture"}], self.ctx)
        return c

    def read(self, cache, fields=("title", "artists"), context=None, arguments=None):
        return cache.read_fields(TARGET, arguments or {"song_id": 7}, fields,
                                 context or self.ctx, self.fetch)

    def test_all_three_modes_return_the_same_projection(self):
        results = [self.read(self.cache(mode)) for mode in ("none", "exact", "contract")]
        self.assertEqual([r.backend_calls for r in results], [1, 1, 0])
        self.assertEqual(results[0].value, results[1].value)
        self.assertEqual(results[1].value, results[2].value)
        self.assertNotIn("added_at", results[2].value)

    def test_exact_baseline_reuses_whole_response_for_different_field_sets(self):
        c = self.cache("exact")
        self.assertEqual(self.read(c, ("title",)).source, "fetched")
        self.assertEqual(self.read(c, ("genre", "duration")).source, "exact")
        self.assertEqual(len(self.calls), 1)

    def test_private_or_uncovered_fields_fetch_instead_of_partial_success(self):
        c = self.cache()
        self.assertEqual(self.read(c, ("title", "genre")).source, "fetched")
        with self.assertRaises(KeyError):
            self.read(c, ("added_at",))
        self.assertEqual(len(self.calls), 2)

    def test_revision_scope_unknown_and_contract_changes_invalidate(self):
        contexts = [ReadContext("other", "revision-1", CONTRACT_ID),
                    ReadContext(self.ctx.execution_scope, "revision-2", CONTRACT_ID),
                    ReadContext(self.ctx.execution_scope, None, CONTRACT_ID),
                    ReadContext(self.ctx.execution_scope, "revision-1", "wrong")]
        for context in contexts:
            with self.subTest(context=context):
                c = self.cache()
                self.assertEqual(self.read(c, context=context).source, "fetched")
                self.assertEqual(self.read(c).source, "fetched")

    def test_explicit_mutation_invalidation_prevents_stale_reuse(self):
        c = self.cache(); c.invalidate()
        self.detail["title"] = "Changed"
        self.assertEqual(self.read(c).value["title"], "Changed")

    def test_prior_conflict_does_not_use_later_reply_as_oracle(self):
        c = self.cache()
        c.observe(SOURCE, {"access_token": "fixture-only"},
                  [self.song | {"title": "Different"}], self.ctx)
        self.assertIsNone(c.lookup(TARGET, {"song_id": 7}, ["title"], self.ctx))
        self.assertEqual(self.read(c).source, "fetched")
        self.assertEqual(self.read(c).source, "fetched")

    def test_exact_reply_conflict_does_not_select_a_winner(self):
        c = self.cache("exact")
        c.observe(TARGET, {"song_id": 7}, self.detail, self.ctx)
        c.observe(TARGET, {"song_id": 7}, self.detail | {"title": "Changed"}, self.ctx)
        self.assertEqual(self.read(c).source, "fetched")

    def test_wrong_id_type_app_or_extra_argument_cannot_reuse(self):
        c = self.cache()
        for args in ({"song_id": "7"}, {"song_id": True}, {"song_id": 8},
                     {"song_id": 7, "extra": True}):
            self.assertIsNone(c.lookup(TARGET, args, ["title"], self.ctx))
        self.assertIsNone(c.lookup("other__show_song", {"song_id": 7}, ["title"], self.ctx))
        self.assertIsNone(c.lookup("spotify__show_album", {"album_id": 7}, ["title"], self.ctx))

    def test_missing_or_bad_source_auth_and_shape_are_not_sources(self):
        for args in ({}, {"access_token": ""}, {"access_token": 4},
                     {"access_token": "fixture", "unverified": True}):
            c = FieldReadCache("contract", verified_contract=CONTRACT_ID)
            c.observe(SOURCE, args, [self.song], self.ctx)
            self.assertEqual(self.read(c).source, "fetched")

    def test_native_values_are_copied_on_ingestion_and_return(self):
        c = self.cache()
        self.song["artists"][0]["name"] = "Modified outside cache"
        first = self.read(c); first.value["artists"][0]["name"] = "Modified result"
        self.assertEqual(self.read(c).value["artists"][0]["name"], "Artist")
        self.assertIs(type(self.read(c).value["artists"]), list)

    def test_errors_and_missing_projection_are_not_cached(self):
        c = self.cache("exact")
        def fail(*args): raise RuntimeError("fixture failure")
        with self.assertRaises(RuntimeError):
            c.read_fields(TARGET, {"song_id": 7}, ["title"], self.ctx, fail)
        with self.assertRaises(KeyError): self.read(c, ("absent",))
        self.assertEqual(c.exact, {})

    def test_unverified_implementation_never_enables_cache(self):
        c = FieldReadCache("contract")
        c.observe(SOURCE, {"access_token": "fixture"}, [self.song], self.ctx)
        self.assertEqual(self.read(c).source, "fetched")
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "apis.py").write_text("changed")
            with self.assertRaises(ValueError): verify_public_implementation(Path(directory))

    def test_limits_skip_values_without_affecting_response(self):
        c = self.cache(max_value_bytes=1)
        self.assertEqual(self.read(c).value["title"], "Example")
        self.assertGreater(c.bounds_rejected, 0)
        c = self.cache(max_records=1)
        c.observe(SOURCE, {"access_token": "fixture"}, [self.song | {"song_id": 8}], self.ctx)
        self.assertEqual(len(c.fields), 1)
        self.assertGreater(c.bounds_rejected, 0)

    def test_invalid_field_request_never_fetches(self):
        c = self.cache()
        for fields in ([], "title", ["title", "title"], [None]):
            with self.assertRaises(ValueError): self.read(c, fields)
        self.assertEqual(self.calls, [])

    def test_malformed_public_fields_cannot_be_served_from_library(self):
        c = FieldReadCache("contract", verified_contract=CONTRACT_ID)
        c.observe(SOURCE, {"access_token": "fixture"},
                  [self.song | {"artists": [{"id": 3, "private": "value"}]}], self.ctx)
        self.assertEqual(self.read(c).source, "fetched")

    def test_probe_invalidates_unknown_get_but_not_unsent_operation(self):
        for sent, expected in ((True, "fetched"), (False, "cross_api")):
            cache = self.cache()
            # Align the explicit revision used by the record adapter.
            cache.invalidate()
            ctx = ReadContext("scope", "0", CONTRACT_ID)
            cache.observe(SOURCE, {"access_token": "fixture"}, [self.song], ctx)
            spans = {"u": {"action": {"name": "a__unknown_read", "arguments": "{}"},
                            "observation": {"observation": {}}},
                     "t": {"action": {"name": TARGET, "arguments": '{"song_id":7}'},
                            "observation": {"observation": self.detail}}}
            _, counts, rows = process([{"span_id": "u", "api_request_sent": sent},
                                      {"span_id": "t", "api_request_sent": True}],
                                     spans, {"contract": cache}, "scope", measure=True)
            self.assertEqual(rows[0]["modes"]["contract"]["source"], expected)
            self.assertEqual(counts["contract_mismatches"], 0)

    def test_probe_current_reply_cannot_seed_or_repair_a_hit(self):
        cache = self.cache()
        cache.invalidate(); ctx = ReadContext("scope", "0", CONTRACT_ID)
        cache.observe(SOURCE, {"access_token": "fixture"}, [self.song], ctx)
        span = {"action": {"name": TARGET, "arguments": '{"song_id":7}'},
                "observation": {"observation": self.detail | {"title": "Unobserved change"}}}
        _, counts, rows = process([{"span_id": "t", "api_request_sent": True}],
                                 {"t": span}, {"contract": cache}, "scope", measure=True)
        self.assertEqual(counts["contract_mismatches"], 1)
        self.assertEqual(cache.exact, {})
        self.assertEqual(cache.lookup(TARGET, {"song_id": 7}, ["title"], ctx).value["title"], "Example")

    def test_probe_cached_success_against_recorded_error_is_a_mismatch(self):
        cache = self.cache(); cache.invalidate()
        ctx = ReadContext("scope", "0", CONTRACT_ID)
        cache.observe(SOURCE, {"access_token": "fixture"}, [self.song], ctx)
        span = {"action": {"name": TARGET, "arguments": '{"song_id":7}'},
                "observation": {"api_error": "fixture error"}}
        _, counts, rows = process([{"span_id": "t", "api_request_sent": True}],
                                 {"t": span}, {"contract": cache}, "scope", measure=True)
        self.assertEqual(counts["contract_mismatches"], 1)
        self.assertNotIn("fixture", json.dumps(rows))


if __name__ == "__main__": unittest.main()
