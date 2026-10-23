import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from api_error_comparison import add_notification, task_snapshot
from budget_observation import BudgetObservationInference, notification
from run_context_comparison import BudgetStop


class BudgetObservationTests(unittest.TestCase):
    def config(self):
        return {'model': {'model': 'fixture', 'num_ctx': 1000, 'call_timeout_seconds': 60},
            'seed': 42, 'draft_temperature': .7, 'agent_temperature': 1,
            'max_calls': 4, 'max_wall_seconds': 60, 'max_total_tokens': 100,
            'max_api_requests': 8, 'max_output_tokens': 40}

    def runner(self, folder, policy='not_exposed'):
        with patch('budget_observation.time.monotonic', return_value=0):
            return BudgetObservationInference(self.config(), Path(folder), time_visibility=policy)

    def response(self, *, input_tokens=75, output_tokens=25, cached=0):
        return {'status': 'ok', 'input_tokens': input_tokens, 'output_tokens': output_tokens,
            'wall_seconds': 1, 'done_reason': 'tool_calls', 'cached_input_tokens': cached,
            'message': {'role': 'assistant', 'content': None, 'tool_calls': [
                {'id': 'fixture', 'type': 'function', 'function': {'name': 'execute', 'arguments': '{}'}}]},
            'timings': {'cache_n': cached, 'prompt_n': input_tokens-cached,
                'predicted_n': output_tokens, 'prompt_ms': 100, 'predicted_ms': 100}}

    def sender(self, captured, response=None):
        response = self.response() if response is None else response
        def send(cfg, messages, out, wall, tools):
            captured.append({'cfg': copy.deepcopy(cfg), 'messages': copy.deepcopy(messages),
                             'wall': wall, 'tools': copy.deepcopy(tools)})
            (out/'response.json').write_text(json.dumps(response))
            return copy.deepcopy(response)
        return send

    def test_measured_policy_preserves_existing_notification_exactly(self):
        state = task_snapshot(self.config(), [], 2, 10.2)
        messages = [{'role': 'user', 'content': 'finish the fixture'}]
        supplied, visible = notification(messages, state, 'measured')
        self.assertEqual(supplied, add_notification(messages, state))
        self.assertEqual(visible, state)
        self.assertIsNot(visible, state)

    def test_omission_changes_only_current_notice_and_keeps_actual_record(self):
        # Historical time information is intentionally not normalized or erased.
        history = [{'role': 'user', 'content': 'historical wall_seconds_at_snapshot: 58'}]
        state = task_snapshot(self.config(), [], 2, 10)
        original = copy.deepcopy(state)
        supplied, visible = notification(history, state, 'not_exposed')
        self.assertEqual(supplied[:-1], history)
        self.assertEqual(state, original)
        self.assertNotIn('wall_seconds_at_snapshot', supplied[-1]['content'])
        self.assertIn('not exposed', supplied[-1]['content'])
        expected = copy.deepcopy(state); del expected['remaining']['wall_seconds_at_snapshot']
        self.assertEqual(visible, expected)

    def test_wall_only_difference_is_absent_from_sent_notice_but_timeout_differs(self):
        observed, recorded = [], []
        for elapsed in (10, 11):
            with tempfile.TemporaryDirectory() as folder:
                runner = self.runner(folder); counted = []
                def count(cfg, messages, tools, timeout):
                    counted.append(copy.deepcopy(messages)); return {'input_tokens': 75}
                with patch('budget_observation.time.monotonic', return_value=elapsed), \
                     patch('residual_output_budget.count_input', side_effect=count), \
                     patch('residual_output_budget.model_call', side_effect=self.sender(observed)):
                    runner.call('agent', [{'role': 'user', 'content': 'fixture'}], [])
                self.assertEqual(counted[0], observed[-1]['messages'])
                self.assertEqual(observed[-1]['cfg']['num_predict'], 25)
                self.assertFalse(observed[-1]['cfg']['cache_prompt'])
                self.assertEqual(runner.tokens, 100)
                recorded.append(json.loads((Path(folder)/'budget_observations.json').read_text())[0])
        self.assertEqual(observed[0]['messages'], observed[1]['messages'])
        self.assertEqual([x['wall'] for x in observed], [50, 49])
        self.assertEqual(recorded[0]['visible_state'], recorded[1]['visible_state'])
        self.assertEqual([r['measured_state']['remaining']['wall_seconds_at_snapshot'] for r in recorded], [50, 49])
        self.assertTrue(all(r['model_attempted'] for r in recorded))

    def test_real_deadline_blocks_count_and_generation_with_either_policy(self):
        for policy in ('measured', 'not_exposed'):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as folder:
                runner = self.runner(folder, policy)
                with patch('budget_observation.time.monotonic', return_value=61), \
                     patch('residual_output_budget.count_input') as count, \
                     patch('residual_output_budget.model_call') as send:
                    with self.assertRaisesRegex(BudgetStop, 'wall_limit'):
                        runner.call('agent', [], [])
                    count.assert_not_called(); send.assert_not_called()
                row = json.loads((Path(folder)/'budget_observations.json').read_text())[0]
                self.assertEqual(row['measured_state']['remaining']['wall_seconds_at_snapshot'], 0)
                self.assertFalse(row['model_attempted'])

    def test_time_spent_counting_still_exhausts_real_deadline(self):
        with tempfile.TemporaryDirectory() as folder:
            runner = self.runner(folder); clock = [59]
            def count(*args, **kwargs): clock[0] = 61; return {'input_tokens': 75}
            with patch('budget_observation.time.monotonic', side_effect=lambda: clock[0]), \
                 patch('residual_output_budget.count_input', side_effect=count), \
                 patch('residual_output_budget.model_call') as send:
                with self.assertRaisesRegex(BudgetStop, 'wall_limit'):
                    runner.call('agent', [], [])
                send.assert_not_called()
            self.assertEqual(runner.calls, [])

    def test_unknown_usage_is_saved_and_cannot_be_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            runner = self.runner(folder); observed = []
            unknown = {'status':'error','input_tokens':None,'output_tokens':None,
                       'wall_seconds':1,'error_kind':'timeout','timeout_scope':'run_wall'}
            with patch('budget_observation.time.monotonic', return_value=10), \
                 patch('residual_output_budget.count_input', return_value={'input_tokens':75}) as count, \
                 patch('residual_output_budget.model_call', side_effect=self.sender(observed, unknown)) as send:
                with self.assertRaisesRegex(BudgetStop, 'wall_limit_during_model_call'):
                    runner.call('agent', [], [])
                with self.assertRaisesRegex(RuntimeError, 'stopped_after_BudgetStop'):
                    runner.call('agent', [], [])
                self.assertEqual(count.call_count, 1); self.assertEqual(send.call_count, 1)
            self.assertEqual(len(runner.snapshots), 1)
            self.assertTrue(runner.snapshots[0]['model_attempted'])
            self.assertIsNone(runner.calls[0]['input_tokens'])

    def test_transport_exception_after_dispatch_stays_unknown_and_blocks_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            runner = self.runner(folder)
            with patch('budget_observation.time.monotonic', return_value=10), \
                 patch('residual_output_budget.count_input', return_value={'input_tokens':75}) as count, \
                 patch('residual_output_budget.model_call', side_effect=OSError('fixture transport failure')) as send:
                with self.assertRaises(OSError): runner.call('agent', [], [])
                with self.assertRaisesRegex(RuntimeError, 'stopped_after_OSError'):
                    runner.call('agent', [], [])
                self.assertEqual(send.call_count, 1); self.assertEqual(count.call_count, 1)
            row = json.loads((Path(folder)/'budget_observations.json').read_text())[0]
            self.assertTrue(row['model_attempted'])
            self.assertTrue(row['usage_unknown'])
            self.assertFalse(row['terminal_usage_recorded'])
            self.assertEqual(row['status'], 'stopped')
            self.assertEqual(runner.calls, [])

    def test_no_output_reservation_means_no_model_request(self):
        with tempfile.TemporaryDirectory() as folder:
            runner = self.runner(folder)
            with patch('budget_observation.time.monotonic', return_value=10), \
                 patch('residual_output_budget.count_input', return_value={'input_tokens':100}), \
                 patch('residual_output_budget.model_call') as send:
                with self.assertRaisesRegex(BudgetStop, 'token_reservation_limit'):
                    runner.call('agent', [], [])
                send.assert_not_called()
            self.assertFalse(runner.snapshots[0]['model_attempted'])

    def test_first_request_reusing_prior_prefix_is_rejected_without_erasing_cost(self):
        with tempfile.TemporaryDirectory() as folder:
            runner = self.runner(folder)
            with patch('budget_observation.time.monotonic', return_value=10), \
                 patch('residual_output_budget.count_input', return_value={'input_tokens':75}), \
                 patch('residual_output_budget.model_call', side_effect=self.sender([], self.response(cached=1))):
                with self.assertRaisesRegex(ValueError, 'reused_prior_condition'):
                    runner.call('agent', [], [])
            self.assertEqual(runner.tokens, 100)
            self.assertTrue(runner.snapshots[0]['model_attempted'])
            self.assertFalse(runner.snapshots[0]['first_input_measurement']['state_confirmed'])

    def test_non_time_resources_still_change_the_notice(self):
        state = task_snapshot(self.config(), [], 2, 10)
        baseline, _ = notification([], state, 'not_exposed')
        for changed in (task_snapshot(self.config(), [], 3, 10),
                task_snapshot(self.config(), [{'status':'ok','input_tokens':10,'output_tokens':2}], 2, 10)):
            self.assertNotEqual(notification([], changed, 'not_exposed')[0], baseline)

    def test_policy_must_be_explicit_and_cannot_be_reassigned(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(TypeError): BudgetObservationInference(self.config(), Path(folder))
            for policy in ('rounded', '', None):
                with self.assertRaises(ValueError):
                    BudgetObservationInference(self.config(), Path(folder), time_visibility=policy)
            runner = self.runner(folder)
            with self.assertRaises(AttributeError): runner.time_visibility = 'measured'
            with self.assertRaisesRegex(ValueError, 'one_executor'):
                runner.call('focus', [], [])

    def test_invalid_measured_clock_is_not_hidden_by_omission(self):
        for value in (-1, 2.5, True, None):
            state = task_snapshot(self.config(), [], 0, 0)
            state['remaining']['wall_seconds_at_snapshot'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                notification([], state, 'not_exposed')


if __name__ == '__main__':
    unittest.main()
