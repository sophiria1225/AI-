"""Native input matching and finite activation, using only synthetic counts."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_whole_task_projection as driver
from whole_task_projection import fixed_fields, validate_plan

ROOT = Path(__file__).resolve().parents[1]


def synthetic_plan():
    previous = json.loads((ROOT / 'configs/P118_whole_task_single_checkpoint_v01.json').read_text())
    plan = fixed_fields()
    plan.update(known_tasks=previous['known_tasks'], source_sha256=deepcopy(previous['source_sha256']))
    for name in ('scripts/automatic_field_projection.py', 'scripts/automatic_projection_runtime.py',
                 'scripts/compact_api_receipts.py', 'scripts/single_checkpoint_inference.py',
                 'docs/experiments/P125_whole_task_projection.md',
                 'reports/P124_projection_replay.json', 'reports/P123_comparison.json',
                 'reports/P123_server_session.json'):
        plan['source_sha256'][name] = 'a' * 64
    return plan


class ProjectionPreflightTests(unittest.TestCase):
    def exercise(self, mismatch=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'root'; root.mkdir(); (root / 'reports').mkdir()
            storage = Path(tmp) / 'storage'; storage.mkdir()
            plan = synthetic_plan()
            original = json.loads((ROOT / 'configs/P29_stateful_code_v01.json').read_text())
            prepared = [{**item, 'public_task': {'instruction': 'Synthetic task only.'}}
                        for item in plan['known_tasks']]
            captured = []
            def count(cfg, messages, tools, timeout):
                captured.append((deepcopy(cfg), deepcopy(messages), deepcopy(tools)))
                return {'input_tokens': 5001 if mismatch and len(captured) == 2 else 5000, 'wall_seconds': 0}
            with patch.object(driver, 'sources', return_value=(plan, original, [], prepared)), \
                 patch.object(driver, 'frozen_hashes', return_value={'fixture': 'a' * 64}), \
                 patch.object(driver, 'frozen_sources', return_value='b' * 40), \
                 patch.object(driver, 'live_identity', return_value=({'fixture': True}, 999999)), \
                 patch.object(driver, 'check_resume', return_value={'fixture': True}), \
                 patch.object(driver, 'count_input', side_effect=count), \
                 patch.object(driver, 'count_summary_input', side_effect=count):
                if mismatch:
                    with self.assertRaisesRegex(ValueError, 'both_initial_inputs_must_match'):
                        driver.preflight(storage, root)
                    saved = json.loads((root / driver.PREFLIGHT).read_text())
                    self.assertEqual(saved['status'], 'failed')
                    self.assertEqual(saved['model_generations'], 0)
                    with self.assertRaises(ValueError): driver.activate(storage, root)
                else:
                    result = driver.preflight(storage, root)
                    self.assertEqual((result['input_count_requests'], result['summary_input_count_requests']), (8, 1))
                    self.assertEqual(len(captured), 9)
                    self.assertTrue(result['all_eight_inputs_checked'])
                    for index in range(0, 8, 2): self.assertEqual(captured[index], captured[index + 1])
                    self.assertTrue(all('api_receipts' in row[1][0]['content'] for row in captured[:8]))
                    self.assertTrue(all(result[key] == 0 for key in ('model_generations', 'environment_api_requests', 'evaluator_calls')))
                    driver.activate(storage, root)
                    self.assertTrue(json.loads((root / driver.ACTIVATION).read_text())['all_eight_conditions_frozen_before_generation'])
                with self.assertRaises(FileExistsError): driver.preflight(storage, root)

    def test_all_initial_inputs_and_common_summary_transport_before_activation(self):
        self.exercise()

    def test_pair_mismatch_is_preserved_and_cannot_activate(self):
        self.exercise(mismatch=True)

    def test_plan_cannot_extend_budget_change_quality_gate_or_drop_shared_controls(self):
        plan = synthetic_plan(); validate_plan(plan)
        for key, value in (('max_cells', 9), ('max_total_tokens', 450001), ('model_seed', 57),
                           ('same_ordinary_complete_cache', False), ('same_compact_receipts', False),
                           ('minimum_projection_hits_on_common_success', 0), ('source_sha256', {}),
                           ('require_no_projection_contract_failure', False), ('adaptive_extension', True)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_plan({**plan, key: value})


if __name__ == '__main__':
    unittest.main()
