import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from api_error_comparison import add_notification
from clock_notice_replay import LEVELS, equality_summary, output_fingerprints, requests_for, reserve_tokens, schedule
from audit_clock_notice import audit_known_record
from inference_cache_control import cache_measurement
from local_llama import parse_response


class ClockNoticeReplayTests(unittest.TestCase):
    def request(self):
        state = {'remaining': {'wall_seconds_at_snapshot': 1696, 'tokens': 123}, 'used': {'calls': 5}}
        messages = [{'role': 'assistant', 'content': '', 'reasoning_content': 'opaque',
            'tool_calls': [{'id': 'kept_id', 'function': {'name': 'run_python', 'arguments': '{"source":"pass"}'}}]},
            {'role': 'tool', 'tool_call_id': 'kept_id', 'content': 'kept'}]
        return {'model': 'minimax-m3-iq4xs', 'seed': 56, 'max_tokens': 4096, 'stream': False,
                'cache_prompt': True, 'messages': add_notification(messages, state)}, state

    def response(self, content='ok', reason='tool_calls', ident='id'):
        return {'status': 'ok', 'done_reason': reason, 'message': {'role': 'assistant',
            'content': content, 'reasoning_content': 'opaque',
            'tool_calls': [{'id': ident, 'function': {'name': 'run_python', 'arguments': '{"source":"pass"}'}}]}}

    def rows(self, response=None):
        return [{**s, 'status': 'ok', **output_fingerprints(response or self.response())} for s in schedule()]

    def test_only_clock_and_common_cache_flag_change(self):
        original, state = self.request(); saved = copy.deepcopy((original, state))
        variants = requests_for(original, state)
        for level, seconds in [('original', 1696), ('plus_one', 1697)]:
            expected = copy.deepcopy(original); changed = copy.deepcopy(state)
            changed['remaining']['wall_seconds_at_snapshot'] = seconds
            expected['messages'][-1] = add_notification([], changed)[0]; expected['cache_prompt'] = False
            self.assertEqual(variants[level], expected)
        self.assertEqual((original, state), saved)
        variants['original']['messages'][0]['reasoning_content'] = 'changed'
        self.assertEqual(variants['plus_one']['messages'][0]['reasoning_content'], 'opaque')

    def test_wrong_notice_or_seed_is_rejected(self):
        original, state = self.request(); state['remaining']['wall_seconds_at_snapshot'] += 1
        with self.assertRaises(ValueError): requests_for(original, state)
        original, state = self.request(); original['seed'] = 57
        with self.assertRaises(ValueError): requests_for(original, state)

    def test_all_twelve_slots_have_three_per_level(self):
        slots = schedule(); self.assertEqual(len({s['id'] for s in slots}), 12)
        for case in (0, 1):
            for level in LEVELS:
                self.assertEqual([s['replicate'] for s in slots if s['case_index'] == case and s['level'] == level], [1, 2, 3])

    def test_budget_reserves_all_inputs_and_maximum_outputs(self):
        self.assertEqual(reserve_tokens([7403, 7403, 8631, 8631]), 145356)
        for counts in ([True, 1, 1, 1], [1, 1, 1], [20000] * 4, [65536] * 4):
            with self.assertRaises(ValueError): reserve_tokens(counts)

    def test_only_generated_transport_ids_are_ignored(self):
        a, b = self.response(ident='a'), self.response(ident='b')
        self.assertEqual(output_fingerprints(a), output_fingerprints(b))
        b['message']['tool_calls'][0]['function']['arguments'] = '{"source":"print(1)"}'
        self.assertNotEqual(output_fingerprints(a)['public_output_sha256'], output_fingerprints(b)['public_output_sha256'])
        b = copy.deepcopy(a); b['message']['reasoning_content'] = 'different opaque bytes'
        self.assertEqual(output_fingerprints(a)['public_output_sha256'], output_fingerprints(b)['public_output_sha256'])
        self.assertNotEqual(output_fingerprints(a)['opaque_message_sha256'], output_fingerprints(b)['opaque_message_sha256'])

    def test_truncated_or_empty_outputs_do_not_confirm_action_repetition(self):
        truncated = self.rows(self.response(reason='length'))
        self.assertIsNone(equality_summary(truncated)[0]['within']['original']['all_three_public_outputs_equal'])
        empty = self.response(content=''); empty['message']['tool_calls'] = []
        self.assertIsNone(equality_summary(self.rows(empty))[0]['within']['original']['all_three_public_outputs_equal'])

    def test_missing_unknown_and_discordant_calls_stay_visible(self):
        rows = self.rows(); summary = equality_summary(rows)
        self.assertTrue(summary[0]['within']['original']['all_three_public_outputs_equal'])
        self.assertEqual(summary[0]['cross']['compared_pairs'], 9)
        rows[0]['public_output_sha256'] = 'different'
        self.assertFalse(equality_summary(rows)[0]['within']['original']['all_three_public_outputs_equal'])
        rows[0].update(status='error', **output_fingerprints({'status': 'error'}))
        self.assertIsNone(equality_summary(rows)[0]['within']['original']['all_three_public_outputs_equal'])
        self.assertEqual(equality_summary(rows)[0]['within']['original']['known'], 2)
        self.assertIsNone(equality_summary(rows[:2])[0]['within']['original']['all_three_public_outputs_equal'])

    def audited_record(self):
        raw = {'usage': {'prompt_tokens': 7403, 'completion_tokens': 12, 'total_tokens': 7415,
                        'prompt_tokens_details': {'cached_tokens': 0}},
               'choices': [{'finish_reason': 'tool_calls', 'message': self.response()['message']}],
               'timings': {'cache_n': 0, 'prompt_n': 7403, 'predicted_n': 12, 'prompt_ms': 500, 'predicted_ms': 200}}
        record = parse_response(raw)
        row = {**record, **output_fingerprints(record), 'cache': cache_measurement('cold_1', record, 7403),
               'idle': {'one_slot_idle': True}}
        return raw, record, row

    def test_audit_recounts_raw_usage_and_requires_cold_idle(self):
        raw, record, row = self.audited_record()
        self.assertEqual(audit_known_record(raw, record, row, 7403, 4096)['known_total_tokens'], 7415)
        for field, bad in [('input_tokens', 7402), ('public_output_sha256', 'tampered'), ('idle', {'one_slot_idle': False})]:
            changed = copy.deepcopy(row); changed[field] = bad
            with self.assertRaises(ValueError): audit_known_record(raw, record, changed, 7403, 4096)

    def test_saved_response_cannot_replace_raw_generation(self):
        raw, record, row = self.audited_record()
        record = copy.deepcopy(record); record['message']['content'] = 'edited'
        with self.assertRaises(ValueError): audit_known_record(raw, record, row, 7403, 4096)


if __name__ == '__main__': unittest.main()
