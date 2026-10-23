import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_conversation import NativeConversation, recover_turn
from reasoning_history import ReasoningConversation, reasoning_shape, with_recorded_reasoning


def sample(arguments='{}'):
    call = {'id': 'c1', 'type': 'function',
            'function': {'name': 'read', 'arguments': arguments}}
    response = {'role': 'assistant', 'content': 'visible', 'tool_calls': [call],
                'reasoning_content': 'PRIVATE_SYNTHETIC_REASONING'}
    spans = [{'id': 's1', 'assistant': 'visible', 'action': call['function'],
              'observation': {'error': 'operation rejected'}}]
    return response, spans


class ReasoningHistoryTests(unittest.TestCase):
    def test_opt_in_preserves_reasoning_without_changing_public_receipts(self):
        response, spans = sample()
        old = NativeConversation('system', {})
        new = ReasoningConversation('system', {})
        old.append(response, spans); new.append(response, spans)
        self.assertNotIn('reasoning_content', old.messages()[2])
        self.assertEqual(new.for_model()[0][2]['reasoning_content'], response['reasoning_content'])
        self.assertEqual(recover_turn(new.messages()[2:]), recover_turn(old.messages()[2:]))
        response['reasoning_content'] = 'changed'
        self.assertEqual(new.messages()[2]['reasoning_content'], 'PRIVATE_SYNTHETIC_REASONING')

    def test_invalid_arguments_and_paging_keep_reasoning_but_not_success(self):
        for arguments in ('{', '[]', '{}'):
            response, spans = sample(arguments)
            spans[0]['observation']['large'] = 'x' * 1000 + 'UNSEEN_TAIL'
            c = ReasoningConversation('system', {}); c.append(response, spans)
            messages, stats = c.for_model(page_limit=300)
            self.assertEqual(messages[2]['reasoning_content'], response['reasoning_content'])
            self.assertEqual(stats['text_fallback_turns'], int(arguments != '{}'))
            self.assertEqual(stats['paged_spans'], 1)
            self.assertNotIn('UNSEEN_TAIL', str(messages))
            self.assertEqual(recover_turn(c.messages()[2:]), spans)

    def test_bad_reasoning_or_invalid_receipts_never_partially_commit(self):
        for variant in ('list', 'dict', 'integer', 'missing_receipt'):
            c = ReasoningConversation('system', {}); original = c.messages()
            response, spans = sample()
            if variant == 'missing_receipt': spans.clear()
            else: response['reasoning_content'] = {'list': [], 'dict': {}, 'integer': 1}[variant]
            with self.assertRaises(ValueError): c.append(response, spans)
            self.assertEqual(c.messages(), original)

    def test_absent_empty_and_null_fields_are_not_fabricated(self):
        for field in ('absent', '', None):
            response = {'role': 'assistant', 'content': 'visible'}
            if field != 'absent': response['reasoning_content'] = field
            spans = [{'id': 's1', 'assistant': 'visible', 'action': None,
                      'observation': {'format_error': 'missing tool'}}]
            c = ReasoningConversation('system', {}); c.append(response, spans)
            self.assertEqual(c.for_model()[0][2], response)
            self.assertEqual(reasoning_shape(response)['characters'], 0)

    def test_metadata_contains_no_reasoning_or_visible_content(self):
        response, _ = sample(); shape = reasoning_shape(response)
        self.assertEqual(shape['characters'], len(response['reasoning_content']))
        self.assertNotIn('PRIVATE_SYNTHETIC_REASONING', str(shape))
        self.assertNotIn('visible', str(shape))

    def test_saved_response_alignment_preserves_other_messages_and_owns_copy(self):
        response, spans = sample(); c = NativeConversation('system', {}); c.append(response, spans)
        original = c.messages() + [{'role': 'user', 'content': 'budget notice'}]
        result = with_recorded_reasoning(original, [response])
        expected = copy.deepcopy(original); expected[2]['reasoning_content'] = response['reasoning_content']
        self.assertEqual(result, expected)
        result[-1]['content'] = 'changed'
        self.assertEqual(original[-1]['content'], 'budget notice')

    def test_missing_future_reordered_and_mismatched_responses_are_rejected(self):
        response, spans = sample(); c = NativeConversation('system', {}); c.append(response, spans)
        altered = copy.deepcopy(response); altered['tool_calls'][0]['id'] = 'wrong'
        for saved in ([], [response, response], [altered]):
            with self.assertRaises(ValueError): with_recorded_reasoning(c.messages(), saved)

    def test_existing_reasoning_is_not_silently_overwritten(self):
        response, spans = sample(); c = ReasoningConversation('system', {}); c.append(response, spans)
        with self.assertRaises(ValueError): with_recorded_reasoning(c.messages(), [response])


if __name__ == '__main__':
    unittest.main()
