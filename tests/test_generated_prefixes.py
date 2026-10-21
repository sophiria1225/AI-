import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from analyze_generated_prefixes import history_effects


class LedgerHistoryTests(unittest.TestCase):
    def test_a_ledger_note_is_not_itself_history_removal(self):
        ledger_only = history_effects({'retained_turns': 2, 'original_turns': 2, 'memory_note_added': True})
        self.assertTrue(ledger_only['right_has_memory_note'])
        self.assertFalse(ledger_only['right_uses_partial_history'])
        partial = history_effects({'retained_turns': 2, 'original_turns': 3, 'memory_note_added': True})
        self.assertTrue(partial['right_uses_partial_history'])
        initial = history_effects({'retained_turns': 0, 'original_turns': 0, 'memory_note_added': False})
        self.assertFalse(initial['right_uses_partial_history'])
        with self.assertRaises(ValueError):
            history_effects({'retained_turns': 3, 'original_turns': 2, 'memory_note_added': True})


if __name__ == '__main__':
    unittest.main()
