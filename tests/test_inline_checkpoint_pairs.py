from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_inline_checkpoint_pairs import TASKS, POLICIES, compare, pre_intervention_requests


def rows():
    result = []
    for task in TASKS:
        for policy in POLICIES:
            separate = policy == 'single_checkpoint'
            roles = {'agent': {'calls': 4, 'unknown_usage': 0,
                              'input_tokens': 800 if separate else 950, 'output_tokens': 100},
                     'focus': {'calls': int(separate), 'unknown_usage': 0,
                               'input_tokens': 180 if separate else 0, 'output_tokens': 20 if separate else 0}}
            controls = [{'status': 'checkpoint_installed', 'after_model_calls': 2,
                         'model_attempted': True, 'ordinary_next_input_tokens': 700,
                         'checkpoint_next_input_tokens': 100}] if separate else [
                {'status': 'inline_offered', 'after_model_calls': 2},
                {'status': 'checkpoint_decided', 'after_model_calls': 3,
                 'ordinary_input_tokens': 900, 'compacted_input_tokens': 200, 'accepted': True}]
            result.append({'task_id': task, 'checkpoint_policy': policy,
                'record_status': 'evaluated', 'success': True, 'usage_by_role': roles,
                'model_calls': 4 + int(separate), 'unknown_usage_calls': 0,
                'known_total_tokens': 1100 if separate else 1050,
                'checkpoint_installed': True, 'checkpoint_controls': controls,
                'request_checks': [{'role': 'agent', 'request_sha256': char * 64,
                    'inline_offered': not separate and i == 2,
                    'response_sha256': ('0' if separate else '1') * 64}
                    for i, char in enumerate(('a', 'b', 'c' if separate else 'd', 'e'))]})
    return result


class InlineCheckpointPairTests(unittest.TestCase):
    def test_removed_summary_cost_does_not_hide_larger_agent_cost_including_metadata(self):
        for pair in compare(rows()):
            self.assertEqual(pair['agent_including_inline_metadata_token_difference'], 150)
            self.assertEqual(pair['separate_summary_exact_tokens'], 200)
            self.assertEqual(pair['inline_minus_separate_whole_task_tokens'], -50)
            self.assertEqual(pair['immediate_counted_inputs']['inline_checkpoint']['difference'], 700)
            self.assertTrue(pair['summary_input_is_not_measured_savings'])

    def test_unknown_summary_or_unrun_comparator_is_not_zero_cost(self):
        data = rows()
        data[0]['usage_by_role']['focus'].update(unknown_usage=1, input_tokens=0, output_tokens=0)
        data[0].update(known_total_tokens=900, unknown_usage_calls=1)
        pair = compare(data)[0]
        self.assertEqual(pair['agent_including_inline_metadata_token_difference'], 150)
        self.assertIsNone(pair['separate_summary_exact_tokens'])
        self.assertIsNone(pair['inline_minus_separate_whole_task_tokens'])
        data[1] = {'task_id': data[1]['task_id'], 'checkpoint_policy': 'inline_checkpoint',
                   'record_status': 'not_run', 'success': None}
        self.assertIsNone(compare(data)[0]['inline_cost']['known_subtotal'])
        self.assertFalse(compare(data)[0]['pre_intervention_request_comparison']['available'])
        with self.assertRaises(ValueError): compare(data[:-1])

    def test_hash_comparison_stops_at_earliest_actual_intervention_and_ignores_responses(self):
        separate, inline = rows()[:2]
        result = pre_intervention_requests(separate, inline)
        self.assertEqual(result['planned_positions'], 2)
        self.assertEqual(result['equal_request_files'], 2)
        self.assertFalse(result['response_file_hashes_used_as_behavior_labels'])
        separate['checkpoint_controls'][0]['after_model_calls'] = 1
        self.assertEqual(pre_intervention_requests(separate, inline)['planned_positions'], 1)
        separate['checkpoint_controls'] = []
        self.assertEqual(pre_intervention_requests(separate, inline)['planned_positions'], 2)

    def test_unattempted_interventions_do_not_invent_a_dispatched_boundary(self):
        separate, inline = deepcopy(rows()[:2])
        separate['checkpoint_controls'][0]['model_attempted'] = False
        for call in inline['request_checks']: call['inline_offered'] = False
        result = pre_intervention_requests(separate, inline)
        self.assertEqual(result['planned_positions'], 4)
        self.assertEqual(result['first_different_request_ordinal'], 3)
        inline['request_checks'][0]['request_sha256'] = None
        self.assertEqual(pre_intervention_requests(separate, inline)['unavailable_positions'], 1)


if __name__ == '__main__':
    unittest.main()
