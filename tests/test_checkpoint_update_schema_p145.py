"""Bounded schema transport and unchanged authoritative host validation."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from checkpoint_update_schema_p145 import (
    FIELDS, UPDATE_SUMMARY_PROMPT, parse_and_apply, schema_for, structured_payload,
)


def old_state():
    return {'completed': ['done'], 'usable_state': ['known', 'stale'],
            'remaining': ['pending'], 'uncertainties': []}


def keep_patch(old):
    return {field: {'keep': list(range(len(old[field]))), 'update': [],
                    'delete': [], 'add': []} for field in FIELDS}


def request(old):
    return {'model': 'synthetic-model', 'messages': [
        {'role': 'system', 'content': UPDATE_SUMMARY_PROMPT},
        {'role': 'user', 'content': json.dumps({'previous_checkpoint': old,
             'older_history': [], 'recent_context': []})}],
        'stream': False, 'seed': 257, 'temperature': 0.7, 'max_tokens': 4096,
        'top_p': 0.95, 'top_k': 0, 'min_p': 0.0, 'repeat_penalty': 1.0,
        'cache_prompt': True, 'reasoning_format': 'deepseek',
        'chat_template_kwargs': {'thinking_mode': 'enabled'},
        'reasoning_budget_tokens': -1}


def response(patch):
    return {'role': 'assistant', 'content': json.dumps(patch)}


class UpdateSchemaTests(unittest.TestCase):
    def test_schema_exact_fields_operations_and_bounded_index_ranges(self):
        old = {field: ['x'] * count for field, count in zip(FIELDS, (0, 1, 3, 32))}
        schema = schema_for(old)
        self.assertEqual(schema['required'], list(FIELDS))
        self.assertFalse(schema['additionalProperties'])
        for field, strings in old.items():
            operations = schema['properties'][field]
            self.assertEqual(operations['required'], ['keep', 'update', 'delete', 'add'])
            self.assertFalse(operations['additionalProperties'])
            for action in ('keep', 'update', 'delete'):
                entry = operations['properties'][action]
                self.assertEqual(entry['minItems'], 0)
                self.assertEqual(entry['maxItems'], len(strings))
                index = entry['items'] if action != 'update' else entry['items']['properties']['index']
                self.assertEqual(index, {'type': 'integer', 'minimum': 0,
                                         'maximum': max(0, len(strings)-1)})
            update = operations['properties']['update']['items']
            self.assertEqual(update['required'], ['index', 'text'])
            self.assertFalse(update['additionalProperties'])
            self.assertEqual(update['properties']['text'], {'type': 'string', 'minLength': 1, 'maxLength': 2048})
            self.assertEqual(operations['properties']['add']['maxItems'], 32)

    def test_schema_contains_no_saved_state_text_or_unsupported_unique_items(self):
        old = old_state()
        old['completed'] = ['PRIVATE_SYNTHETIC_STATE_MUST_NOT_ENTER_SCHEMA']
        before = deepcopy(old)
        serialized = json.dumps(schema_for(old))
        self.assertNotIn(old['completed'][0], serialized)
        self.assertNotIn('uniqueItems', serialized)
        self.assertNotIn('allOf', serialized)
        self.assertEqual(old, before)

    def test_payload_changes_only_schema_and_predeclared_reasoning_budget(self):
        old = old_state()
        saved = request(old)
        original = deepcopy(saved)
        for budget in (-1, 2048):
            with self.subTest(budget=budget):
                actual = structured_payload(saved, old, budget)
                form = actual.pop('response_format')
                self.assertEqual(form['type'], 'json_schema')
                self.assertEqual(form['json_schema']['schema'], schema_for(old))
                self.assertTrue(form['json_schema']['strict'])
                self.assertEqual(actual.pop('reasoning_budget_tokens'), budget)
                expected = deepcopy(saved)
                expected.pop('reasoning_budget_tokens')
                self.assertEqual(actual, expected)
        self.assertEqual(saved, original)

    def test_conflicting_controls_and_changed_saved_input_are_rejected(self):
        old = old_state()
        saved = request(old)
        mutations = ({'response_format': {}}, {'json_schema': {}}, {'grammar': ''},
            {'tools': []}, {'tool_choice': 'auto'}, {'parallel_tool_calls': False},
            {'reasoning_effort': 'none'}, {'thinking_budget_tokens': 2048},
            {'max_tokens': 4095}, {'max_tokens': True}, {'stream': True},
            {'reasoning_budget_tokens': 2048}, {'chat_template_kwargs': {'thinking_mode': 'disabled'}})
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                structured_payload(saved | mutation, old, -1)
        for budget in (True, 0, 2049, 2048.0):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                structured_payload(saved, old, budget)
        changed = deepcopy(old)
        changed['remaining'] = ['different']
        with self.assertRaises(ValueError):
            structured_payload(saved, changed, -1)

    def test_frozen_parser_applies_valid_complete_patch_without_mutation(self):
        old = old_state()
        patch = keep_patch(old)
        patch['usable_state'] = {'keep': [], 'update': [{'index': 0, 'text': 'revised'}],
                                  'delete': [1], 'add': ['new']}
        before = deepcopy((old, patch))
        updated, counts = parse_and_apply(response(patch), 'stop', old)
        self.assertEqual(updated['usable_state'], ['revised', 'new'])
        self.assertEqual(counts['changed_old_items'], 2)
        self.assertEqual(counts['updated_old_items'], 1)
        self.assertEqual(counts['deleted_old_items'], 1)
        self.assertEqual((old, patch), before)

    def test_host_rejects_cross_operation_duplicates_and_incomplete_coverage(self):
        old = old_state()
        missing = keep_patch(old)
        missing['completed']['keep'] = []
        duplicate = keep_patch(old)
        duplicate['completed']['delete'] = [0]
        invalid_bool = keep_patch(old)
        invalid_bool['completed']['keep'] = [False]
        for patch in (missing, duplicate, invalid_bool):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                parse_and_apply(response(patch), 'stop', old)

    def test_host_materialized_budget_still_applies_to_valid_operation_shapes(self):
        old = old_state()
        old['completed'] = ['x'] * 32
        patch = keep_patch(old)
        patch['completed']['add'] = ['overflow']
        with self.assertRaises(ValueError):
            parse_and_apply(response(patch), 'stop', old)
        oversized = old_state()
        oversized['completed'] = ['x' * 2049]
        with self.assertRaises(ValueError):
            schema_for(oversized)

    def test_empty_content_length_stop_and_ordinary_checkpoint_are_not_repaired(self):
        old = old_state()
        for message, finish in (({'role':'assistant', 'content':''}, 'length'),
                (response(keep_patch(old)), 'length'), (response(old), 'stop'),
                (response(keep_patch(old)) | {'tool_calls':[{}]}, 'stop')):
            with self.subTest(finish=finish), self.assertRaises(ValueError):
                parse_and_apply(message, finish, old)


if __name__ == '__main__':
    unittest.main()
