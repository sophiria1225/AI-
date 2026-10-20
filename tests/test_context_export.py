import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from summarize_context_pilot import summarize_trial
from watch_context_pilot import public_body


class ExportControls(unittest.TestCase):
    def setup_record(self, root):
        summary = {
            "run_id": "probe", "task_id": "fixture", "arm": "focus",
            "stop_reason": "token_reservation_limit", "declared_complete": False,
            "known_total_tokens": 50, "usage_by_role": {
                "focus": {"calls": 1, "input_tokens": 40, "output_tokens": 10}},
            "model_calls": 1, "tool_turns": 0, "compression_events": 1,
            "format_errors": 0, "api_bridge_errors": 0, "wall_seconds": 1}
        (root / "summary.json").write_text(json.dumps(summary))
        row = {"id": "call_001", "status": "ok", "input_tokens": 40,
               "output_tokens": 10, "predicted_input_tokens": 40}
        (root / "usage.json").write_text(json.dumps([row]))
        call = root / "call_001"
        call.mkdir()
        (call / "response.json").write_text(json.dumps(
            dict(row, message={"content": "PRIVATE_MODEL_REASONING"})))
        (root / "evaluation_private.json").write_text("PRIVATE_EVALUATION")

    def test_export_uses_counts_not_private_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.setup_record(root)
            result = summarize_trial(root)
            self.assertEqual(result["known_total_tokens"], 50)
            self.assertEqual(result["audit_errors"], [])
            self.assertNotIn("PRIVATE", json.dumps(result))

    def test_evaluation_from_different_execution_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.setup_record(root)
            (root / "evaluation.json").write_text(json.dumps({
                "execution_summary_sha256": "0" * 64, "run_id": "probe",
                "task_id": "fixture", "official_success": True, "pass_count": 1,
                "fail_count": 0, "evaluation_returned_to_model": False}))
            self.assertIn("evaluation is not bound to frozen execution",
                          summarize_trial(root)["audit_errors"])

    def test_terminal_cost_mismatch_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.setup_record(root)
            response = root / "call_001/response.json"
            value = json.loads(response.read_text())
            value["output_tokens"] = 11
            response.write_text(json.dumps(value))
            self.assertTrue(summarize_trial(root)["audit_errors"])

    def test_progress_ignores_raw_model_and_evaluator_fields(self):
        row = {"task_number": 1, "arm": "full", "status": "running",
               "calls": 2, "tokens": 70, "model_text": "PRIVATE_TRACE",
               "evaluator": "PRIVATE_ANSWER"}
        self.assertNotIn("PRIVATE", public_body([row]))
        row["success"] = "PRIVATE_ANSWER"
        with self.assertRaises(ValueError):
            public_body([row])


if __name__ == "__main__":
    unittest.main()
