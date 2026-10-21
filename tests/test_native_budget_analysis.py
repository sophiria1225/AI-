import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from analyze_native_budget import analyze


class BudgetAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan = {'phase': 'CHECK', 'batch_id': 'batch', 'arms': ['native_roles'],
                     'max_calls': 5, 'max_api_requests': 8, 'max_total_tokens': 1000,
                     'max_wall_seconds': 30, 'max_output_tokens': 100,
                     'run_order': [['task', 'native_roles', 'trial']]}
        self.plan_path = self.root/'plan.json'
        self.batch = self.root/'records/context_pilot/batch'
        self.trial = self.root/'records/context_pilot/trial'
        self.write(self.plan_path, self.plan)
        self.write(self.batch/'plan.json', self.plan)
        self.write(self.batch/'status.json', {'status': 'complete'})
        self.write(self.trial/'plan.json', self.plan)
        self.summary = {'run_id': 'trial', 'task_id': 'task', 'arm': 'native_roles',
                        'model_calls': 1, 'known_total_tokens': 220, 'api_requests': 2,
                        'tool_turns': 3, 'wall_seconds': 31.2, 'declared_complete': False,
                        'stop_reason': 'wall_limit'}
        self.usage = [{'id': 'call_001', 'role': 'agent', 'status': 'ok',
                       'input_tokens': 200, 'output_tokens': 20, 'wall_seconds': 28,
                       'finish_reason': 'length'}]
        self.response = {'status': 'ok', 'input_tokens': 200, 'output_tokens': 20,
                         'cached_input_tokens': 150,
                         'timings': {'cache_n': 150, 'prompt_n': 50, 'predicted_n': 20,
                                     'prompt_ms': 1000, 'predicted_ms': 2000},
                         'message': {'content': 'PRIVATE_RESPONSE_SENTINEL'}}
        self.write(self.trial/'summary.json', self.summary)
        self.write(self.trial/'usage.json', self.usage)
        self.write(self.trial/'events.json', [{'call': 'call_001', 'api_request_sent': sent}
                                             for sent in [True, True, False]])
        self.write(self.trial/'call_001/response.json', self.response)
        # A deliberately non-JSON evaluator file ensures its contents are not loaded.
        (self.trial/'evaluation.json').write_text('PRIVATE_EVALUATOR_SENTINEL: NOT JSON')

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def test_counts_each_api_and_separates_server_time_from_trial_time(self):
        result = analyze(self.root, self.plan_path)
        row = result['trials'][0]
        self.assertEqual(row['api_requests'], 2)
        self.assertEqual(row['model_calls'], 1)
        self.assertEqual(row['max_api_requests_in_one_response'], 2)
        self.assertEqual(row['prefill_seconds_in_timed_calls'], 1)
        self.assertAlmostEqual(row['wall_seconds_over_limit'], 1.2)
        self.assertTrue(row['unused_capacity_is_exact'])
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertFalse(result['evaluator_contents_read'])

    def test_rejects_running_batch_before_opening_trial_records(self):
        self.write(self.batch/'status.json', {'status': 'running'})
        (self.trial/'summary.json').unlink()
        with self.assertRaisesRegex(ValueError, 'all fixed trials'):
            analyze(self.root, self.plan_path)

    def test_rejects_changed_plan_even_if_terminal(self):
        changed = copy.deepcopy(self.plan)
        changed['max_api_requests'] += 1
        self.write(self.plan_path, changed)
        with self.assertRaisesRegex(ValueError, 'plan differs'):
            analyze(self.root, self.plan_path)

    def test_rejects_tampered_token_partition(self):
        self.response['timings']['cache_n'] -= 1
        self.write(self.trial/'call_001/response.json', self.response)
        with self.assertRaisesRegex(ValueError, 'partition differs'):
            analyze(self.root, self.plan_path)

    def test_unknown_usage_remains_unknown_not_zero_cost_success(self):
        self.usage.append({'id': 'call_002', 'role': 'agent', 'status': 'timeout',
                           'input_tokens': None, 'output_tokens': None, 'wall_seconds': 28})
        self.summary['model_calls'] = 2
        self.write(self.trial/'usage.json', self.usage)
        self.write(self.trial/'call_002/response.json', {
            'status': 'timeout', 'input_tokens': None, 'output_tokens': None})
        self.write(self.trial/'summary.json', self.summary)
        row = analyze(self.root, self.plan_path)['trials'][0]
        self.assertEqual(row['unknown_usage_calls'], 1)
        self.assertFalse(row['unused_capacity_is_exact'])
        self.assertEqual(row['timed_calls'], 1)
        self.assertEqual(row['known_total_tokens'], 220)
        self.assertEqual(row['call_wall_seconds_unknown'], 28)

    def test_rejects_operations_from_unknown_model_output(self):
        self.usage[0].update(status='timeout', input_tokens=None, output_tokens=None)
        self.response.update(status='timeout', input_tokens=None, output_tokens=None)
        self.summary['known_total_tokens'] = 0
        self.write(self.trial/'usage.json', self.usage)
        self.write(self.trial/'call_001/response.json', self.response)
        self.write(self.trial/'summary.json', self.summary)
        with self.assertRaisesRegex(ValueError, 'unknown model result'):
            analyze(self.root, self.plan_path)

    def test_redacts_unrecognized_stop_reason_and_rejects_count_tamper(self):
        self.summary['stop_reason'] = 'PRIVATE_ERROR_SENTINEL'
        self.write(self.trial/'summary.json', self.summary)
        self.assertNotIn('PRIVATE', json.dumps(analyze(self.root, self.plan_path)))
        self.summary['api_requests'] += 1
        self.write(self.trial/'summary.json', self.summary)
        with self.assertRaisesRegex(ValueError, 'counts disagree'):
            analyze(self.root, self.plan_path)


if __name__ == '__main__':
    unittest.main()
