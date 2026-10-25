import json
import unittest

from inline_checkpoint_worker_fixture import fixture


class InlineCheckpointWorkerTests(unittest.TestCase):
    def test_both_policies_use_same_finite_worker_and_record_complete_usage(self):
        for policy in ('single_checkpoint', 'inline_checkpoint'):
            with self.subTest(policy=policy):
                run = fixture(policy=policy, actions=('echo', 'echo', 'echo', 'echo', 'finish'))
                self.assertEqual(run['result']['phase'], 'P119')
                self.assertEqual(run['result']['stop_reason'], 'agent_declared_complete')
                self.assertEqual(run['result']['api_requests'], 5)
                self.assertEqual(run['programs'], ['echo', 'echo', 'echo', 'echo', 'finish'])
                self.assertTrue(run['result']['cleanup_confirmed'])
                self.assertEqual(run['result']['unknown_usage_calls'], 0)
                self.assertTrue(run['result']['checkpoint_control']['checkpoint_installed'])
                self.assertEqual(run['result']['model_calls'], 6 if policy == 'single_checkpoint' else 5)
                self.assertEqual(sum(c['role'] == 'focus' for c in run['captured']),
                                 1 if policy == 'single_checkpoint' else 0)
                self.assertEqual(run['result']['known_total_tokens'], sum(
                    c['input_tokens'] + c['output_tokens'] for c in run['saved']['usage']))

    def test_inline_transport_witness_and_original_action_are_archived(self):
        run = fixture(actions=('echo', 'echo', 'echo', 'echo', 'finish'))
        events = [e for e in run['saved']['events'] if 'inline_transport' in e]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['stage'], 'model_tool')
        sid = events[0]['span_id']
        self.assertIn('checkpoint', json.loads(run['saved']['spans'][sid]['action']['arguments']))
        self.assertFalse(events[0]['inline_transport']['semantics_verified'])
        self.assertEqual(len([e for e in run['saved']['events'] if e['stage'] == 'python_api']), 5)

    def test_invalid_and_missing_metadata_still_execute_once_without_summary_retry(self):
        for mode in ('invalid', 'missing', 'truncated'):
            run = fixture(summary_mode=mode, actions=('echo', 'echo', 'echo', 'echo', 'finish'))
            self.assertEqual(run['result']['stop_reason'], 'agent_declared_complete')
            self.assertEqual(run['result']['model_calls'], 5)
            self.assertEqual(run['result']['api_requests'], 5)
            self.assertFalse(run['result']['checkpoint_control']['checkpoint_installed'])
            self.assertEqual(len([c for c in run['saved']['inline_controls'] if c['status'] == 'inline_offered']), 1)

    def test_unknown_model_usage_or_dispatch_cannot_execute_offered_action(self):
        for action in ('unknown', 'transport_error'):
            run = fixture(actions=('echo', 'echo', 'echo', action))
            self.assertEqual(run['result']['unknown_usage_calls'], 1)
            self.assertEqual(run['result']['model_calls'], 4)
            self.assertEqual(run['result']['api_requests'], 3)
            self.assertEqual(run['programs'], ['echo'] * 3)
            self.assertFalse(run['result']['checkpoint_control']['checkpoint_installed'])

    def test_api_unknown_stop_and_cleanup_failure_remain_failures(self):
        unknown = fixture(unknown_api=True)
        self.assertEqual(unknown['result']['stop_reason'], 'runtime_error')
        self.assertFalse(unknown['result']['declared_complete'])
        stopped = fixture(stop_after_api=True)
        self.assertEqual(stopped['result']['stop_reason'], 'user_stop')
        self.assertEqual(stopped['result']['api_requests'], 1)
        failed = fixture(cleanup_ok=False)
        self.assertEqual(failed['result']['stop_reason'], 'cleanup_error')
        self.assertFalse(failed['result']['cleanup_confirmed'])


if __name__ == '__main__':
    unittest.main()
