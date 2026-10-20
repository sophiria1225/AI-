import copy
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_native_recent import replay_selection
from native_recent_window import recent_window
import test_native_memory_view as fixtures


class RecentSelectionAuditControls(unittest.TestCase):
    def test_exact_count_inputs_replay_and_tampered_counts_are_rejected(self):
        conversation = fixtures.NativeMemoryViewControls().example()
        counts = []
        def count(text):
            counts.append({'status': 'ok', 'content_sha256': hashlib.sha256(text.encode()).hexdigest(),
                           'characters': len(text), 'tokens': 100})
            return 100
        messages, selected = recent_window(conversation, count)
        plan = {'history_budget_tokens': 4096, 'observation_page_characters': 24000}
        self.assertEqual(replay_selection(conversation, {'selection': selected}, counts, plan), messages)
        for key, value in [('content_sha256', '0' * 64), ('status', 'failed'), ('characters', 1), ('tokens', 6000)]:
            corrupt = copy.deepcopy(counts); corrupt[0][key] = value
            with self.assertRaises(ValueError):
                replay_selection(conversation, {'selection': selected}, corrupt, plan)


if __name__ == '__main__':
    unittest.main()
