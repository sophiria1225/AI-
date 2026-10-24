from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from read_view_compatibility import check_saved_boundary, inspect_program


class ReadViewCompatibilityTests(unittest.TestCase):
    def test_retained_result_and_later_json_are_syntax_only(self):
        code = "import json\ncache={}\nfor k in keys:\n v=call_api('spotify','show_song',song_id=k)\n cache[k]=v\nfor v in cache.values():\n print(json.dumps(v))\n"
        row = inspect_program(code)
        self.assertEqual(len(row['target_syntax_sites']), 1)
        self.assertEqual(len(row['container_store_syntax']), 1)
        self.assertEqual(len(row['json_serialization_syntax']), 1)
        self.assertFalse(row['interface_compatibility_proved'])
        self.assertFalse(row['dynamic_field_demand_established'])
        self.assertIsNone(row['measured_savings'])

    def test_inline_field_is_not_a_retained_root(self):
        row = inspect_program("out=call_api('spotify','show_song',song_id=1)['title']")
        self.assertEqual(row['container_store_syntax'], [])
        self.assertEqual(row['target_syntax_sites'][0]['root_use'], 'literal_subscript')

    def test_another_value_or_earlier_store_is_not_the_same_syntactic_binding(self):
        row = inspect_program("for k in keys:\n cache[k]=v\n v=call_api('spotify','show_song',song_id=k)\n cache[k]=other\n")
        self.assertEqual(row['container_store_syntax'], [])

    def test_json_alias_and_observations_access_are_reported(self):
        row = inspect_program("import json as j\nprint(j.dumps(observations))")
        self.assertEqual(len(row['json_serialization_syntax']), 1)
        self.assertEqual(row['observations_name_loads'], 1)

    def test_dynamic_hazard_is_kept_and_not_certified(self):
        row = inspect_program("exec(text)\nv=call_api('spotify','show_song',song_id=1)")
        self.assertIn('dynamic_execution_or_namespace_access', row['current_program_hazards'])
        self.assertFalse(row['interface_compatibility_proved'])

    def test_source_bound_and_syntax_are_not_silently_truncated(self):
        for source in ('x'*20001, 'for x in:'):
            with self.assertRaises(ValueError): inspect_program(source)

    def fixture(self):
        source = dict(program_index=1, code='pass', observations=[], api_schemas={})
        result = dict(program_index=1, status='execution_error', session_usable=True,
                      api_requests=1, stdout='', stdout_truncated=False, error='stopped')
        wire = [dict(kind='api', id=1, program_index=1),
                dict(kind='done', program_index=1, stdout='', stdout_truncated=False, error='stopped')]
        return source, result, wire

    def test_saved_failure_is_preserved_as_a_usable_record_not_success(self):
        row = check_saved_boundary(*self.fixture())
        self.assertEqual(row['status'], 'execution_error')
        self.assertFalse(row['runtime_replay_executed'])

    def test_completion_mismatch_or_missing_packet_is_rejected(self):
        for field in ('stdout', 'stdout_truncated', 'error'):
            source, result, wire = self.fixture();wire[-1][field] = 'different'
            with self.assertRaises(ValueError): check_saved_boundary(source, result, wire)
        source, result, wire = self.fixture()
        with self.assertRaises(ValueError): check_saved_boundary(source, result, wire[:-1])

    def test_rpc_identity_and_unusable_session_are_rejected(self):
        source, result, wire = self.fixture()
        for changed in (dict(wire[0], id=2), dict(wire[0], id=True), dict(wire[0], program_index=2)):
            with self.assertRaises(ValueError): check_saved_boundary(source, result, [changed, wire[-1]])
        result['session_usable'] = False
        with self.assertRaises(ValueError): check_saved_boundary(source, result, wire)


if __name__ == '__main__': unittest.main()
