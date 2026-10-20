import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_context_runtime import audit_trial


class RuntimeAuditControls(unittest.TestCase):
    def test_missing_attempt_and_mutated_snapshot_are_detected_without_exporting_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            usage = [
                {"id": "call_001", "role": "focus", "status": "ok", "input_tokens": 10,
                 "output_tokens": 5, "wall_seconds": 1, "finish_reason": "tool_calls"},
                {"id": "call_002", "role": "agent", "status": "ok", "input_tokens": 10,
                 "output_tokens": 5, "wall_seconds": 1},
                {"id": "call_003", "role": "focus", "status": "error", "input_tokens": None,
                 "output_tokens": None, "wall_seconds": 3}]
            (root / "usage.json").write_text(json.dumps(usage))
            (root / "compressions.json").write_text(json.dumps([{
                "status": "invalid_keep_original", "visible_before": ["s1", "s2"],
                "visible_after": ["s1"]}]))
            for call in (usage[0], usage[2]):
                out = root / call["id"]
                out.mkdir()
                (out / "request.json").write_text(json.dumps({
                    "messages": [{"content": json.dumps({
                        "task": "PRIVATE_TASK", "memory": {"visible_spans": [
                            {"id": "s1", "observation": "PRIVATE_OBSERVATION"}]}})}]}))
                (out / "response.json").write_text(json.dumps({
                    "status": call["status"], "message": {"reasoning_content": "PRIVATE_REASONING",
                    "tool_calls": [{"function": {"arguments": json.dumps({
                        "steps": [{"plan": "PRIVATE_PLAN", "depends_on": ["bad", "bad"]}],
                        "rescued": []})}}]}}))
            with patch("audit_context_runtime.summarize_trial", return_value={}):
                result = audit_trial(root)
            self.assertEqual(result["runtime_artifact_findings"], {
                "before_snapshot_mismatches": 1, "missing_compression_records": 1})
            self.assertEqual(result["compression_audit"][0]["structural_errors"], {
                "unparseable_arguments": 0, "unavailable_references": 1,
                "duplicate_reference_lists": 1})
            self.assertNotIn("PRIVATE_", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
