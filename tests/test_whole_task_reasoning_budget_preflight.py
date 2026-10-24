"""The full preflight sees only synthetic tasks and a synthetic token counter."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_whole_task_reasoning_budget as runner

ROOT = Path(__file__).resolve().parents[1]


class WholeTaskBudgetPreflightTests(unittest.TestCase):
    def exercise(self, mismatch=False):
        plan = json.loads((ROOT / runner.PLAN).read_text())
        original = json.loads((ROOT / plan['source_plan']).read_text())
        prepared = [dict(item, public_task={'instruction': 'synthetic task', 'ground_truth_loaded': False})
                    for item in plan['known_tasks']]
        captured = []
        def count(config, messages, tools, timeout):
            captured.append(dict(config))
            return {'input_tokens': 101 if mismatch and len(captured) == 2 else 100,
                    'wall_seconds': 0, 'method': 'synthetic'}
        with tempfile.TemporaryDirectory() as temp:
            storage, root = Path(temp) / 'storage', Path(temp) / 'repo'
            (root / 'reports').mkdir(parents=True)
            with patch.object(runner, 'sources', return_value=(plan, original, [], prepared)), \
                 patch.object(runner, 'frozen_hashes', return_value={'synthetic': 'bound'}), \
                 patch.object(runner, 'frozen_sources', return_value='synthetic-head'), \
                 patch.object(runner, 'live_identity', return_value=({'synthetic': True}, 'lease-end')), \
                 patch.object(runner, 'check_resume', return_value={'synthetic': True}), \
                 patch.object(runner, 'count_input', side_effect=count):
                if mismatch:
                    with self.assertRaisesRegex(ValueError, 'tokens_not_matched'):
                        runner.preflight(storage, root)
                else:
                    runner.preflight(storage, root)
            result = json.loads((root / runner.PREFLIGHT).read_text())
            request_paths = list((storage / 'records/context_pilot/P88_preflight_v01').glob('*_request_private.json'))
            requests = [json.loads(p.read_text()) for p in request_paths]
        return result, captured, requests

    def test_all_eight_count_requests_have_explicit_budget_and_identical_paired_prompts(self):
        result, captured, requests = self.exercise()
        self.assertEqual(result['status'], 'complete')
        self.assertTrue(result['all_eight_inputs_checked'])
        self.assertEqual(result['input_count_requests'], 8)
        self.assertEqual(len(requests), 8)
        self.assertEqual([x['reasoning_budget_tokens'] for x in captured], [-1, 2048] * 4)
        self.assertEqual(result['model_generations'], 0)
        self.assertEqual(result['environment_api_requests'], 0)
        self.assertEqual(result['evaluator_calls'], 0)
        for row in result['rows']:
            a, b = row['conditions']['unlimited'], row['conditions']['half']
            self.assertEqual(a['model_messages_sha256'], b['model_messages_sha256'])
            self.assertEqual(a['input_tokens'], b['input_tokens'])
            self.assertNotEqual(a['count_request_sha256'], b['count_request_sha256'])

    def test_input_disagreement_preserves_failed_preflight_and_stops_without_generation(self):
        result, captured, requests = self.exercise(mismatch=True)
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(result['all_eight_inputs_checked'])
        self.assertEqual(result['input_count_requests'], 2)
        self.assertEqual(len(captured), 2)
        self.assertEqual(len(requests), 2)
        self.assertEqual(result['model_generations'], 0)


if __name__ == '__main__':
    unittest.main()
