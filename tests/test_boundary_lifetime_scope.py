import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from boundary_lifetime_scope import analyze
from inspect_boundary_lifetime_scope import validate

CALL = "song = call_api('spotify', 'show_song', song_id=sid)\n"


class BoundaryLifetimeScopeTests(unittest.TestCase):
    def binding(self, source):
        return analyze(source)['bindings'][0]

    def test_last_field_use_is_not_death_at_next_generation(self):
        r = self.binding(CALL + "title = song['title']\n")
        self.assertTrue(r['current_window_literal_subscripts_only'])
        self.assertIsNone(r['same_suite_release_kind'])
        self.assertFalse(r['normal_path_release_syntax_candidate'])
        self.assertFalse(r['persistent_namespace_equivalence_verified'])

    def test_explicit_delete_is_only_normal_path_syntax(self):
        r = self.binding(CALL + "title = song['title']\ndel song\n")
        self.assertEqual(r['same_suite_release_kind'], 'delete')
        self.assertTrue(r['normal_path_release_syntax_candidate'])
        self.assertFalse(r['exception_exit_equivalence_verified'])
        self.assertFalse(r['online_replacement_verified'])

    def test_rebinding_does_not_attribute_later_objects_to_old_root(self):
        r = self.binding(CALL + "title = song['title']\nsong = other\nprint(song)\n")
        self.assertTrue(r['normal_path_release_syntax_candidate'])
        self.assertEqual(r['lexical_loads_in_window'], 1)
        self.assertEqual(r['later_same_spelling_loads_after_release'], 1)

    def test_rebinding_rhs_can_escape_old_root(self):
        r = self.binding(CALL + "title = song['title']\nsong = {'old': song}\n")
        self.assertEqual(r['load_counts']['whole_root_use'], 1)
        self.assertFalse(r['normal_path_release_syntax_candidate'])

    def test_alias_or_container_escape_blocks_pattern(self):
        for use in ('alias = song', 'saved.append(song)', 'print(song)', 'saved = [song]'):
            r = self.binding(CALL + "title = song['title']\n" + use + '\ndel song\n')
            self.assertFalse(r['normal_path_release_syntax_candidate'])

    def test_loop_final_value_may_survive(self):
        source = 'for sid in ids:\n ' + CALL.strip() + "\n title = song['title']\n"
        r = self.binding(source)
        self.assertIn('For', r['scope_kinds'])
        self.assertIsNone(r['same_suite_release_kind'])
        self.assertFalse(r['normal_path_release_syntax_candidate'])
        self.assertFalse(self.binding(source + ' del song\n')['normal_path_release_syntax_candidate'])

    def test_conditional_deletion_is_not_unconditional_release(self):
        r = self.binding(CALL + "title = song['title']\nif cond:\n del song\n")
        self.assertIsNone(r['same_suite_release_kind'])
        self.assertFalse(r['normal_path_release_syntax_candidate'])

    def test_intervening_control_blocks_the_linear_pattern(self):
        r = self.binding(CALL + "if cond:\n title = song['title']\ndel song\n")
        self.assertTrue(r['intervening_control_structure'])
        self.assertFalse(r['normal_path_release_syntax_candidate'])

    def test_get_and_dynamic_or_unknown_fields_are_not_promoted(self):
        for expression in ("song.get('title')", "song.get('title', effect())", 'song[key]',
                           "song['rating']", 'song[0]'):
            r = self.binding(CALL + 'value = ' + expression + '\ndel song\n')
            self.assertFalse(r['normal_path_release_syntax_candidate'])

    def test_member_mutation_is_not_a_field_read(self):
        r = self.binding(CALL + "song['title'] = 'changed'\ndel song\n")
        self.assertEqual(r['load_counts'], {'member_mutation_or_delete': 1})
        self.assertFalse(r['normal_path_release_syntax_candidate'])

    def test_deferred_or_nested_references_are_not_current_demand(self):
        r = self.binding(CALL + "later = lambda: song['title']\ndel song\n")
        self.assertEqual(r['deferred_name_loads'], 1)
        self.assertFalse(r['normal_path_release_syntax_candidate'])
        r = self.binding('def later():\n ' + CALL.strip() + "\n title = song['title']\n del song\n")
        self.assertIn('FunctionDef', r['scope_kinds'])
        self.assertFalse(r['normal_path_release_syntax_candidate'])

    def test_namespace_and_bridge_hazards_block_pattern(self):
        for prefix in ('globals()', 'exec(text)', 'alias = call_api', 'call_api = fake'):
            r = self.binding(prefix + '\n' + CALL + "title = song['title']\ndel song\n")
            self.assertFalse(r['normal_path_release_syntax_candidate'])

    def test_old_value_in_call_arguments_is_not_new_root_demand(self):
        r = self.binding("song = call_api('spotify', 'show_song', song_id=song['song_id'])\n"
                         "title = song['title']\ndel song\n")
        self.assertEqual(r['lexical_loads_in_window'], 1)
        self.assertEqual(r['permitted_field_labels'], ['title'])

    def test_annotation_without_value_does_not_release(self):
        r = self.binding(CALL + "title = song['title']\nsong: dict\n")
        self.assertIsNone(r['same_suite_release_kind'])

    def test_comprehension_shadowing_and_walrus_do_not_attribute_demand(self):
        for middle in ("values = [song['title'] for song in others]",
                       "values = [(song := other), song['title']]"):
            r = self.binding(CALL + middle + '\ndel song\n')
            self.assertGreater(r['other_same_spelling_stores_in_window'], 0)
            self.assertFalse(r['normal_path_release_syntax_candidate'])

    def test_chained_bindings_are_retained_as_untracked(self):
        r = analyze("song = alias = call_api('spotify', 'show_song', song_id=sid)")
        self.assertEqual(r['counts']['root_name_binding_sites'], 1)
        self.assertEqual(r['counts']['tracked_single_name_bindings'], 0)

    def test_literals_names_and_code_are_not_published(self):
        secret = 'secret_test_value_not_for_report'
        r = analyze(f"{secret} = call_api('spotify', 'show_song', song_id='{secret}')\n"
                    f"print({secret}['{secret}'])\n")
        self.assertNotIn(secret, json.dumps(r))
        self.assertEqual(r['bindings'][0]['unknown_literal_field_uses'], 1)

    def test_current_program_only_and_parser_bounds(self):
        with self.assertRaisesRegex(ValueError, 'source_bound'): analyze(' ' * 20001)
        with self.assertRaisesRegex(ValueError, 'ast_node_bound'): analyze('x=0\n' * 1300)
        with self.assertRaisesRegex(ValueError, 'unsupported_source_syntax'): analyze('(')
        r = analyze("raise RuntimeError('never executed')")
        self.assertEqual(r['counts']['tracked_single_name_bindings'], 0)
        self.assertIsNone(r['measured_savings'])

    def test_manifest_does_not_expand_the_population_or_source_set(self):
        root = Path(__file__).resolve().parents[1]
        plan = json.loads((root / 'configs/P74_boundary_lifetime_v01.json').read_text())
        source, old = validate(plan)
        self.assertEqual(len(source['rows']), 12)
        self.assertEqual(len(old['rows']), 12)
        plan['source_sha256']['private_eval/never_read.json'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'fixed_source_set_changed'): validate(plan)
        del plan['source_sha256']['private_eval/never_read.json']
        plan['known_tasks'] = 5
        with self.assertRaisesRegex(ValueError, 'fixed_population_or_scope_changed'): validate(plan)


if __name__ == '__main__':
    unittest.main()
