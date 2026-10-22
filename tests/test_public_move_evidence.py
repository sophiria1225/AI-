"""Boundary cases for conditional public-receipt checks, never task success."""
import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from public_move_evidence import MoveRequirement, assess_moves


class PublicMoveEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.contract = MoveRequirement('/photos', ((2, 'Alpha'), (3, 'Beta')), 'Other')
        self.paths = ['/photos/a.jpg', '/photos/b.jpg']
        self.metadata = [
            {'path': self.paths[0], 'file_id': 1, 'created_at': '2023-02-01T00:00:00'},
            {'path': self.paths[1], 'file_id': 2, 'created_at': '2022-03-01T00:00:00'},
        ]
        self.moves = [
            {'source': self.paths[0], 'destination': '/photos/Alpha/a.jpg', 'response_destination': '/photos/Alpha/a.jpg', 'overwrite': False},
            {'source': self.paths[1], 'destination': '/photos/Other/b.jpg', 'response_destination': '/photos/Other/b.jpg', 'overwrite': False},
        ]

    def assess(self, **kwargs):
        return assess_moves(self.contract, self.paths, self.metadata, self.moves,
            **{'inventory_complete': True, **kwargs})

    def test_matching_year_does_not_supply_a_clock(self):
        result = self.assess()
        self.assertEqual(result['trace_support'], 'unknown')
        self.assertFalse(result['matched_year_is_clock_evidence'])
        self.assertIn({'year': 2023, 'destination_mismatches': 0}, result['conditional_year_checks'])

    def test_bound_year_and_exact_moves_support_declared_requirement(self):
        self.assertEqual(self.assess(current_year=2023)['trace_support'], 'supported')

    def test_different_observed_year_changes_the_obligation(self):
        self.assertEqual(self.assess(current_year=2022)['trace_support'], 'contradicted')

    def test_equal_move_count_with_different_source_set_is_not_coverage(self):
        self.moves[1]['source'] = '/photos/c.jpg'
        result = self.assess(current_year=2023)
        self.assertEqual(result['trace_support'], 'unknown')
        self.assertEqual((result['missing_sources'], result['extra_sources']), (1, 1))

    def test_preserves_original_filename(self):
        self.moves[0]['destination'] = self.moves[0]['response_destination'] = '/photos/Alpha/renamed.jpg'
        self.assertEqual(self.assess(current_year=2023)['trace_support'], 'contradicted')

    def test_duplicate_move_cannot_replace_a_missing_source(self):
        self.moves[1] = copy.deepcopy(self.moves[0])
        self.assertEqual(self.assess(current_year=2023)['trace_support'], 'unknown')

    def test_incomplete_or_tainted_receipts_are_not_completion_support(self):
        for kwargs in [{'inventory_complete': False}, {'evidence_tainted': True}]:
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.assess(current_year=2023, **kwargs)['trace_support'], 'unknown')

    def test_missing_original_metadata_cannot_be_replaced_by_current_file_count(self):
        self.metadata.pop()
        self.assertEqual(self.assess(current_year=2023)['trace_support'], 'unknown')

    def test_overwrite_or_mismatched_receipt_is_not_an_exact_move(self):
        original = copy.deepcopy(self.moves)
        for key, value in [('overwrite', True), ('response_destination', '/photos/Other/a.jpg')]:
            self.moves = copy.deepcopy(original)
            self.moves[0][key] = value
            self.assertEqual(self.assess(current_year=2023)['trace_support'], 'unknown')

    def test_original_dates_are_input_and_not_rewritten_by_the_checker(self):
        original = copy.deepcopy(self.metadata)
        self.assess(current_year=2023)
        self.assertEqual(self.metadata, original)
        self.metadata[0]['created_at'] = '2023-10-01T00:00:00'
        self.assertEqual(self.assess(current_year=2023)['trace_support'], 'contradicted')

    def test_directory_traversal_and_nested_scope_are_rejected(self):
        for path in ['/photos/../a.jpg', '/photos/nested/a.jpg']:
            with self.subTest(path=path):
                self.paths[0] = path
                self.assertEqual(self.assess(current_year=2023)['trace_support'], 'unknown')

    def test_invalid_date_year_and_duplicate_file_identity_are_not_supported(self):
        self.assertEqual(self.assess(current_year=True)['trace_support'], 'unknown')
        self.metadata[1]['file_id'] = 1
        self.assertEqual(self.assess(current_year=2023)['trace_support'], 'unknown')
        self.metadata[1]['file_id'] = 2
        self.metadata[0]['created_at'] = 'not a date'
        self.assertEqual(self.assess(current_year=2023)['trace_support'], 'unknown')


if __name__ == '__main__':
    unittest.main()
