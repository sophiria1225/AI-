import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_conversation import NativeConversation, recover_turn


def turn():
    calls = [{'id': 'a', 'type': 'function', 'function': {'name': 'public__read', 'arguments': '{}'}},
             {'id': 'b', 'type': 'function', 'function': {'name': 'public__write', 'arguments': '{'}}]
    message = {'role': 'assistant', 'content': 'proposed work', 'tool_calls': calls,
               'reasoning_content': 'do not reinsert this private reasoning'}
    spans = [dict(id='s1', assistant='proposed work', action=calls[0]['function'],
                  observation={'observation': 'Execution failed.'}),
             dict(id='s2', assistant='', action=calls[1]['function'],
                  observation={'format_error': 'unparseable arguments'})]
    return message, spans


class NativeConversationControls(unittest.TestCase):
    def test_round_trip_retains_failure_and_invalid_action_not_reasoning(self):
        conversation = NativeConversation('system', {'task': 'private sample'})
        message, spans = turn()
        conversation.append(message, spans)
        self.assertEqual(recover_turn(conversation.messages()[2:]), spans)
        self.assertNotIn('reasoning_content', str(conversation.messages()))
        self.assertEqual([m['role'] for m in conversation.messages()],
                         ['system', 'user', 'assistant', 'tool', 'tool'])

    def test_missing_duplicate_or_reordered_receipt_never_partially_commits(self):
        for variant in ('missing', 'duplicate', 'reordered'):
            c = NativeConversation('system', {})
            m, spans = turn()
            if variant == 'missing': spans.pop()
            elif variant == 'duplicate': m['tool_calls'][1]['id'] = 'a'
            else: spans.reverse()
            original = c.messages()
            with self.subTest(variant=variant), self.assertRaises(ValueError): c.append(m, spans)
            self.assertEqual(c.messages(), original)

    def test_append_preserves_all_earlier_messages_and_owns_copies(self):
        c = NativeConversation('system', {})
        m, spans = turn(); c.append(m, spans)
        prefix = c.messages()
        m['content'] = 'changed'; spans[0]['observation']['new'] = 'changed'
        self.assertEqual(c.messages(), prefix)
        c.append({'role': 'assistant', 'content': 'finished without a tool'},
                 [{'id': 's3', 'assistant': 'finished without a tool', 'action': None,
                   'observation': {'format_error': 'at least one tool call required'}}])
        self.assertEqual(c.messages()[:len(prefix)], prefix)
        self.assertEqual(recover_turn(c.messages()[len(prefix):])[0]['action'], None)

    def test_skipped_operation_remains_a_skipped_tool_result(self):
        c = NativeConversation('system', {}); m, spans = turn()
        spans[1]['observation'] = {'not_executed': 'prior request has unknown effects'}
        c.append(m, spans)
        self.assertEqual(recover_turn(c.messages()[2:])[1]['observation'], spans[1]['observation'])
        with self.assertRaises(ValueError): c.append(m, spans)

    def test_invalid_arguments_keep_the_whole_batch_and_its_actual_results(self):
        for arguments in ('{', '[]', 'null'):
            c = NativeConversation('system', {}); message, spans = turn()
            message['tool_calls'][1]['function']['arguments'] = arguments
            c.append(message, spans)
            rendered, stats = c.for_model()
            self.assertEqual(stats['text_fallback_turns'], 1)
            self.assertNotIn('tool_calls', rendered[2])
            self.assertEqual(json.loads(rendered[2]['content'])['tool_call_records'],
                             message['tool_calls'])
            self.assertEqual(json.loads(rendered[3]['content'])['recorded_results'], spans)
            self.assertEqual(recover_turn(c.messages()[2:]), spans)

    def test_long_receipt_keeps_same_archive_page_and_no_unseen_tail(self):
        from context_preservation import page_span
        c = NativeConversation('system', {}); message, spans = turn()
        message['tool_calls'][1]['function']['arguments'] = '{}'
        spans[1]['observation'] = {'observation': 'x' * 1000 + 'private_tail'}
        c.append(message, spans)
        rendered, stats = c.for_model(page_limit=300)
        self.assertEqual(stats, {'text_fallback_turns': 0, 'paged_spans': 1})
        self.assertNotIn('private_tail', str(rendered))
        self.assertEqual(json.loads(rendered[-1]['content'])['first_page'],
                         page_span({'s2': spans[1]}, 's2', 0, 300))
        self.assertEqual(rendered[2]['tool_calls'], message['tool_calls'])


if __name__ == '__main__':
    unittest.main()
