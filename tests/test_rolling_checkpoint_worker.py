import json
import unittest

from checkpoint_replication_worker_fixture import fixture as previous_fixture
from rolling_checkpoint_worker_fixture import fixture


class RollingWorkerTests(unittest.TestCase):
    def test_single_baseline_preserves_old_requests_and_ledger(self):
        actions = ('echo',) * 5 + ('finish',)
        old = previous_fixture(policy='single_checkpoint', actions=actions, repetition=1)
        new = fixture(policy='single_checkpoint', actions=actions, max_calls=8)
        self.assertEqual(old['captured'], new['captured'])
        self.assertEqual(old['saved']['usage'], new['saved']['usage'])
        self.assertEqual(old['result']['checkpoint_control'], new['result']['checkpoint_control'])

    def test_first_inline_offer_matches_previous_protocol(self):
        actions = ('echo',) * 5 + ('finish',)
        old = previous_fixture(actions=actions, repetition=1)
        new = fixture(actions=actions, max_calls=8)
        self.assertEqual(old['captured'], new['captured'])
        self.assertEqual(new['result']['checkpoint_control']['installations'], 1)

    def test_three_opportunities_share_budget_and_keep_original_archive(self):
        for policy in ('rolling_separate', 'rolling_inline'):
            with self.subTest(policy=policy):
                actions = ('echo',) * 12 + ('finish',)
                run = fixture(policy=policy, actions=actions, api_limit=32)
                result, saved = run['result'], run['saved']
                self.assertEqual(result['stop_reason'], 'agent_declared_complete')
                self.assertEqual(run['programs'], list(actions))
                self.assertEqual(result['api_requests'], len(actions))
                control = result['checkpoint_control']
                self.assertEqual(control['opportunities'], 3)
                self.assertEqual(control['installations'], 3)
                focus = 3 if policy == 'rolling_separate' else 0
                self.assertEqual(result['model_calls'], len(actions) + focus)
                self.assertEqual(control['separate_summary_calls'], focus)
                self.assertEqual(result['known_total_tokens'], sum(
                    c['input_tokens'] + c['output_tokens'] for c in saved['usage']))
                self.assertEqual(len([m for m in saved['conversation_private'] if m['role']=='assistant']), len(actions))
                self.assertFalse(control['semantic_fidelity_verified'])
                self.assertFalse(control['task_quality_established'])
                for role, temperature in (('agent', 1.0), ('focus', 0.7)):
                    calls = [c for c in run['captured'] if c['role']==role]
                    self.assertEqual([c['cfg']['seed'] for c in calls], list(range(57,57+len(calls))))
                    self.assertTrue(all(c['cfg']['temperature']==temperature for c in calls))

    def test_recurrent_packet_contains_previous_state_and_only_new_old_turns(self):
        run = fixture(policy='rolling_separate', actions=('echo',)*9+('finish',), api_limit=32)
        offers = run['saved']['rolling_offers_private']
        for prior, current in zip(offers, offers[1:]):
            previous, offer = prior['offer'], current['offer']
            self.assertGreater(offer['cutoff'], previous['cutoff'])
            packet = json.loads(offer['summary_messages'][1]['content'])
            self.assertIsNotNone(packet['previous_checkpoint'])
            self.assertEqual(len(packet['older_history']), offer['cutoff']-offer['previous_cutoff'])
            self.assertFalse(packet['previous_checkpoint_semantics_verified'])

    def test_insufficient_shared_calls_skips_summary_without_faking_a_response(self):
        run = fixture(policy='rolling_separate', actions=('echo',)*3+('finish',), max_calls=4)
        self.assertEqual(run['result']['stop_reason'], 'agent_declared_complete')
        self.assertEqual(run['result']['model_calls'], 4)
        self.assertTrue(all(c['role']=='agent' for c in run['saved']['usage']))
        self.assertEqual(run['result']['checkpoint_control']['decisions'][0]['reason'],
                         'insufficient_shared_call_budget')

    def test_screening_does_not_take_tokens_from_an_unstarted_summary(self):
        for tokens, summary_input, reason in ((55000, 10000, 'insufficient_shared_token_budget'),
                                              (450000, 64000, 'summary_context_limit')):
            run = fixture(policy='rolling_separate', actions=('echo',)*3+('finish',),
                          token_limit=tokens, focus_input_tokens=summary_input)
            self.assertEqual(run['result']['stop_reason'], 'agent_declared_complete')
            self.assertEqual(run['result']['model_calls'], 4)
            self.assertEqual(run['result']['checkpoint_control']['decisions'][0]['reason'], reason)
            self.assertEqual(run['result']['usage_by_role']['focus']['calls'], 0)

    def test_invalid_checkpoint_spends_opportunity_and_requires_fresh_turns(self):
        for policy, mode in (('rolling_separate','invalid'), ('rolling_inline','invalid'),
                             ('rolling_inline','missing'), ('rolling_inline','truncated')):
            run = fixture(policy=policy, summary_mode=mode, actions=('echo',)*12+('finish',),
                          api_limit=32)
            control = run['result']['checkpoint_control']
            self.assertEqual(control['opportunities'], 3)
            self.assertEqual(control['installations'], 0)
            self.assertEqual(run['result']['stop_reason'], 'agent_declared_complete')
            self.assertEqual(len(run['programs']), 13)
            offers = run['saved']['rolling_offers_private']
            self.assertTrue(all(o['offer']['fresh_closed_turns'] >= 3 for o in offers))
            self.assertTrue(all(not d['accepted'] for d in control['decisions']))

    def test_unknown_second_summary_stops_before_next_action(self):
        for mode in ('unknown', 'transport_error'):
            run = fixture(policy='rolling_separate', summary_mode=('valid',mode),
                          actions=('echo',)*12+('finish',), api_limit=32)
            self.assertEqual(run['result']['unknown_usage_calls'], 1)
            self.assertEqual(run['result']['usage_by_role']['focus']['calls'], 2)
            self.assertEqual(run['result']['usage_by_role']['focus']['unknown_usage'], 1)
            self.assertEqual(run['captured'][-1]['role'], 'focus')
            self.assertEqual(run['result']['model_calls'], len(run['captured']))
            self.assertEqual(run['result']['api_requests'], len(run['programs']))
            self.assertFalse(run['result']['declared_complete'])

    def test_unknown_inline_actor_cannot_execute_offered_action(self):
        for action in ('unknown', 'transport_error'):
            run = fixture(actions=('echo',)*7+(action,), api_limit=32)
            self.assertEqual(run['result']['unknown_usage_calls'], 1)
            self.assertEqual(run['programs'], ['echo']*7)
            self.assertEqual(run['result']['model_calls'], 8)
            self.assertEqual(run['result']['checkpoint_control']['installations'], 1)

    def test_terminal_inline_offer_does_not_add_post_completion_count_or_generation(self):
        run = fixture(actions=('echo',)*3+('finish',))
        control = run['result']['checkpoint_control']
        self.assertEqual(run['result']['model_calls'], 4)
        self.assertTrue(control['valid_checkpoint_pending_without_next_request'])
        self.assertEqual(control['installations'], 0)
        self.assertTrue(all(c['after_model_calls'] < 4 for c in run['saved']['rolling_input_counts']))

    def test_stop_cache_API_and_cleanup_guards_still_apply(self):
        for options, reason, programs in (({'first_cached':1}, 'runtime_error', 0),
                ({'initial_mismatch':True}, 'setup_failure', 0),
                ({'stop_after_api':True}, 'user_stop', 1),
                ({'unknown_api':True}, 'runtime_error', 1),
                ({'cleanup_ok':False}, 'cleanup_error', 2),
                ({'count_delay':61}, 'wall_limit', 0)):
            with self.subTest(options=options):
                run = fixture(**options)
                self.assertEqual(run['result']['stop_reason'], reason)
                self.assertEqual(len(run['programs']), programs)


if __name__ == '__main__':
    unittest.main()
