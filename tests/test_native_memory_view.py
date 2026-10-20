import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_conversation import NativeConversation
from native_memory_view import retained_view


class NativeMemoryViewControls(unittest.TestCase):
    def example(self, invalid=False):
        conversation = NativeConversation('system prompt', {'instruction': 'task'})
        for turn in range(2):
            calls, spans = [], []
            for index in range(2):
                sid = f's{turn * 2 + index + 1}'
                fn = {'name': 'app__read', 'arguments': '{bad' if invalid and turn == 0 and index == 1 else '{}'}
                calls.append({'id': sid, 'type': 'function', 'function': fn})
                spans.append({'id': sid, 'assistant': 'plan' if index == 0 else '',
                              'action': fn, 'observation': ({'format_error': 'not executed'}
                                      if fn['arguments'] == '{bad' else {'value': sid})})
            conversation.append({'role': 'assistant', 'content': 'plan', 'tool_calls': calls}, spans)
        return conversation

    def test_all_retained_is_exactly_the_frozen_full_history_input(self):
        conversation = self.example()
        before = conversation.messages()
        messages, stats = retained_view(conversation, ['s1', 's2', 's3', 's4'])
        self.assertEqual(messages, conversation.for_model()[0])
        self.assertFalse(stats['memory_note_added'])
        self.assertEqual(conversation.messages(), before)

    def test_partial_selection_keeps_the_original_action_result_pairs(self):
        conversation = self.example()
        messages, stats = retained_view(conversation, ['s1'])
        self.assertEqual(stats['retained_span_ids'], ['s1', 's2'])
        self.assertEqual(stats['additional_spans_to_preserve_call_result_pairs'], 1)
        self.assertEqual(messages[2:5], conversation.for_model()[0][2:5])
        self.assertEqual([m['tool_call_id'] for m in messages if m['role'] == 'tool'], ['s1', 's2'])

    def test_invalid_unexecuted_request_is_neither_repaired_nor_dropped(self):
        conversation = self.example(invalid=True)
        messages, stats = retained_view(conversation, ['s2'])
        self.assertEqual(messages[2:4], conversation.for_model()[0][2:4])
        self.assertEqual(stats['text_fallback_turns'], 1)
        self.assertIn('not executed', messages[3]['content'])
        self.assertIn('{bad', messages[2]['content'])

    def test_removed_history_stays_in_archive_and_ledger_is_copied(self):
        conversation = self.example(); before = conversation.messages()
        ledger = {'items': [{'status': 'uncertain'}]}; saved = copy.deepcopy(ledger)
        messages, stats = retained_view(conversation, [], ledger)
        self.assertEqual(len(messages), 3)
        self.assertEqual(stats['retained_turns'], 0)
        self.assertIn('s4', messages[-1]['content'])
        ledger['items'].clear()
        self.assertIn('uncertain', messages[-1]['content'])
        self.assertEqual(conversation.messages(), before)
        self.assertTrue(saved['items'])

    def test_invented_or_duplicated_ids_cannot_drive_retention(self):
        for ids in [['s1', 's1'], ['not_observed'], [1]]:
            with self.assertRaises(ValueError):
                retained_view(self.example(), ids)


if __name__ == '__main__':
    unittest.main()
