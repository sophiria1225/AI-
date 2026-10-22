import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_baseline_repair_census import inspect_events


class BaselineRepairCensusTests(unittest.TestCase):
    def fixtures(self):
        tool = {'type': 'function', 'function': {'name': 'phone__move', 'description': 'Move',
            'parameters': {'type': 'object', 'properties': {'destination': {'type': 'string'}}}}}
        events = [
            {'call': 'call_001', 'span_id': 's1', 'api_request_sent': True,
             'effects_unknown': False, 'new_tools': ['phone__move']},
            {'call': 'call_001', 'span_id': 's2', 'api_request_sent': False,
             'effects_unknown': False, 'new_tools': []},
        ]
        spans = {'s1': {'action': {}, 'observation': {}},
            's2': {'action': {'name': 'phone__move', 'arguments': json.dumps({'dest': 'PRIVATE_PATH'})},
                   'observation': {'format_error': 'unknown API parameter'}}}
        return events, spans, [tool]

    def test_native_same_response_does_not_gain_later_discovery(self):
        events, spans, tools = self.fixtures()
        result = inspect_events(events, spans, tools, 'native_calls')
        self.assertEqual(result['categories'], {'not_admitted': 1})
        self.assertFalse(result['rejections'][0]['contract_exposed_at_rejection'])
        events[1]['call'] = 'call_002'
        result = inspect_events(events, spans, tools, 'native_calls')
        self.assertEqual(result['categories'], {'complete_rename_candidate': 1})

    def test_python_same_program_sees_sequential_discovery_without_values_in_report(self):
        events, spans, tools = self.fixtures()
        for event in events:
            event['stage'] = 'python_api'
        result = inspect_events(events, spans, tools, 'persistent_python')
        self.assertEqual(result['categories'], {'complete_rename_candidate': 1})
        self.assertNotIn('PRIVATE_PATH', json.dumps(result))
        self.assertNotIn('arguments', json.dumps(result))

    def test_outer_model_rejection_is_separate(self):
        events, spans, tools = self.fixtures()
        for event in events:
            event['stage'] = 'model_tool'
        result = inspect_events(events, spans, tools, 'persistent_python')
        self.assertEqual(result['categories'], {'outside_api_repair': 1})

    def test_unknown_schema_or_duplicate_or_orphan_span_fails(self):
        events, spans, tools = self.fixtures()
        events[0]['new_tools'] = ['phone__missing']
        with self.assertRaises(ValueError):
            inspect_events(events, spans, tools, 'native_calls')
        events, spans, tools = self.fixtures()
        with self.assertRaises(ValueError):
            inspect_events(events + [events[1]], spans, tools, 'native_calls')
        spans['orphan'] = {}
        with self.assertRaises(ValueError):
            inspect_events(events, spans, tools, 'native_calls')

    def test_sent_request_never_admitted(self):
        events, spans, tools = self.fixtures()
        events[1]['call'] = 'call_002'
        events[1]['api_request_sent'] = True
        result = inspect_events(events, spans, tools, 'native_calls')
        self.assertEqual(result['categories'], {'not_admitted': 1})

    def test_noncontiguous_response_order_fails(self):
        events, spans, tools = self.fixtures()
        events[1]['call'] = 'call_002'
        events.append({**events[0], 'span_id': 's3'})
        spans['s3'] = spans['s1']
        with self.assertRaises(ValueError):
            inspect_events(events, spans, tools, 'native_calls')


if __name__ == '__main__':
    unittest.main()
