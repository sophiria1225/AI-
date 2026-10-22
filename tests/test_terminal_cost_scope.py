import unittest

from inspect_terminal_cost_scope import classify, cost, mutation_tail


def call(name, categories=None, tokens=20, cached=12):
    return {'call_id': name, 'sent_categories': categories or {},
        'known_total_tokens': tokens, 'input_tokens': tokens - 3 if tokens is not None else None,
        'output_tokens': 3 if tokens is not None else None,
        'cached_input_tokens': cached if tokens is not None else None,
        'model_request_wall_seconds': 0.1, 'sent_api_requests': sum((categories or {}).values())}


class TerminalCostScopeTests(unittest.TestCase):
    def test_unknown_usage_is_retained_and_cached_input_counts_in_primary_cost(self):
        summary = cost([call('known'), call('unknown', tokens=None)])
        self.assertEqual(summary['known_total_tokens'], 20)
        self.assertEqual(summary['known_uncached_input_plus_output_tokens'], 8)
        self.assertEqual(summary['unknown_usage_calls'], 1)

    def test_no_mutation_is_missing_boundary_not_all_calls_as_savings(self):
        result = mutation_tail([call('read', {'information_request': 1})])
        self.assertIsNone(result['boundary_call'])
        self.assertIsNone(result['cost_after_boundary'])

    def test_late_write_moves_boundary_and_does_not_certify_early_completion(self):
        result = mutation_tail([call('write1', {'task_mutation_request': 1}),
            call('check', {'information_request': 1}),
            call('write2', {'task_mutation_request': 1}), call('local')])
        self.assertEqual(result['boundary_call'], 'write2')
        self.assertEqual(result['cost_after_boundary']['model_calls'], 1)
        self.assertFalse(result['is_completion_or_safely_removable_boundary'])

    def test_new_api_cannot_be_silently_treated_as_read_only(self):
        with self.assertRaisesRegex(ValueError, 'unclassified'):
            classify('file_system__unreviewed_operation')


if __name__ == '__main__':
    unittest.main()
