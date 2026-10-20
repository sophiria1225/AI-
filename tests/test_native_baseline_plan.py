import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_native_batch import public_body


class NativeBaselinePlanControls(unittest.TestCase):
    def test_task_model_and_inference_budgets_match_the_existing_comparison(self):
        before = json.loads((ROOT / "configs/P6_context_plan_v03.json").read_text())
        after = json.loads((ROOT / "configs/P8_native_baseline_v01.json").read_text())
        for key in ("appworld_version", "task_ids", "model_selection", "model", "seed",
                    "agent_temperature", "max_output_tokens", "max_calls", "max_total_tokens",
                    "max_wall_seconds", "observation_page_characters"):
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(after["max_api_requests"], before["max_calls"])
        self.assertEqual([r[0] for r in after["run_order"]], before["task_ids"])
        self.assertEqual(after["wait_for_probe"], "P7_01")

    def test_progress_exports_only_counts_and_does_not_call_declaration_success(self):
        rows = [{"task_number": 1, "status": "finished", "calls": 3, "tokens": 200,
                 "unknown_usage_calls": 1, "declared_complete": True,
                 "instruction": "PRIVATE_TASK", "reasoning": "PRIVATE_REASONING"}]
        text = public_body(rows, {"status": "running"})
        self.assertNotIn("PRIVATE_", text)
        self.assertIn("未確定", text)
        self.assertNotIn("| 成功 |", text)
        rows[0]["success"] = "true"
        with self.assertRaises(ValueError):
            public_body(rows, {"status": "running"})


if __name__ == "__main__":
    unittest.main()
