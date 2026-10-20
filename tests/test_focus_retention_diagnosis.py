import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analyze_focus_retention import analyze, operations


class RetentionDiagnosisControls(unittest.TestCase):
    def test_operations_ignore_transport_ids_but_preserve_argument_values(self):
        def message(identifier, value):
            return {"tool_calls": [{"id": identifier, "function": {
                "name": "tool", "arguments": json.dumps({"target": value})}}]}
        self.assertEqual(operations(message("a", 1)), operations(message("b", 1)))
        self.assertNotEqual(operations(message("a", 1)), operations(message("a", 2)))

    def make_trial(self, root, name, drafts, threshold):
        out = root / name
        out.mkdir()
        (out / "plan.json").write_text(json.dumps({"focus_rollouts": 3, "focus_threshold": threshold}))
        usage = []
        for index, draft in enumerate(drafts, 1):
            call = f"call_{index:03d}"
            directory = out / call
            directory.mkdir()
            (directory / "request.json").write_text(json.dumps({"messages": [{"content":
                json.dumps({"task": "PRIVATE_TASK", "memory": {"visible_spans": [
                    {"id": "s1", "observation": "PRIVATE_DATA"}, {"id": "s2"}]}})}]}))
            (directory / "response.json").write_text(json.dumps({"status": "ok",
                "message": {"reasoning_content": "PRIVATE_REASONING", "tool_calls": [{
                    "function": {"name": "submit_selection", "arguments": draft}}]}}))
            usage.append({"id": call, "role": "focus", "status": "ok"})
        (out / "usage.json").write_text(json.dumps(usage))
        return out

    def test_partial_drafts_do_not_change_the_predeclared_voting_threshold(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = json.dumps({"steps": [{"depends_on": ["s1", "s2", "future_step"]}],
                                "rescued": []})
            trial = self.make_trial(root, "trial", [value, "TRUNCATED"], .7)
            reference = self.make_trial(root, "reference", [], .7)
            result = analyze(trial, reference)
            row = result["cycles"][0]
            self.assertEqual(result["retention_minimum"], 3)
            self.assertFalse(row["already_all_retained"])
            self.assertEqual(row["forward_kept_lower_bound"], 0)
            self.assertEqual(row["nonhistory_reference_count"], 1)
            self.assertNotIn("PRIVATE_", json.dumps(result))

    def test_rescue_can_prove_all_retained_even_with_missing_future_drafts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = json.dumps({"steps": [], "rescued": ["s1", "s2", "future_step"]})
            trial = self.make_trial(root, "trial", [value, "TRUNCATED"], .7)
            reference = self.make_trial(root, "reference", [], .7)
            row = analyze(trial, reference)["cycles"][0]
            self.assertTrue(row["already_all_retained"])
            self.assertEqual(row["earliest_observed_draft_proving_all_retained"], 1)


if __name__ == "__main__":
    unittest.main()
