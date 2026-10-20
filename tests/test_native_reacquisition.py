import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from analyze_native_reacquisition import repeated_requests


class ReacquisitionControls(unittest.TestCase):
    def test_exact_equality_and_visibility_do_not_export_private_values(self):
        spans = {s: {'id': s, 'action': {'name': 'public__read',
                 'arguments': '{"token":"PRIVATE"}'}, 'observation': {'value': 'PRIVATE'}}
                 for s in ['s1', 's2', 's3']}
        spans['s3']['observation'] = {'value': 'CHANGED_PRIVATE'}
        events = [{'span_id': s, 'call': f'call_{i}', 'api_request_sent': True}
                  for i, s in enumerate(spans, 1)]
        views = [{'next_call_id': 'call_2', 'selection': {'retained_span_ids': []}},
                 {'next_call_id': 'call_3', 'selection': {'retained_span_ids': ['s2']}}]
        rows = repeated_requests(spans, events, views, {'public__read'})
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[0]['previous_span_retained'])
        self.assertTrue(rows[0]['same_recorded_observation'])
        self.assertTrue(rows[1]['previous_span_retained'])
        self.assertFalse(rows[1]['same_recorded_observation'])
        self.assertNotIn('PRIVATE', json.dumps(rows))
        events[1]['call'] = events[0]['call']
        rows = repeated_requests(spans, events, views, {'public__read'})
        self.assertFalse(rows[0]['prior_result_predates_current_call'])


if __name__ == '__main__':
    unittest.main()
