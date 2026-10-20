import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_p5_evidence import describe_operation, TRUNCATION_MARKER


TEMPLATE = """{% if output.output | length < 10000 %}{{output.output}}{% else %}
<output_head>{{output.output[:5000]}}</output_head>
<output_tail>{{output.output[-5000:]}}</output_tail>{% endif %}"""


class EvidenceAuditControls(unittest.TestCase):
    def row(self, output, command="cat source", code=0, **updates):
        operation = {"record": "tool_001", "command": command,
                     "result": {"output": output, "returncode": code, "exception_info": ""}}
        captured = {"output": output, "exit_code": code,
                    "total_bytes": len(output.encode()), "captured_bytes": len(output.encode())}
        captured.update(updates)
        return describe_operation(operation, captured, TEMPLATE)

    def test_second_elision_can_remove_only_a_marker(self):
        row = self.row("a"*5000 + TRUNCATION_MARKER + "b"*5000)
        self.assertTrue(row["formatter_elision"])
        self.assertTrue(row["formatter_removes_only_upstream_marker"])
        self.assertEqual(row["formatter_additional_source_chars_removed"], 0)

    def test_actual_middle_loss_is_not_dismissed_as_presentation(self):
        row = self.row("a"*5000 + "RELEVANT_MIDDLE" + "b"*5000)
        self.assertEqual(row["formatter_additional_source_chars_removed"], 15)
        self.assertFalse(row["formatter_removes_only_upstream_marker"])

    def test_short_or_boundary_output_has_no_middle_loss(self):
        for n in (0, 9999, 10000):
            with self.subTest(n=n):
                self.assertEqual(
                    self.row("a"*n)["formatter_additional_source_chars_removed"], 0
                )

    def test_non_ascii_bytes_are_not_character_counts(self):
        row = self.row("漢字")
        self.assertEqual(row["delivered_output_chars"], 2)
        self.assertEqual(row["captured_bytes"], 6)

    def test_pipeline_limit_is_recorded_even_when_result_is_short(self):
        row = self.row("one line", "rg key . | head -n 2")
        self.assertTrue(row["contains_head_or_tail_syntax"])
        self.assertFalse(row["upstream_truncation_marker"])

    def test_empty_grep_does_not_become_global_absence(self):
        row = self.row("", "grep needle one_file | head", code=1)
        self.assertTrue(row["empty_output_exit_one_with_grep"])
        self.assertNotIn("global_absence", row)
        self.assertFalse(self.row("", "python broken.py", code=1)[
            "empty_output_exit_one_with_grep"])

    def test_unknown_and_impossible_sizes_fail(self):
        for updates in ({"captured_bytes": None}, {"captured_bytes": -1},
                        {"total_bytes": 0, "captured_bytes": 1},
                        {"captured_bytes": True}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                self.row("x", **updates)

    def test_report_does_not_export_source_content(self):
        text = "UNPUBLISHED_CONTENT_SENTINEL"
        row = self.row(text, command="echo UNPUBLISHED_COMMAND_SENTINEL")
        self.assertNotIn(text, repr(row))
        self.assertNotIn("UNPUBLISHED_COMMAND_SENTINEL", repr(row))


if __name__ == "__main__":
    unittest.main()
