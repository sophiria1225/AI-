import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inline_checkpoint_protocol import (
    choose_counted_projection, inline_tools, projection_after_turn, split_inline_response)
from protocol_stable_history import StableReferenceConversation
from public_display import CODE_TOOLS
from single_checkpoint_history import FIELDS, candidate


def response(value=None, *, content='', arguments=None):
    args = {'code': 'text = "checkpoint stays in code"\nprint(text)', 'span_ids': ['s1', 's2']}
    if value is not None:
        args['checkpoint'] = value
    return {'role': 'assistant', 'content': content, 'reasoning_content': 'synthetic planning',
        'tool_calls': [{'id': 'new-call', 'type': 'function', 'function': {'name': 'run_python',
                        'arguments': arguments if arguments is not None else json.dumps(args)}}]}


VALID = {name: ['synthetic ' + name] for name in FIELDS}


def fixture(message=None, *, observation_status='ok'):
    conversation = StableReferenceConversation('synthetic instructions', {'instruction': 'synthetic task'})
    for n in range(4):
        msg = {'role': 'assistant', 'content': '', 'reasoning_content': 'old synthetic reasoning',
            'tool_calls': [{'id': f'old-{n}', 'type': 'function',
                           'function': {'name': 'run_python', 'arguments': '{"code":"pass","span_ids":[]}'}}]}
        conversation.append(msg, [{'id': f's{n+1}', 'action': msg['tool_calls'][0]['function'],
                                  'observation': {'status': 'ok', 'stdout': f'old-{n}'}}])
    before, _ = conversation.for_model()
    msg = copy.deepcopy(message if message is not None else response(VALID))
    conversation.append(msg, [{'id': 's5', 'action': msg['tool_calls'][0]['function'],
        'observation': {'status': observation_status, 'stdout': 'current result must remain literal'}}])
    after, _ = conversation.for_model()
    return before, after, msg, conversation


def split(message, finish='tool_calls'):
    return split_inline_response(message, offered=True, finish_reason=finish, usage_known=True)


class InlineCheckpointProtocolTests(unittest.TestCase):
    def test_tool_extension_does_not_mutate_shared_schema_or_require_metadata(self):
        original = copy.deepcopy(CODE_TOOLS)
        changed = inline_tools(CODE_TOOLS)
        self.assertEqual(CODE_TOOLS, original)
        a = original[0]['function']['parameters']
        b = changed[0]['function']['parameters']
        self.assertEqual(b['required'], a['required'])
        self.assertEqual({k: b['properties'][k] for k in ('code', 'span_ids')}, a['properties'])
        self.assertEqual(set(b['properties']['checkpoint']['properties']), set(FIELDS))
        self.assertEqual(changed[1:], original[1:])

    def test_only_metadata_is_removed_from_execution_code_and_ordered_references(self):
        message = response(VALID)
        original = copy.deepcopy(message)
        result = split(message)
        self.assertEqual(message, original)
        old = json.loads(message['tool_calls'][0]['function']['arguments'])
        new = json.loads(result['execution_message']['tool_calls'][0]['function']['arguments'])
        self.assertEqual(new, {k: old[k] for k in ('code', 'span_ids')})
        self.assertIn('checkpoint stays in code', new['code'])
        self.assertEqual(result['execution_message']['reasoning_content'], message['reasoning_content'])
        self.assertEqual(result['status'], 'checkpoint_structurally_valid')
        self.assertFalse(result['semantics_verified'])

    def test_current_closed_turn_and_recent_two_remain_and_archive_is_unchanged(self):
        before, after, message, conv = fixture()
        archived = copy.deepcopy(conv.messages())
        views = projection_after_turn(before, after, split(message))
        cutoff = candidate(before)['cutoff']
        self.assertEqual(views['compacted'][:2], before[:2])
        self.assertEqual(views['compacted'][3:], views['ordinary'][cutoff:])
        self.assertEqual(views['ordinary'][:len(before)], before)
        self.assertEqual(views['ordinary'][-1], after[-1])
        self.assertEqual(conv.messages(), archived)
        self.assertTrue(views['transport_metadata_hidden'])
        self.assertFalse(views['same_call_observations_summarized'])
        self.assertFalse(json.loads(views['compacted'][2]['content'])['semantics_verified'])

    def test_incomplete_current_turn_or_changed_old_record_cannot_install(self):
        before, after, message, _ = fixture()
        changed = copy.deepcopy(after)
        changed[3]['content'] += ' changed'
        for history in (after[:-1], changed, before):
            with self.subTest(history=history), self.assertRaises(ValueError):
                projection_after_turn(before, history, split(message))

    def test_summary_cannot_be_attached_to_a_different_response_or_program(self):
        before, after, message, _ = fixture()
        unrelated = response(VALID, content='another response')
        with self.assertRaisesRegex(ValueError, 'differs_from_received'):
            projection_after_turn(before, after, split(unrelated))
        altered = split(message)
        altered['execution_message']['tool_calls'][0]['function']['arguments'] = '{"code":"different","span_ids":[]}'
        with self.assertRaisesRegex(ValueError, 'binding_changed'):
            projection_after_turn(before, after, altered)
        altered = split(message)
        altered['checkpoint']['completed'] = ['forged claim']
        with self.assertRaisesRegex(ValueError, 'value_changed'):
            projection_after_turn(before, after, altered)

    def test_invalid_or_truncated_summary_keeps_old_history_but_valid_action_survives(self):
        for message, finish in ((response({'completed': []}), 'tool_calls'),
                                (response(VALID), 'length'), (response(VALID), 'stop')):
            before, after, raw, _ = fixture(message)
            result = split(raw, finish)
            self.assertEqual(result['status'], 'invalid_checkpoint_keep_old_history')
            views = projection_after_turn(before, after, result)
            self.assertIsNone(views['compacted'])
            self.assertEqual(views['ordinary'][:len(before)], before)
            self.assertEqual(json.loads(result['execution_message']['tool_calls'][0]['function']['arguments'])['code'],
                             json.loads(raw['tool_calls'][0]['function']['arguments'])['code'])
            selected, accepted = choose_counted_projection(views, 100, None)
            self.assertFalse(accepted)
            self.assertEqual(selected, views['ordinary'])

    def test_unknown_usage_blocks_extraction_before_any_execution(self):
        with self.assertRaisesRegex(ValueError, 'unknown_usage_blocks'):
            split_inline_response(response(VALID), offered=True, finish_reason='tool_calls', usage_known=False)

    def test_no_offer_missing_metadata_and_unsupported_batch_leave_original_response(self):
        message = response(VALID)
        result = split_inline_response(message, offered=False, finish_reason='tool_calls', usage_known=True)
        self.assertEqual(result['execution_message'], message)
        self.assertIsNone(result['binding'])
        message = response()
        self.assertEqual(split(message)['status'], 'checkpoint_absent_keep_original')
        message = response(VALID)
        message['tool_calls'].append(copy.deepcopy(message['tool_calls'][0]))
        result = split(message)
        self.assertEqual(result['execution_message'], message)
        self.assertIsNone(result['checkpoint'])

    def test_duplicate_fields_extra_arguments_and_nonfinite_json_are_not_repaired(self):
        texts = ['{"code":"pass","code":"different","span_ids":[],"checkpoint":{}}',
                 '{"code":"pass","span_ids":[],"extra":1,"checkpoint":{}}',
                 '{"code":"pass","span_ids":[],"checkpoint":NaN}', 'not JSON']
        for text in texts:
            message = response(arguments=text)
            result = split(message)
            self.assertEqual(result['status'], 'invalid_envelope_keep_original')
            self.assertEqual(result['execution_message'], message)
            self.assertIsNone(result['binding'])

    def test_malformed_call_renderer_fallback_preserves_history_without_installation(self):
        for text in ('not JSON', '["not an argument object"]'):
            before, after, message, _ = fixture(response(arguments=text))
            result = split(message)
            views = projection_after_turn(before, after, result)
            self.assertEqual(views['ordinary'], after)
            self.assertIsNone(views['compacted'])
            self.assertFalse(views['transport_metadata_hidden'])
            changed = copy.deepcopy(after)
            value = json.loads(changed[len(before)]['content'])
            value['assistant_text'] += 'unrelated'
            changed[len(before)]['content'] = json.dumps(value, separators=(',', ':'))
            with self.assertRaisesRegex(ValueError, 'differs_from_received'):
                projection_after_turn(before, changed, result)

    def test_current_execution_error_stays_visible_and_does_not_verify_summary(self):
        before, after, message, _ = fixture(observation_status='error')
        views = projection_after_turn(before, after, split(message))
        self.assertEqual(views['compacted'][-1], after[-1])
        self.assertIn('error', views['compacted'][-1]['content'])
        self.assertFalse(views['semantics_verified'])

    def test_nonshrinking_checkpoint_is_rejected_and_counted_view_mutation_is_rejected(self):
        before, after, message, _ = fixture()
        views = projection_after_turn(before, after, split(message))
        for amount in (100, 101):
            selected, accepted = choose_counted_projection(views, 100, amount)
            self.assertFalse(accepted)
            self.assertEqual(selected, views['ordinary'])
        selected, accepted = choose_counted_projection(views, 100, 99)
        self.assertTrue(accepted)
        self.assertEqual(selected, views['compacted'])
        selected[0]['content'] = 'caller mutation'
        self.assertEqual(views['compacted'][0]['content'], 'synthetic instructions')
        views['compacted'][0]['content'] = 'altered after counting'
        with self.assertRaisesRegex(ValueError, 'counted_compacted_view_changed'):
            choose_counted_projection(views, 100, 99)


if __name__ == '__main__':
    unittest.main()
