import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from context_preservation import compact
from input_exposure_accounting import (COMPONENTS, cumulative_inputs, documentation_renderings,
                                       match_receipt_text, receipt_group, token_increments)


class InputExposureAccountingTests(unittest.TestCase):
    def fixture(self):
        value = {'description': '日本語と private-test-sentinel'}
        observation = {'status': 'ok', 'stdout': 'Heading\n' + str(value) + '\n',
                       'api_receipts': [{'span_id': 's1', 'api': 'api_docs__show_api_doc',
                                         'api_request_sent': True}], 'error': None}
        spans = {'s1': {'action': {'name': 'api_docs__show_api_doc'},
                        'observation': {'observation': json.dumps(value)}}}
        events = {'s1': {'stage': 'python_api', 'api_request_sent': True}}
        return observation, spans, events

    def test_labeled_documentation_is_measured_without_a_safe_to_delete_claim(self):
        obs, spans, events = self.fixture()
        before = copy.deepcopy((obs, spans, events))
        group, docs = receipt_group(obs, spans, events)
        result = match_receipt_text(obs['stdout'], docs)
        self.assertEqual(group, 'documentation_only')
        self.assertEqual(result['unattributed_characters'], len('Heading\n'))
        self.assertGreater(result['covered_utf8_bytes'], result['covered_characters'])
        self.assertFalse(result['dataflow_proven'])
        self.assertFalse(result['safe_to_remove_claim'])
        self.assertNotIn('private-test-sentinel', json.dumps(result))
        self.assertEqual((obs, spans, events), before)

    def test_mixed_calls_are_distinguished_even_with_exact_documentation_text(self):
        obs, spans, events = self.fixture()
        obs['api_receipts'].append({'span_id': 's2', 'api': 'files__read', 'api_request_sent': True})
        spans['s2'] = {'action': {'name': 'files__read'}, 'observation': {'observation': {'task': 'data'}}}
        events['s2'] = dict(events['s1'])
        self.assertEqual(receipt_group(obs, spans, events)[0], 'mixed')
        obs['api_receipts'] = obs['api_receipts'][1:]
        self.assertEqual(receipt_group(obs, spans, events)[0], 'other')

    def test_error_truncation_no_receipts_and_failed_dispatch_remain_uncertain(self):
        for field, value in (('status', 'execution_error'), ('error', 'failed'),
                             ('stdout_truncated', True), ('unknown_effects', True),
                             ('declared_complete', True), ('api_receipts', [])):
            obs, spans, events = self.fixture(); obs[field] = value
            self.assertEqual(receipt_group(obs, spans, events)[0], 'uncertain')
        obs, spans, events = self.fixture()
        obs['api_receipts'][0]['api_request_sent'] = events['s1']['api_request_sent'] = False
        self.assertEqual(receipt_group(obs, spans, events)[0], 'uncertain')
        obs, spans, events = self.fixture()
        obs['api_receipts'][0]['api'] = spans['s1']['action']['name'] = 'files__read'
        spans['s1']['observation']['observation'] = json.dumps({'error': 'missing object'})
        self.assertEqual(receipt_group(obs, spans, events)[0], 'uncertain')

    def test_corrupt_or_duplicate_receipts_fail_instead_of_becoming_other(self):
        obs, spans, events = self.fixture()
        obs['api_receipts'].append(copy.deepcopy(obs['api_receipts'][0]))
        with self.assertRaises(ValueError): receipt_group(obs, spans, events)
        obs, spans, events = self.fixture(); events['s1']['stage'] = 'model_tool'
        with self.assertRaises(ValueError): receipt_group(obs, spans, events)
        obs, spans, events = self.fixture(); obs['api_receipts'][0]['api'] = 'different__api'
        with self.assertRaises(ValueError): receipt_group(obs, spans, events)

    def test_repeated_or_overlapping_matches_are_not_arbitrarily_attributed(self):
        for text, docs in (
            ('abc\nabc\n', [('a', {'print': 'abc\n'})]),
            ('abc\n', [('a', {'print': 'abc\n'}), ('b', {'print': 'abc\n'})]),
            ('abcdef\n', [('a', {'print': 'abcdef\n'}), ('b', {'print': 'def\n'})]),
            ('abcdef\nabc', [('a', {'print': 'abcdef\n'}), ('b', {'print': 'abc'})]),
        ):
            result = match_receipt_text(text, docs)
            self.assertEqual(result['covered_characters'], 0)
            self.assertEqual(result['unattributed_characters'], len(text))

    def test_renderer_aliases_share_a_match_and_missing_newline_is_not_repaired(self):
        result = match_receipt_text('value\n', [('s1', {'a': 'value\n', 'b': 'value\n'})])
        self.assertEqual(len(result['whole_response_matches']), 1)
        self.assertEqual(result['whole_response_matches'][0]['renderers'], ['a', 'b'])
        self.assertEqual(match_receipt_text('value', [('s1', {'a': 'value\n'})])['covered_characters'], 0)
        for value in ('not json', {'error': 'failed'}, {'detail': 'failed'}, 1):
            self.assertEqual(documentation_renderings(value), {})

    def input_fixture(self):
        messages = [{'role': 'system', 'content': 'System guidance'},
                    {'role': 'user', 'content': compact({'task': 'Task content'})}]
        groups = {}
        for number, group in enumerate(('documentation_only', 'mixed', 'other', 'uncertain')):
            sid = f's{number}'; groups[sid] = group
            messages.extend([
                {'role': 'assistant', 'content': 'Explanation', 'tool_calls': [
                    {'id': f'c{number}', 'type': 'function', 'function': {'name': 'run_python',
                     'arguments': json.dumps({'code': 'print(1)', 'span_ids': []})}}]},
                {'role': 'tool', 'name': 'run_python', 'tool_call_id': f'c{number}',
                 'content': compact({'span_id': sid, 'observation': {'stdout': f'Output {group}',
                                     'error': None, 'status': 'ok'}})}])
        return messages, [{'type': 'function', 'function': {'name': 'run_python'}}], groups

    def test_cumulative_inputs_reconstruct_full_input_without_mutating_it(self):
        messages, tools, groups = self.input_fixture(); before = copy.deepcopy(messages)
        cases = cumulative_inputs(messages, tools, groups)
        self.assertEqual([c['component'] for c in cases], ['envelope', *COMPONENTS])
        self.assertEqual(cases[-1]['messages'], messages)
        self.assertEqual(cases[-1]['tools'], tools)
        self.assertEqual(messages, before)
        for c in cases:
            for msg in c['messages']:
                if msg['role'] == 'assistant':
                    self.assertIsInstance(json.loads(msg['tool_calls'][0]['function']['arguments']), dict)
        meta = next(c for c in cases if c['component'] == 'receipt_metadata')
        for msg in meta['messages'][3::2]:
            obs = json.loads(msg['content'])['observation']
            self.assertEqual(obs['stdout'], '')
            self.assertEqual(obs['status'], 'ok')

    def test_paging_and_incomplete_classification_are_rejected(self):
        messages, tools, groups = self.input_fixture()
        messages[3]['content'] = compact({'span_id': 's0', 'first_page': {'text': 'partial'}})
        with self.assertRaises(ValueError): cumulative_inputs(messages, tools, groups)
        messages, tools, groups = self.input_fixture(); del groups['s0']
        with self.assertRaises(ValueError): cumulative_inputs(messages, tools, groups)
        messages, tools, groups = self.input_fixture(); groups['extra'] = 'other'
        with self.assertRaises(ValueError): cumulative_inputs(messages, tools, groups)

    def test_token_accounting_preserves_negative_interactions_and_refuses_unknown_usage(self):
        counts = dict(zip(('envelope', *COMPONENTS), (100, 150, 149, 200, 201, 300, 350, 500, 800, 900, 950)))
        increments = token_increments(counts)
        self.assertEqual(increments['system'], -1)
        self.assertEqual(sum(increments.values()), 950)
        for invalid in (None, True, 1.5, 0):
            with self.assertRaises(ValueError): token_increments({**counts, 'stdout_other': invalid})
        with self.assertRaises(ValueError): token_increments(dict(reversed(list(counts.items()))))


if __name__ == '__main__':
    unittest.main()
