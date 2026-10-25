from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_checkpoint_pair_controls import TASKS, POLICIES, compare, pre_summary_requests


def rows():
    result = []
    for task in TASKS:
        for policy in POLICIES:
            summary = policy == 'single_checkpoint'
            roles = {'agent': {'calls': 3, 'unknown_usage': 0,
                              'input_tokens': 800 if summary else 900, 'output_tokens': 100},
                     'focus': {'calls': int(summary), 'unknown_usage': 0,
                               'input_tokens': 180 if summary else 0, 'output_tokens': 20 if summary else 0}}
            controls = [{'status': 'checkpoint_installed', 'after_model_calls': 2,
                         'model_attempted': True, 'ordinary_next_input_tokens': 700,
                         'checkpoint_next_input_tokens': 100}] if summary else []
            result.append({'task_id': task, 'checkpoint_policy': policy,
                'record_status': 'evaluated', 'success': True, 'usage_by_role': roles,
                'model_calls': 3 + int(summary), 'unknown_usage_calls': 0,
                'known_total_tokens': 1100 if summary else 1000,
                'checkpoint_installed': summary, 'checkpoint_controls': controls,
                'request_checks': [{'role': 'agent', 'request_sha256': char * 64,
                                    'response_sha256': ('0' if summary else '1') * 64}
                                   for char in ('a', 'b', 'd' if summary else 'c')]})
    return result


class CheckpointPairControlsTests(unittest.TestCase):
    def test_agent_and_immediate_input_savings_do_not_hide_summary_cost(self):
        pairs = compare(rows())
        self.assertEqual(len(pairs), 4)
        for pair in pairs:
            self.assertEqual(pair['agent_token_difference'], -100)
            self.assertEqual(pair['summary_exact_tokens'], 200)
            self.assertEqual(pair['whole_task_token_difference'], 100)
            self.assertEqual(pair['immediate_counted_input_reduction'], 600)

    def test_unknown_and_unrun_are_not_zero_cost_comparators(self):
        values = rows()
        values[1]['usage_by_role']['focus'].update(unknown_usage=1, input_tokens=0, output_tokens=0)
        values[1].update(unknown_usage_calls=1, known_total_tokens=900)
        pair = compare(values)[0]
        self.assertEqual(pair['checkpoint_cost']['known_subtotal'], 900)
        self.assertIsNone(pair['checkpoint_cost']['exact_total'])
        self.assertIsNone(pair['whole_task_token_difference'])
        self.assertIsNone(pair['summary_exact_tokens'])
        values[0] = {k: values[0][k] for k in ('task_id', 'checkpoint_policy')}
        values[0].update(record_status='not_run', success=None)
        pair = compare(values)[0]
        self.assertIsNone(pair['full_cost']['known_subtotal'])
        self.assertFalse(pair['pre_summary_request_comparison']['available'])
        with self.assertRaises(ValueError):
            compare(values[:-1])

    def test_hash_comparison_stops_before_summary_and_ignores_response_files(self):
        full, checkpoint = rows()[:2]
        result = pre_summary_requests(full, checkpoint)
        self.assertEqual(result['planned_positions'], 2)
        self.assertEqual(result['equal_request_files'], 2)
        self.assertIsNone(result['first_different_request_ordinal'])
        self.assertFalse(result['response_file_hashes_used_as_behavior_labels'])
        checkpoint['request_checks'][1]['request_sha256'] = 'e' * 64
        self.assertEqual(pre_summary_requests(full, checkpoint)['first_different_request_ordinal'], 2)
        full['request_checks'][1]['request_sha256'] = None
        self.assertEqual(pre_summary_requests(full, checkpoint)['unavailable_positions'], 1)

    def test_unattempted_summary_does_not_create_an_intervention_boundary(self):
        full, checkpoint = deepcopy(rows()[:2])
        checkpoint['checkpoint_controls'] = [{'status': 'insufficient_shared_token_budget',
                                             'after_model_calls': 2, 'model_attempted': False}]
        result = pre_summary_requests(full, checkpoint)
        self.assertFalse(result['summary_was_attempted'])
        self.assertEqual(result['planned_positions'], 3)
        self.assertEqual(result['first_different_request_ordinal'], 3)


if __name__ == '__main__':
    unittest.main()
