import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_pro_public_inputs import (
    GENERATOR_TEXT_COLUMNS, PUBLIC_COLUMNS, screen_projected_rows, validate_plan,
)


class PublicProjectionTests(unittest.TestCase):
    def row(self, repository, task_id):
        result = {key: "public fixture" for key in PUBLIC_COLUMNS}
        result.update(repo=repository, instance_id=task_id, version="2.0.0")
        return result

    def test_gold_column_is_rejected_instead_of_silently_passing_through(self):
        row = self.row("example/project", "one") | {"patch": "synthetic secret"}
        with self.assertRaisesRegex(ValueError, "Unexpected columns"):
            screen_projected_rows([row], set())

    def test_exposed_repository_is_excluded_without_removing_unseen_peers(self):
        rows = [self.row("NodeBB/NodeBB", "one"), self.row("example/project", "two")]
        kept, excluded = screen_projected_rows(rows, {"NodeBB/NodeBB"})
        self.assertEqual([row["instance_id"] for row in kept], ["two"])
        self.assertEqual(excluded, {"NodeBB/NodeBB": 1})

    def test_config_cannot_expand_inputs_or_ignore_the_exposure_registry(self):
        exposure = {"datasets": [{"dataset": "fixture",
                    "exclude_repositories_from_untouched_confirmation": ["NodeBB/NodeBB"]}]}
        plan = {"dataset": "fixture", "public_columns": list(PUBLIC_COLUMNS),
                "generator_text_columns": list(GENERATOR_TEXT_COLUMNS),
                "screening_excluded_repositories": ["NodeBB/NodeBB"]}
        validate_plan(plan, exposure)
        for key, value in [
            ("public_columns", list(PUBLIC_COLUMNS) + ["test_patch"]),
            ("generator_text_columns", list(GENERATOR_TEXT_COLUMNS) + ["before_repo_set_cmd"]),
            ("screening_excluded_repositories", []),
        ]:
            modified = copy.deepcopy(plan)
            modified[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_plan(modified, exposure)


if __name__ == "__main__":
    unittest.main()
