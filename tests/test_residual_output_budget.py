import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from residual_output_budget import ResidualInference, admission
from run_context_comparison import BudgetStop


class ResidualOutputTests(unittest.TestCase):
    def config(self):
        return {'model': {'model': 'fixture', 'num_ctx': 1000, 'call_timeout_seconds': 60},
                'seed': 42, 'draft_temperature': .7, 'agent_temperature': 1,
                'max_calls': 4, 'max_wall_seconds': 60, 'max_total_tokens': 100,
                'max_output_tokens': 40}

    def test_budget_is_full_input_plus_output_not_only_generation(self):
        self.assertFalse(admission(100, 75, 40, 1000, 'fixed')['admitted'])
        self.assertEqual(admission(100, 75, 40, 1000, 'residual')['selected_output_cap'], 25)
        self.assertFalse(admission(100, 100, 40, 1000, 'residual')['admitted'])
        self.assertFalse(admission(100, 101, 40, 1000, 'residual')['admitted'])

    def test_configured_output_and_context_limits_remain_hard_bounds(self):
        self.assertEqual(admission(10000, 100, 40, 1000, 'residual')['selected_output_cap'], 40)
        self.assertEqual(admission(10000, 990, 40, 1000, 'residual')['stop_reason'], 'context_limit')
        for value in (-1, 1.5, True):
            with self.assertRaises(ValueError): admission(value, 10, 40, 1000, 'residual')

    def test_accounting_and_model_payload_use_the_selected_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(); runner = ResidualInference(config, Path(directory))
            seen = []
            def complete(cfg, messages, out, wall, tools):
                seen.append(cfg.copy())
                return {'status': 'ok', 'input_tokens': 75, 'output_tokens': 25,
                        'wall_seconds': 1, 'done_reason': 'length', 'message': {'role': 'assistant', 'content': ''}}
            with patch('residual_output_budget.count_input', return_value={'input_tokens': 75}), \
                 patch('residual_output_budget.model_call', side_effect=complete):
                runner.call('agent', [], [])
            self.assertEqual(seen[0]['num_predict'], 25)
            self.assertEqual(runner.tokens, 100)
            self.assertEqual(config['max_output_tokens'], 40)
            self.assertEqual(runner.calls[0]['output_cap'], 25)
            self.assertTrue(json.loads((Path(directory)/'admissions.json').read_text())[0]['model_attempted'])

    def test_rejection_does_not_make_a_model_request(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = ResidualInference(self.config(), Path(directory))
            with patch('residual_output_budget.count_input', return_value={'input_tokens': 101}), \
                 patch('residual_output_budget.model_call') as call:
                with self.assertRaisesRegex(BudgetStop, 'token_reservation_limit'):
                    runner.call('agent', [], [])
                call.assert_not_called()
            self.assertEqual(runner.calls, [])

    def test_unknown_usage_is_saved_and_cannot_enable_a_free_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = ResidualInference(self.config(), Path(directory))
            with patch('residual_output_budget.count_input', return_value={'input_tokens': 75}), \
                 patch('residual_output_budget.model_call', return_value={
                    'status': 'error', 'input_tokens': None, 'output_tokens': None,
                    'wall_seconds': 1, 'error_kind': 'timeout', 'timeout_scope': 'run_wall'}) as call:
                with self.assertRaisesRegex(BudgetStop, 'wall_limit_during_model_call'):
                    runner.call('agent', [], [])
                with self.assertRaisesRegex(RuntimeError, 'unknown usage'):
                    runner.call('agent', [], [])
                self.assertEqual(call.call_count, 1)
            self.assertIsNone(runner.calls[0]['input_tokens'])

    def test_counting_cannot_bypass_elapsed_time_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('residual_output_budget.time.monotonic', return_value=0):
                runner = ResidualInference(self.config(), Path(directory))
            with patch('residual_output_budget.time.monotonic', side_effect=[59, 61]), \
                 patch('residual_output_budget.count_input', return_value={'input_tokens': 75}), \
                 patch('residual_output_budget.model_call') as call:
                with self.assertRaisesRegex(BudgetStop, 'wall_limit'):
                    runner.call('agent', [], [])
                call.assert_not_called()

    def test_changed_count_is_rejected_before_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {**self.config(), 'expected_input_tokens': 75}
            runner = ResidualInference(config, Path(directory))
            with patch('residual_output_budget.count_input', return_value={'input_tokens': 76}), \
                 patch('residual_output_budget.model_call') as call:
                with self.assertRaisesRegex(ValueError, 'frozen'):
                    runner.call('agent', [], [])
                call.assert_not_called()

    def test_server_overrun_is_not_accepted_as_budget_compliant(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = ResidualInference(self.config(), Path(directory))
            with patch('residual_output_budget.count_input', return_value={'input_tokens': 75}), \
                 patch('residual_output_budget.model_call', return_value={
                    'status': 'ok', 'input_tokens': 75, 'output_tokens': 26, 'wall_seconds': 1}):
                with self.assertRaisesRegex(RuntimeError, 'exceeded'):
                    runner.call('agent', [], [])
            self.assertEqual(runner.tokens, 101)


if __name__ == '__main__':
    unittest.main()
