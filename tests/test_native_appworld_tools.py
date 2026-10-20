import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from appworld_native_tools import NativeCatalog, dispatch_native_calls


def tool(name, properties):
    return {"type": "function", "function": {
        "name": name, "parameters": {"type": "object", "properties": properties}}}


def call(name, arguments):
    return {"function": {"name": name, "arguments": json.dumps(arguments)}}


class NativeToolControls(unittest.TestCase):
    def setUp(self):
        self.tools = [
            tool("api_docs__show_api_doc", {"app_name": {}, "api_name": {}}),
            tool("api_docs__show_api_descriptions", {"app_name": {}}),
            tool("supervisor__complete_task", {}),
            tool("example__read", {"item": {}}),
        ]
        self.catalog = NativeCatalog(self.tools)
        self.bridge = Mock()
        self.bridge.request.return_value = {
            "ok": True, "result": {"observation": "public", "declared_complete": False}}

    def dispatch(self, calls, remaining=10, **kwargs):
        return dispatch_native_calls({"tool_calls": calls}, self.catalog, self.bridge,
                                     lambda sid, offset: {"id": sid, "offset": offset},
                                     remaining_api_calls=remaining, **kwargs)

    def test_discovery_uses_requested_public_name_without_answers_and_preserves_schemas(self):
        original = copy.deepcopy(self.tools)
        with self.assertRaises(ValueError):
            self.catalog.decode(call("example__read", {"item": 1})["function"])
        self.dispatch([call("api_docs__show_api_doc", {"app_name": "example", "api_name": "read"})])
        self.assertEqual(self.catalog.decode(call("example__read", {"item": 1})["function"]),
                         {"app": "example", "api": "read", "args": {"item": 1}})
        self.assertEqual(self.tools, original)
        supplied = self.catalog.tools()
        supplied[0]["function"]["name"] = "changed"
        self.assertNotEqual(self.catalog.tools()[0]["function"]["name"], "changed")

    def test_malformed_or_unknown_calls_are_never_dispatched(self):
        rows = self.dispatch([
            {"function": {"name": "supervisor__complete_task", "arguments": "{"}},
            call("supervisor__complete_task", []),
            call("supervisor__complete_task", {"unexpected": 1}),
            call("admin__read", {}),
        ])
        self.bridge.request.assert_not_called()
        self.assertTrue(all(not r["api_request_sent"] for r in rows))
        self.assertTrue(all("format_error" in r["observation"] for r in rows))

    def test_multiple_calls_preserve_order_and_completion_stops_later_operations(self):
        self.bridge.request.side_effect = [
            {"ok": True, "result": {"declared_complete": False}},
            {"ok": True, "result": {"declared_complete": True}},
        ]
        rows = self.dispatch([
            call("api_docs__show_api_doc", {"app_name": "example", "api_name": "read"}),
            call("supervisor__complete_task", {}),
            call("example__read", {"item": 1}),
        ])
        self.assertEqual(self.bridge.request.call_count, 2)
        self.assertTrue(rows[1]["observation"]["declared_complete"])
        self.assertIn("not_executed", rows[2]["observation"])

    def test_budget_stops_are_explicit_and_do_not_silently_drop_calls(self):
        rows = self.dispatch([call("supervisor__complete_task", {})] * 3, remaining=1)
        self.assertEqual(self.bridge.request.call_count, 1)
        self.assertEqual(len(rows), 3)
        self.assertEqual(sum(r["api_request_sent"] for r in rows), 1)
        blocked = self.dispatch([call("supervisor__complete_task", {})], may_continue=lambda: False)
        self.assertIn("not_executed", blocked[0]["observation"])
        self.assertEqual(self.bridge.request.call_count, 1)

    def test_archive_reads_do_not_repeat_api_actions(self):
        rows = self.dispatch([call("read_span", {"span_id": "s1", "offset": 12})])
        self.assertEqual(rows[0]["observation"], {"id": "s1", "offset": 12})
        self.bridge.request.assert_not_called()

    def test_api_error_is_not_reported_as_a_format_rejection(self):
        self.bridge.request.return_value = {"ok": False, "error": "simulated API rejection"}
        rows = self.dispatch([call("supervisor__complete_task", {})])
        self.assertTrue(rows[0]["api_request_sent"])
        self.assertIn("api_error", rows[0]["observation"])
        self.assertNotIn("format_error", rows[0]["observation"])

    def test_partial_batch_is_persisted_and_unknown_effects_block_later_calls(self):
        stored = []
        self.bridge.request.side_effect = [
            {"ok": True, "result": {"declared_complete": False}},
            TimeoutError("uncertain"),
        ]
        rows = self.dispatch([call("supervisor__complete_task", {})] * 3, on_record=stored.append)
        self.assertEqual(rows, stored)
        self.assertEqual(self.bridge.request.call_count, 2)
        self.assertTrue(rows[1]["api_request_sent"])
        self.assertTrue(rows[1]["effects_unknown"])
        self.assertNotIn("format_error", rows[1]["observation"])
        self.assertIn("not_executed", rows[2]["observation"])

    def test_newly_discovered_schema_applies_to_next_request_not_the_current_one(self):
        rows = self.dispatch([
            call("api_docs__show_api_doc", {"app_name": "example", "api_name": "read"}),
            call("example__read", {"item": 1}),
        ])
        self.assertIn("format_error", rows[1]["observation"])
        self.assertEqual(self.bridge.request.call_count, 1)
        later = self.dispatch([call("example__read", {"item": 1})])
        self.assertTrue(later[0]["api_request_sent"])

    def test_app_description_exposes_that_public_app_without_task_labels(self):
        rows = self.dispatch([
            call("api_docs__show_api_descriptions", {"app_name": "example"})])
        self.assertEqual(rows[0]["new_tools"], ["example__read"])
        self.assertEqual(self.catalog.decode(call("example__read", {"item": 2})["function"]),
                         {"app": "example", "api": "read", "args": {"item": 2}})
        self.assertEqual(self.catalog.expose_requested_document(
            {"app": "api_docs", "api": "show_api_descriptions", "args": {"app_name": "admin"}}), [])


if __name__ == "__main__":
    unittest.main()
