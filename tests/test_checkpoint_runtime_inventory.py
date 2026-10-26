"""Synthetic namespace inspection only; no saved programs or external services."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from checkpoint_runtime_inventory import (CheckpointInventory, collect_inventory,
    checked_inventory, digest, MAX_BINDINGS, MAX_NAMESPACE_BINDINGS)
from runtime_inventory import validate_inventory


class InventoryCollectionTests(unittest.TestCase):
    def test_values_scalar_lengths_and_secret_contents_are_absent(self):
        secret = 'SYNTHETIC_SECRET_SHOULD_NEVER_BE_RENDERED'
        scope = dict(metadata={1: {'title': secret}}, rows=[secret], serialized=secret,
            number=123456789, finite=float('nan'), truth=True, nothing=None)
        before = {key: id(value) for key, value in scope.items()}
        value = collect_inventory(scope)
        self.assertEqual(validate_inventory(value), value)
        labels = {r['name']: r for r in value['bindings']}
        self.assertEqual(labels['metadata'], dict(name='metadata', type='dict', length=1))
        self.assertEqual(labels['rows']['length'], 1)
        self.assertIsNone(labels['serialized']['length'])
        self.assertIsNone(labels['number']['length'])
        self.assertNotIn(secret, json.dumps(value)); self.assertNotIn('123456789', json.dumps(value))
        self.assertEqual(before, {key: id(item) for key, item in scope.items()})

    def test_custom_operations_metaclass_hash_and_nested_objects_are_never_called(self):
        calls = []
        class Meta(type):
            def __hash__(self): calls.append('metaclass_hash'); raise AssertionError()
            def __eq__(self, other): calls.append('metaclass_eq'); raise AssertionError()
        class Trap(metaclass=Meta):
            def __repr__(self): calls.append('repr'); raise AssertionError()
            def __str__(self): calls.append('str'); raise AssertionError()
            def __len__(self): calls.append('len'); raise AssertionError()
            def __iter__(self): calls.append('iter'); raise AssertionError()
            def __getattribute__(self, name): calls.append('getattribute'); raise AssertionError()
        trap = Trap(); cyc = []; cyc.append(cyc)
        scope = {'custom': trap, 'nested': [trap], 'cycle': cyc}
        value = collect_inventory(scope)
        self.assertEqual([r['name'] for r in value['bindings']], ['cycle', 'nested'])
        self.assertEqual(calls, [])

    def test_custom_keys_in_exact_container_are_not_read_or_hashed(self):
        calls = []
        class Key:
            def __hash__(self): calls.append('hash'); return 7
            def __eq__(self, other): calls.append('eq'); return self is other
            def __repr__(self): calls.append('repr'); raise AssertionError()
        key = Key(); value = {key: object()}; calls.clear()
        result = collect_inventory({'container': value})
        self.assertEqual(result['bindings'][0]['length'], 1)
        self.assertEqual(calls, [])

    def test_subclasses_and_nonplain_namespace_are_rejected_without_callbacks(self):
        calls = []
        class ListSubclass(list):
            def __len__(self): calls.append('len'); raise AssertionError()
        class DictSubclass(dict):
            def items(self): calls.append('items'); raise AssertionError()
        self.assertEqual(collect_inventory({'custom': ListSubclass([1])})['bindings'], [])
        with self.assertRaisesRegex(ValueError, 'exact_runtime_namespace_required'):
            collect_inventory(DictSubclass())
        self.assertEqual(calls, [])

    def test_names_helpers_private_unicode_modules_and_functions_are_omitted(self):
        scope = {'_private': [1], 'call_api': [1], 'read_fields': [1], 'observations': [1],
            'api_schemas': [1], 'bad-name': [1], 'é': [1], 'n' * 81: [1],
            'module': sys, 'function': lambda: None, 'visible': (1, 2)}
        self.assertEqual(collect_inventory(scope)['bindings'],
                         [dict(name='visible', type='tuple', length=2)])

    def test_names_shadowing_builtins_do_not_change_collector_binding(self):
        scope = dict(type='shadow', len=[1, 2], sorted={'x': 1}, dict=(1,))
        value = collect_inventory(scope)
        self.assertEqual({r['name']: r['length'] for r in value['bindings']},
                         {'type': None, 'len': 2, 'sorted': 1, 'dict': 1})

    def test_aliases_are_listed_without_dedup_or_object_identity_claims(self):
        shared = [1, 2, 3]
        result = collect_inventory({'left': shared, 'right': shared})
        self.assertEqual([row['length'] for row in result['bindings']], [3, 3])
        self.assertEqual(result['eligible_binding_count'], 2)

    def test_bounded_sorted_listing_reports_truncation_and_rejects_unbounded_scope(self):
        result = collect_inventory({f'item{i:03d}': [] for i in reversed(range(140))})
        self.assertEqual(result['eligible_binding_count'], 140)
        self.assertTrue(result['truncated']); self.assertEqual(len(result['bindings']), MAX_BINDINGS)
        self.assertEqual(result['bindings'][0]['name'], 'item000')
        with self.assertRaisesRegex(ValueError, 'bounded_runtime_namespace_required'):
            collect_inventory({f'v{i}': None for i in range(MAX_NAMESPACE_BINDINGS + 1)})

    def test_snapshot_validation_rejects_types_values_extra_fields_and_custom_keys(self):
        value = collect_inventory({'rows': [1]})
        for changed in [dict(value, eligible_binding_count=True), dict(value, extra='secret'),
                dict(value, bindings=[dict(name='rows', type='list', length=True)]),
                dict(value, bindings=[dict(name='rows', type='other', length=None)]),
                dict(value, bindings=[dict(name='rows', type='str', length=1)])]:
            with self.assertRaises(ValueError): checked_inventory(changed)
        class Key:
            def __hash__(self): return 5
            def __eq__(self, other): raise AssertionError('no custom key comparison')
        with self.assertRaises(ValueError): checked_inventory({Key(): None})


class CheckpointInventoryTests(unittest.TestCase):
    def prepared(self, mode='checkpoint_inventory'):
        controller = CheckpointInventory(mode=mode, execution_scope='synthetic-execution')
        snapshot = collect_inventory({'metadata': {1: {'title': 'not rendered'}}, 'csv_data': 'not rendered'})
        packet = controller.prepare(snapshot, accepted=True, revision=1, program_index=7,
                                    source_boundary_sha256='a' * 64)
        return controller, snapshot, packet

    def test_both_modes_capture_same_packet_only_on_exposes_it(self):
        off, snapshot, packet = self.prepared('off'); on, _, other = self.prepared()
        self.assertEqual(packet, other)
        messages = [dict(role='user', content='synthetic task')]
        self.assertEqual(off.view(messages, revision=1), messages)
        self.assertEqual(len(on.view(messages, revision=1)), len(messages) + 1)
        for controller in (off, on): controller.submitted(revision=1, call_id='call_010')
        self.assertEqual((off.summary()['prepared'], on.summary()['prepared']), (1, 1))
        self.assertEqual((off.summary()['exposed'], on.summary()['exposed']), (0, 1))

    def test_rejected_decisions_do_not_capture_and_only_positive_exact_revision_is_allowed(self):
        for mode in ('off', 'checkpoint_inventory'):
            controller = CheckpointInventory(mode=mode, execution_scope='synthetic')
            self.assertFalse(controller.needs_snapshot(accepted=False, revision=0))
            self.assertTrue(controller.needs_snapshot(accepted=True, revision=1))
            with self.assertRaises(ValueError): controller.needs_snapshot(accepted=True, revision=True)
            with self.assertRaises(ValueError): controller.needs_snapshot(accepted=True, revision=0)
            with self.assertRaises(ValueError): controller.prepare(collect_inventory({}),
                accepted=False, revision=0, program_index=0, source_boundary_sha256='a' * 64)

    def test_count_send_views_are_identical_and_do_not_mutate_archive_or_snapshot(self):
        controller, snapshot, packet = self.prepared()
        messages = [dict(role='system', content='base'), dict(role='assistant', content='source')]
        original = deepcopy(messages); original_packet = deepcopy(packet)
        count_view = controller.view(messages, revision=1)
        snapshot['bindings'].clear(); packet['inventory']['bindings'].clear()
        send_view = controller.view(messages, revision=1)
        self.assertEqual(digest(count_view), digest(send_view))
        self.assertEqual(messages, original)
        self.assertEqual(controller.pending['packet'], original_packet)
        count_view[-1]['content'] = 'tampered returned copy'
        self.assertEqual(controller.view(messages, revision=1), send_view)

    def test_focus_never_receives_notice_and_unsent_preparation_remains_pending(self):
        controller, _, _ = self.prepared(); messages = [dict(role='user', content='summary source')]
        self.assertEqual(controller.view(messages, revision=1, role='focus'), messages)
        self.assertTrue(controller.summary()['pending']); self.assertEqual(controller.summary()['exposed'], 0)
        with self.assertRaises(ValueError): controller.view(messages, revision=2)
        with self.assertRaises(ValueError): controller.view(messages, revision=1, role='other')

    def test_notice_is_offered_once_per_accepted_revision_without_replay(self):
        controller, snapshot, _ = self.prepared(); messages = []
        controller.submitted(revision=1, call_id='call_010')
        self.assertEqual(controller.view(messages, revision=1), messages)
        self.assertFalse(controller.needs_snapshot(accepted=True, revision=1))
        with self.assertRaises(ValueError): controller.submitted(revision=1, call_id='call_010')
        with self.assertRaises(ValueError): controller.prepare(snapshot, accepted=True, revision=3,
            program_index=8, source_boundary_sha256='b' * 64)
        controller.prepare(snapshot, accepted=True, revision=2, program_index=8,
                           source_boundary_sha256='b' * 64)
        self.assertEqual(controller.summary()['prepared'], 2)
        self.assertEqual(controller.summary()['exposed'], 1)


if __name__ == '__main__':
    unittest.main()
