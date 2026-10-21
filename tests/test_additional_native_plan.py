import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from run_native_batch import validate_schedule, public_body


class AdditionalNativePlanControls(unittest.TestCase):
    def test_memory_comparisons_preserve_all_tasks_budgets_and_api_access(self):
        previous = json.loads((ROOT / 'configs/P11_additional_baseline_v01.json').read_text())
        for filename, prerequisite in [('P12_recent_window_v01.json', 'P11_batch_v01'),
                                       ('P13_native_focus_v01.json', 'P12_batch_v01'),
                                       ('P14_native_ledger_v01.json', 'P13_recovery_v01')]:
            actual = json.loads((ROOT / 'configs' / filename).read_text())
            validate_schedule(actual)
            for key in ('task_ids', 'appworld_version', 'model_selection', 'model', 'seed',
                        'agent_temperature', 'max_calls', 'max_api_requests', 'max_total_tokens',
                        'max_wall_seconds', 'max_output_tokens', 'observation_page_characters',
                        'discovery_policy', 'max_checkpoint_object_bytes',
                        'max_checkpoint_new_bytes_per_boundary', 'source_selection_sha256'):
                self.assertEqual(previous[key], actual[key], (filename, key))
            self.assertEqual(actual['wait_for_native_batch'], prerequisite)
            if filename == 'P14_native_ledger_v01.json':
                recovery = json.loads((ROOT / 'configs/P13_recovery_v01.json').read_text())
                original = json.loads((ROOT / 'configs/P13_native_focus_v01.json').read_text())
                self.assertEqual([row[:2] for row in recovery['cohort']],
                                 [row[:2] for row in original['run_order']])
                self.assertEqual(recovery['cohort'][:2], original['run_order'][:2])
                self.assertEqual(recovery['cohort'][3], original['run_order'][3])
                self.assertEqual(recovery['cohort'][2][2], 'P13_03_FOCUS_RECOVERY01')
            self.assertEqual(actual['history_budget_tokens'], 4096)
            import hashlib
            self.assertEqual(actual['source_comparison_plan_sha256'], hashlib.sha256(
                (ROOT / 'configs/P11_additional_baseline_v01.json').read_bytes()).hexdigest())

    def test_execution_budget_and_interface_match_the_selected_baseline(self):
        previous = json.loads((ROOT / 'configs/P10_native_history_v01.json').read_text())
        actual = json.loads((ROOT / 'configs/P11_additional_baseline_v01.json').read_text())
        validate_schedule(actual)
        for key in ('appworld_version', 'model_selection', 'model', 'seed', 'agent_temperature',
                    'max_calls', 'max_api_requests', 'max_total_tokens', 'max_wall_seconds',
                    'max_output_tokens', 'observation_page_characters', 'discovery_policy',
                    'history_representation'):
            self.assertEqual(previous[key], actual[key], key)
        self.assertEqual(actual['wait_for_native_batch'], 'P10_batch_v01')
        self.assertEqual(actual['max_checkpoint_object_bytes'], 512 * 1024**2)

    def plan(self):
        chosen = json.loads((ROOT / 'reports/P11_public_task_selection.json').read_text())
        ids = [row['task_id'] for row in chosen['selected']]
        return {'phase': 'P11', 'batch_id': 'P11_batch_v01', 'task_ids': ids,
                'arms': ['native_roles'], 'run_order': [
                    [task, 'native_roles', f'P11_{i:02d}_ROLES'] for i, task in enumerate(ids, 1)]}

    def test_selected_order_cannot_be_replaced_or_repeated(self):
        plan = self.plan()
        validate_schedule(plan)
        for kind in ('replace', 'reorder', 'same_run', 'extra'):
            altered = copy.deepcopy(plan)
            if kind == 'replace':
                altered['task_ids'][0] = altered['run_order'][0][0] = '07b42fd_1'
            elif kind == 'reorder':
                altered['run_order'].reverse()
            elif kind == 'same_run':
                altered['run_order'][1][2] = altered['run_order'][0][2]
            else:
                altered['run_order'].append(altered['run_order'][0])
            with self.assertRaises(ValueError):
                validate_schedule(altered)

    def test_four_trial_progress_stays_in_the_dedicated_issue_scope(self):
        body = public_body([{'task_number': 1, 'status': 'evaluated', 'success': False,
                             'instruction': 'PRIVATE_INSTRUCTION'}],
                           {'status': 'complete', 'phase': 'P11'})
        self.assertIn('4試行', body)
        self.assertIn('P11_batch_v01', body)
        self.assertIn('| 未達 |', body)
        self.assertNotIn('PRIVATE_INSTRUCTION', body)


if __name__ == '__main__':
    unittest.main()
