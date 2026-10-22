import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from decompose_continuation_cost import contrast, describe


def fixture(inputs, outputs, arm='full_keep'):
    calls = [{'call_id': f'call_{i:03d}', 'status': 'ok', 'input_tokens': x,
              'output_tokens': y} for i, (x, y) in enumerate(zip(inputs, outputs, strict=True))]
    return {'task_id': 'task', 'run_id': arm, 'arm': arm, 'calls': calls,
            'totals': {'calls': len(calls), 'unknown_usage_calls': 0,
                       'input_tokens': sum(inputs), 'output_tokens': sum(outputs),
                       'known_total_tokens': sum(inputs) + sum(outputs)}}


class ContinuationCostTests(unittest.TestCase):
    def test_shorter_input_can_have_higher_total_without_claiming_a_cause(self):
        a = fixture([100, 150], [10, 10])
        b = fixture([50, 100, 150], [10, 10, 10], 'stdout_mask_keep')
        original = copy.deepcopy((a, b))
        result = contrast(a, b)
        self.assertEqual(result['exact_total_token_change'], 60)
        self.assertEqual(result['components'], {'initial_input_size': -125,
            'number_of_calls': 75, 'later_input_growth': 100, 'output_tokens': 10})
        self.assertFalse(result['causal_components'])
        self.assertEqual((a, b), original)

    def test_unknown_usage_prevents_an_exact_saving_claim(self):
        a = fixture([100], [10]); b = fixture([50], [10], 'stdout_mask_keep')
        b['calls'].append({'call_id': 'call_001', 'status': 'error',
                           'input_tokens': None, 'output_tokens': None})
        b['totals'].update(calls=2, unknown_usage_calls=1)
        result = contrast(a, b)
        self.assertIsNone(result['components'])
        self.assertIsNone(result['exact_total_token_change'])
        self.assertEqual(result['candidate']['unknown_usage_calls'], 1)

    def test_shortening_during_a_trace_is_not_forced_positive(self):
        row = fixture([100, 60], [1, 1])
        self.assertEqual(describe(row)['decomposition']['later_input_growth_tokens'], -40)
        result = contrast(row, fixture([50], [1], 'stdout_mask_keep'))
        self.assertEqual(sum(result['components'].values()), -111)

    def test_task_and_usage_mismatches_are_rejected(self):
        a = fixture([100], [10]); b = fixture([50], [10])
        b['task_id'] = 'different'
        with self.assertRaisesRegex(ValueError, 'task differs'): contrast(a, b)
        for key in ('calls', 'input_tokens', 'known_total_tokens', 'unknown_usage_calls'):
            broken = copy.deepcopy(a); broken['totals'][key] += 1
            with self.assertRaises(ValueError): describe(broken)


if __name__ == '__main__': unittest.main()
