"""Native input matching and finite activation, using only synthetic counts."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_whole_task_region_projection as driver
from whole_task_region_projection import fixed_fields, validate_plan, config_for, POLICIES

ROOT = Path(__file__).resolve().parents[1]


def synthetic_plan():
    previous = json.loads((ROOT / 'configs/P118_whole_task_single_checkpoint_v01.json').read_text())
    plan = fixed_fields()
    plan.update(known_tasks=previous['known_tasks'], source_sha256=deepcopy(previous['source_sha256']))
    for name in ('scripts/region_field_projection.py', 'scripts/region_projection_runtime.py',
                 'scripts/demand_joined_read_adapter.py', 'scripts/joined_public_read_views.py',
                 'scripts/compact_api_receipts.py', 'scripts/rolling_checkpoint_inference.py',
                 'scripts/audit_rolling_checkpoint_trace.py',
                 'docs/experiments/P127_whole_task_region_projection.md',
                 'reports/P126_region_projection_replay.json', 'reports/P125_comparison.json',
                 'reports/P125_server_session.json', 'reports/P123_comparison.json',
                 'reports/P123_server_session.json'):
        plan['source_sha256'][name] = 'a' * 64
    return plan


class ProjectionPreflightTests(unittest.TestCase):
    def test_fixed_new_API_caps_are_common_and_do_not_mutate_old_configuration(self):
        plan = synthetic_plan()
        original = json.loads((ROOT / 'configs/P29_stateful_code_v01.json').read_text())
        unchanged = deepcopy(original)
        for number, task in enumerate(plan['known_tasks']):
            configs = [config_for(original, plan, task['task_id'], policy) for policy in POLICIES]
            self.assertEqual([c['max_api_requests'] for c in configs], [plan['api_budget_by_task_slot'][number]] * 2)
            self.assertTrue(all(c['checkpoint_policy'] == 'rolling_separate'
                                and c['rolling_checkpoint_max_opportunities'] == 3 for c in configs))
        self.assertEqual(original, unchanged)
        self.assertEqual(sum(plan['api_budget_by_task_slot']) * 2, 880)

    def test_missing_started_timing_does_not_become_zero(self):
        from inspect_whole_task_region_projection_session import attempt_time_totals, cell_time_totals
        rows = [{'evaluation_started_at': 'synthetic', 'evaluation_wall_seconds': 2},
                {'evaluation_started_at': 'synthetic'}, {}]
        result = attempt_time_totals(rows, 'evaluation')
        self.assertEqual((result['known_subtotal'], result['unknown_attempts']), (2, 1))
        self.assertIsNone(result['exact_total'])
        cells = cell_time_totals([{'record_status': 'not_run'}, {'record_status': 'incomplete_worker'}])
        self.assertEqual(cells['unknown_cell_full_wall_count'], 1)
        self.assertIsNone(cells['cell_full_wall_seconds'])

    def test_predecessor_requires_closed_all_slots_and_finite_offline_frontier(self):
        from types import SimpleNamespace
        from whole_task_projection import cell_id as p125_id, run_order as p125_order
        from whole_task_rolling_checkpoint import cell_id as p123_id, run_order as p123_order
        with tempfile.TemporaryDirectory() as tmp:
            root, storage = Path(tmp) / 'root', Path(tmp) / 'storage'
            def write(path, value):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value))
            for phase, get_id, order in (('P125', p125_id, p125_order), ('P123', p123_id, p123_order)):
                folder = storage / f'records/context_pilot/{phase}_pipeline_v01'
                write(folder / 'status.json', dict(status='complete', server_stopped=True, server_supervisor_pid=23))
                write(folder / 'server_final.json', dict(status='stopped', supervisor_pid=23, pid=24))
                report = root / f'reports/{phase}_comparison.json'
                write(report, dict(phase=phase, audit_errors=[], owned_processes_absent=True,
                    rows=[dict(run_id=get_id(n,p), record_status='evaluated') for n,p in order()],
                    pipeline_status_sha256=driver.sha(folder / 'status.json'),
                    server_final_sha256=driver.sha(folder / 'server_final.json')))
                write(root / f'reports/{phase}_server_session.json', dict(phase=phase, status='stopped',
                    owned_processes_absent=True, audit_source_sha256=driver.sha(report)))
            paths = ('scripts/region_field_projection.py', 'scripts/region_projection_runtime.py',
                     'scripts/demand_joined_read_adapter.py', 'scripts/joined_public_read_views.py',
                     'configs/python_export_image_v01.json', 'docs/experiments/P126_region_projection_replay.md')
            for name in paths:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('# synthetic implementation\n')
            replay = dict(phase='P126', status='complete', all_original_sources_accounted=True,
                observed_region_partial_hits=13, unobserved_suffix_executed=False,
                original_sources_changed=False, additional_model_calls=0,
                additional_API_requests=0, additional_evaluations=0, replay_audit_errors=[],
                normal_path_synthetic_contract_tests_passed=True,
                source_sha256={name: driver.sha(root / name) for name in paths})
            path = root / driver.REPLAY_REPORT
            write(path, replay)
            with patch.object(driver.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='')):
                result = driver.predecessor_closed(storage, root)
                self.assertEqual(set(result), {'P123', 'P125', 'P126'})
                # No full normal-boundary equivalence or completion claim is needed.
                for key, value in (('unobserved_suffix_executed', True), ('observed_region_partial_hits', 0),
                        ('normal_path_synthetic_contract_tests_passed', False), ('additional_API_requests', 1),
                        ('replay_audit_errors', ['synthetic']), ('original_sources_changed', True)):
                    write(path, {**replay, key: value})
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        driver.predecessor_closed(storage, root)
                write(path, replay)
                for invalid in ('../escape.py', 'scripts/../../escape.py', str(root / paths[0])):
                    write(path, {**replay, 'source_sha256': {**replay['source_sha256'], invalid: 'a' * 64}})
                    with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'implementation_changed'):
                        driver.predecessor_closed(storage, root)
                write(path, replay)
                (root / paths[0]).write_text('# mutated synthetic implementation\n')
                with self.assertRaisesRegex(ValueError, 'implementation_changed'):
                    driver.predecessor_closed(storage, root)

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
                    self.assertTrue(all('api_receipts' in row[1][0]['content'] and 'read_fields' in row[1][0]['content'] for row in captured[:8]))
                    self.assertTrue(all(result[key] == 0 for key in ('model_generations', 'environment_api_requests', 'evaluator_calls')))
                    if activation_mutations:
                        changes = (
                            ('old_phase', lambda p: p.update(phase='P125_preflight')),
                            ('missing_conditions', lambda p: p.update(rows=[])),
                            ('duplicate_task', lambda p: p['rows'].__setitem__(1, deepcopy(p['rows'][0]))),
                            ('old_policy', lambda p: p['rows'][0]['conditions'].update(eager_cached={})),
                            ('generated', lambda p: p.update(model_generations=1)),
                            ('environment_API', lambda p: p.update(environment_api_requests=1)),
                            ('evaluation', lambda p: p.update(evaluator_calls=1)),
                            ('reserved_read', lambda p: p.update(reserved_scenarios_read=1)),
                            ('missing_usage', lambda p: p['rows'][0]['conditions'][POLICIES[0]].pop('input_tokens')),
                            ('boolean_usage', lambda p: p['rows'][0]['conditions'][POLICIES[0]].update(input_tokens=True)),
                            ('nonfinite_count_time', lambda p: p['rows'][0]['conditions'][POLICIES[0]].update(wall_seconds=float('nan'))),
                            ('missing_summary_usage', lambda p: p['summary_transport'].pop('input_tokens')),
                            ('changed_source', lambda p: p.update(source_hashes={})),
                            ('changed_admission', lambda p: p['rows'][0]['conditions'][POLICIES[0]].update(admission={'admitted':True})),
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
                        path = storage / 'records/context_pilot/P127_preflight_v01' / (
                            plan['known_tasks'][0]['source_run'] + '_' + POLICIES[0] + '_request_private.json')
                        original_bytes = path.read_bytes()
                        request = json.loads(original_bytes)
                        request['tool_choice'] = 'required'
                        path.write_text(json.dumps(request))
                        candidate = deepcopy(result)
                        candidate['rows'][0]['conditions'][POLICIES[0]]['count_request_sha256'] = driver.sha(path)
                        (root / driver.PREFLIGHT).write_text(json.dumps(candidate))
                        with self.assertRaisesRegex(ValueError, 'count_input_request_or_usage'):
                            driver.activate(storage, root)
                        self.assertFalse((root / driver.ACTIVATION).exists())
                        path.write_bytes(original_bytes)
                        (root / driver.PREFLIGHT).write_text(json.dumps(result))
                    driver.activate(storage, root)
                    activation = json.loads((root / driver.ACTIVATION).read_text())
                    self.assertTrue(activation['all_eight_conditions_frozen_before_generation'])
                    driver.validate_activation(storage, root, activation)
                    with self.assertRaises(ValueError):
                        driver.validate_activation(storage, root, {**activation, 'phase': 'P125'})
                    if worker_runtime_checks:
                        required = sum(plan[key] for key in ('max_setup_seconds', 'max_wall_seconds',
                            'max_cleanup_seconds', 'max_idle_wait_seconds', 'max_evaluation_seconds'))
                        with patch.object(driver, 'run_cell', return_value={'synthetic': True}) as worker:
                            with patch.object(driver, 'live_identity', return_value=({'fixture': True}, 999999)) as live:
                                self.assertEqual(driver.run_worker(storage, root, 1, POLICIES[0]), {'synthetic': True})
                                live.assert_called_once_with(storage, original, required)
                                worker.assert_called_once()
                                self.assertEqual(worker.call_args.args[5], prepared[0])
                                self.assertEqual(worker.call_args.kwargs, {'projection_policy': POLICIES[0]})
                            worker.reset_mock()
                            with patch.object(driver, 'live_identity', return_value=({'fixture': False}, 999999)):
                                with self.assertRaisesRegex(ValueError, 'prepared_model_identity_changed'):
                                    driver.run_worker(storage, root, 1, POLICIES[0])
                            worker.assert_not_called()
                            # The shared live checker verifies ownership, idle
                            # slots and sufficient lease. Every rejection must
                            # precede cell setup, API dispatch or generation.
                            for reason in ('owned_runtime_changed', 'server_not_idle', 'insufficient_lease'):
                                with self.subTest(reason=reason), patch.object(driver, 'live_identity', side_effect=ValueError(reason)):
                                    with self.assertRaisesRegex(ValueError, reason):
                                        driver.run_worker(storage, root, 1, POLICIES[0])
                                worker.assert_not_called()
                            (storage / '.runtime').mkdir()
                            (storage / '.runtime/P127.stop').touch()
                            with patch.object(driver, 'live_identity') as live:
                                with self.assertRaisesRegex(InterruptedError, 'explicit_P127_stop'):
                                    driver.run_worker(storage, root, 1, POLICIES[0])
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
        for key, value in (('max_cells', 9), ('max_total_tokens', 450001), ('model_seed', 57),
                           ('same_ordinary_complete_cache', False), ('same_compact_receipts', False),
                           ('same_explicit_field_capability', False), ('same_joined_authority', False),
                           ('api_budget_by_task_slot', [160,80,80,80]), ('max_reserved_environment_api_requests',800),
                           ('checkpoint_policy','single_checkpoint'), ('max_summary_calls_in_batch',8),
                           ('explicit_field_guide_sha256','f'*64),
                           ('minimum_projection_hits_on_common_success', 0), ('source_sha256', {}),
                           ('require_no_projection_contract_failure', False), ('adaptive_extension', True)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_plan({**plan, key: value})


if __name__ == '__main__':
    unittest.main()
