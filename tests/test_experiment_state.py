import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from experiment_state import SharedBudget, CompletionState, ProtocolStop


def response(input_count=100, output_count=20, **updates):
    return dict(status='ok', input_tokens=input_count, output_tokens=output_count,
                done_reason='tool_calls', cached_input_tokens=input_count) | updates


class SharedBudgetTests(unittest.TestCase):
    def make(self, **updates):
        return SharedBudget(**(dict(max_calls=4, max_total_tokens=400, num_ctx=1000,
                                   num_predict=100, max_wall_seconds=60) | updates))

    def test_workers_cannot_spend_separate_copies_of_global_budget(self):
        budget = self.make()
        for worker in ('implementation', 'validation'):
            self.assertIn('ALL units', budget.notice(1, worker))
            budget.begin_request(100, 1)
            budget.finish_request(response())
        self.assertEqual(budget.total_tokens, 240)  # Cached input is still included exactly once.
        with self.assertRaisesRegex(ProtocolStop, 'conservative_budget_guard'):
            budget.begin_request(100, 2)
        self.assertEqual(budget.calls, 2)

    def test_unknown_terminal_usage_prevents_further_spending(self):
        budget = self.make()
        budget.begin_request(100, 1)
        with self.assertRaisesRegex(ProtocolStop, 'usage_unknown'):
            budget.finish_request({'status': 'error', 'input_tokens': None, 'output_tokens': None})
        self.assertFalse(budget.usage_complete)
        self.assertEqual(budget.calls, 1)
        with self.assertRaisesRegex(ProtocolStop, 'usage_unknown'):
            budget.begin_request(100, 2)

    def test_truncated_completion_is_charged_but_must_not_execute(self):
        budget = self.make()
        budget.begin_request(100, 1)
        with self.assertRaisesRegex(ProtocolStop, 'generation_limit_incomplete_response'):
            budget.finish_request(response(output_count=100, done_reason='length'))
        self.assertEqual(budget.total_tokens, 200)
        self.assertTrue(budget.usage_complete)

    def test_counter_mismatch_preserves_actual_usage_and_stops(self):
        budget = self.make()
        budget.begin_request(100, 1)
        with self.assertRaisesRegex(ProtocolStop, 'input_counter_mismatch'):
            budget.finish_request(response(input_count=101))
        self.assertEqual(budget.total_tokens, 121)

    def test_backend_output_over_reserved_limit_is_charged_and_stopped(self):
        budget = self.make()
        budget.begin_request(100, 1)
        with self.assertRaisesRegex(ProtocolStop, 'output_limit_exceeded'):
            budget.finish_request(response(output_count=101))
        self.assertEqual(budget.total_tokens, 201)

    def test_pending_request_cannot_be_double_issued_or_double_charged(self):
        budget = self.make()
        budget.begin_request(100, 1)
        with self.assertRaisesRegex(ProtocolStop, 'request_already_pending'):
            budget.begin_request(100, 1)
        budget.finish_request(response())
        with self.assertRaisesRegex(ProtocolStop, 'no_pending_request'):
            budget.finish_request(response())
        self.assertEqual(budget.total_tokens, 120)

    def test_call_wall_and_context_limits_also_apply(self):
        budget = self.make(max_calls=1)
        budget.begin_request(100, 1)
        budget.finish_request(response())
        with self.assertRaisesRegex(ProtocolStop, 'call_limit'):
            budget.begin_request(100, 2)
        with self.assertRaisesRegex(ProtocolStop, 'wall_limit'):
            self.make().begin_request(100, 60)
        with self.assertRaisesRegex(ProtocolStop, 'conservative_budget_guard'):
            self.make(max_total_tokens=10000).begin_request(901, 1)


class CompletionStateTests(unittest.TestCase):
    def test_read_only_turn_preserves_vote_but_new_artifact_invalidates_it(self):
        state = CompletionState(('implementation', 'validation'), 'a'*64)
        state.vote('implementation', 'a'*64)
        self.assertFalse(state.observe_artifact('a'*64))
        self.assertIn('implementation', state.votes)
        self.assertTrue(state.observe_artifact('b'*64))
        state.vote('validation', 'b'*64)
        self.assertFalse(state.complete)
        with self.assertRaisesRegex(ProtocolStop, 'stale_completion_vote'):
            state.vote('implementation', 'a'*64)
        state.vote('implementation', 'b'*64)
        self.assertTrue(state.complete)

    def test_returning_to_old_content_does_not_resurrect_prior_vote(self):
        state = CompletionState(('implementation', 'validation'), 'a'*64)
        state.vote('implementation', 'a'*64)
        state.observe_artifact('b'*64)
        state.observe_artifact('a'*64)
        state.vote('validation', 'a'*64)
        self.assertFalse(state.complete)
        self.assertEqual(state.revision, 2)

    def test_single_unit_uses_the_same_completion_protocol(self):
        state = CompletionState(('single',), 'c'*64)
        self.assertFalse(state.complete)
        state.vote('single', 'c'*64)
        self.assertTrue(state.complete)


if __name__ == '__main__':
    unittest.main()
