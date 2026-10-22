from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from probe_residual_output import syntax_only


class ResidualSyntaxTests(unittest.TestCase):
    def message(self, code, spans=None):
        return {'tool_calls': [{'function': {'name': 'run_python', 'arguments': json.dumps(
            {'code': code, 'span_ids': ['s1'] if spans is None else spans})}}]}

    def test_static_check_never_executes_valid_code(self):
        checked = syntax_only(self.message('raise RuntimeError("must not execute")'), {'s1'})
        self.assertTrue(checked['all_tools_valid_envelope_and_syntax'])
        self.assertEqual(checked['tool_execution_calls'], 0)
        self.assertFalse(checked['semantics_or_task_success_claim'])

    def test_truncated_code_and_unavailable_receipt_are_not_usable_syntax(self):
        for msg in (self.message('x = ['), self.message('print(1)', ['s2']), self.message('print(1)', ['s1', 's1'])):
            self.assertFalse(syntax_only(msg, {'s1'})['all_tools_valid_envelope_and_syntax'])

    def test_reasoning_or_final_text_without_a_tool_is_not_a_program(self):
        checked = syntax_only({'content': 'done', 'reasoning_content': 'thinking'}, {'s1'})
        self.assertFalse(checked['all_tools_valid_envelope_and_syntax'])

    def test_archive_function_must_reference_an_existing_receipt(self):
        message = {'tool_calls': [{'function': {'name': 'read_span', 'arguments': '{"span_id":"s1"}'}}]}
        self.assertTrue(syntax_only(message, {'s1'})['all_tools_valid_envelope_and_syntax'])
        self.assertFalse(syntax_only(message, set())['all_tools_valid_envelope_and_syntax'])


if __name__ == '__main__':
    unittest.main()
