import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_memory_submissions import classify


class MemorySubmissionControls(unittest.TestCase):
    def test_classification_exports_counts_and_categories_only(self):
        result = classify({'content': '', 'reasoning_content': 'PRIVATE'}, 'focus', ['s1'])
        self.assertEqual(result['format'], 'missing_or_multiple_submissions')
        self.assertEqual(result['reasoning_characters'], 7)
        message = {'tool_calls': [{'function': {'name': 'submit_selection', 'arguments': json.dumps({
            'steps': [{'plan': 'PRIVATE', 'depends_on': ['s1', 'PRIVATE', 'Step A']}],
            'rescued': [], 'rescue_reason': 'PRIVATE'})}}]}
        result = classify(message, 'focus', ['s1'])
        self.assertEqual(result['format'], 'source_or_schema_invalid')
        self.assertEqual(result['unavailable_citations'], 2)
        self.assertEqual(result['unavailable_plan_step_labels'], 1)
        self.assertTrue(result['all_visible_spans_cited'])
        self.assertNotIn('PRIVATE', json.dumps(result))
        message['tool_calls'][0]['function'] = {'name': 'submit_ledger', 'arguments': json.dumps({
            'items': [{'key': 'PRIVATE', 'requirement': 'PRIVATE', 'status': 'done', 'source_ids': ['s0']}],
            'constraints': [], 'unresolved': []})}
        result = classify(message, 'ledger', ['s1'], {'items': [{'source_ids': ['s0']}]})
        self.assertEqual(result['format'], 'structurally_valid_not_semantically_verified')
        self.assertNotIn('PRIVATE', json.dumps(result))
