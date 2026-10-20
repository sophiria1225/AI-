import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_context_costs import archive_last, audit, memory_sizes, prefix_length


class CostAuditControls(unittest.TestCase):
    def test_layout_preserves_all_information_and_original_is_immutable(self):
        original = {'messages': [{'role': 'user', 'content': json.dumps({
            'task': 'PRIVATE_TASK', 'memory': {
                'available_archive_ids': ['s1'], 'visible_spans': [
                    {'id': 's1', 'observation': 'PRIVATE_BODY'}],
                'working_ledger': {'items': ['PRIVATE_MEMORY']}}})}],
                    'tools': ['PRIVATE_SCHEMA']}
        frozen = json.dumps(original)
        changed = archive_last(original)
        self.assertEqual(json.dumps(original), frozen)
        self.assertEqual(json.loads(original['messages'][0]['content']),
                         json.loads(changed['messages'][0]['content']))
        self.assertEqual(changed['tools'], original['tools'])
        self.assertEqual(list(json.loads(changed['messages'][0]['content'])['memory'])[-1],
                         'available_archive_ids')
        self.assertEqual(prefix_length([1, 2, 3], [1, 2, 4]), 2)
        self.assertEqual(prefix_length([1], [1, 2]), 1)

    def test_unknown_cost_and_nested_api_error_are_not_silently_zero_or_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            usage = [dict(id='call_001', role='agent', status='ok', input_tokens=10,
                          output_tokens=2, cached_input_tokens=3, predicted_input_tokens=10,
                          wall_seconds=2),
                     dict(id='call_002', role='ledger', status='error', input_tokens=None,
                          output_tokens=None, predicted_input_tokens=20, wall_seconds=3)]
            files = {
                'summary.json': dict(run_id='control', arm='ledger', known_total_tokens=12,
                                     model_calls=2, wall_seconds=6, stop_reason='wall_limit'),
                'usage.json': usage, 'plan.json': {'secret': 'PRIVATE_PLAN'},
                'events.json': [],
                'spans.json': {'s1': {'action': {'name': 'appworld_api', 'arguments': '{}'},
                                     'observation': {'observation': 'Execution failed. PRIVATE_ERROR'}}},
            }
            for name, value in files.items():
                (root / name).write_text(json.dumps(value))
            for call in usage:
                out = root / call['id']
                out.mkdir()
                (out / 'request.json').write_text('PRIVATE_REQUEST')
                response = {'message': {'reasoning_content': 'PRIVATE_REASONING'}}
                if call['status'] == 'ok':
                    response['timings'] = dict(cache_n=3, prompt_n=7, prompt_ms=500, predicted_ms=1000)
                (out / 'response.json').write_text(json.dumps(response))
            result = audit(root)
            self.assertEqual(result['known_total_tokens'], 12)
            self.assertEqual(result['roles']['ledger']['unknown_usage_calls'], 1)
            self.assertEqual(result['roles']['ledger']['timing_calls'], 0)
            self.assertEqual(result['roles']['agent']['prompt_seconds'], 0.5)
            self.assertEqual(result['operations']['api_execution_errors'], 1)
            self.assertEqual(result['operations']['bridge_errors'], 0)
            self.assertEqual(result['audit_errors'], [])
            self.assertNotIn('PRIVATE_', json.dumps(result))

    def test_interrupted_compression_has_no_measured_after_size(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'plan.json').write_text(json.dumps({'compression_trigger_tokens': 4096}))
            (root / 'usage.json').write_text(json.dumps([{'id': 'call_001', 'role': 'focus'}]))
            out = root / 'call_001'
            out.mkdir()
            (out / 'request.json').write_text(json.dumps({'messages': [{'content': json.dumps({
                'memory': {'visible_spans': [], 'available_archive_ids': []}})}]}))
            result = memory_sizes(root, lambda text: [1, 2])
            self.assertIsNone(result['updates'][0]['after_memory_tokens'])
            self.assertIsNone(result['updates'][0]['after_above_trigger'])


if __name__ == '__main__':
    unittest.main()
