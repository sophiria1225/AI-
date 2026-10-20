import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from local_llama import model_call
from run_context_comparison import BudgetStop, Inference, recorded_compression


class RuntimeControls(unittest.TestCase):
    def test_continuation_keeps_experiment_parameters_and_does_not_retry(self):
        root = Path(__file__).resolve().parents[1]
        old = json.loads((root / "configs/P6_context_plan_v02.json").read_text())
        new = json.loads((root / "configs/P6_context_plan_v03.json").read_text())
        metadata = {"version", "supersedes", "run_order", "prior_run_order", "runtime_correction"}
        self.assertEqual({k: v for k, v in old.items() if k not in metadata},
                         {k: v for k, v in new.items() if k not in metadata})
        self.assertEqual(new["prior_run_order"], old["run_order"][:2])
        self.assertEqual(new["run_order"], [
            [task, arm, name.replace("_V02", "_V03")] for task, arm, name in old["run_order"][2:]])

    def config(self):
        return {"model": {"model": "test", "num_ctx": 1000, "temperature": 1,
                          "seed": 42, "num_predict": 100, "call_timeout_seconds": 600},
                "draft_temperature": .7, "agent_temperature": 1, "seed": 42,
                "max_output_tokens": 100, "max_calls": 4,
                "max_wall_seconds": 60, "max_total_tokens": 1000}

    def test_wall_timeout_keeps_unknown_usage_and_stops_trial(self):
        with tempfile.TemporaryDirectory() as directory:
            inference = Inference(self.config(), Path(directory))
            with patch("run_context_comparison.count_input", return_value={"input_tokens": 40}), \
                    patch("run_context_comparison.model_call", return_value={
                        "status": "error", "input_tokens": None, "output_tokens": None,
                        "wall_seconds": 3, "error_kind": "timeout", "timeout_scope": "run_wall"
                    }) as call:
                with self.assertRaisesRegex(BudgetStop, "wall_limit_during_model_call"):
                    inference.call("focus", [], [])
                self.assertEqual(call.call_count, 1)
            self.assertEqual(inference.tokens, 0)  # known cost only, not true zero cost
            saved = json.loads((Path(directory) / "usage.json").read_text())
            self.assertIsNone(saved[0]["input_tokens"])
            self.assertEqual(saved[0]["status"], "error")

    def test_call_timeout_is_not_misclassified_as_run_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            inference = Inference(self.config(), Path(directory))
            with patch("run_context_comparison.count_input", return_value={"input_tokens": 40}), \
                    patch("run_context_comparison.model_call", return_value={
                        "status": "error", "input_tokens": None, "output_tokens": None,
                        "wall_seconds": 3, "error_kind": "timeout", "timeout_scope": "call"}):
                with self.assertRaisesRegex(RuntimeError, "usage unknown"):
                    inference.call("focus", [], [])

    def test_network_failure_at_wall_scoped_call_is_still_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            inference = Inference(self.config(), Path(directory))
            with patch("run_context_comparison.count_input", return_value={"input_tokens": 40}), \
                    patch("run_context_comparison.model_call", return_value={
                        "status": "error", "input_tokens": None, "output_tokens": None,
                        "wall_seconds": .01, "error_kind": "request_or_response",
                        "timeout_scope": "run_wall"}):
                with self.assertRaises(RuntimeError):
                    inference.call("agent", [], [])

    def test_input_count_cannot_use_stale_remaining_time(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("run_context_comparison.time.monotonic", return_value=0):
                inference = Inference(self.config(), Path(directory))
            with patch("run_context_comparison.time.monotonic", side_effect=[59, 61]), \
                    patch("run_context_comparison.count_input", return_value={"input_tokens": 40}), \
                    patch("run_context_comparison.model_call") as call:
                with self.assertRaisesRegex(BudgetStop, "wall_limit"):
                    inference.call("agent", [], [])
                call.assert_not_called()

    def test_invalid_compression_snapshot_is_not_changed_by_next_turn(self):
        with tempfile.TemporaryDirectory() as directory:
            inference = Inference(self.config(), Path(directory))
            events = []
            selected = ["s1"]
            ledger = {"items": []}
            with patch("run_context_comparison.compress", side_effect=ValueError("bad source")):
                selected, kept_ledger, invalid = recorded_compression(
                    "focus", inference, {}, {"s1": {}}, selected, ledger, {}, events)
            selected.append("s2")
            self.assertTrue(invalid)
            self.assertIs(kept_ledger, ledger)
            self.assertEqual(events[0]["visible_before"], ["s1"])
            self.assertEqual(events[0]["visible_after"], ["s1"])

    def test_interrupted_compression_is_saved_with_cost_and_original_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            inference = Inference(self.config(), Path(directory))
            events, selected = [], ["s1"]

            def fail(*args):
                inference.calls += [
                    {"status": "ok", "input_tokens": 10, "output_tokens": 5},
                    {"status": "error", "input_tokens": None, "output_tokens": None}]
                raise BudgetStop("wall_limit_during_model_call")

            with patch("run_context_comparison.compress", side_effect=fail):
                with self.assertRaises(BudgetStop):
                    recorded_compression("focus", inference, {}, {"s1": {}},
                                         selected, None, {}, events)
            event = json.loads((Path(directory) / "compressions.json").read_text())[0]
            self.assertEqual(event["status"], "aborted")
            self.assertEqual(event["calls"], 2)
            self.assertEqual(event["tokens"], 15)
            self.assertEqual(event["unknown_usage_calls"], 1)
            self.assertEqual(event["visible_after"], ["s1"])

    def test_adapter_records_timeout_cause_without_inventing_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("local_llama.post", side_effect=TimeoutError("timed out")), \
                    patch("local_llama.signal.alarm"):
                result = model_call(self.config()["model"], [], directory, 3, [])
            self.assertEqual(result["error_kind"], "timeout")
            self.assertEqual(result["timeout_scope"], "run_wall")
            self.assertEqual(result["timeout_seconds"], 3)
            self.assertIsNone(result["input_tokens"])
            self.assertIsNone(result["output_tokens"])


if __name__ == "__main__":
    unittest.main()
