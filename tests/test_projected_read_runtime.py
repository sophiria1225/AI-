import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from appworld_native_tools import NativeCatalog
from container_api_python import ApiChannel
from field_read_contract import CONTRACT_ID, SOURCE, TARGET
from projected_read_runtime import FieldChannel, INSTALL, ProjectedReadRuntime


SONG = {"song_id": 7, "title": "Example", "album_id": None,
        "duration": 120, "artists": [{"id": 3, "name": "Artist"}]}


def catalog():
    specs = {TARGET: ["song_id"], SOURCE: ["access_token", "page_index", "page_limit"],
             "spotify__change": ["song_id"], "supervisor__complete_task": ["status"],
             "api_docs__show_api_doc": ["app_name", "api_name"]}
    c = NativeCatalog([{"type": "function", "function": {"name": name,
                      "parameters": {"type": "object", "properties": {k: {} for k in keys}}}}
                      for name, keys in specs.items()])
    c.visible.update(specs)
    return c


class FixtureBridge:
    def __init__(self):
        self.calls = []
        self.value = SONG | {"genre": "test"}
        self.fail = False
        self.transport_error = False

    def request(self, message):
        self.calls.append(copy.deepcopy(message))
        if self.transport_error: raise OSError("fixture transport")
        if self.fail: return {"ok": False, "error": "fixture error"}
        action = message["call"]
        value = self.value
        if action["api"] == "show_song_library": value = [SONG | {"added_at": "fixture"}]
        return {"ok": True, "result": {"observation": json.dumps(value),
                                       "declared_complete": action["api"] == "complete_task"}}


def packet(number, app="spotify", api="show_song", **args):
    return {"kind": "api", "id": number, "app": app, "api": api,
            "arguments": args or {"song_id": 7}}


def field_packet(number, fields=("title", "artists"), **args):
    return packet(number, "_harness", "read_fields", target_app="spotify", target_api="show_song",
                  fields=list(fields), arguments=args or {"song_id": 7})


class ProjectedRuntimeTests(unittest.TestCase):
    def make(self, mode="contract", remaining=10):
        bridge = FixtureBridge(); base = ApiChannel(catalog(), bridge, remaining)
        runtime = ProjectedReadRuntime(mode, execution_scope="test", verified_contract=CONTRACT_ID)
        return FieldChannel(base, runtime), bridge, runtime

    def test_installed_helper_uses_separate_target_names(self):
        calls = []
        scope = {"call_api": lambda app, api, **kwargs: calls.append((app, api, kwargs)) or {"title": "ok"}}
        exec(INSTALL, scope, scope)
        self.assertEqual(scope["read_fields"]("spotify", "show_song", ["title"], song_id=7), {"title": "ok"})
        self.assertEqual(calls[0][0:2], ("_harness", "read_fields"))
        self.assertEqual(calls[0][2]["arguments"], {"song_id": 7})

    def test_partial_hit_has_one_row_no_dispatch_and_no_budget_spend(self):
        c, b, runtime = self.make()
        c.exchange(packet(1, "spotify", "show_song_library", access_token="fixture"))
        reply = c.exchange(field_packet(2))
        self.assertEqual(reply["value"], {"title": "Example", "artists": SONG["artists"]})
        self.assertEqual(len(b.calls), 1); self.assertEqual(len(c.rows), 2)
        self.assertEqual(c.remaining, 9)
        self.assertFalse(c.rows[-1]["api_request_sent"])
        self.assertFalse(c.rows[-1]["observation"]["field_read"]["full_api_response"])

    def test_all_modes_project_identically_and_exact_is_a_strong_raw_baseline(self):
        for mode in ("none", "exact", "contract"):
            c, b, _ = self.make(mode)
            first = c.exchange(field_packet(1, ("title",)))
            second = c.exchange(packet(2))
            self.assertEqual(first["value"], {"title": "Example"})
            self.assertEqual(second["value"], b.value)
            self.assertEqual(len(b.calls), 2 if mode == "none" else 1)
            self.assertEqual(len(c.rows), 2)

    def test_cache_cannot_bypass_discovery_or_bad_arguments(self):
        c, b, r = self.make()
        r.cache.observe(SOURCE, {"access_token": "fixture"}, [SONG], r.context())
        c.catalog.visible.remove(TARGET)
        self.assertFalse(c.exchange(field_packet(1))["ok"])
        c.catalog.visible.add(TARGET)
        self.assertFalse(c.exchange(field_packet(2, unknown=3))["ok"])
        self.assertEqual(b.calls, [])

    def test_budget_deadline_completion_and_fatal_state_block_even_cached_values(self):
        for mode in ("budget", "deadline", "complete", "fatal"):
            c, b, r = self.make()
            r.cache.observe(SOURCE, {"access_token": "fixture"}, [SONG], r.context())
            if mode == "budget": c.base.remaining = 0
            if mode == "deadline": c.base.may_continue = lambda: False
            if mode == "complete": c.base.complete = True
            if mode == "fatal": c.base.fatal = True
            self.assertFalse(c.exchange(field_packet(1))["ok"])
            self.assertIn("not_executed", c.rows[-1]["observation"])
            self.assertEqual(b.calls, [])

    def test_unknown_sent_operation_invalidates_but_rejected_one_does_not(self):
        c, b, r = self.make()
        r.cache.observe(SOURCE, {"access_token": "fixture"}, [SONG], r.context())
        c.exchange(packet(1, "spotify", "not_discovered"))
        self.assertTrue(c.exchange(field_packet(2))["ok"])
        self.assertEqual(len(b.calls), 0)
        c.exchange(packet(3, "spotify", "change"))
        c.exchange(field_packet(4))
        self.assertEqual(len(b.calls), 2)
        self.assertEqual(r.revision, 1)

    def test_projection_failure_preserves_backend_charge_and_full_receipt(self):
        c, b, r = self.make()
        reply = c.exchange(field_packet(1, ("missing",)))
        self.assertFalse(reply["ok"])
        self.assertEqual(c.remaining, 9)
        self.assertTrue(c.rows[-1]["api_request_sent"])
        self.assertEqual(json.loads(c.rows[-1]["observation"]["observation"]), b.value)
        self.assertEqual(r.cache.exact, {})

    def test_transport_failure_propagates_to_original_channel(self):
        c, b, r = self.make(); b.transport_error = True
        self.assertFalse(c.exchange(field_packet(1))["ok"])
        self.assertTrue(c.base.fatal)
        self.assertTrue(c.rows[-1]["effects_unknown"])
        self.assertFalse(c.exchange(field_packet(2))["ok"])
        self.assertEqual(len(b.calls), 1)

    def test_completion_propagates_and_blocks_following_reads(self):
        c, b, r = self.make()
        c.exchange(packet(1, "supervisor", "complete_task", status="success"))
        self.assertTrue(c.base.complete)
        self.assertFalse(c.exchange(field_packet(2))["ok"])
        self.assertEqual(len(b.calls), 1)

    def test_internal_envelope_does_not_grant_other_api_access(self):
        c, b, r = self.make()
        p = field_packet(1); p["arguments"]["target_app"] = "admin"
        self.assertFalse(c.exchange(p)["ok"])
        p = field_packet(2); p["arguments"]["fields"] = []
        self.assertFalse(c.exchange(p)["ok"])
        with self.assertRaises(ValueError): c.exchange(field_packet(2))
        self.assertEqual(len(c.rows), 2); self.assertEqual(b.calls, [])

    def test_api_error_is_charged_and_not_cached(self):
        c, b, r = self.make(); b.fail = True
        self.assertFalse(c.exchange(field_packet(1))["ok"])
        self.assertEqual(c.remaining, 9)
        self.assertEqual(r.cache.exact, {})
        self.assertEqual(r.counts["projected_failed"], 1)


if __name__ == "__main__": unittest.main()
