import ast
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from inspect_truncated_code_prefixes import code_string_prefix, syntactic_prefix
from inspect_truncated_prefix_followup import api_shapes, statement_matches


class PrefixScopeTests(unittest.TestCase):
    def test_observed_escapes_and_incomplete_final_escape(self):
        value = code_string_prefix('{"code":"import csv\\nx = [1, 2\\')
        self.assertEqual(value['status'], 'open_string_prefix')
        self.assertEqual(value['code'], 'import csv\nx = [1, 2')
        parsed = syntactic_prefix(value['code'])
        self.assertEqual(parsed['characters'], len('import csv\n'))
        self.assertEqual(parsed['statement_types'], {'Import': 1})
        self.assertEqual(parsed['direct_call_api_nodes'], 0)
        self.assertFalse(parsed['safe_to_execute_established'])

    def test_partial_unicode_does_not_invent_character(self):
        self.assertEqual(code_string_prefix('{"code":"x=1\\n\\u12')['code'], 'x=1\n')
        self.assertEqual(code_string_prefix('{"code":"\\u65e5')['code'], '日')
        self.assertIsNone(code_string_prefix('{"code":"\\u12xz')['code'])

    def test_other_member_order_is_out_of_scope_not_absence(self):
        value = code_string_prefix('{"span_ids":[],"code":"x=1\\n')
        self.assertEqual(value['status'], 'outside_first_code_string_scope')
        self.assertIsNone(value['code'])

    def test_literal_control_and_unknown_escape_are_refused(self):
        self.assertIsNone(code_string_prefix('{"code":"x=1\n')['code'])
        self.assertIsNone(code_string_prefix('{"code":"x=1\\q')['code'])

    def test_closed_code_string_does_not_consume_later_members(self):
        value = code_string_prefix('{"code":"x=1\\n", "span_ids": [')
        self.assertEqual(value['status'], 'closed_string')
        self.assertEqual(value['code'], 'x=1\n')

    def test_unfinished_list_is_not_parseable_work(self):
        self.assertEqual(syntactic_prefix('items = [\n  1,\n')['status'], 'no_parseable_nonempty_line_prefix')

    def test_parseable_compound_is_not_execution_authorization(self):
        value = syntactic_prefix('if ready:\n    call_api("a", "write")\nelse:\n')
        self.assertEqual(value['direct_call_api_nodes'], 1)
        self.assertFalse(value['safe_to_execute_established'])
        self.assertFalse(value['reusable_work_established'])

    def test_final_expression_without_observed_newline_is_excluded(self):
        self.assertEqual(syntactic_prefix('call_api("a", "write")')['status'], 'no_parseable_nonempty_line_prefix')
        self.assertEqual(syntactic_prefix('x' * 20001)['status'], 'outside_code_length_scope')

    def test_ast_matching_ignores_layout_but_preserves_values(self):
        left = ast.parse('x = 1\ny = 2\n')
        self.assertEqual(statement_matches(left, ast.parse('\nx=1\n\ny=2\nz=3\n')), 2)
        self.assertEqual(statement_matches(left, ast.parse('x=2\ny=2\n')), 0)
        self.assertEqual(statement_matches(left, ast.parse('x=1\n')), 1)

    def test_dynamic_api_names_remain_unknown(self):
        shapes = api_shapes(ast.parse('call_api(app, "read", **kw)\n'))
        self.assertEqual(shapes, [{'line': 1, 'app': None, 'api': 'read', 'keyword_names': [None]}])


if __name__ == '__main__':
    unittest.main()
