import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pro_verifier_result import classify_result, expected_control


class ProVerifierResultTests(unittest.TestCase):
    def setUp(self):
        self.config = {"fail_to_pass": "['synthetic_fix']", "pass_to_pass": ["synthetic_existing"]}
        self.output = {"tests": [{"name": "synthetic_fix", "status": "FAILED"},
                                 {"name": "synthetic_existing", "status": "PASSED"}]}

    def test_complete_negative_result_with_exit_one_is_valid(self):
        result = classify_result(self.config, self.output, 0.0, 1, False)
        self.assertTrue(result["required_results_complete"])
        self.assertTrue(expected_control(result, "negative_control"))
        self.assertFalse(expected_control(result, "reference_control"))
        self.assertNotIn("synthetic_fix", str(result))

    def test_complete_positive_requires_matching_reward_and_exit(self):
        self.output["tests"][0]["status"] = "PASSED"
        result = classify_result(self.config, self.output, 1.0, 0, False)
        self.assertTrue(expected_control(result, "reference_control"))
        for reward, code in [(0.0, 0), (1.0, 1)]:
            with self.subTest(reward=reward, code=code), self.assertRaises(ValueError):
                classify_result(self.config, self.output, reward, code, False)

    def test_missing_skipped_or_duplicated_results_are_not_valid_failures(self):
        cases = [
            {"tests": self.output["tests"][1:]},
            {"tests": self.output["tests"] + [self.output["tests"][0]]},
        ]
        for status in ("SKIPPED", "ERROR", None):
            changed = copy.deepcopy(self.output)
            changed["tests"][0]["status"] = status
            cases.append(changed)
        for output in cases:
            with self.subTest(output=output), self.assertRaises(ValueError):
                classify_result(self.config, output, 0.0, 1, False)

    def test_abnormal_process_or_unknown_oom_is_not_task_failure(self):
        for code, oom in [(2, False), (137, True), (1, None), (True, False)]:
            with self.subTest(code=code, oom=oom), self.assertRaises(ValueError):
                classify_result(self.config, self.output, 0.0, code, oom)

    def test_existing_regressions_do_not_pass_negative_calibration(self):
        self.output["tests"][1]["status"] = "FAILED"
        result = classify_result(self.config, self.output, 0.0, 1, False)
        self.assertFalse(expected_control(result, "negative_control"))

    def test_bad_expected_lists_and_nonbinary_rewards_are_rejected(self):
        for expected in ([], ["synthetic_fix", "synthetic_fix"], "[1]", "__import__('os')"):
            with self.subTest(expected=expected), self.assertRaises((ValueError, SyntaxError)):
                classify_result({**self.config, "fail_to_pass": expected}, self.output, 0.0, 1, False)
        for reward in (None, True, 0.5):
            with self.subTest(reward=reward), self.assertRaises(ValueError):
                classify_result(self.config, self.output, reward, 1, False)


if __name__ == "__main__":
    unittest.main()
