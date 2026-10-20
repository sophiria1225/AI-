"""Detect accidental changes in budget, sampling or verification conditions."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_p2_comparability import ALLOWED_CHANGES, compare_configs


class ComparisonControls(unittest.TestCase):
    def setUp(self):
        self.baseline = json.loads((ROOT / 'configs/P2_minimax_15380.json').read_text())
        self.candidate = json.loads((ROOT / 'configs/P2_minimax_iq4kv8_15380.json').read_text())
        self.runtime_allowed = ALLOWED_CHANGES | {
            'scope', 'version', 'cache_type_k', 'cache_type_v'}

    def test_q8_candidate_requires_explicitly_wider_comparison_scope(self):
        ordinary = compare_configs(self.baseline, self.candidate)
        self.assertIn('cache_type_k', ordinary['unexpected_changed_fields'])
        result = compare_configs(self.baseline, self.candidate, self.runtime_allowed)
        self.assertEqual(result['unexpected_changed_fields'], [])
        self.assertTrue(result['identical_agent_templates'])

    def test_budget_sampling_and_visible_checks_are_not_exempt(self):
        for field, value in [('max_total_tokens', 400000), ('temperature', 0.5),
                             ('visible_checks', [])]:
            with self.subTest(field=field):
                changed = copy.deepcopy(self.candidate)
                changed[field] = value
                result = compare_configs(self.baseline, changed, self.runtime_allowed)
                self.assertIn(field, result['unexpected_changed_fields'])


if __name__ == '__main__':
    unittest.main()
