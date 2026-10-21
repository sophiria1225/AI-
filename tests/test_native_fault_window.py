import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_conversation import NativeConversation
from native_fault_window import fault_window, reacquired_receipts
from native_recent_window import recent_window


def add(conversation, start, values, api='example__read'):
    calls, spans = [], []
    for index, value in enumerate(values, start):
        sid = 's' + str(index)
        fn = {'name': api, 'arguments': json.dumps({'private': 'DO_NOT_EXPORT'})}
        calls.append({'id': sid, 'type': 'function', 'function': fn})
        spans.append({'id': sid, 'assistant': '', 'action': fn,
                      'observation': {'observation': value}})
    conversation.append({'role': 'assistant', 'content': '', 'tool_calls': calls}, spans)
    return spans


def tokens(text):
    # Independent test resource: each original receipt consumes ten units.
    return sum(message['role'] == 'tool' for message in json.loads(text)) * 10


class FaultWindowControls(unittest.TestCase):
    def example(self):
        c = NativeConversation('system', {'instruction': 'synthetic only'})
        add(c, 1, ['a', 'b'])
        add(c, 3, ['c'])
        add(c, 4, ['d'])
        return c

    def history(self, values=('same', 'same', 'same'), visible=((), (), ())):
        c = NativeConversation('system', {})
        spans, events, views = {}, [], []
        for i, value in enumerate(values, 1):
            row = add(c, i, [value])[0]
            spans[row['id']] = row
            events.append({'span_id': row['id'], 'call': f'call_{i}', 'api_request_sent': True})
            views.append({'next_call_id': f'call_{i}',
                          'selection': {'retained_span_ids': list(visible[i - 1])}})
        return spans, events, views

    def detect(self, data):
        return reacquired_receipts(*data, {'example__read'})

    def test_no_pin_is_exact_existing_recent_baseline(self):
        c = self.example()
        expected, details = recent_window(c, tokens, 20)
        actual, got = fault_window(c, tokens, [], 20)
        self.assertEqual(actual, expected)
        for key, value in details.items():
            self.assertEqual(got[key], value)

    def test_pin_retains_complete_batch_and_order_with_same_budget(self):
        c = self.example()
        original = c.messages()
        messages, detail = fault_window(c, tokens, ['s1'], 30)
        self.assertEqual(detail['retained_span_ids'], ['s1', 's2', 's4'])
        self.assertEqual([m['tool_call_id'] for m in messages if m['role'] == 'tool'],
                         ['s1', 's2', 's4'])
        self.assertEqual(detail['history_tokens'], 30)
        self.assertEqual(c.messages(), original)

    def test_unaffordable_pin_is_skipped_not_free(self):
        _, detail = fault_window(self.example(), tokens, ['s1'], 20)
        self.assertEqual(detail['retained_span_ids'], ['s3', 's4'])
        self.assertEqual(detail['unretained_pin_span_ids'], ['s1'])
        self.assertFalse(detail['history_budget_overflow'])

    def test_newest_turn_remains_even_if_it_alone_overflows(self):
        _, detail = fault_window(self.example(), tokens, ['s1'], 5)
        self.assertEqual(detail['retained_span_ids'], ['s4'])
        self.assertTrue(detail['history_budget_overflow'])

    def test_full_input_is_not_changed_when_it_fits(self):
        c = self.example()
        messages, detail = fault_window(c, tokens, ['s1'], 40)
        self.assertEqual(messages, c.for_model()[0])
        self.assertFalse(detail['memory_note_added'])

    def test_pins_compete_in_supplied_priority_order(self):
        c = self.example()
        _, first = fault_window(c, tokens, ['s3', 's1'], 30)
        _, second = fault_window(c, tokens, ['s1', 's3'], 30)
        self.assertEqual(first['retained_span_ids'], ['s3', 's4'])
        self.assertEqual(second['retained_span_ids'], ['s1', 's2', 's4'])

    def test_exact_repeat_after_omission_pins_latest_receipt_no_values_exported(self):
        data = self.history()
        original = copy.deepcopy(data)
        got = self.detect(data)
        self.assertEqual(got['fault_events'], 2)
        self.assertEqual([p['span_id'] for p in got['pin_candidates_newest_first']], ['s3'])
        self.assertNotIn('DO_NOT_EXPORT', json.dumps(got))
        self.assertNotIn('same', json.dumps(got))
        self.assertEqual(data, original)

    def test_visible_repeat_is_not_a_fault(self):
        got = self.detect(self.history(visible=((), ('s1',), ('s2',))))
        self.assertEqual(got['fault_events'], 0)
        self.assertEqual(got['pin_candidates_newest_first'], [])

    def test_same_response_duplicate_is_not_a_memory_fault(self):
        spans, events, views = self.history()
        events[1]['call'] = events[0]['call']
        events[2]['call'] = events[0]['call']
        got = self.detect((spans, events, views[:1]))
        self.assertEqual(got['fault_events'], 0)

    def test_changed_result_removes_old_pin_without_certifying_freshness(self):
        got = self.detect(self.history(('same', 'same', 'changed')))
        self.assertEqual(got['fault_events'], 1)
        self.assertEqual(got['changed_result_unpins'], 1)
        self.assertEqual(got['pin_candidates_newest_first'], [])

    def test_unsent_archive_or_rejection_cannot_be_pinned_as_api(self):
        spans, events, views = self.history()
        events[1]['api_request_sent'] = False
        events[2]['api_request_sent'] = False
        spans['s2']['action'] = None
        spans['s3']['action']['name'] = 'read_span'
        self.assertEqual(self.detect((spans, events, views))['fault_events'], 0)

    def test_missing_visibility_unknown_api_and_repeated_ids_are_rejected(self):
        data = self.history()
        with self.assertRaisesRegex(ValueError, 'visibility'):
            self.detect((data[0], data[1], data[2][1:]))
        with self.assertRaisesRegex(ValueError, 'allowlist'):
            reacquired_receipts(*data, set())
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.detect((data[0], data[1] + [data[1][0]], data[2]))

    def test_invalid_pin_or_token_count_rejected(self):
        c = self.example()
        for ids in (['absent'], ['s1', 's1']):
            with self.assertRaises(ValueError):
                fault_window(c, tokens, ids)
        with self.assertRaises(ValueError):
            fault_window(c, lambda text: True, ['s1'])

    def test_unknown_effects_are_not_treated_as_a_known_result(self):
        data = self.history()
        data[1][1]['effects_unknown'] = True
        with self.assertRaisesRegex(ValueError, 'unknown request effects'):
            self.detect(data)


if __name__ == '__main__':
    unittest.main()
