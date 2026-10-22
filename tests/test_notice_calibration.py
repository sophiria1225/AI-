import copy
import json
from pathlib import Path
import unittest

from notice_calibration import compare, message_hash, requests


PLAN = json.loads((Path(__file__).resolve().parents[1] / 'configs/P58_notice_calibration_v01.json').read_text())


def originals():
    left = {'cache_prompt': True, 'stream': False, 'seed': 51, 'max_tokens': 4096,
        'messages': [{'role': 'assistant', 'tool_calls': [{'id': 'old_a', 'function': {'name': 'x'}}]},
            {'role': 'tool', 'tool_call_id': 'old_a', 'content': 'same'},
            {'role': 'user', 'content': '<harness_residual_budget_v1>\n{"wall_seconds_at_snapshot":335}\n</harness_residual_budget_v1>'}]}
    right = copy.deepcopy(left)
    right['messages'][0]['tool_calls'][0]['id'] = 'old_b'
    right['messages'][1]['tool_call_id'] = 'old_b'
    right['messages'][-1]['content'] = right['messages'][-1]['content'].replace('335', '336')
    return [left, right]


class NoticeCalibrationTests(unittest.TestCase):
    def test_only_clock_literal_differs_and_transport_ids_are_shared(self):
        source = originals(); before = copy.deepcopy(source)
        variants = requests(source, PLAN)
        self.assertEqual(source, before)
        self.assertFalse(variants[335]['cache_prompt'])
        expected = copy.deepcopy(variants[335])
        expected['messages'][-1]['content'] = expected['messages'][-1]['content'].replace('335', '336')
        self.assertEqual(expected, variants[336])

    def test_changed_nonclock_content_or_generation_setting_is_rejected(self):
        for modify in (lambda x: x[1]['messages'][1].update(content='different'),
                       lambda x: x[1].update(seed=52)):
            values = originals(); modify(values)
            with self.assertRaises(ValueError): requests(values, PLAN)

    def test_no_extra_repeats_or_budget_extension(self):
        for key, value in [('max_calls', 5), ('max_total_tokens', 200000), ('max_wall_seconds', 2400)]:
            plan = {**PLAN, key: value}
            with self.assertRaises(ValueError): requests(originals(), plan)

    def test_within_condition_variation_blocks_one_field_attribution(self):
        rows = [{'wall_snapshot_seconds': s, 'status': 'ok', 'cache_confirmed': True, 'message_sha256': h}
                for s, h in zip(PLAN['schedule'], ['A', 'B', 'B', 'C'])]
        result = compare(rows)
        self.assertFalse(result['within_literal_repeats_equal']['335'])
        self.assertIsNone(result['local_sensitivity_observed'])
        rows[-1]['status'] = 'not_run'
        self.assertFalse(compare(rows)['all_four_confirmed'])

    def test_stable_different_messages_are_only_local_sensitivity(self):
        rows = [{'wall_snapshot_seconds': s, 'status': 'ok', 'cache_confirmed': True, 'message_sha256': str(s)}
                for s in PLAN['schedule']]
        result = compare(rows)
        self.assertTrue(result['local_sensitivity_observed'])
        self.assertFalse(result['historical_P55_cause_identified'])
        self.assertFalse(result['task_quality_effect_measured'])

    def test_message_equality_retains_reasoning_and_arguments(self):
        a = {'role': 'assistant', 'reasoning_content': 'first', 'tool_calls':
             [{'id': 'one', 'function': {'name': 'execute_code', 'arguments': '{"code":"x"}'}}]}
        b = copy.deepcopy(a); b['tool_calls'][0]['id'] = 'two'
        self.assertEqual(message_hash(a), message_hash(b))
        b['reasoning_content'] = 'second'
        self.assertNotEqual(message_hash(a), message_hash(b))


if __name__ == '__main__':
    unittest.main()
