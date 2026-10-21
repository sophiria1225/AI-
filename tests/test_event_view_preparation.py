import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_event_view_probe import prepare_source, reject_response


def tool(name):
    return {'type': 'function', 'function': {'name': name,
            'parameters': {'type': 'object', 'properties': {'item': {'type': 'integer'}}}}}


def message(name='example__update'):
    return {'content': 'proposed change', 'tool_calls': [
        {'id': 'c1', 'type': 'function', 'function': {'name': name, 'arguments': '{"item":1}'}}]}


class PreparationTests(unittest.TestCase):
    def test_normal_dispatcher_rejects_without_bridge_and_source_is_immutable(self):
        original = message(); before = copy.deepcopy(original)
        altered, rows = reject_response(original, [tool('example__update')], '__p16_bad__')
        self.assertEqual(original, before)
        self.assertNotEqual(altered, original)
        self.assertFalse(rows[0]['api_request_sent'])
        self.assertEqual(rows[0]['observation'], {'format_error': 'unknown API parameter'})

    def test_mixed_helper_response_is_not_silently_subselected(self):
        mixed = message(); mixed['tool_calls'] += message('supervisor__complete_task')['tool_calls']
        with self.assertRaises(ValueError):
            reject_response(mixed, [tool('example__update'), tool('supervisor__complete_task')], '__p16_bad__')

    def test_prefix_excludes_later_completion_and_rejected_observation_has_no_real_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'call_002').mkdir()
            m = message()
            spans = {
                's1': {'id': 's1', 'assistant': '', 'action': {'name': 'api_docs__show_api_descriptions',
                      'arguments': '{}'}, 'observation': {'observation': 'PUBLIC_PREFIX'}},
                's2': {'id': 's2', 'assistant': m['content'], 'action': m['tool_calls'][0]['function'],
                      'observation': {'observation': 'ACTUAL_RETURN'}},
                's3': {'id': 's3', 'assistant': 'FUTURE_SECRET',
                      'action': {'name': 'supervisor__complete_task', 'arguments': '{}'},
                      'observation': {'observation': 'FUTURE_SECRET'}}}
            events = [{'call': f'call_{i:03d}', 'span_id': f's{i}', 'api_request_sent': True,
                       'effects_unknown': False} for i in (1, 2, 3)]
            values = {'events.json': events, 'spans.json': spans, 'public_task.json': {'instruction': 'task'},
                      'call_002/request.json': {'tools': [tool('example__update')]},
                      'call_002/response.json': {'status': 'ok', 'message': m}}
            for name, data in values.items(): (root/name).write_text(json.dumps(data))
            (root/'evaluation.json').write_text('THIS MUST NEVER BE PARSED')
            cases, hashes = prepare_source(root, '__p16_bad__')
            self.assertNotIn('FUTURE_SECRET', json.dumps(cases))
            self.assertIn('ACTUAL_RETURN', json.dumps(cases['recorded']))
            self.assertNotIn('ACTUAL_RETURN', json.dumps(cases['rejected_before_dispatch']))
            self.assertEqual(cases['recorded']['selected_span_ids'], ['s2'])
            self.assertFalse(cases['rejected_before_dispatch']['receipts']['s2']['api_request_sent'])
            self.assertNotIn('evaluation.json', hashes)


if __name__ == '__main__':
    unittest.main()
