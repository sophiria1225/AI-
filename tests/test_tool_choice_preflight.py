"""Synthetic preflight checks; no real task instructions or model requests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_whole_task_tool_choice as runner
from tool_choice_local_llama import payload_for

ROOT = Path(__file__).resolve().parents[1]


class ToolChoicePreflightTests(unittest.TestCase):
    def exercise(self, mismatch=False):
        plan = json.loads((ROOT / 'configs/P88_whole_task_reasoning_budget_v01.json').read_text())
        original = json.loads((ROOT / plan['source_plan']).read_text())
        prepared = [dict(item, public_task=dict(instruction='synthetic task', ground_truth_loaded=False))
                    for item in plan['known_tasks']]
        captured = []
        def count(cfg, messages, tools, timeout):
            captured.append(dict(cfg))
            return dict(input_tokens=101 if cfg['tool_choice'] == 'required' else 100,
                        wall_seconds=0, method='synthetic')
        def request(cfg, messages, tools):
            value = payload_for(cfg, messages, tools)
            if mismatch and cfg['tool_choice'] == 'required': value['temperature'] = .5
            return value
        with tempfile.TemporaryDirectory() as directory:
            storage, root = Path(directory) / 'storage', Path(directory) / 'repo'
            (root / 'reports').mkdir(parents=True)
            with patch.object(runner, 'sources', return_value=(plan, original, [], prepared)), \
                 patch.object(runner, 'frozen_hashes', return_value={'synthetic': 'bound'}), \
                 patch.object(runner, 'frozen_sources', return_value='synthetic-head'), \
                 patch.object(runner, 'live_identity', return_value=({'synthetic': True}, 'lease-end')), \
                 patch.object(runner, 'check_resume', return_value={'synthetic': True}), \
                 patch.object(runner, 'count_input', side_effect=count), \
                 patch.object(runner, 'payload_for', side_effect=request):
                if mismatch:
                    with self.assertRaisesRegex(ValueError, 'only_tool_choice'):
                        runner.preflight(storage, root)
                else: runner.preflight(storage, root)
            result = json.loads((root / runner.PREFLIGHT).read_text())
        return result, captured

    def test_all_eight_keep_messages_but_allow_template_token_difference(self):
        result, captured = self.exercise()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['input_count_requests'], 8)
        self.assertEqual([c['tool_choice'] for c in captured], ['auto', 'required'] * 4)
        self.assertEqual([c['reasoning_budget_tokens'] for c in captured], [-1] * 8)
        for row in result['rows']:
            a, b = row['conditions']['auto'], row['conditions']['required']
            self.assertEqual(a['model_messages_sha256'], b['model_messages_sha256'])
            self.assertNotEqual(a['input_tokens'], b['input_tokens'])
        self.assertEqual(result['model_generations'], 0)

    def test_other_request_change_preserves_failed_attempt_and_stops(self):
        result, captured = self.exercise(mismatch=True)
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(result['all_eight_inputs_checked'])
        self.assertEqual(len(captured), 2)
        self.assertEqual(result['model_generations'], 0)


if __name__ == '__main__': unittest.main()
