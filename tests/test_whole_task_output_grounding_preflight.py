"""Native input matching and finite activation, using only synthetic counts."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_whole_task_output_grounding as driver
from whole_task_output_grounding import fixed_fields, validate_plan, config_for, MODES

ROOT = Path(__file__).resolve().parents[1]


def synthetic_plan():
    previous = json.loads((ROOT / 'configs/P118_whole_task_single_checkpoint_v01.json').read_text())
    plan = fixed_fields()
    plan.update(known_tasks=[task for task in previous['known_tasks'] if task['source_run'] == 'P29_04_CODE'], source_sha256=deepcopy(previous['source_sha256']))
    for name in ('scripts/public_output_grounding.py', 'scripts/output_grounding_runtime.py',
                 'scripts/run_whole_task_output_grounding_cell.py',
                 'scripts/audit_whole_task_output_grounding.py',
                 'docs/experiments/P129_whole_task_output_grounding.md',
                 'reports/P129_closed_source_diagnosis_20261026.json',
                 'reports/P127_comparison.json', 'reports/P127_server_session.json'):
        plan['source_sha256'][name] = 'a' * 64
    return plan


class GroundingPreflightTests(unittest.TestCase):
    def test_fixed_new_API_caps_are_common_and_do_not_mutate_old_configuration(self):
        plan = synthetic_plan()
        original = json.loads((ROOT / 'configs/P29_stateful_code_v01.json').read_text())
        unchanged = deepcopy(original)
        for number, task in enumerate(plan['known_tasks']):
            configs = [config_for(original, plan, task['task_id'], policy, 1) for policy in MODES]
            self.assertEqual([c['max_api_requests'] for c in configs], [120] * 3)
            self.assertTrue(all(c['checkpoint_policy'] == 'rolling_separate'
                                and c['rolling_checkpoint_max_opportunities'] == 3 for c in configs))
        self.assertEqual(original, unchanged)
        self.assertEqual(sum(plan['api_budget_by_task_slot']) * 6, 720)

    def exercise(self, mismatch=False, activation_mutations=False, worker_runtime_checks=False):
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
                 patch.object(driver, 'launch_predecessor_closed', return_value={'P128': 'a'*64}), \
                 patch.object(driver, 'frozen_hashes', return_value={'fixture': 'a' * 64}), \
                 patch.object(driver, 'frozen_sources', return_value='b' * 40), \
                 patch.object(driver, 'live_identity', return_value=({'fixture': True}, 999999)), \
                 patch.object(driver, 'check_resume', return_value={'fixture': True}), \
                 patch.object(driver, 'count_input', side_effect=count), \
                 patch.object(driver, 'count_summary_input', side_effect=count):
                if mismatch:
                    with self.assertRaisesRegex(ValueError, 'all_three_initial_inputs_must_match'):
                        driver.preflight(storage, root)
                    saved = json.loads((root / driver.PREFLIGHT).read_text())
                    self.assertEqual(saved['status'], 'failed')
                    self.assertEqual(saved['model_generations'], 0)
                    with self.assertRaises(ValueError): driver.activate(storage, root)
                else:
                    result = driver.preflight(storage, root)
                    self.assertEqual((result['input_count_requests'], result['summary_input_count_requests']), (6, 2))
                    self.assertEqual(len(captured), 8)
                    self.assertTrue(result['all_six_inputs_checked'])
                    for index in range(0, 6, 3):
                        self.assertEqual(captured[index], captured[index + 1])
                        self.assertEqual(captured[index], captured[index + 2])
                    self.assertTrue(all('api_receipts' in row[1][0]['content'] and 'read_fields' in row[1][0]['content'] for row in captured[:6]))
                    self.assertTrue(all(result[key] == 0 for key in ('model_generations', 'environment_api_requests', 'evaluator_calls')))
                    if activation_mutations:
                        changes = (
                            ('changed_seed', lambda p: p['rows'][1].update(model_seed=57)),
                            ('boolean_replication', lambda p: p['rows'][0].update(replication=True)),
                            ('floating_seed', lambda p: p['rows'][0].update(model_seed=57.0)),
                            ('changed_replication', lambda p: p['rows'][1].update(replication=1)),
                            ('old_phase', lambda p: p.update(phase='P125_preflight')),
                            ('missing_conditions', lambda p: p.update(rows=[])),
                            ('duplicate_task', lambda p: p['rows'].__setitem__(1, deepcopy(p['rows'][0]))),
                            ('old_policy', lambda p: p['rows'][0]['conditions'].update(eager_cached={})),
                            ('generated', lambda p: p.update(model_generations=1)),
                            ('environment_API', lambda p: p.update(environment_api_requests=1)),
                            ('evaluation', lambda p: p.update(evaluator_calls=1)),
                            ('reserved_read', lambda p: p.update(reserved_scenarios_read=1)),
                            ('missing_usage', lambda p: p['rows'][0]['conditions'][MODES[0]].pop('input_tokens')),
                            ('boolean_usage', lambda p: p['rows'][0]['conditions'][MODES[0]].update(input_tokens=True)),
                            ('nonfinite_count_time', lambda p: p['rows'][0]['conditions'][MODES[0]].update(wall_seconds=float('nan'))),
                            ('missing_summary_usage', lambda p: p['summary_transport']['57'].pop('input_tokens')),
                            ('changed_source', lambda p: p.update(source_hashes={})),
                            ('changed_admission', lambda p: p['rows'][0]['conditions'][MODES[0]].update(admission={'admitted':True})),
                        )
                        for label, change in changes:
                            candidate = deepcopy(result); change(candidate)
                            (root / driver.PREFLIGHT).write_text(json.dumps(candidate))
                            with self.subTest(label=label), self.assertRaises(ValueError):
                                driver.activate(storage, root)
                            self.assertFalse((root / driver.ACTIVATION).exists())
                        (root / driver.PREFLIGHT).write_text(json.dumps(result))
                        # Even a self-consistent saved hash cannot authorize a
                        # different request transport from the fixed condition.
                        path = storage / 'records/context_pilot/P129_preflight_v01' / (
                            'R01_' + plan['known_tasks'][0]['source_run'] + '_' + MODES[0] + '_request_private.json')
                        original_bytes = path.read_bytes()
                        request = json.loads(original_bytes)
                        request['tool_choice'] = 'required'
                        path.write_text(json.dumps(request))
                        candidate = deepcopy(result)
                        candidate['rows'][0]['conditions'][MODES[0]]['count_request_sha256'] = driver.sha(path)
                        (root / driver.PREFLIGHT).write_text(json.dumps(candidate))
                        with self.assertRaisesRegex(ValueError, 'count_input_request_or_usage'):
                            driver.activate(storage, root)
                        self.assertFalse((root / driver.ACTIVATION).exists())
                        path.write_bytes(original_bytes)
                        (root / driver.PREFLIGHT).write_text(json.dumps(result))
                    driver.activate(storage, root)
                    activation = json.loads((root / driver.ACTIVATION).read_text())
                    self.assertTrue(activation['all_six_conditions_frozen_before_generation'])
                    driver.validate_activation(storage, root, activation)
                    with self.assertRaises(ValueError):
                        driver.validate_activation(storage, root, {**activation, 'phase': 'P125'})
                    if worker_runtime_checks:
                        required = sum(plan[key] for key in ('max_setup_seconds', 'max_wall_seconds',
                            'max_cleanup_seconds', 'max_idle_wait_seconds', 'max_evaluation_seconds'))
                        with patch.object(driver, 'run_cell', return_value={'synthetic': True}) as worker:
                            with patch.object(driver, 'live_identity', return_value=({'fixture': True}, 999999)) as live:
                                self.assertEqual(driver.run_worker(storage, root, 1, 1, MODES[0]), {'synthetic': True})
                                live.assert_called_once_with(storage, original, required)
                                worker.assert_called_once()
                                self.assertEqual(worker.call_args.args[5], prepared[0])
                                self.assertEqual(worker.call_args.kwargs, {'grounding_mode': MODES[0], 'replication': 1})
                            worker.reset_mock()
                            with patch.object(driver, 'live_identity', return_value=({'fixture': False}, 999999)):
                                with self.assertRaisesRegex(ValueError, 'prepared_model_identity_changed'):
                                    driver.run_worker(storage, root, 1, 1, MODES[0])
                            worker.assert_not_called()
                            # The shared live checker verifies ownership, idle
                            # slots and sufficient lease. Every rejection must
                            # precede cell setup, API dispatch or generation.
                            for reason in ('owned_runtime_changed', 'server_not_idle', 'insufficient_lease'):
                                with self.subTest(reason=reason), patch.object(driver, 'live_identity', side_effect=ValueError(reason)):
                                    with self.assertRaisesRegex(ValueError, reason):
                                        driver.run_worker(storage, root, 1, 1, MODES[0])
                                worker.assert_not_called()
                            (storage / '.runtime').mkdir()
                            (storage / '.runtime/P129.stop').touch()
                            with patch.object(driver, 'live_identity') as live:
                                with self.assertRaisesRegex(InterruptedError, 'explicit_P129_stop'):
                                    driver.run_worker(storage, root, 1, 1, MODES[0])
                                live.assert_not_called()
                            worker.assert_not_called()
                with self.assertRaises(FileExistsError): driver.preflight(storage, root)

    def test_all_initial_inputs_and_common_summary_transport_before_activation(self):
        self.exercise()

    def test_pair_mismatch_is_preserved_and_cannot_activate(self):
        self.exercise(mismatch=True)

    def test_activation_requires_fixed_identities_saved_requests_and_zero_execution(self):
        self.exercise(activation_mutations=True)

    def test_single_worker_rechecks_owned_live_identity_and_lease_before_cell_setup(self):
        self.exercise(worker_runtime_checks=True)

    def test_plan_cannot_extend_budget_change_quality_gate_or_drop_shared_controls(self):
        plan = synthetic_plan(); validate_plan(plan)
        for key, value in (('max_cells', 9), ('max_total_tokens', 450001), ('model_seeds', [57, 257]),
                           ('same_ordinary_complete_cache', False), ('same_compact_receipts', False),
                           ('same_explicit_field_capability', False), ('same_joined_authority', False),
                           ('api_budget_by_task_slot', [160,80,80,80]), ('max_reserved_environment_api_requests',800),
                           ('checkpoint_policy','single_checkpoint'), ('max_summary_calls_in_batch',8),
                           ('explicit_field_guide_sha256','f'*64),
                           ('minimum_successful_repairs_on_common_success', 0), ('source_sha256', {}),
                           ('require_no_grounding_contract_failure', False), ('adaptive_extension', True)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_plan({**plan, key: value})


if __name__ == '__main__':
    unittest.main()
