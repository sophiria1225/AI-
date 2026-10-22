import copy
import json
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from contract_feedback import UNKNOWN_PARAMETER
from request_repair_binding import RepairBinding, RepairNotAdmitted, fits_scalar_contract, maximum_matching

FLAGS = {'api_request_sent': False, 'effects_unknown': False, 'format_error': UNKNOWN_PARAMETER}


def fixture(args=None, props=None):
    if args is None: args = {'credential': 'DO_NOT_REGENERATE', 'old_from': '/source', 'old_to': '/target'}
    if props is None: props = {k: {'type': 'string'} for k in ('credential', 'source_path', 'destination_path')}
    function = {'name': 'fixture__move', 'arguments': json.dumps(args)}
    exposed = {'fixture__move': {'name': 'fixture__move', 'description': 'Move source to destination.',
        'parameters': {'type': 'object', 'properties': props}}}
    return function, exposed


def rename_proposal(binding):
    return {'ticket': binding.packet()['ticket'], 'renames': [
        {'from': 'old_from', 'to': 'source_path'}, {'from': 'old_to', 'to': 'destination_path'}], 'drop': []}


class RequestRepairBindingTests(unittest.TestCase):
    def test_host_retains_values_without_exposing_them_in_packet(self):
        f, schemas = fixture(); saved = copy.deepcopy((f, schemas))
        b = RepairBinding(f, schemas, **FLAGS)
        packet = json.dumps(b.packet())
        self.assertNotIn('DO_NOT_REGENERATE', packet)
        self.assertNotIn('/source', packet)
        result = b.evaluate(rename_proposal(b), f, schemas, **FLAGS)
        self.assertTrue(result['accepted'])
        self.assertEqual(json.loads(result['private_candidate_function']['arguments']), {
            'credential': 'DO_NOT_REGENERATE', 'source_path': '/source', 'destination_path': '/target'})
        self.assertEqual((f, schemas), saved)
        self.assertFalse(result['api_dispatched'])
        self.assertFalse(result['semantic_equivalence_verified'])

    def test_proposal_cannot_edit_valid_named_value_or_change_api(self):
        f, schemas = fixture()
        for extra in ({'arguments': {'credential': 'NEW'}}, {'name': 'other__tool'}, {'value': 'NEW'}):
            b = RepairBinding(f, schemas, **FLAGS)
            self.assertEqual(b.evaluate({**rename_proposal(b), **extra}, f, schemas, **FLAGS)['reason'], 'proposal_shape')
        for target in ('credential', 'not_public'):
            b = RepairBinding(f, schemas, **FLAGS); p = rename_proposal(b)
            p['renames'][0]['to'] = target
            self.assertEqual(b.evaluate(p, f, schemas, **FLAGS)['reason'], 'destination_scope_mismatch')

    def test_all_unknown_fields_once_and_collision_rejected(self):
        f, schemas = fixture()
        for kind in ('missing', 'duplicate_source', 'collision'):
            b = RepairBinding(f, schemas, **FLAGS); p = rename_proposal(b)
            if kind == 'missing': p['renames'].pop()
            elif kind == 'duplicate_source': p['renames'][1]['from'] = 'old_from'
            else: p['renames'][1]['to'] = 'source_path'
            self.assertFalse(b.evaluate(p, f, schemas, **FLAGS)['accepted'])

    def test_empty_contract_drop_is_separate_from_nonempty_omission(self):
        f, schemas = fixture({'excess': 'PRIVATE'}, {})
        b = RepairBinding(f, schemas, **FLAGS)
        p = {'ticket': b.packet()['ticket'], 'renames': [], 'drop': ['excess']}
        result = b.evaluate(p, f, schemas, **FLAGS)
        self.assertTrue(result['accepted'])
        self.assertEqual(json.loads(result['private_candidate_function']['arguments']), {})
        f, schemas = fixture({'excess': 'PRIVATE'}, {'optional': {'type': 'string'}})
        b = RepairBinding(f, schemas, **FLAGS); p['ticket'] = b.packet()['ticket']
        self.assertEqual(b.evaluate(p, f, schemas, **FLAGS)['reason'], 'drop_requires_empty_contract')

    def test_no_type_coercion_and_no_unimplemented_constraint_bypass(self):
        self.assertFalse(fits_scalar_contract(True, {'type': 'integer'}))
        self.assertFalse(fits_scalar_contract('true', {'type': 'boolean'}))
        self.assertFalse(fits_scalar_contract('x', {'type': 'string', 'pattern': '^x$'}))
        self.assertFalse(fits_scalar_contract('x', {'type': 'string', 'enum': ['y']}))
        self.assertFalse(fits_scalar_contract([1], {'type': 'array'}))
        self.assertTrue(fits_scalar_contract(1, {'type': 'number'}))
        f, schemas = fixture({'privacy': 'private'}, {'private': {'type': 'boolean'}})
        b = RepairBinding(f, schemas, **FLAGS)
        p = {'ticket': b.packet()['ticket'], 'renames': [{'from': 'privacy', 'to': 'private'}], 'drop': []}
        self.assertEqual(b.evaluate(p, f, schemas, **FLAGS)['reason'], 'unsupported_or_incompatible_property')

    def test_original_request_and_public_schema_must_still_match(self):
        for change in ('request', 'schema', 'sent', 'unknown', 'unexposed'):
            f, schemas = fixture(); b = RepairBinding(f, schemas, **FLAGS); p = rename_proposal(b)
            current_f, current_s, flags = copy.deepcopy(f), copy.deepcopy(schemas), dict(FLAGS)
            if change == 'request': current_f['arguments'] = json.dumps({'old_from': 'CHANGED'})
            elif change == 'schema': current_s['fixture__move']['description'] = 'Changed'
            elif change == 'sent': flags['api_request_sent'] = True
            elif change == 'unknown': flags['effects_unknown'] = True
            else: current_s = {}
            self.assertFalse(b.evaluate(p, current_f, current_s, **flags)['accepted'])

    def test_unexposed_unknown_effects_generic_errors_and_duplicate_json_refused(self):
        f, schemas = fixture()
        cases = [(f, {}, FLAGS), (f, schemas, {**FLAGS, 'effects_unknown': True}),
                 (f, schemas, {**FLAGS, 'api_request_sent': True}),
                 (f, schemas, {**FLAGS, 'format_error': 'different_error'}),
                 ({**f, 'arguments': '{"x":1,"x":2}'}, schemas, FLAGS)]
        for fun, sch, flags in cases:
            with self.assertRaises(RepairNotAdmitted): RepairBinding(fun, sch, **flags)

    def test_decline_and_invalid_proposals_consume_one_local_attempt(self):
        f, schemas = fixture()
        for first in ('decline', 'invalid'):
            b = RepairBinding(f, schemas, **FLAGS)
            proposal = {'ticket': b.packet()['ticket'], 'decline': True} if first == 'decline' else {}
            self.assertFalse(b.evaluate(proposal, f, schemas, **FLAGS)['accepted'])
            self.assertEqual(b.evaluate(rename_proposal(b), f, schemas, **FLAGS)['reason'], 'proposal_already_consumed')

    def test_concurrent_local_delivery_assembles_at_most_one_candidate(self):
        f, schemas = fixture(); b = RepairBinding(f, schemas, **FLAGS); p = rename_proposal(b)
        barrier = threading.Barrier(2); results = []
        def invoke():
            barrier.wait(); results.append(b.evaluate(p, f, schemas, **FLAGS))
        threads = [threading.Thread(target=invoke) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=2)
        self.assertEqual(sum(r['accepted'] for r in results), 1)
        self.assertEqual(len(results), 2)

    def test_feasibility_requires_injective_assignment_not_each_nonempty_edge(self):
        self.assertEqual(maximum_matching({'a': ['x'], 'b': ['x']}), 1)
        self.assertEqual(maximum_matching({'a': ['x', 'y'], 'b': ['x']}), 2)
        f, schemas = fixture({'first': 'A', 'second': 'B'}, {'only': {'type': 'string'}})
        self.assertFalse(RepairBinding(f, schemas, **FLAGS).packet()['complete_type_compatible_renaming_exists'])
        f, schemas = fixture()
        self.assertTrue(RepairBinding(f, schemas, **FLAGS).packet()['complete_type_compatible_renaming_exists'])

    def test_packet_tampering_does_not_expand_private_binding(self):
        f, schemas = fixture(); b = RepairBinding(f, schemas, **FLAGS)
        packet = b.packet(); packet['destination_properties']['credential'] = {'type': 'string'}
        packet['protected_parameter_names'] = []
        p = rename_proposal(b); p['renames'][0]['to'] = 'credential'
        self.assertFalse(b.evaluate(p, f, schemas, **FLAGS)['accepted'])

    def test_binding_has_finite_request_schema_and_packet_scope(self):
        for args, props in [({'old': 'x' * 65537}, {'new': {'type': 'string'}}),
                            ({f'key{i}': 'x' for i in range(129)}, {}),
                            ({'old': 'x'}, {f'key{i}': {'type': 'string'} for i in range(129)})]:
            f, schemas = fixture(args, props)
            with self.assertRaises(RepairNotAdmitted): RepairBinding(f, schemas, **FLAGS)


if __name__ == '__main__': unittest.main()
