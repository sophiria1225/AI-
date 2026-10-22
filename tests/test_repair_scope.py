import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_repair_scope import argument_changes, call_shape, rejection_shape
from contract_feedback import UNKNOWN_PARAMETER


class RepairScopeTests(unittest.TestCase):
    def test_argument_transport_is_hindsight_and_value_private(self):
        secret = 'private-value-not-for-export'
        before = {'token': secret, 'old_a': '/source', 'old_b': '/destination'}
        after = {'token': secret, 'new_a': '/source', 'new_b': '/destination'}
        result = argument_changes(before, after)
        self.assertEqual(result['same_name_unchanged_values'], 1)
        self.assertEqual(result['removed_to_added_equal_type_edges'], 4)
        self.assertEqual(result['removed_to_added_equal_value_edges'], 2)
        self.assertFalse(result['semantic_equivalence_verified'])
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn('/source', json.dumps(result))
        self.assertNotIn('old_a', json.dumps(result))

    def test_type_changes_and_unchanged_names_are_distinct(self):
        result = argument_changes({'private': 'yes', 'x': True}, {'private': True, 'x': 1})
        self.assertEqual(result['same_name_changed_values'], 2)
        self.assertEqual(result['same_name_unchanged_values'], 0)
        self.assertEqual(result['removed_parameter_count'], 0)
        nested = argument_changes({'x': {'a': 1}}, {'x': {'a': True}})
        self.assertEqual(nested['same_name_changed_values'], 1)

    def test_literal_site_inside_loop_does_not_locate_runtime_resume(self):
        code = "for item in items:\n    call_api('fixture', 'move', key=item)\n"
        result = call_shape(code, 'fixture__move')
        self.assertEqual(result['literal_matching_sites'], 1)
        self.assertEqual(result['matching_site_context_counts']['loop'], 1)
        self.assertEqual(result['matching_argument_load_names'], 1)
        self.assertFalse(result['runtime_resume_point_identified'])
        self.assertNotIn('item', json.dumps(result))

    def test_dynamic_alias_and_duplicate_sites_are_not_certified(self):
        code = "call_api('fixture', name)\nother = call_api\nother('fixture', 'read')\ncall_api('fixture', 'read')\ncall_api('fixture', 'read')\n"
        result = call_shape(code, 'fixture__read')
        self.assertEqual(result['dynamic_name_direct_call_sites'], 1)
        self.assertEqual(result['literal_matching_sites'], 2)
        self.assertFalse(result['alias_or_reflective_calls_resolved'])
        self.assertFalse(call_shape('if', 'fixture__read')['parsed'])

    def test_native_two_part_interface_with_keyword_and_dynamic_bindings(self):
        code = "call_api(app='fixture', api='read', key=value)\ncall_api('fixture', api='read')\ncall_api('fixture', 'read', **values)\n"
        result = call_shape(code, 'fixture__read')
        self.assertEqual(result['literal_matching_sites'], 2)
        self.assertEqual(result['dynamic_name_direct_call_sites'], 1)
        self.assertEqual(result['matching_argument_load_names'], 1)

    def test_empty_contract_requires_exposure_and_known_nondispatch(self):
        span = {'action': {'name': 'fixture__time', 'arguments': '{"credential":"secret"}'},
                'observation': {'format_error': UNKNOWN_PARAMETER}}
        event = {'api_request_sent': False, 'effects_unknown': False}
        schemas = {'fixture__time': {'parameters': {'properties': {}}}}
        result = rejection_shape(span, event, schemas)
        self.assertTrue(result['empty_contract_extra_argument_candidate'])
        self.assertFalse(rejection_shape(span, event, {})['empty_contract_extra_argument_candidate'])
        for flag in ('api_request_sent', 'effects_unknown'):
            self.assertFalse(rejection_shape(span, {**event, flag: True}, schemas)['empty_contract_extra_argument_candidate'])
        self.assertNotIn('secret', json.dumps(result))
        self.assertNotIn('credential', json.dumps(result))
        self.assertFalse(result['automatic_repair_performed'])


if __name__ == '__main__':
    unittest.main()
