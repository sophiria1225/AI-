import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from context_preservation import (
    api_code, page_span, parse_submission, select_focus, validate_ledger,
    render_memory,
)
from run_context_comparison import BudgetStop, Inference


class MemoryControls(unittest.TestCase):
    def draft(self, cited=(), rescued=()):
        return {"steps": [{"plan": "continue", "depends_on": list(cited)}],
                "rescued": list(rescued), "rescue_reason": ""}

    def test_defensive_rescue_survives_no_forward_citation(self):
        keep, _ = select_focus([self.draft(rescued=["s2"]), self.draft(), self.draft()],
                               ["s1", "s2"])
        self.assertEqual(keep, ["s2"])

    def test_three_drafts_point_three_is_union_not_majority(self):
        keep, _ = select_focus([self.draft(["s1"]), self.draft(["s2"]), self.draft()],
                               ["s1", "s2", "s3"], .3)
        self.assertEqual(keep, ["s1", "s2"])

    def test_invalid_citation_does_not_silently_delete_memory(self):
        with self.assertRaises(ValueError):
            select_focus([self.draft(["hidden_answer"])], ["s1"])

    def test_page_reconstruction_preserves_unicode_without_reexecution(self):
        spans = {"s1": {"observation": "日" * 21}}
        chunks, offset = [], 0
        while True:
            result = page_span(spans, "s1", offset, 7)
            chunks.append(result["text"])
            offset = result["next_offset"]
            if offset is None:
                break
        self.assertEqual(json.loads("".join(chunks)), spans["s1"])

    def test_unknown_archive_id_is_rejected(self):
        with self.assertRaises(ValueError):
            page_span({}, "s1")

    def test_visible_page_is_reversible_and_archive_is_not_modified(self):
        spans = {"s1": {"id": "s1", "observation": "x" * 200}}
        before = json.dumps(spans)
        memory = json.loads(render_memory(spans, ["s1"], page_limit=50))
        page = memory["visible_spans"][0]["first_page"]
        self.assertEqual(page["next_offset"], 50)
        self.assertEqual(before, json.dumps(spans))

    def test_ledger_requires_available_source_but_does_not_claim_truth(self):
        ledger = {"items": [{"key": "x", "requirement": "check",
                             "status": "uncertain", "source_ids": ["s1"]}],
                  "constraints": [], "unresolved": ["scope unknown"]}
        self.assertEqual(validate_ledger(ledger, ["s1"]), ledger)
        with self.assertRaises(ValueError):
            validate_ledger(ledger, [])

    def test_completion_is_not_inferred_from_ledger_status(self):
        ledger = {"items": [], "constraints": [], "unresolved": []}
        self.assertEqual(validate_ledger(ledger, []), ledger)
        self.assertNotIn("success", ledger)

    def test_multiple_submissions_are_not_cherry_picked(self):
        call = {"function": {"name": "submit_selection", "arguments": "{}"}}
        with self.assertRaises(ValueError):
            parse_submission({"tool_calls": [call, call]}, "submit_selection")

    def test_api_string_is_data_not_executable_code(self):
        docs = {"phone": {"lookup": {"parameters": [{"name": "query"}]}}}
        payload = {"app": "phone", "api": "lookup",
                   "args": {"query": "' ); __import__('os').system('bad') #"}}
        tree = ast.parse(api_code(payload, docs))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        self.assertEqual(len(calls), 2)  # print and the whitelisted API
        with self.assertRaises(ValueError):
            api_code({"app": "admin", "api": "lookup", "args": {}}, docs)

    def test_unknown_parameter_cannot_override_requester_controls(self):
        docs = {"phone": {"lookup": {"parameters": [{"name": "query"}]}}}
        with self.assertRaises(ValueError):
            api_code({"app": "phone", "api": "lookup",
                      "args": {"client": "override"}}, docs)

    def config(self):
        return {"model": {"num_ctx": 1000}, "draft_temperature": .7,
                "agent_temperature": 1, "seed": 42, "max_output_tokens": 100,
                "max_calls": 4, "max_wall_seconds": 60, "max_total_tokens": 300}

    def test_draft_cost_counts_against_execution_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            inference = Inference(self.config(), Path(directory))
            inference.calls = [{"status": "ok", "input_tokens": 150,
                                "output_tokens": 20, "role": "focus"}]
            with patch("run_context_comparison.count_input",
                       return_value={"input_tokens": 40}), patch(
                           "run_context_comparison.model_call") as model:
                with self.assertRaises(BudgetStop):
                    inference.call("agent", [], [])
                model.assert_not_called()

    def test_unknown_usage_stops_without_free_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            inference = Inference(self.config(), Path(directory))
            with patch("run_context_comparison.count_input",
                       return_value={"input_tokens": 40}), patch(
                    "run_context_comparison.model_call",
                    return_value={"status": "error", "input_tokens": None,
                                  "output_tokens": None, "wall_seconds": .1}):
                with self.assertRaisesRegex(RuntimeError, "usage unknown"):
                    inference.call("focus", [], [])
            self.assertEqual(len(inference.calls), 1)
            self.assertIsNone(inference.calls[0]["input_tokens"])


if __name__ == "__main__":
    unittest.main()
