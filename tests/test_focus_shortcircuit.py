import itertools
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from analyze_focus_shortcircuit import all_retained_certificate
from context_preservation import select_focus


def draft(cited=(), rescued=()):
    return {'steps': [{'plan': 'a step', 'depends_on': list(cited)}],
            'rescued': list(rescued), 'rescue_reason': ''}


class FocusShortcircuitControls(unittest.TestCase):
    def test_every_possible_remaining_selection_on_three_spans_keeps_certificate(self):
        available = ['s1', 's2', 's3']
        first = draft(available)
        self.assertTrue(all_retained_certificate([first], available, 3, 0.3))
        choices = []
        for states in itertools.product(range(4), repeat=3):
            choices.append(draft([s for s, n in zip(available, states) if n & 1],
                                 [s for s, n in zip(available, states) if n & 2]))
        for left, right in itertools.product(choices, repeat=2):
            self.assertEqual(select_focus([first, left, right], available, 0.3)[0], available)

    def test_certificate_uses_final_vote_threshold_and_rescue_union(self):
        available = ['s1', 's2']
        self.assertFalse(all_retained_certificate([draft(available)], available, 3, 0.6))
        self.assertTrue(all_retained_certificate([draft(rescued=available)], available, 3, 0.6))
        self.assertFalse(all_retained_certificate([draft(['s1'])], available, 3, 0.3))

    def test_future_or_duplicate_ids_are_not_repaired_into_a_certificate(self):
        for candidate in [draft(['s1', 'future']), draft(['s1', 's1'])]:
            with self.assertRaises(ValueError):
                all_retained_certificate([candidate], ['s1'], 3, 0.3)


if __name__ == '__main__':
    unittest.main()
