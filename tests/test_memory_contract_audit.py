import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_memory_contracts import inspect
from context_preservation import LEDGER_TOOL


class ContractAuditTest(unittest.TestCase):
    def submission(self, source_ids, status='pending'):
        value = {'items': [{'key': 'private-key', 'requirement': 'private-prose',
                            'status': status, 'source_ids': source_ids}],
                 'constraints': [], 'unresolved': []}
        response = {'status': 'ok', 'input_tokens': 40, 'output_tokens': 10,
                    'done_reason': 'tool_calls', 'message': {
                        'content': 'private-content', 'reasoning_content': 'private-reasoning',
                        'tool_calls': [{'function': {'name': 'submit_ledger',
                                                    'arguments': json.dumps(value)}}]}}
        request = {'max_tokens': 50, 'tools': [copy.deepcopy(LEDGER_TOOL)]}
        return response, request

    def test_empty_sources_advertised_but_receiver_rejects(self):
        response, request = self.submission([])
        result = inspect(response, request, 'ledger', ['s1'])
        self.assertEqual(result['advertised_source_min_items'], 0)
        self.assertFalse(result['receiver_accepts'])
        self.assertEqual(result['issue_counts'], {'empty_sources': 1})

    def test_task_is_unregistered_not_malformed_json(self):
        response, request = self.submission(['task'])
        result = inspect(response, request, 'ledger', ['s1'])
        self.assertFalse(result['receiver_accepts'])
        self.assertEqual(result['issue_counts']['unregistered_task_reference'], 1)

    def test_prior_ledger_source_allowed(self):
        response, request = self.submission(['s1'])
        result = inspect(response, request, 'ledger', ['s2'], {'items': [{'source_ids': ['s1']}]})
        self.assertTrue(result['receiver_accepts'])
        self.assertEqual(result['issue_counts'], {})

    def test_private_text_and_invalid_status_never_exported(self):
        response, request = self.submission(['private-id'], status='private-enum')
        result = inspect(response, request, 'ledger', ['s1'])
        self.assertNotIn('private-', json.dumps(result))
        self.assertEqual(result['affected_items'][0]['status_class'], 'outside_declared_enum')

    def test_aborted_response_is_not_zero_error(self):
        _, request = self.submission([])
        result = inspect({'status': 'error', 'input_tokens': None, 'output_tokens': None},
                         request, 'ledger', ['s1'])
        self.assertEqual(result['format'], 'no_completed_response')
        self.assertIsNone(result['output_at_cap'])
        self.assertNotIn('receiver_accepts', result)


if __name__ == '__main__':
    unittest.main()
