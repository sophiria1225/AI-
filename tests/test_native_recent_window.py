from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_recent_window import recent_window
import test_native_memory_view as fixtures


class RecentWindowControls(unittest.TestCase):
    def test_under_budget_preserves_exact_full_input(self):
        conversation = fixtures.NativeMemoryViewControls().example()
        messages, detail = recent_window(conversation, lambda _: 100, 4096)
        self.assertEqual(messages, conversation.for_model()[0])
        self.assertEqual(detail['token_count_requests'], 1)

    def test_over_budget_preserves_latest_complete_turn_and_reports_overflow(self):
        conversation = fixtures.NativeMemoryViewControls().example()
        messages, detail = recent_window(conversation, lambda _: 5000, 4096)
        self.assertEqual(detail['retained_span_ids'], ['s3', 's4'])
        self.assertTrue(detail['history_budget_overflow'])
        self.assertEqual([m['tool_call_id'] for m in messages if m['role'] == 'tool'], ['s3', 's4'])

    def test_window_stops_at_first_excess_and_does_not_query_a_model(self):
        conversation = fixtures.NativeMemoryViewControls().example()
        values = iter([6000, 1000, 6000])
        _, detail = recent_window(conversation, lambda _: next(values), 4096)
        self.assertEqual(detail['retained_span_ids'], ['s3', 's4'])
        self.assertEqual(detail['token_count_requests'], 3)
        self.assertFalse(detail['history_budget_overflow'])


if __name__ == '__main__':
    unittest.main()
