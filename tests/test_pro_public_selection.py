import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_pro_public_inputs import PUBLIC_COLUMNS
from select_pro_public_candidates import select


class ProPublicSelectionTests(unittest.TestCase):
    def setUp(self):
        self.rows = []
        for repo in ("one/repo", "two/repo", "three/repo"):
            for n in range(3):
                row = {k: "" for k in PUBLIC_COLUMNS}
                row.update(repo=repo, instance_id=f"{repo}-{n}", version="2.0.0",
                           base_commit="a" * 40, problem_statement=f"Public request {n}")
                self.rows.append(row)
        self.exposure = {"datasets": [{"dataset": "test",
                                      "exclude_repositories_from_untouched_confirmation": ["exposed/repo"]}]}
        self.plan = {"dataset": "test", "dataset_revision": "fixed", "seed": "bounded-test",
                     "expected_rows": 9, "expected_repositories": 3,
                     "repository_count": 2, "per_repository": 2}

    def run_selection(self, rows=None):
        raw = "\n".join(json.dumps(row) for row in (self.rows if rows is None else rows)).encode()
        plan = {**self.plan, "public_inputs_sha256": hashlib.sha256(raw).hexdigest()}
        return select(raw, plan, self.exposure)

    def test_order_invariance_and_untouched_repository(self):
        result = self.run_selection()
        self.assertEqual(result, self.run_selection(list(reversed(self.rows))))
        self.assertEqual(len(result["candidates"]), 4)
        self.assertEqual(len(result["repositories_not_reviewed_in_this_plan"]), 1)
        self.assertTrue(set(result["review_repositories"]).isdisjoint(
            result["repositories_not_reviewed_in_this_plan"]))

    def test_reject_nonpublic_columns_and_exposure(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["patch"] = "private"
        with self.assertRaisesRegex(ValueError, "allowlist"):
            self.run_selection(rows)
        rows = copy.deepcopy(self.rows)
        rows[0]["repo"] = "exposed/repo"
        with self.assertRaisesRegex(ValueError, "exposed"):
            self.run_selection(rows)

    def test_reject_duplicate_ids_and_input_mutation(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["instance_id"] = rows[1]["instance_id"]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.run_selection(rows)
        with self.assertRaisesRegex(ValueError, "differs"):
            select(b"changed", {**self.plan, "public_inputs_sha256": "0" * 64}, self.exposure)


if __name__ == "__main__":
    unittest.main()
