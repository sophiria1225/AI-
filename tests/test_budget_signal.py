import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from budget_signal import BudgetInference, add_notification, snapshot


class BudgetSignalTests(unittest.TestCase):
    config = {'max_api_requests': 80, 'max_calls': 16, 'max_total_tokens': 120000,
              'max_wall_seconds': 480, 'max_output_tokens': 4096, 'model': {'num_ctx': 65536}}

    def test_remaining_includes_prefix_and_uses_measured_full_tokens(self):
        state = snapshot(self.config, [{'status': 'ok', 'input_tokens': 10000,
                         'output_tokens': 123, 'cached_input_tokens': 9999}], 18, 4, 20.2)
        self.assertEqual(state['remaining'], {'api_calls': 58, 'model_calls': 15,
                         'logical_input_plus_output_tokens': 109877, 'wall_seconds_at_snapshot': 459})

    def test_unknown_usage_and_overspending_are_not_exact_remaining_budgets(self):
        for calls, prefix, suffix, elapsed in (([{'status': 'error'}], 18, 0, 0),
                                              ([], 18, 63, 0), ([], -1, 0, 0), ([], 0, 0, float('nan'))):
            with self.assertRaises(ValueError):
                snapshot(self.config, calls, prefix, suffix, elapsed)

    def test_notification_does_not_modify_or_remove_any_base_message(self):
        messages = [{'role': 'system', 'content': 'rules'}, {'role': 'tool', 'content': 'receipt'}]
        state = snapshot(self.config, [], 18, 0, 0)
        plain = add_notification(messages, state, 'plain_keep')
        supplied = add_notification(messages, state, 'budget_keep')
        self.assertEqual(plain, messages)
        self.assertEqual(supplied[:-1], messages)
        self.assertIn('"api_calls":62', supplied[-1]['content'])
        supplied[0]['content'] = 'changed'
        self.assertEqual(messages[0]['content'], 'rules')

    def test_first_input_policy_and_measurement_are_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = BudgetInference(self.config, Path(tmp), 'budget_keep')
            runner.set_environment_usage(18, 0)
            policies = []
            def fake_call(self, role, messages, tools):
                policies.append(self.config['model']['cache_prompt'])
                cid = f'call_{len(self.calls)+1:03d}'
                self.calls.append({'id': cid, 'status': 'ok', 'input_tokens': 100, 'output_tokens': 5})
                p = self.output / cid
                p.mkdir()
                (p / 'response.json').write_text(json.dumps({'status': 'ok', 'input_tokens': 100,
                    'output_tokens': 5, 'cached_input_tokens': 0, 'timings': {'cache_n': 0,
                    'prompt_n': 100, 'predicted_n': 5, 'prompt_ms': 100, 'predicted_ms': 10}}))
                return {'role': 'assistant', 'content': 'fixture'}
            with patch('budget_signal.Inference.call', fake_call):
                runner.call('agent', [], [])
                runner.call('agent', [], [])
            self.assertEqual(policies, [False, True])
            self.assertTrue(runner.snapshots[0]['first_input_measurement']['state_confirmed'])
            self.assertTrue(all(s['model_attempted'] for s in runner.snapshots))
            self.assertNotIn('cache_prompt', self.config['model'])


if __name__ == '__main__':
    unittest.main()
