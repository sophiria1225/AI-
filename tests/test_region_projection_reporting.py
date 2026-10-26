import copy
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_region_projection_summary as reporting


class ProjectionReportingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.root_patch = patch.object(reporting, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        for name in (reporting.BUILDER, reporting.AUDITOR, reporting.INSPECTOR, reporting.HELPER):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# synthetic public source: ' + name + '\n')
        self.write(reporting.PREFLIGHT, {'synthetic': True})
        sources = {name: reporting.sha(self.root / name) for name in (
            reporting.BUILDER, reporting.AUDITOR, reporting.INSPECTOR, reporting.HELPER)}
        self.plan = {'experiment': 'P127', 'projection_policies': list(reporting.POLICIES),
                     'known_tasks': [{'task_id': f'synthetic-{n}'} for n in range(1, 5)],
                     'source_sha256': sources.copy()}
        self.activation = {'source_hashes': sources.copy(),
                           'preflight_sha256': reporting.sha(self.root / reporting.PREFLIGHT)}
        self.write(reporting.PLAN, self.plan)
        self.write(reporting.ACTIVATION, self.activation)
        self.rows = [self.row(number, policy) for number, policy in reporting.run_order()]
        self.refresh()

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True) + '\n')

    def row(self, number, policy):
        projected = policy == reporting.POLICIES[1]
        runtime = {key: 0 for key in reporting.RUNTIME_COUNTS}
        runtime.update({key: 0.01 for key in reporting.RUNTIME_TIMES})
        runtime.update({key: True for key in reporting.RUNTIME_FLAGS})
        runtime.update(policy=policy, projection_failed=False, program_attempts=2,
            program_evidence_records=2, static_eligible_programs=1,
            transformed_programs=int(projected), projection_lookup_requests=int(projected),
            projection_partial_hits=int(projected), automatic_region_partial_hits=int(projected),
            explicit_field_interface_shared_between_policies=True, joined_provider_shared_between_policies=True,
            known_control_requests=3,
            known_control_request_bytes=120, known_control_reply_bytes=240,
            schema_deliveries=2, known_schema_reply_wire_bytes=100)
        return {'run_id': reporting.cell_id(number, policy), 'task_id': f'synthetic-{number}',
            'projection_policy': policy, 'checkpoint_policy': 'rolling_separate',
            'record_status': 'evaluated', 'success': True, 'stop_reason': 'completed',
            'model_calls': 2, 'known_total_tokens': 90 if projected else 100,
            'unknown_usage_calls': 0, 'api_requests': 1 if projected else 2,
            'input_tokens': 70 if projected else 80, 'output_tokens': 20,
            'cached_input_tokens': 0, 'projection_hits': int(projected),
            'setup_wall_seconds': 0.1, 'wall_seconds': 1.0,
            'cleanup_wall_seconds': 0.2, 'full_wall_seconds': 1.3,
            'checkpoint_installed': False, 'checkpoint_opportunity': None, 'checkpoint_installations': 0,
            'projection_contract_failed': False, 'projection_runtime': runtime,
            'summary_sha256': 'a' * 64, 'usage_sha256': 'b' * 64,
            'evaluation_sha256': 'c' * 64}

    def refresh(self):
        self.report = {'phase': 'P127', 'batch_status': 'complete', 'rows': self.rows,
            'owned_processes_absent': True, 'audit_errors': [],
            'plan_sha256': reporting.sha(self.root / reporting.PLAN),
            'activation_sha256': reporting.sha(self.root / reporting.ACTIVATION),
            'auditor_sha256': reporting.sha(self.root / reporting.AUDITOR),
            'pipeline_status_sha256': 'd' * 64, 'server_final_sha256': 'e' * 64,
            **reporting.summarize(self.rows, [])}
        self.session = {'phase': 'P127', 'status': 'stopped', 'owned_processes_absent': True,
            'pipeline_source_sha256': 'd' * 64, 'source_sha256': 'e' * 64,
            'inspector_sha256': reporting.sha(self.root / reporting.INSPECTOR),
            'wall_seconds': 20.0, 'cell_full_wall_seconds': 10.4,
            'known_cell_full_wall_seconds': 10.4, 'unknown_cell_full_wall_count': 0,
            'batch_other_wall_seconds': 2.0}
        self.persist()

    def persist(self):
        self.write(reporting.AUDIT, self.report)
        self.session['audit_source_sha256'] = reporting.sha(self.root / reporting.AUDIT)
        self.write(reporting.SESSION, self.session)

    def test_complete_public_output_and_exclusive_atomic_publication(self):
        self.rows[0]['private_prompt'] = 'PRIVATE_SENTINEL_NEVER_COPY'
        self.rows[0]['projection_runtime']['feedback'] = {'private': 'PRIVATE_SENTINEL_NEVER_COPY'}
        self.refresh()
        result = reporting.build(self.root)
        target = self.root / reporting.TARGET
        self.assertEqual(set(p.name for p in target.iterdir()),
                         {'summary.json', 'conditions.csv', 'README.md', 'build_manifest.json'})
        self.assertEqual(result['all_conditions']['exact_total_tokens'], 760)
        self.assertEqual(result['all_conditions']['known_token_subtotal'], 760)
        self.assertEqual(result['common_successful_tasks'], 4)
        self.assertTrue(result['audited_criteria']['development_gate_met'])
        self.assertFalse(result['novel_method_claim'])
        self.assertEqual(result['by_policy'][reporting.POLICIES[1]]['measures']['api_requests']
                         ['exact_all_condition_total'], 4)
        with (target / 'conditions.csv').open() as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), 8)
        manifest = json.loads((target / 'build_manifest.json').read_text())
        self.assertEqual(manifest['new_model_calls'], 0)
        self.assertEqual(manifest['new_API_requests'], 0)
        self.assertEqual(manifest['source_sha256'][reporting.AUDIT],
                         reporting.sha(self.root / reporting.AUDIT))
        for name, digest in manifest['artifact_sha256'].items():
            self.assertEqual(digest, reporting.sha(target / name))
        before = {p.name: p.read_bytes() for p in target.iterdir()}
        self.assertNotIn('PRIVATE_SENTINEL_NEVER_COPY', ''.join(p.read_text() for p in target.iterdir()))
        with self.assertRaises(FileExistsError):
            reporting.build(self.root)
        self.assertEqual(before, {p.name: p.read_bytes() for p in target.iterdir()})

    def test_unknown_usage_and_control_keep_subtotals_without_exact_totals(self):
        self.rows[0]['unknown_usage_calls'] = 1
        self.rows[0]['projection_runtime']['control_accounting_complete'] = False
        self.refresh()
        self.session.update(cell_full_wall_seconds=None, unknown_cell_full_wall_count=1,
                            batch_other_wall_seconds=None)
        self.persist()
        result = reporting.build(self.root)
        overall = result['all_conditions']
        self.assertEqual(overall['known_token_subtotal'], 760)
        self.assertEqual(overall['recorded_unknown_usage_calls'], 1)
        self.assertIsNone(overall['exact_total_tokens'])
        self.assertEqual(overall['measures']['known_control_request_bytes']['known_subtotal'], 960)
        self.assertIsNone(overall['measures']['known_control_request_bytes']['exact_all_condition_total'])
        self.assertIsNone(overall['measures']['control_wall_seconds_including_backend']['exact_all_condition_total'])
        self.assertIsNone(result['conditions'][0]['exact_total_tokens'])
        self.assertIsNone(result['server_measures']['cell_full_wall_seconds'])
        self.assertEqual(result['server_measures']['known_cell_full_wall_seconds'], 10.4)
        self.assertEqual(result['server_measures']['wall_seconds'], 20.0)
        self.assertFalse(result['audited_criteria']['development_gate_met'])

    def test_all_missing_and_unperformed_slots_stay_missing(self):
        for index, status in enumerate(('not_run', 'incomplete_worker', 'audit_error')):
            original = self.rows[index]
            self.rows[index] = {key: original[key] for key in (
                'run_id', 'task_id', 'projection_policy', 'checkpoint_policy')}
            self.rows[index].update(record_status=status, success=None,
                known_total_tokens=None, unknown_usage_calls=None,
                projection_hits=None, projection_contract_failed=None)
        self.rows[3].update(record_status='unevaluated', success=None, evaluation_sha256=None)
        self.refresh()
        result = reporting.build(self.root)
        self.assertEqual(len(result['conditions']), 8)
        self.assertEqual(result['all_conditions']['accounted_conditions'], 5)
        self.assertEqual(result['all_conditions']['unknown_usage_count_missing_conditions'], 3)
        self.assertIsNone(result['all_conditions']['exact_total_tokens'])
        for row in result['conditions'][:3]:
            for key in ('known_total_tokens', 'unknown_usage_calls', 'api_requests',
                        'full_wall_seconds', 'projection_contract_failed'):
                self.assertIsNone(row[key])
        self.assertFalse(result['audited_criteria']['development_gate_met'])
        with (self.root / reporting.TARGET / 'conditions.csv').open() as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[0]['known_total_tokens'], '')

    def test_cheap_failure_and_known_contract_stop_are_not_goal_success(self):
        candidate = next(row for row in self.rows if row['projection_policy'] == reporting.POLICIES[1])
        candidate.update(success=False, known_total_tokens=1, input_tokens=1, output_tokens=0,
                         projection_contract_failed=True, stop_reason='projection_contract_stopped')
        candidate['projection_runtime']['projection_failed'] = True
        candidate['projection_runtime']['projection_failure_events'] = 1
        self.refresh()
        result = reporting.build(self.root)
        self.assertEqual(result['all_conditions']['exact_total_tokens'], 671)
        self.assertEqual(result['common_successful_tasks'], 3)
        self.assertEqual(result['audited_criteria']['projection_contract_failure_cells'], 1)
        self.assertFalse(result['audited_criteria']['mechanism_contracts_intact'])
        self.assertFalse(result['audited_criteria']['development_gate_met'])

    def test_no_interpreter_runtime_keeps_known_model_cost_and_unknown_mechanism(self):
        self.rows[0].update(projection_runtime=None, projection_hits=None,
                            projection_contract_failed=None)
        self.refresh()
        result = reporting.build(self.root)
        self.assertEqual(result['all_conditions']['exact_total_tokens'], 760)
        self.assertEqual(result['conditions'][0]['known_total_tokens'], 100)
        self.assertIsNone(result['conditions'][0]['projection_hits'])
        self.assertIsNone(result['conditions'][0]['program_attempts'])
        self.assertIsNone(result['all_conditions']['measures']['program_attempts']['exact_all_condition_total'])
        self.assertFalse(result['audited_criteria']['mechanism_contracts_intact'])
        self.assertFalse(result['audited_criteria']['development_gate_met'])

    def test_missing_slot_exaggerated_claim_or_runtime_fields_are_rejected(self):
        pristine_rows = copy.deepcopy(self.rows)
        for case in ('missing_slot', 'novel_claim', 'wrong_gate', 'runtime_hits', 'unrun_zero'):
            with self.subTest(case=case):
                self.rows = copy.deepcopy(pristine_rows)
                self.refresh()
                if case == 'missing_slot':
                    self.report['rows'].pop()
                elif case == 'novel_claim':
                    self.report['novel_method_claim'] = True
                elif case == 'wrong_gate':
                    self.report['development_gate_met'] = False
                elif case == 'runtime_hits':
                    self.report['rows'][0]['projection_runtime']['projection_partial_hits'] = 999
                else:
                    self.report['rows'][0].update(record_status='not_run', success=None)
                    self.report.update(reporting.summarize(self.report['rows'], []))
                self.persist()
                with self.assertRaises(ValueError):
                    reporting.build(self.root)
                self.assertFalse((self.root / reporting.TARGET).exists())

    def test_hash_binding_source_root_and_path_changes_are_rejected(self):
        original_source = (self.root / reporting.HELPER).read_bytes()
        for case in ('audit_hash', 'pipeline_hash', 'source_changed', 'source_escape', 'wrong_root'):
            with self.subTest(case=case):
                (self.root / reporting.HELPER).write_bytes(original_source)
                self.write(reporting.ACTIVATION, self.activation)
                self.refresh()
                if case == 'audit_hash':
                    self.session['audit_source_sha256'] = 'f' * 64
                    self.write(reporting.SESSION, self.session)
                elif case == 'pipeline_hash':
                    self.session['pipeline_source_sha256'] = 'f' * 64
                    self.write(reporting.SESSION, self.session)
                elif case == 'source_changed':
                    (self.root / reporting.HELPER).write_text('# changed source\n')
                elif case == 'source_escape':
                    changed = copy.deepcopy(self.activation)
                    changed['source_hashes']['scripts/../../private.json'] = 'f' * 64
                    self.write(reporting.ACTIVATION, changed)
                    self.report['activation_sha256'] = reporting.sha(self.root / reporting.ACTIVATION)
                    self.persist()
                with self.assertRaises(ValueError):
                    reporting.build(self.root / 'different' if case == 'wrong_root' else self.root)
                self.assertFalse((self.root / reporting.TARGET).exists())

    def test_publication_failure_cleans_staging_and_never_replaces_empty_directory(self):
        with patch.object(reporting, 'publish_directory', side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError):
                reporting.build(self.root)
        self.assertFalse((self.root / reporting.TARGET).exists())
        self.assertEqual(list((self.root / 'materials').glob('.p127-materials-*')), [])
        source, destination = self.root / 'staging', self.root / 'already_exists'
        source.mkdir()
        (source / 'keep.txt').write_text('synthetic')
        destination.mkdir()
        with self.assertRaises(OSError):
            reporting.publish_directory(source, destination)
        self.assertTrue((source / 'keep.txt').is_file())
        self.assertEqual(list(destination.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
