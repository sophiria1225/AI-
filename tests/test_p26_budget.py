import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import run_native_batch as batch
from audit_native_execution import audit as execution_audit
from audit_native_boundaries import audit as boundary_audit
import test_p18_plan as fixture


class P26Budget(unittest.TestCase):
    def test_only_declared_budget_and_known_case_can_change(self):
        plan = json.loads((ROOT/'configs/P26_photo_budget_v01.json').read_text())
        batch.validate_schedule(plan)
        batch.check_p26_activation(plan)
        for key, value in [('max_api_requests', 320), ('max_wall_seconds', 3600),
                           ('seed', 43), ('task_ids', ['aa8502b_1']),
                           ('ordinary_compute', {}), ('general_guidance_version', 'changed')]:
            changed = copy.deepcopy(plan)
            changed[key] = value
            with self.assertRaises(ValueError):
                batch.check_p26_activation(changed)

    def test_ceiling_does_not_change_pre_ceiling_inputs_or_actions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            helper = fixture.P18Controls()
            shared = dict(arms=['native_guided'], general_guidance_version='appworld_public_rules_v1')
            old, old_sent, old_requests = helper.run_fixture(root/'old', 'P25',
                config_updates=dict(shared, max_api_requests=80))
            new, new_sent, new_requests = helper.run_fixture(root/'new', 'P26',
                config_updates=dict(shared, max_api_requests=160))
            self.assertEqual(old_sent, new_sent)
            self.assertEqual(old_requests, new_requests)
            self.assertEqual(old['api_requests'], new['api_requests'])
            trial = root/'new/storage/records/context_pilot/P26_FIXTURE'
            self.assertEqual(boundary_audit(trial, root/'new/world')['audit_errors'], [])
            report = execution_audit(trial)
            for key in ('audit_errors', 'dispatch_audit_errors', 'history_audit_errors'):
                self.assertEqual(report[key], [])

    def test_public_progress_reports_changed_ceiling(self):
        body = batch.public_body([dict(task_number=1, status='running', instruction='PRIVATE')],
                                 dict(status='running', phase='P26'))
        self.assertIn('160 API', body)
        self.assertNotIn('PRIVATE', body)
        self.assertEqual(batch.PHASES['P26']['issue'], 128)
