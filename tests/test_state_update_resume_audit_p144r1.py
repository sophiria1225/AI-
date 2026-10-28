"""Synthetic adversarial checks for paused-cohort linkage; no experiments."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import audit_state_update_resume_p144r1 as audit
from test_state_update_study_p144 import rows as original_rows


def physical_rows():
    values = original_rows()
    for row, slot in zip(values, audit.slots()):
        row['run_id'] = slot['run_id']
    return values


def batch():
    expected = [s['run_id'] for s in audit.slots()[2:]]
    return dict(phase='P144R1', status='complete', planned=expected,
                completed=list(expected), active=None)


def pipeline():
    return dict(phase='P144R1_pipeline', status='complete', server_stopped=True,
                server_supervisor_pid=101), dict(status='stopped', supervisor_pid=101, pid=102)


class ResumeAuditTests(unittest.TestCase):
    def test_real_ids_retained_while_canonical_copies_are_independent(self):
        values = physical_rows()
        saved = deepcopy(values)
        canonical = audit.canonical_slots(values)
        self.assertEqual(canonical, original_rows())
        canonical[-1]['request_checks'].append({'synthetic': True})
        self.assertEqual(values, saved)
        self.assertEqual(values[1]['run_id'], audit.slots()[1]['canonical_run_id'])
        self.assertIn('BOC_P144R1_', values[2]['run_id'])

    def test_old_third_run_cannot_be_relabelled_as_a_new_continuation(self):
        values = physical_rows()
        values[2]['run_id'] = audit.slots()[2]['canonical_run_id']
        with self.assertRaises(ValueError):
            audit.canonical_slots(values)

    def test_duplicate_or_reordered_slots_cannot_be_summarized(self):
        for indexes in ((0, 0), (2, 3)):
            values = physical_rows()
            if indexes == (0, 0):
                values[1] = deepcopy(values[0])
            else:
                values[2], values[3] = values[3], values[2]
            with self.assertRaises(ValueError):
                audit.descriptive_summary(values, [])

    def test_wrong_mode_or_task_is_rejected_even_with_valid_physical_id(self):
        for key, bad in (('task_id', 'another_task'), ('object_timing_mode', 'threshold_recursive')):
            values = physical_rows()
            values[2][key] = bad
            with self.assertRaises(ValueError):
                audit.canonical_slots(values)

    def test_perfect_descriptive_outcome_never_becomes_adoption_claim(self):
        result = audit.descriptive_summary(physical_rows(), [])
        self.assertTrue(result['descriptive_development_criteria_met'])
        self.assertFalse(result['development_gate_met'])
        self.assertFalse(result['scientific_adoption_gate_met'])
        self.assertFalse(result['scientific_adoption_evaluated'])
        self.assertTrue(all(c['descriptive_comparison_criteria_met'] for c in result['comparisons']))
        self.assertTrue(all(c['comparison_gate_met'] is False and c['component_effect_attributable'] is False
                            for c in result['comparisons']))
        self.assertEqual([c['all_task_token_difference'] for c in result['comparisons']], [-400, -200, -200])

    def test_session_split_is_marked_per_pair_without_hiding_real_ids(self):
        result = audit.descriptive_summary(physical_rows(), [])
        first, second, third = [c['pairs'][0] for c in result['comparisons']]
        self.assertFalse(first['same_execution_session'])
        self.assertFalse(second['same_execution_session'])
        self.assertTrue(third['same_execution_session'])
        self.assertIn('BOC_P144R1_', first['candidate_run_id'])
        self.assertTrue(all(p['same_execution_session'] for c in result['comparisons'] for p in c['pairs'][1:]))

    def test_missing_pending_slot_remains_null_and_blocks_exact_total(self):
        values = physical_rows()
        values[2].update(record_status='not_run', success=None, known_total_tokens=None, unknown_usage_calls=None)
        result = audit.descriptive_summary(values, [])
        self.assertEqual(result['evaluated_conditions'], 11)
        self.assertTrue(all(v is None for v in result['total_tokens_by_mode'].values()))
        self.assertIsNone(result['comparisons'][0]['all_task_token_difference'])
        self.assertIsNone(result['comparisons'][1]['all_task_token_difference'])
        self.assertEqual(result['comparisons'][2]['all_task_token_difference'], -200)
        self.assertFalse(result['descriptive_development_criteria_met'])

    def test_unknown_usage_is_not_zero_imputed(self):
        values = physical_rows()
        values[2]['unknown_usage_calls'] = 1
        result = audit.descriptive_summary(values, [])
        self.assertEqual(result['recorded_unknown_usage_calls'], 1)
        self.assertIsNone(result['comparisons'][0]['all_task_token_difference'])

    def test_same_success_count_does_not_hide_a_paired_loss(self):
        values = physical_rows()
        values[0]['success'] = False
        values[4]['success'] = False
        result = audit.descriptive_summary(values, [])
        self.assertEqual(result['comparisons'][0]['success_loss_tasks'], ['3c13f5a_1'])
        self.assertFalse(result['descriptive_development_criteria_met'])

    def test_complete_batch_requires_all_ten_and_no_active_worker(self):
        for mutation in ({'completed': batch()['completed'][:-1]}, {'active': batch()['completed'][0]},
                         {'phase': 'P144'}, {'status': 'running'}):
            value = batch()
            value.update(mutation)
            with self.assertRaises(ValueError):
                audit.validate_batch_status(value, batch()['planned'])

    def test_stopped_batch_can_preserve_empty_or_prefix_completion(self):
        for count in (0, 3, 10):
            value = batch()
            value.update(status='stopped', completed=value['completed'][:count])
            self.assertEqual(audit.validate_batch_status(value, batch()['planned']), value['completed'])
        value = batch()
        value.update(status='stopped', completed=[value['completed'][1]])
        with self.assertRaises(ValueError):
            audit.validate_batch_status(value, batch()['planned'])

    def test_live_or_unknown_process_state_prevents_audit(self):
        owner, server = pipeline()
        for result in (SimpleNamespace(returncode=0, stdout='owned server'),
                       SimpleNamespace(returncode=2, stdout=''),
                       SimpleNamespace(returncode=1, stdout='unexpected output')):
            with self.assertRaises(ValueError):
                audit.validate_closed_pipeline(owner, server, lambda *a, **k: result)
        audit.validate_closed_pipeline(owner, server,
            lambda *a, **k: SimpleNamespace(returncode=1, stdout=''))

    def test_server_owner_mismatch_or_nonpositive_pids_are_rejected(self):
        for update in ({'supervisor_pid': 999}, {'pid': True}, {'pid': -1}, {'pid': 101}):
            owner, server = pipeline()
            server.update(update)
            with self.assertRaises(ValueError):
                audit.validate_closed_pipeline(owner, server)

    def test_running_pipeline_cannot_read_any_cell_or_source_outcome(self):
        owner, server = pipeline()
        owner['status'] = 'batch'
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(audit, 'read', side_effect=[owner, server]) as reader, \
                    patch.object(audit, 'audit_cell', side_effect=AssertionError('must not read cell')):
                with self.assertRaises(ValueError):
                    audit.run(Path(directory), Path(directory))
                self.assertEqual(reader.call_count, 2)

    def test_existing_audit_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / audit.TARGET
            target.parent.mkdir()
            target.write_text('frozen report')
            with patch.object(audit, 'read', side_effect=AssertionError('must not inspect')):
                with self.assertRaises(FileExistsError):
                    audit.run(Path(directory), Path(directory))
            self.assertEqual(target.read_text(), 'frozen report')

    def test_closed_linked_report_keeps_physical_rows_and_original_report_bytes(self):
        # Cell arithmetic has separate frozen-auditor tests; this fixture checks
        # the entire closure, ID linkage, output and non-overwrite integration.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def put(relative, value):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value))
                return path
            owner, server = pipeline()
            put('records/context_pilot/P144R1_pipeline_v01/status.json', owner)
            put('records/context_pilot/P144R1_pipeline_v01/server_final.json', server)
            put('records/context_pilot/P144R1_batch_v01/status.json', batch())
            plan = {'model_seed': 257}
            put(audit.PLAN, plan)
            put(audit.SPEC, dict(inherited_plan_sha256=audit.sha(root / audit.PLAN),
                remaining_run_ids=[s['run_id'] for s in audit.slots()[2:]],
                canonical_remaining_run_ids=[s['canonical_run_id'] for s in audit.slots()[2:]]))
            prepared = [{'task_id': task} for task in audit.TASKS]
            pre = dict(phase='P144R1_preflight', status='complete', rows=[
                {'conditions': {s['mode']: {} for s in audit.slots() if s['number'] == number}}
                for number in range(1, 5)])
            put('reports/P144_initial_checks.json', pre)
            put('reports/P144R1_initial_checks.json', pre)
            put('records/context_pilot/P144R1_preflight_v01/status.json', pre)
            put('reports/P144R1_activation_v01.json', dict(source_hashes={},
                preflight_sha256=audit.sha(root / 'reports/P144R1_initial_checks.json')))
            put('scripts/audit_whole_task_state_update_p144.py', {'frozen_source_fixture': True})
            original_report = put('reports/P144_comparison.json', {'frozen_original_report': True})
            original_bytes = original_report.read_bytes()
            fixture_rows = physical_rows()
            for index, slot in enumerate(audit.slots()):
                rid = slot['run_id']
                put('records/context_pilot/' + rid + '/summary.json',
                    dict(phase='P144' if index < 2 else 'P144R1'))
                batch_name = 'P144_batch_v01' if index < 2 else 'P144R1_batch_v01'
                put('records/context_pilot/' + batch_name + '/' + rid + '_worker_exit.json',
                    dict(run_id=rid, status='exited', returncode=0, timed_out=False, forced_group_kill=False))
            source = SimpleNamespace(sources=lambda *args, **kwargs: (plan, {}, [], prepared),
                                     frozen_hashes=lambda *args: {})
            with patch.dict(sys.modules, {'run_state_update_resume_p144r1': source}), \
                    patch.object(audit, 'validate_closed_pipeline'), \
                    patch.object(audit, 'verify_saved_artifacts', return_value={'saved_artifacts_verified': 518}), \
                    patch.object(audit, 'audit_cell', side_effect=fixture_rows):
                result = audit.run(root, root)
            self.assertEqual(original_report.read_bytes(), original_bytes)
            self.assertEqual(result['audit_errors'], [])
            self.assertEqual(result['evaluated_conditions'], 12)
            self.assertEqual([row['run_id'] for row in result['rows']], [s['run_id'] for s in audit.slots()])
            self.assertEqual([row['evaluation_recovered_after_shutdown'] for row in result['rows']],
                             [False, True] + [False] * 10)
            self.assertFalse(result['development_gate_met'])
            self.assertEqual(json.loads((root / audit.TARGET).read_text()), result)


if __name__ == '__main__':
    unittest.main()
