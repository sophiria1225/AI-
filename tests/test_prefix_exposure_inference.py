from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from checkpoint_prefix_exposure import MODES
from prefix_exposure_inference import PrefixExposureInference
from receipt_reasoning_history import digest
from rolling_checkpoint_worker_fixture import fixture
from run_context_comparison import BudgetStop


def run(mode='rolling_separate', **kwargs):
    instances = []
    def make(config, output, *, conversation):
        config['prefix_exposure_mode'] = mode
        instance = PrefixExposureInference(config, output, conversation=conversation)
        instances.append(instance)
        return instance
    with patch('run_whole_task_rolling_checkpoint_cell.RollingCheckpointInference', side_effect=make):
        result = fixture(policy='rolling_separate', **kwargs)
    result['exposure'] = instances[0].exposure_summary()
    result['controller'] = instances[0]
    return result


class PrefixExposureInferenceTests(unittest.TestCase):
    def test_ordinary_mode_retains_original_actual_requests_usage_and_decisions(self):
        args = dict(actions=('echo',)*9+('finish',), api_limit=32)
        original = fixture(policy='rolling_separate', **args)
        new = run(**args)
        self.assertEqual(original['captured'], new['captured'])
        self.assertEqual(original['saved']['usage'], new['saved']['usage'])
        self.assertEqual(original['result']['checkpoint_control'], new['result']['checkpoint_control'])
        self.assertGreater(new['exposure']['extra_native_counts'], 0)
        self.assertTrue(new['exposure']['accounting_complete'])

    def test_first_summary_and_actor_prefix_match_all_three_modes(self):
        args = dict(actions=('echo',)*5+('finish',), api_limit=32)
        results = [run(mode, **args) for mode in MODES]
        for result in results[1:]:
            self.assertEqual(result['captured'], results[0]['captured'])
            self.assertEqual(result['counted'], results[0]['counted'])
            self.assertEqual(result['saved']['usage'], results[0]['saved']['usage'])
        self.assertEqual(results[0]['exposure']['known_paid_focuses'], 1)

    def test_exposure_delays_repeat_instead_of_adding_an_and_gate_to_native_offer(self):
        args = dict(actions=('echo',)*10+('finish',), api_limit=32,
                    focus_input_tokens=30000)
        old = run('rolling_separate', **args)
        new = run('prefix_exposure', **args)
        interval = run('fixed_interval', **args)
        old_focus = [n for n,c in enumerate(old['captured']) if c['role'] == 'focus']
        new_focus = [n for n,c in enumerate(new['captured']) if c['role'] == 'focus']
        self.assertEqual(old_focus[0], new_focus[0])
        self.assertGreater(new_focus[1], old_focus[1])
        self.assertEqual(old_focus, [n for n,c in enumerate(interval['captured']) if c['role'] == 'focus'])
        self.assertEqual(old['programs'], new['programs'])
        decisions = new['saved']['prefix_exposure_decisions']
        self.assertTrue(any(d['ordinary_would_offer'] and not d['offer'] for d in decisions))

    def test_count_only_projection_never_enters_model_generation(self):
        result = run('prefix_exposure', actions=('echo',)*9+('finish',), api_limit=32)
        actual = {digest(x['messages']) for x in result['captured']}
        counts = result['saved']['prefix_exposure_counts']
        self.assertTrue(counts)
        self.assertTrue(all(x['count_only'] and not x['model_generation_allowed'] for x in counts))
        self.assertTrue(all(x['messages_sha256'] not in actual for x in counts))
        self.assertEqual(result['exposure']['count_only_generation_calls'], 0)

    def test_unsent_focus_does_not_create_paid_cost_or_exposure(self):
        result = run('prefix_exposure', actions=('echo',)*3+('finish',), max_calls=4)
        events = result['saved']['prefix_exposure_events']
        focus = [e for e in events if e['role'] == 'focus']
        self.assertEqual(len(focus), 1)
        self.assertEqual(focus[0]['status'], 'not_dispatched')
        self.assertIsNone(result['exposure']['previous_focus_cost'])
        self.assertEqual(result['exposure']['accumulated_exposure'], 0)
        self.assertEqual(result['exposure']['extra_native_counts'], 0)

    def test_invalid_paid_focus_resets_and_is_charged_without_installation(self):
        result = run('prefix_exposure', actions=('echo',)*9+('finish',), api_limit=32,
                     summary_mode='invalid')
        events = result['saved']['prefix_exposure_events']
        focus = [e for e in events if e['role'] == 'focus']
        self.assertGreaterEqual(len(focus), 2)
        self.assertTrue(all(e['paid_focus_tokens'] == 10020 and e['exposure_after'] == 0 for e in focus))
        self.assertEqual(result['result']['checkpoint_control']['installations'], 0)
        self.assertTrue(result['exposure']['accounting_complete'])

    def test_unknown_focus_or_actor_never_accrues_and_stops_continuation(self):
        focus = run('prefix_exposure', actions=('echo',)*9+('finish',), api_limit=32,
                    summary_mode='unknown')
        self.assertEqual(focus['captured'][-1]['role'], 'focus')
        self.assertTrue(focus['exposure']['blocked'])
        actor = run('prefix_exposure', actions=('echo',)*3+('unknown',), api_limit=32)
        self.assertEqual(actor['programs'], ['echo']*3)
        self.assertTrue(actor['exposure']['blocked'])
        self.assertEqual(actor['saved']['prefix_exposure_events'][-1]['status'], 'unknown_terminal')
        self.assertFalse(actor['exposure']['accounting_complete'])

    def test_post_actor_count_failure_preserves_paid_usage_and_withholds_action(self):
        with patch.object(PrefixExposureInference, '_count_without_raw',
                          side_effect=ValueError('synthetic counter failure')):
            result = run('prefix_exposure', actions=('echo',)*9+('finish',), api_limit=32)
        self.assertEqual(result['result']['stop_reason'], 'runtime_error')
        self.assertTrue(result['exposure']['contract_failed'])
        self.assertFalse(result['exposure']['accounting_complete'])
        actors = [c for c in result['saved']['usage'] if c['role'] == 'agent']
        self.assertEqual(len(actors), len(result['programs'])+1)
        self.assertTrue(all(c['status'] == 'ok' for c in actors))
        self.assertGreater(actors[-1]['input_tokens'], 0)
        last = result['saved']['prefix_exposure_events'][-1]
        self.assertEqual(last['status'], 'known_paid_actor_measurement_failed')
        self.assertEqual(last['input_tokens'], actors[-1]['input_tokens'])
        self.assertFalse(last['action_returned_to_worker'])
        self.assertEqual(last['added_exposure'], 0)

    def test_added_count_wall_stop_keeps_known_actor_and_stops_before_its_action(self):
        with patch.object(PrefixExposureInference, '_count_without_raw',
                          side_effect=BudgetStop('wall_limit_during_prefix_exposure_count')):
            result = run('prefix_exposure', actions=('echo',)*9+('finish',), api_limit=32)
        self.assertEqual(result['result']['stop_reason'], 'wall_limit_during_prefix_exposure_count')
        self.assertFalse(result['exposure']['contract_failed'])
        self.assertFalse(result['exposure']['accounting_complete'])
        self.assertTrue(result['exposure']['blocked'])
        self.assertEqual(result['exposure']['incomplete_paid_actor_measurements'], 1)
        actors = [c for c in result['saved']['usage'] if c['role'] == 'agent']
        self.assertEqual(len(actors), len(result['programs'])+1)
        self.assertEqual(result['result']['unknown_usage_calls'], 0)

    def test_counter_uses_same_actor_seed_cap_and_shared_remaining_wall(self):
        inference = PrefixExposureInference.__new__(PrefixExposureInference)
        inference.started = 0
        inference.config = {'max_wall_seconds': 60, 'agent_temperature': 1.0, 'seed': 57,
                            'model': {'cache_prompt': True}}
        inference.calls = [{'role': 'agent'}, {'role': 'focus'}, {'role': 'agent'}]
        inference.exposure_counts = []
        inference._save = lambda: None
        seen = []
        def counter(cfg, messages, tools, timeout):
            seen.append((cfg, messages, tools, timeout))
            return {'input_tokens': 4000, 'wall_seconds': 55}
        with patch('prefix_exposure_inference.time.monotonic', side_effect=[10, 10, 65, 65]), \
             patch('rolling_checkpoint_inference.count_agent_input', side_effect=counter):
            with self.assertRaisesRegex(BudgetStop, 'wall_limit_during_prefix_exposure_count'):
                inference._count_without_raw([{'role': 'system', 'content': 'fixture'}],
                                              [{'type': 'function'}], {'id': 'call_003', 'output_cap': 27})
        self.assertEqual(seen[0][0]['seed'], 58)
        self.assertEqual(seen[0][0]['num_predict'], 27)
        self.assertEqual(seen[0][3], 50)
        self.assertEqual(inference.exposure_counts[-1]['status'], 'failed')
        self.assertEqual(inference.exposure_counts[-1]['input_tokens'], 4000)
        self.assertEqual(inference.exposure_counts[-1]['control_wall_seconds'], 55)


if __name__ == '__main__': unittest.main()
