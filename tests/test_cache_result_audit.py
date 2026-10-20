import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_prompt_cache_probe import check_call


class CacheResultAuditControls(unittest.TestCase):
    def setUp(self):
        self.request = {'messages': [{'role': 'user', 'content': 'private sample'}],
                        'cache_prompt': False, 'max_tokens': 1, 'seed': 42}
        self.response = {'status': 'ok', 'input_tokens': 100, 'output_tokens': 1,
                         'cached_input_tokens': 0, 'timings': {'cache_n': 0, 'prompt_n': 100}}

    def test_reused_warm_cache_and_inconsistent_partition_are_rejected(self):
        self.assertEqual(check_call(self.request, self.request, self.response, 'warm'), [])
        changed = copy.deepcopy(self.response)
        changed.update(cached_input_tokens=10, timings={'cache_n': 10, 'prompt_n': 90})
        self.assertEqual(check_call(self.request, self.request, changed, 'target'), [])
        self.assertTrue(check_call(self.request, self.request, changed, 'warm'))
        changed['timings']['prompt_n'] = 100
        self.assertTrue(check_call(self.request, self.request, changed, 'target'))

    def test_changes_and_unknown_cost_are_detected_without_echoing_payloads(self):
        changed = copy.deepcopy(self.request); changed['seed'] = 43
        errors = check_call(self.request, changed, self.response, 'warm')
        self.assertTrue(errors); self.assertNotIn('private sample', str(errors))
        unknown = {'status': 'error', 'input_tokens': None, 'output_tokens': None}
        self.assertIn('terminal usage is unknown', check_call(self.request, self.request, unknown, 'target'))


if __name__ == '__main__':
    unittest.main()
