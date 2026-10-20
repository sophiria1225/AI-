import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analyze_p3_timeline import describe_timeline


class TimelineInterpretationTests(unittest.TestCase):
    def setUp(self):
        self.summary = {
            "calls": [
                {"unit": "single", "input_tokens": 100, "output_tokens": 10,
                 "cached_input_tokens": 80, "wall_seconds": 1.5}
                for _ in range(4)
            ],
            "artifact_sha256": "final", "total_recorded_tokens": 440,
        }
        self.events = [
            {"turn": i, "unit": "single", "artifact": {"artifact_sha256": version},
             "artifact_changed": i != 4, "completion_vote_accepted": i == 4,
             "operations": [{"result": {"returncode": 0}}]}
            for i, version in enumerate(["final", "other", "final", "final"], 1)
        ]

    def test_returning_to_a_version_does_not_erase_intervening_work(self):
        result = describe_timeline(self.summary, self.events, "initial")
        self.assertEqual(result["first_final_hash_observation"], 1)
        self.assertEqual(result["final_hash_uninterrupted_suffix_starts_after_turn"], 3)
        self.assertEqual(result["later_model_calls"], 1)
        self.assertEqual(result["later_input_output_tokens"], 110)
        self.assertEqual(result["total_input_output_tokens"], 440)
        self.assertEqual(result["known_cached_input_tokens"], 320)

    def test_unknown_usage_and_overstated_cache_are_rejected(self):
        for key, value in (("input_tokens", None), ("cached_input_tokens", 101)):
            summary = copy.deepcopy(self.summary)
            summary["calls"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                describe_timeline(summary, self.events, "initial")

    def test_absent_cache_is_unknown_not_a_zero_cache_measurement(self):
        self.summary["calls"][0].pop("cached_input_tokens")
        result = describe_timeline(self.summary, self.events, "initial")
        self.assertEqual(result["unknown_cache_calls"], 1)
        self.assertIsNone(result["cached_fraction_of_input"])
        self.assertEqual(result["total_input_output_tokens"], 440)

    def test_mismatched_final_artifact_or_missing_turn_is_not_summarized(self):
        for summary, events in [
            (self.summary | {"artifact_sha256": "unobserved"}, self.events),
            (self.summary, self.events[:-1]),
        ]:
            with self.subTest(events=len(events)), self.assertRaises(ValueError):
                describe_timeline(summary, events, "initial")


if __name__ == "__main__":
    unittest.main()
