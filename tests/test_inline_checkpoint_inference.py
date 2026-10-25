import json
import unittest

from inline_checkpoint_inference_fixture import fixture


class InlineCheckpointInferenceTests(unittest.TestCase):
    def test_offer_is_counted_once_all_output_is_charged_and_future_requests_use_checkpoint(self):
        run = fixture()
        self.assertEqual(run['errors'], [])
        self.assertEqual(len(run['calls']), 6)
        self.assertEqual(len(run['executed']), 6)
        self.assertEqual([i for i, c in enumerate(run['captured']) if c['offered']], [3])
        self.assertTrue(run['summary']['checkpoint_installed'])
        self.assertEqual(run['summary']['separate_summary_calls'], 0)
        self.assertEqual(run['summary']['judge_calls'], 0)
        self.assertEqual(run['infer'].tokens, sum(c['input_tokens'] + c['output_tokens'] for c in run['calls']))
        self.assertEqual(run['calls'][3]['input_tokens'], 17500)
        self.assertEqual(run['calls'][3]['output_tokens'], 80)
        for call in run['captured'][4:]:
            self.assertTrue(any('ordinary_fallible_summary' in (m.get('content') or '')
                                for m in call['messages'] if m['role'] == 'user'))
            for m in call['messages']:
                for tool in m.get('tool_calls') or []:
                    self.assertNotIn('checkpoint', json.loads(tool['function']['arguments']))
        self.assertIn('checkpoint', json.loads(run['archived'][3]['action']['arguments']))
        self.assertEqual([c['cfg']['seed'] for c in run['captured']],
                         list(range(run['captured'][0]['cfg']['seed'], run['captured'][0]['cfg']['seed'] + 6)))
        self.assertEqual([c['cfg']['cache_prompt'] for c in run['captured']], [False] + [True] * 5)

    def test_native_comparison_uses_identical_post_execution_budget_notice(self):
        run = fixture()
        measured = run['saved']['inline_input_counts']
        a = next(r for r in measured if r['purpose'] == 'ordinary_next_input')
        b = next(r for r in measured if r['purpose'] == 'compacted_next_input')
        self.assertEqual(a['after_model_calls'], 4)
        self.assertEqual(b['after_model_calls'], 4)
        self.assertEqual(a['tools_sha256'], b['tools_sha256'])
        candidates = [c for c in run['counts'] if len(c['messages']) > 2 and
                      'remaining' in c['messages'][-1]['content']]
        # Find the first compacted native count and compare its immediately
        # preceding ordinary count, not synthetic token values as real savings.
        i = next(i for i, c in enumerate(candidates) if any(
            'ordinary_fallible_summary' in (m.get('content') or '')
            for m in c['messages'] if m['role'] == 'user'))
        self.assertEqual(candidates[i-1]['messages'][-1], candidates[i]['messages'][-1])
        self.assertEqual(candidates[i-1]['tools'], candidates[i]['tools'])

    def test_invalid_missing_malformed_and_truncated_summary_keep_history_and_never_retry(self):
        for mode in ('invalid', 'missing', 'malformed', 'truncated'):
            with self.subTest(mode=mode):
                run = fixture(mode=mode)
                self.assertEqual(run['errors'], [])
                self.assertFalse(run['summary']['checkpoint_installed'])
                self.assertEqual(sum(c['offered'] for c in run['captured']), 1)
                self.assertEqual(len(run['calls']), 6)
                self.assertEqual(len(run['executed']), 5 if mode == 'malformed' else 6)
                self.assertEqual(sum(m['role'] == 'assistant' for m in run['captured'][-1]['messages']), 5)

    def test_nonshrinking_checkpoint_is_spent_without_retry_and_without_compaction(self):
        run = fixture(nonshrinking=True)
        self.assertEqual(run['errors'], [])
        self.assertFalse(run['summary']['checkpoint_installed'])
        self.assertEqual(run['summary']['decision']['reason'], 'not_shorter')
        self.assertEqual(sum(c['offered'] for c in run['captured']), 1)
        self.assertEqual(sum(m['role'] == 'assistant' for m in run['captured'][-1]['messages']), 5)

    def test_unknown_or_missing_terminal_usage_stops_without_executing_response_or_retry(self):
        for mode in ('unknown', 'transport_error'):
            run = fixture(mode=mode)
            self.assertEqual(len(run['attempts']), 4)
            self.assertEqual(sum(c['status'] != 'ok' for c in run['attempts']), 1)
            self.assertEqual(len(run['executed']), 3)
            self.assertEqual(len(run['errors']), 1)
            self.assertFalse(run['summary']['offered_turn_closed'])
            self.assertFalse(run['summary']['checkpoint_installed'])

    def test_shared_budget_cannot_admit_base_request_while_ignoring_offer_overhead(self):
        run = fixture(token_limit=44000)
        self.assertEqual(len(run['captured']), 3)
        self.assertEqual(len(run['executed']), 3)
        self.assertEqual(len(run['attempts']), 3)
        self.assertTrue(run['summary']['opportunity_used'])
        self.assertIn('token', run['errors'][0]['message'])
        self.assertEqual(run['infer'].admissions[-1]['input_tokens'], 17500)

    def test_counting_time_consumes_the_same_work_deadline(self):
        run = fixture(offer_count_delay=61)
        self.assertEqual(len(run['captured']), 3)
        self.assertEqual(len(run['executed']), 3)
        self.assertIn('wall_limit', run['errors'][0]['message'])

    def test_no_trigger_no_extra_schema_and_valid_terminal_checkpoint_is_not_counted_unnecessarily(self):
        run = fixture(below_trigger=True)
        self.assertEqual(run['errors'], [])
        self.assertFalse(run['summary']['opportunity_used'])
        self.assertFalse(any(c['offered'] for c in run['captured']))
        terminal = fixture(steps=4)
        self.assertEqual(terminal['errors'], [])
        self.assertTrue(terminal['summary']['valid_checkpoint_pending_without_next_request'])
        self.assertFalse(terminal['summary']['checkpoint_installed'])
        self.assertFalse(any(c['purpose'] != 'trigger' for c in terminal['saved']['inline_input_counts']))

    def test_unclosed_offered_turn_blocks_next_generation(self):
        run = fixture(omit_close=True)
        self.assertEqual(len(run['captured']), 4)
        self.assertIn('must_close', run['errors'][0]['message'])

    def test_reused_first_cache_stops_before_any_execution(self):
        run = fixture(first_cached=1)
        self.assertEqual(len(run['attempts']), 1)
        self.assertEqual(run['executed'], [])
        self.assertIn('reused_prior_condition_cache', run['errors'][0]['message'])


if __name__ == '__main__':
    unittest.main()
