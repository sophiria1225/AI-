import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prompt_identity import PAIR_RUNS, renamed_request, selected_requests


def request():
    return {'seed': 42, 'messages': [
        {'role': 'system', 'content': 'Keep the literal call_A unchanged.'},
        {'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'call_A', 'type': 'function', 'function': {'name': 'read', 'arguments': '{"key":"call_A"}'}},
            {'id': 'call_B', 'type': 'function', 'function': {'name': 'count', 'arguments': '{}'}},
        ]},
        {'role': 'tool', 'tool_call_id': 'call_B', 'name': 'count', 'content': '2'},
        {'role': 'tool', 'tool_call_id': 'call_A', 'name': 'read', 'content': 'value'},
    ]}


class PromptIdentityTests(unittest.TestCase):
    @staticmethod
    def cohort():
        rows = []
        for before, after, count in PAIR_RUNS:
            for run in (before, after):
                rows.append({'run_id': run, 'official_success': 'EXPORT' not in run, 'calls': [
                    {'call_id': f'call_{i + 1:03d}', 'status': 'ok', 'usage_known': True, 'input_tokens': 100}
                    for i in range(count)]})
        return [{'audit_errors': [], 'server_stopped': True, 'rows': rows}]

    def test_selection_keeps_failed_export_and_all_matched_prefixes(self):
        pairs = selected_requests(self.cohort())
        self.assertEqual(len(pairs), 33)
        self.assertEqual(sum('EXPORT' in pair[0]['run_id'] for pair in pairs), 8)

    def test_selection_rejects_incomplete_prefix(self):
        cohort = self.cohort(); cohort[0]['rows'][-1]['calls'].pop()
        with self.assertRaises(ValueError): selected_requests(cohort)

    def test_selection_rejects_unknown_usage(self):
        cohort = self.cohort(); cohort[0]['rows'][-1]['calls'][-1]['usage_known'] = False
        with self.assertRaises(ValueError): selected_requests(cohort)

    def test_bijection_preserves_out_of_order_result_binding(self):
        value = request(); original = copy.deepcopy(value)
        renamed, count = renamed_request(value)
        self.assertEqual(value, original)
        self.assertEqual(count, 2)
        self.assertEqual(renamed['messages'][2]['tool_call_id'], 'p73_binding_0002')
        self.assertEqual(renamed['messages'][3]['tool_call_id'], 'p73_binding_0001')
        self.assertEqual(renamed['messages'][0], original['messages'][0])
        self.assertEqual(renamed['messages'][1]['tool_calls'][0]['function'], original['messages'][1]['tool_calls'][0]['function'])

    def test_wrong_binding_is_not_erased(self):
        a = request(); b = copy.deepcopy(a)
        b['messages'][2]['tool_call_id'] = 'call_A'
        b['messages'][3]['tool_call_id'] = 'call_B'
        for m in b['messages'][2:]: m.pop('name')
        a['messages'][2].pop('name'); a['messages'][3].pop('name')
        self.assertNotEqual(renamed_request(a)[0], renamed_request(b)[0])

    def test_duplicate_declaration_rejected(self):
        value = request(); value['messages'][1]['tool_calls'][1]['id'] = 'call_A'
        with self.assertRaises(ValueError): renamed_request(value)

    def test_unknown_result_rejected(self):
        value = request(); value['messages'][2]['tool_call_id'] = 'absent'
        with self.assertRaises(ValueError): renamed_request(value)

    def test_repeated_result_rejected(self):
        value = request(); value['messages'].append(copy.deepcopy(value['messages'][-1]))
        with self.assertRaises(ValueError): renamed_request(value)

    def test_name_mismatch_rejected(self):
        value = request(); value['messages'][2]['name'] = 'read'
        with self.assertRaises(ValueError): renamed_request(value)

    def test_missing_result_rejected(self):
        value = request(); value['messages'].pop()
        with self.assertRaises(ValueError): renamed_request(value)

    def test_media_rejected(self):
        value = request(); value['messages'][0]['content'] = [{'type': 'image_url', 'image_url': {'url': 'https://invalid'}}]
        with self.assertRaises(ValueError): renamed_request(value)

    def test_original_content_and_parameters_remain_comparable(self):
        value = request(); other = copy.deepcopy(value); other['seed'] = 43
        self.assertNotEqual(renamed_request(value)[0], renamed_request(other)[0])
        other = copy.deepcopy(value); other['messages'][-1]['content'] += ' changed'
        self.assertNotEqual(renamed_request(value)[0], renamed_request(other)[0])


if __name__ == '__main__': unittest.main()
