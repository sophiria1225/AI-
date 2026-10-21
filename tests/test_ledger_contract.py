import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from context_preservation import LEDGER_TOOL, validate_ledger
from ledger_contract import LedgerContract, inputs
from native_ledger_memory import draft_messages


class LedgerContractTests(unittest.TestCase):
    def value(self, source_ids, status='pending'):
        return {'items': [{'key': 'a', 'requirement': 'Do the requested operation',
                           'status': status, 'source_ids': source_ids}],
                'constraints': [], 'unresolved': []}

    def test_empty_list_excluded_in_both_schema_and_receiver(self):
        contract = LedgerContract(['s1'])
        spec = contract.tool()['function']['parameters']['properties']['items']['items']['properties']
        self.assertEqual(spec['source_ids']['minItems'], 1)
        self.assertNotIn('minLength', spec['requirement'])
        with self.assertRaises(ValueError):
            contract.validate(self.value([]))

    def test_task_reference_registered_not_replaced_by_an_observation(self):
        contract = LedgerContract(['s1'])
        value = self.value(['task'])
        self.assertEqual(contract.validate(value)['items'][0]['source_ids'], ['task'])
        with self.assertRaises(ValueError):
            validate_ledger(value, {'s1'})

    def test_unknown_source_rejected_and_prior_sources_registered(self):
        previous = self.value(['s1'])
        contract = LedgerContract(['s2'], previous)
        self.assertEqual(contract.source_ids, {'s1', 's2', 'task'})
        contract.validate(self.value(['s1']))
        with self.assertRaises(ValueError):
            contract.validate(self.value(['missing']))

    def test_definitions_not_mutated_and_legacy_inputs_identical(self):
        original = copy.deepcopy(LEDGER_TOOL)
        case = {'task': {'instruction': 'Do work'}, 'tools': [], 'spans': {
            's1': {'id': 's1', 'action': {}, 'observation': {'message': 'observed'}}}}
        legacy, tool = inputs(case, 'legacy', 24000)
        self.assertEqual(legacy, draft_messages(case['task'], case['spans'], ['s1'], None, [], 24000))
        self.assertEqual(tool, original)
        new, _ = inputs(case, 'aligned', 24000)
        a, b = json.loads(legacy[1]['content']), json.loads(new[1]['content'])
        self.assertEqual(b.pop('task_source_id'), 'task')
        self.assertEqual(a, b)
        self.assertEqual(LEDGER_TOOL, original)

    def test_bad_status_extra_fields_duplicates_and_collisions_rejected(self):
        contract = LedgerContract(['s1'])
        values = [self.value(['s1'], 'in_progress'), self.value(['s1', 's1'])]
        extra = self.value(['s1']); extra['items'][0]['unexpected'] = True; values.append(extra)
        duplicate = self.value(['s1']); duplicate['items'] *= 2; values.append(duplicate)
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                contract.validate(value)
        with self.assertRaises(ValueError):
            LedgerContract(['task'])

    def test_structural_validity_does_not_certify_completion_semantics(self):
        contract = LedgerContract(['s1'])
        # Kept deliberately as a structural acceptance: later semantic review
        # must reject unsupported completion; this validator is not an oracle.
        self.assertEqual(contract.validate(self.value(['task'], 'done'))['items'][0]['status'], 'done')


if __name__ == '__main__':
    unittest.main()
