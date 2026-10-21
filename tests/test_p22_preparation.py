import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import run_native_batch as batch
import test_p18_plan as fixture
from audit_native_boundaries import audit as audit_boundaries


class P22PreparationControls(unittest.TestCase):
    def plan(self):
        selection = json.loads((ROOT/'reports/P22_public_task_selection.json').read_text())
        ids = [r['task_id'] for r in selection['selected']]
        return {'phase': 'P22', 'batch_id': 'P22_batch_v01', 'task_ids': ids,
                'arms': ['native_roles'], 'run_order': [
                    [task, 'native_roles', f'P22_{i:02d}_ROLES'] for i, task in enumerate(ids, 1)]}

    def test_six_tasks_cannot_be_replaced_by_confirmation_or_reordered(self):
        plan = self.plan()
        batch.validate_schedule(plan)
        for kind in ('reserved', 'reordered', 'duplicate', 'extra'):
            value = copy.deepcopy(plan)
            if kind == 'reserved':
                value['task_ids'][0] = value['run_order'][0][0] = 'aa8502b_1'
            elif kind == 'reordered':
                value['run_order'].reverse()
            elif kind == 'duplicate':
                value['run_order'][1][2] = value['run_order'][0][2]
            else:
                value['run_order'].append(value['run_order'][0])
            with self.assertRaises(ValueError):
                batch.validate_schedule(value)

    def test_activation_requires_completed_primary_review_and_decision(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'reports').mkdir()
            result = root/'reports/P21_export_diagnostic_summary.json'
            decision = root/'reports/P22_activation_v01.json'
            with patch.object(batch, 'ROOT', root):
                with self.assertRaises(FileNotFoundError):
                    batch.check_p22_activation(self.plan())
                result.write_text(json.dumps({'phase': 'P21', 'model_calls': 6, 'audit_errors': []}))
                record = {'decision': 'run_six_full_history_development_tasks',
                          'why': 'fixture', 'alternatives': 'fixture',
                          'p21_primary_sha256': hashlib.sha256(result.read_bytes()).hexdigest()}
                decision.write_text(json.dumps(record))
                batch.check_p22_activation(self.plan())
                result.write_text(json.dumps({'phase': 'P21', 'model_calls': 5, 'audit_errors': []}))
                with self.assertRaises(ValueError):
                    batch.check_p22_activation(self.plan())
                record['p21_primary_sha256'] = hashlib.sha256(result.read_bytes()).hexdigest()
                decision.write_text(json.dumps(record))
                with self.assertRaises(ValueError):
                    batch.check_p22_activation(self.plan())

    def test_native_execution_messages_and_costs_match_original_baseline(self):
        helper = fixture.P18Controls()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = helper.run_fixture(root/'original', 'P11')
            prepared = helper.run_fixture(root/'prepared', 'P22')
            self.assertEqual(original[1:], prepared[1:])
            for key in ('known_total_tokens', 'model_calls', 'api_requests', 'boundary_records', 'stop_reason'):
                self.assertEqual(original[0][key], prepared[0][key], key)
            self.assertEqual(prepared[0]['boundary_records'], 3)
            self.assertEqual(prepared[0]['known_total_tokens'], 22)
            checked = audit_boundaries(root/'prepared/storage/records/context_pilot/P22_FIXTURE',
                                       root/'prepared/world')
            self.assertEqual(checked['audit_errors'], [])
            self.assertTrue(checked['final_db_files_match'])

    def test_public_progress_excludes_instruction_and_uses_matching_issue(self):
        body = batch.public_body([{'task_number': 1, 'status': 'evaluated', 'success': True,
                                   'instruction': 'DO_NOT_PUBLISH'}],
                                 {'status': 'complete', 'phase': 'P22'})
        self.assertEqual(batch.PHASES['P22']['issue'], 102)
        self.assertIn('6試行', body)
        self.assertNotIn('DO_NOT_PUBLISH', body)


if __name__ == '__main__':
    unittest.main()
