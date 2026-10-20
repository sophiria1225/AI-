import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from probe_memory_input import transform, outcome, public_body


class MemoryInputProbeControls(unittest.TestCase):
    def messages(self):
        return [{"role": "system", "content": "same instruction"},
                {"role": "user", "content": json.dumps({
                    "task": {"instruction": "PRIVATE_TASK"},
                    "memory": {"visible_spans": [
                        {"id": "s1", "action": {"name": "appworld_api", "arguments": "{}"},
                         "observation": {"observation": "real"}, "assistant": "read it"},
                        {"id": "s2", "action": {"name": "appworld_api", "arguments": '{"bad":'},
                         "observation": {"format_error": "incomplete"},
                         "assistant": "PRIVATE_PROPOSAL"}],
                        "available_archive_ids": ["s1", "s2"]}})}]

    def test_raw_is_identical_and_transformations_never_mutate_archive_input(self):
        messages = self.messages()
        frozen = copy.deepcopy(messages)
        raw, ids = transform(messages, "raw")
        self.assertEqual(raw, messages)
        self.assertEqual(ids, {"s2"})
        transform(messages, "quarantine")
        transform(messages, "execution_tag")
        self.assertEqual(messages, frozen)

    def test_only_unexecuted_body_changes_and_real_observations_survive(self):
        original = json.loads(self.messages()[-1]["content"])
        for variant in ("quarantine", "execution_tag"):
            output, _ = transform(self.messages(), variant)
            body = json.loads(output[-1]["content"])
            self.assertEqual(body["task"], original["task"])
            self.assertEqual(body["memory"]["visible_spans"][0], original["memory"]["visible_spans"][0])
            self.assertEqual(body["memory"]["visible_spans"][1]["observation"],
                             original["memory"]["visible_spans"][1]["observation"])
        tagged, _ = transform(self.messages(), "execution_tag")
        last = json.loads(tagged[-1]["content"])["memory"]["visible_spans"][1]
        self.assertFalse(last["runtime_execution"]["action_dispatched"])
        self.assertEqual(last["action"], original["memory"]["visible_spans"][1]["action"])

    def test_indicator_does_not_claim_truth_and_public_export_has_no_private_text(self):
        ledger = {"items": [{"key": "x", "requirement": "PRIVATE_REQUIREMENT",
                             "status": "done", "source_ids": ["s2"]}],
                  "constraints": [], "unresolved": []}
        message = {"tool_calls": [{"function": {
            "name": "submit_ledger", "arguments": json.dumps(ledger)}}]}
        result = outcome(message, self.messages(), {"s2"})
        self.assertEqual(result["done_only_unexecuted_sources"], 1)
        self.assertNotIn("success", result)
        body = public_body([dict(variant="raw", seed=43, known_tokens=10,
                                 reasoning="PRIVATE_REASONING", **result)], "running")
        self.assertNotIn("PRIVATE_", body)

    def test_nonobject_ledger_item_is_invalid_output_not_an_aborted_probe(self):
        message = {"tool_calls": [{"function": {
            "name": "submit_ledger", "arguments": json.dumps({
                "items": ["malformed"], "constraints": [], "unresolved": []})}}]}
        result = outcome(message, self.messages(), {"s2"})
        self.assertFalse(result["schema_valid"])
        self.assertIsNone(result["done_items"])


if __name__ == "__main__":
    unittest.main()
