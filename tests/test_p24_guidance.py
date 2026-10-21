import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import run_native_appworld as runner
import run_native_batch as batch
import test_p18_plan as fixture
from audit_native_boundaries import audit as audit_boundaries
from audit_native_execution import audit as audit_execution


class P24GuidanceControls(unittest.TestCase):
    def plan(self):
        return json.loads((ROOT/'configs/P24_generic_guidance_v01.json').read_text())

    def test_plan_rejects_changed_cohort_budget_and_unreviewed_guidance(self):
        plan = self.plan()
        batch.validate_schedule(plan)
        batch.check_p24_activation(plan)
        for key in ('task_ids', 'max_total_tokens', 'general_guidance_version', 'ordinary_compute'):
            value = copy.deepcopy(plan)
            if key == 'task_ids':
                value[key][0] = value['run_order'][0][0] = 'aa8502b_1'
            elif key == 'max_total_tokens':
                value[key] += 1
            elif key == 'ordinary_compute':
                value[key] = {'max_executions': 1}
            else:
                value[key] = 'different'
            with self.assertRaises(ValueError):
                batch.validate_schedule(value)
                batch.check_p24_activation(value)

    def test_legacy_prompt_does_not_silently_change(self):
        self.assertEqual(runner.system_prompt_for({'phase': 'P22'}), runner.NATIVE_PROMPT)
        with self.assertRaises(ValueError):
            runner.system_prompt_for({'phase': 'P22', 'general_guidance_version': 'appworld_public_rules_v1'})
        self.assertEqual(runner.system_prompt_for(self.plan()), runner.NATIVE_PROMPT + runner.GENERAL_GUIDANCE)

    def test_only_system_instruction_changes_and_audits_detect_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            helper = fixture.P18Controls()
            old, old_sent, old_requests = helper.run_fixture(root/'old', 'P22')
            new, new_sent, new_requests = helper.run_fixture(root/'new', 'P24', config_updates={
                'arms': ['native_guided'], 'general_guidance_version': 'appworld_public_rules_v1'})
            self.assertEqual(old_sent, new_sent)
            self.assertEqual(len(old_requests), len(new_requests))
            for old_r, new_r in zip(old_requests, new_requests, strict=True):
                self.assertEqual(old_r[0], new_r[0])
                self.assertEqual(old_r[2], new_r[2])
                self.assertEqual(old_r[1][1:], new_r[1][1:])
                self.assertEqual(new_r[1][0]['content'], old_r[1][0]['content']+runner.GENERAL_GUIDANCE)
            for key in ('model_calls', 'api_requests', 'boundary_records', 'stop_reason'):
                self.assertEqual(old[key], new[key], key)
            trial = root/'new/storage/records/context_pilot/P24_FIXTURE'
            checked = audit_boundaries(trial, root/'new/world')
            self.assertEqual(checked['audit_errors'], [])
            execution = audit_execution(trial)
            self.assertEqual(execution['audit_errors'], [])
            self.assertEqual(execution['dispatch_audit_errors'], [])
            self.assertEqual(execution['history_audit_errors'], [])
            request = trial/'call_001/request.json'
            payload = json.loads(request.read_text())
            payload['messages'][0]['content'] = runner.NATIVE_PROMPT
            request.write_text(json.dumps(payload))
            self.assertTrue(audit_execution(trial)['history_audit_errors'])

    def test_progress_targets_own_issue_without_private_text(self):
        self.assertEqual(batch.PHASES['P24']['issue'], 115)
        body = batch.public_body([{'task_number': 1, 'status': 'running', 'instruction': 'PRIVATE'}],
                                 {'status': 'running', 'phase': 'P24'})
        self.assertNotIn('PRIVATE', body)
        self.assertIn('一般指示', body)


if __name__ == '__main__':
    unittest.main()
