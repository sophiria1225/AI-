import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from return_use_scope import analyze
from inspect_return_use_scope import validate


class ReturnUseScopeTests(unittest.TestCase):
    def test_direct_projection_is_only_a_syntax_candidate(self):
        r = analyze("title = call_api('spotify', 'show_song', song_id=sid)['title']")
        self.assertEqual(r['direct_field_helper_syntax_candidates'], 1)
        self.assertFalse(r['online_replacement_verified'])
        self.assertIsNone(r['measured_savings'])

    def test_binding_remains_open_to_future_programs_and_aliases(self):
        r = analyze("song = call_api('spotify', 'show_song', song_id=sid)\n"
                    "title = song['title']\nalias = song\n")
        self.assertEqual(r['use_counts'], {'name_binding': 1})
        self.assertEqual(r['direct_field_helper_syntax_candidates'], 0)
        # Future access to rating is possible; the earlier classification must
        # neither consult a future program nor infer title-only demand from it.
        self.assertEqual(analyze("print(alias['rating'])")['call_api_syntax_sites'], 0)

    def test_whole_value_escapes_and_ignored_return_are_not_projection(self):
        for template, expected in [("print({})", 'whole_value_argument'),
                                   ("saved = [{}]", 'container_escape'),
                                   ("{}", 'discarded_root'),
                                   ("for x in {}:\n pass", 'iteration')]:
            r = analyze(template.format("call_api('spotify', 'show_song', song_id=1)"))
            self.assertEqual(r['use_counts'], {expected: 1})
            self.assertEqual(r['direct_field_helper_syntax_candidates'], 0)

    def test_get_missing_and_default_semantics_are_not_rewritten(self):
        r = analyze("print(call_api('spotify', 'show_song', song_id=1).get('title', 'missing'))")
        self.assertEqual(r['sites'][0]['root_use'], 'literal_get')
        self.assertTrue(r['sites'][0]['get_has_default'])
        self.assertEqual(r['direct_field_helper_syntax_candidates'], 0)

    def test_dynamic_key_private_field_and_other_api_fail_closed(self):
        for source in ["call_api('spotify', 'show_song', song_id=1)[field]",
                       "call_api('spotify', 'show_song', song_id=1)['rating']",
                       "call_api('spotify', 'show_song', song_id=1)['added_at']",
                       "call_api('other', 'show_song', song_id=1)['title']",
                       "call_api(app, 'show_song', song_id=1)['title']",
                       "call_api('spotify', 'show_song', **args)['title']"]:
            self.assertEqual(analyze(source)['direct_field_helper_syntax_candidates'], 0)

    def test_deferred_execution_and_nested_definitions_are_not_admitted(self):
        expr = "call_api('spotify', 'show_song', song_id=1)['title']"
        for source in [f"def later():\n return {expr}", f"later = lambda: {expr}",
                       f"later = ({expr} for x in values)", f"class Later:\n title = {expr}"]:
            r = analyze(source)
            self.assertTrue(r['sites'][0]['deferred_or_nested_definition'])
            self.assertEqual(r['direct_field_helper_syntax_candidates'], 0)

    def test_bridge_rebinding_and_introspection_are_recorded(self):
        expr = "title = call_api('spotify', 'show_song', song_id=1)['title']"
        for prefix in ["call_api = fake", "from module import f as call_api", "globals()", "exec(text)"]:
            r = analyze(prefix+'\n'+expr)
            self.assertTrue(r['current_program_hazards'])
            self.assertEqual(r['direct_field_helper_syntax_candidates'], 0)

    def test_syntax_occurrence_is_not_runtime_api_count(self):
        r = analyze("for sid in ids:\n print(call_api('spotify', 'show_song', song_id=sid)['title'])")
        self.assertEqual(r['call_api_syntax_sites'], 1)
        self.assertEqual(r['direct_field_helper_syntax_candidates'], 1)

    def test_explicit_helper_and_bridge_alias_are_separate(self):
        r = analyze("read_fields('spotify', 'show_song', ['title'], song_id=1)\n"
                    "f = call_api\nf('spotify', 'show_song', song_id=1)")
        self.assertEqual(r['explicit_read_fields_syntax_sites'], 1)
        self.assertEqual(r['bridge_name_non_call_loads'], 1)
        self.assertEqual(r['call_api_syntax_sites'], 0)

    def test_mutation_does_not_become_a_field_read(self):
        r = analyze("call_api('spotify', 'show_song', song_id=1)['title'] = 'changed'")
        self.assertEqual(r['direct_field_helper_syntax_candidates'], 0)

    def test_literal_values_and_code_are_not_published(self):
        secret = 'secret-test-value-not-for-report'
        r = analyze(f"print(call_api('spotify','show_song',song_id='{secret}')['{secret}'])")
        self.assertNotIn(secret, json.dumps(r))
        self.assertIsNone(r['sites'][0]['field_label'])

    def test_bounded_parser_does_not_execute(self):
        with self.assertRaisesRegex(ValueError, 'source_bound'):analyze(' ' * 20001)
        with self.assertRaisesRegex(ValueError, 'ast_node_bound'):analyze('x=0\n' * 1300)
        with self.assertRaisesRegex(ValueError, 'unsupported_source_syntax'):analyze('x = (')
        self.assertEqual(analyze("raise RuntimeError('not executed')")['call_api_syntax_sites'], 0)

    def test_fixed_manifest_rejects_other_files_before_loading(self):
        root = Path(__file__).resolve().parents[1]
        plan = json.loads((root/'configs/P70_return_use_scope_v01.json').read_text())
        old = json.loads((root/'reports/P35_read_footprint.json').read_text())
        validate(plan, old)
        plan['rows'][0]['inputs'][0]['path'] = 'private_eval/anything.json'
        with self.assertRaisesRegex(ValueError, 'fixed_input_identity_changed'):validate(plan, old)


if __name__ == '__main__':
    unittest.main()
