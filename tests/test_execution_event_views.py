import copy
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from execution_event_views import project_span, project_spans, rejected_before_dispatch


class EventViewTests(unittest.TestCase):
    def setUp(self):
        self.span = {'id': 's2', 'assistant': 'proposed operation',
                     'action': {'name': 'app__edit', 'arguments': '{invalid'},
                     'observation': {'format_error': 'invalid JSON'}}
        self.receipt = {'span_id': 's2', 'api_request_sent': False, 'effects_unknown': False}

    def test_role_split_preserves_repair_but_not_memory_request(self):
        memory = project_span(self.span, self.receipt, variant='role_split', consumer='memory')
        repair = project_span(self.span, self.receipt, variant='role_split', consumer='repair')
        self.assertNotIn('action', memory)
        self.assertNotIn('assistant', memory)
        self.assertEqual(memory['unexecuted_output_archive_id'], 's2')
        self.assertEqual(repair['action'], self.span['action'])
        self.assertFalse(repair['runtime_execution']['api_request_sent'])

    def test_raw_unchanged_and_global_quarantine_hides_from_both(self):
        for role in ('memory', 'repair'):
            self.assertEqual(project_span(self.span, self.receipt, variant='raw', consumer=role), self.span)
            hidden = project_span(self.span, self.receipt, variant='quarantine', consumer=role)
            self.assertNotIn('action', hidden)

    def test_no_mutation_and_request_independence_of_memory_view(self):
        before = copy.deepcopy(self.span)
        first = project_span(self.span, self.receipt, variant='role_split', consumer='memory')
        changed = copy.deepcopy(self.span)
        changed['assistant'] = 'different alleged success'
        changed['action']['arguments'] = 'different rejected details'
        second = project_span(changed, self.receipt, variant='role_split', consumer='memory')
        self.assertEqual(first, second)
        self.assertEqual(self.span, before)

    def test_missing_or_unknown_receipt_does_not_authorize_removal(self):
        for receipt in (None, {**self.receipt, 'effects_unknown': True},
                        {**self.receipt, 'api_request_sent': True},
                        {**self.receipt, 'api_request_sent': 0},
                        {**self.receipt, 'effects_unknown': None}):
            self.assertEqual(project_span(self.span, receipt, variant='role_split', consumer='memory'), self.span)

    def test_successful_error_return_and_archive_read_are_not_rejection(self):
        for observation in ({'observation': 'API error'}, {'api_error': 'returned failure'},
                            {'transport_error_type': 'TimeoutError'}):
            s = {**self.span, 'observation': observation}
            self.assertFalse(rejected_before_dispatch(s, self.receipt))
        s = copy.deepcopy(self.span)
        s['action']['name'] = 'read_span'
        self.assertFalse(rejected_before_dispatch(s, self.receipt))

    def test_mismatched_receipts_and_invalid_views_fail(self):
        with self.assertRaises(ValueError):
            project_span(self.span, {**self.receipt, 'span_id': 's3'}, variant='raw', consumer='memory')
        with self.assertRaises(ValueError):
            project_spans({'s2': self.span}, {'s9': self.receipt}, variant='raw', consumer='memory')
        with self.assertRaises(ValueError):
            project_span(self.span, self.receipt, variant='unspecified', consumer='memory')


if __name__ == '__main__':
    unittest.main()
