"""Guard unknown-use isolation, whole-cohort selection and multi-task routing."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from public_completion_scope import fixed_cases, verify_complete_selection, verify_source_usage


class PublicCompletionScopeTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((ROOT / 'configs/P72_public_completion_scope_v01.json').read_text())
        self.audit = json.loads((ROOT / 'reports/P71_comparison.json').read_text())
        self.summary = {'model_calls': 2, 'unknown_usage_calls': 1, 'unknown_effect_requests': 0,
                        'stop_reason': 'wall_limit_during_model_call',
                        'setup': {'status': 'matched_observable_prefix'}}
        self.usage = [{'id': 'call_001', 'status': 'ok', 'input_tokens': 10, 'output_tokens': 3},
                      {'id': 'call_002', 'status': 'error', 'input_tokens': None, 'output_tokens': None}]
        self.events = [{'call': 'call_001', 'effects_unknown': False}]

    def test_all_uncompleted_sources_have_two_task_correct_cases(self):
        verify_complete_selection(self.audit, self.plan)
        cases = fixed_cases(self.plan)
        self.assertEqual(len(cases), 14)
        for source in self.plan['source_runs']:
            pair = [c for c in cases if c['source_run'] == source]
            self.assertEqual([c['arm'] for c in pair], self.plan['arms'])
            self.assertEqual({c['task_id'] for c in pair}, {self.plan['source_task_ids'][source]})
        self.assertEqual(len({c['task_id'] for c in cases}), 3)

    def test_selection_never_filters_on_official_success(self):
        for row in self.audit['rows']:
            row['success'] = not row['success']
        verify_complete_selection(self.audit, self.plan)

    def test_missing_source_or_added_uncompleted_source_stops(self):
        self.audit['rows'][0]['sent_api_names']['supervisor__complete_task'] = 0
        with self.assertRaises(ValueError): verify_complete_selection(self.audit, self.plan)
        with self.assertRaises(ValueError): fixed_cases({**self.plan, 'source_runs': self.plan['source_runs'][:-1]})

    def test_task_exchange_or_budget_extension_is_rejected(self):
        altered = copy.deepcopy(self.plan)
        altered['source_task_ids'][self.plan['source_runs'][0]] = 'different_task'
        with self.assertRaises(ValueError): fixed_cases(altered)
        with self.assertRaises(ValueError): fixed_cases({**self.plan, 'max_cases': 16})
        with self.assertRaises(ValueError): fixed_cases({**self.plan, 'max_batch_seconds': 1801})

    def test_unknown_unexecuted_terminal_usage_is_preserved(self):
        before = copy.deepcopy(self.usage)
        self.assertEqual(verify_source_usage(self.summary, self.usage, self.events), 1)
        self.assertEqual(self.usage, before)

    def test_unknown_api_effects_prohibit_replay(self):
        with self.assertRaises(ValueError):
            verify_source_usage({**self.summary, 'unknown_effect_requests': 1}, self.usage, self.events)
        with self.assertRaises(ValueError):
            verify_source_usage(self.summary, self.usage, [{'call': 'call_001', 'effects_unknown': True}])

    def test_executed_or_retried_unknown_generation_is_rejected(self):
        with self.assertRaises(ValueError):
            verify_source_usage(self.summary, self.usage, self.events + [{'call': 'call_002', 'effects_unknown': False}])
        extra = {'id': 'call_003', 'status': 'ok', 'input_tokens': 5, 'output_tokens': 2}
        with self.assertRaises(ValueError):
            verify_source_usage({**self.summary, 'model_calls': 3}, self.usage + [extra], self.events)

    def test_zero_imputation_or_wrong_unknown_count_is_rejected(self):
        bad = copy.deepcopy(self.usage); bad[-1]['input_tokens'] = 0
        with self.assertRaises(ValueError): verify_source_usage(self.summary, bad, self.events)
        with self.assertRaises(ValueError):
            verify_source_usage({**self.summary, 'unknown_usage_calls': 0}, self.usage, self.events)


if __name__ == '__main__': unittest.main()
