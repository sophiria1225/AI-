import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from budget_signal import snapshot
from documentation_comparison import ARMS, NOTICE, OriginBudgetInference, add_notification
from residual_output_budget import admission
from run_context_comparison import BudgetStop
from run_documentation_comparison import run_order


class DocumentationComparisonTests(unittest.TestCase):
    def config(self):
        return {'model': {'model': 'fixture', 'num_ctx': 1000, 'call_timeout_seconds': 60},
                'seed': 50, 'draft_temperature': .7, 'agent_temperature': 1,
                'max_api_requests': 80, 'max_calls': 4, 'max_wall_seconds': 60,
                'max_total_tokens': 200, 'max_output_tokens': 40}

    def response(self, cfg, messages, out, wall, tools):
        result = {'status': 'ok', 'input_tokens': 75, 'output_tokens': cfg['num_predict'],
                  'cached_input_tokens': 0, 'wall_seconds': 1, 'done_reason': 'length',
                  'message': {'role': 'assistant', 'content': 'fixture'},
                  'timings': {'cache_n': 0, 'prompt_n': 75, 'predicted_n': cfg['num_predict'],
                              'prompt_ms': 100, 'predicted_ms': 10}}
        (out / 'response.json').write_text(json.dumps(result))
        return result

    def test_both_arms_charge_same_notice_and_remaining_budget_without_history_growth(self):
        original = [{'role': 'system', 'content': 'rules'}, {'role': 'tool', 'content': 'receipt'}]
        seen = []
        for arm in ARMS:
            with tempfile.TemporaryDirectory() as directory:
                config = self.config(); frozen = copy.deepcopy(config)
                runner = OriginBudgetInference(config, Path(directory), arm)
                runner.set_environment_usage(18, 2)
                requests = []
                def complete(cfg, messages, out, wall, tools):
                    requests.append((copy.deepcopy(cfg), copy.deepcopy(messages)))
                    return self.response(cfg, messages, out, wall, tools)
                with patch('documentation_comparison.time.monotonic', return_value=runner.started), \
                     patch('residual_output_budget.count_input', return_value={'input_tokens': 75}), \
                     patch('residual_output_budget.model_call', side_effect=complete):
                    runner.call('agent', original, [])
                    runner.set_environment_usage(18, 3)
                    runner.call('agent', original, [])
                self.assertEqual(config, frozen)
                self.assertEqual([c['output_cap'] for c in runner.calls], [40, 10])
                self.assertEqual(runner.tokens, 200)
                self.assertEqual([cfg['cache_prompt'] for cfg, _ in requests], [False, True])
                self.assertEqual([cfg['seed'] for cfg, _ in requests], [50, 51])
                for _, messages in requests:
                    self.assertEqual(messages[:-1], original)
                    self.assertEqual(len(messages), len(original) + 1)
                    self.assertTrue(messages[-1]['content'].startswith(NOTICE))
                self.assertEqual(runner.snapshots[1]['state']['remaining']['logical_input_plus_output_tokens'], 85)
                self.assertEqual(runner.snapshots[1]['state']['remaining']['api_calls'], 59)
                self.assertTrue(runner.snapshots[0]['first_input_measurement']['state_confirmed'])
                seen.append(requests)
        self.assertEqual(seen[0], seen[1])

    def test_first_call_with_cached_prefix_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = OriginBudgetInference(self.config(), Path(directory), ARMS[1])
            def contaminated(cfg, messages, out, wall, tools):
                result = self.response(cfg, messages, out, wall, tools)
                result['cached_input_tokens'] = 20
                result['timings'].update(cache_n=20, prompt_n=55)
                (out / 'response.json').write_text(json.dumps(result))
                return result
            with patch('residual_output_budget.count_input', return_value={'input_tokens': 75}), \
                 patch('residual_output_budget.model_call', side_effect=contaminated):
                with self.assertRaisesRegex(ValueError, 'reused'):
                    runner.call('agent', [], [])
            self.assertTrue(runner.snapshots[0]['model_attempted'])
            self.assertFalse(runner.snapshots[0]['first_input_measurement']['state_confirmed'])

    def test_unknown_usage_cannot_be_turned_into_a_remaining_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = OriginBudgetInference(self.config(), Path(directory), ARMS[0])
            runner.calls.append({'status': 'error', 'input_tokens': None, 'output_tokens': None})
            with patch('residual_output_budget.model_call') as model:
                with self.assertRaisesRegex(ValueError, 'unknown'):
                    runner.call('agent', [], [])
                model.assert_not_called()

    def test_rejected_input_is_logged_without_free_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = OriginBudgetInference(self.config(), Path(directory), ARMS[1])
            with patch('residual_output_budget.count_input', return_value={'input_tokens': 201}), \
                 patch('residual_output_budget.model_call') as model:
                with self.assertRaisesRegex(BudgetStop, 'reservation'):
                    runner.call('agent', [], [])
                model.assert_not_called()
            self.assertFalse(runner.snapshots[0]['model_attempted'])
            self.assertFalse(runner.admissions[0]['admitted'])
            self.assertTrue((Path(directory) / 'initial_messages_private.json').exists())

    def test_notice_matches_residual_policy_and_does_not_mutate_base(self):
        messages = [{'role': 'user', 'content': 'task'}]
        state = snapshot(self.config(), [], 18, 0, 0)
        actual = add_notification(messages, state)
        actual[0]['content'] = 'changed'
        self.assertEqual(messages[0]['content'], 'task')
        self.assertIn('smaller of the configured maximum', NOTICE)
        self.assertEqual(admission(100, 75, 40, 1000, 'residual')['selected_output_cap'], 25)

    def test_fixed_order_covers_all_four_tasks_including_the_lower_savings_case(self):
        tasks = [{'source_run': f'P29_{n:02d}_CODE'} for n in range(1, 5)]
        order = run_order(tasks)
        self.assertEqual(len(order), 8)
        self.assertEqual([arm for _, _, arm in order[::2]], [ARMS[0], ARMS[1], ARMS[0], ARMS[1]])
        for n, task in enumerate(tasks, 1):
            self.assertEqual({arm for number, item, arm in order if item == task and number == n}, set(ARMS))


if __name__ == '__main__':
    unittest.main()
