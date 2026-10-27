"""P140 closed-report integration with handwritten I/O, never a live experiment.

The new worker and both auditors run unchanged. Only the existing synthetic
fixture's task selector, external transport and closed-process/source discovery
are supplied here. Evaluation files contain handwritten booleans, not eval runs.
"""
import copy
import csv
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import checkpoint_delta_envelope_worker_fixture_p140 as worker_fixture
import audit_whole_task_checkpoint_delta_envelope_p140 as audit
import inspect_whole_task_checkpoint_delta_envelope_session_p140 as session
import build_checkpoint_delta_envelope_summary_p140 as report
import whole_task_checkpoint_delta_envelope_p140 as study
from receipt_reasoning_history import digest
from run_handoff_factors import sha

ROOT = Path(__file__).resolve().parents[1]
AUDIT = 'reports/P140_comparison.json'
SESSION = 'reports/P140_server_session.json'
BUILDER = 'scripts/build_checkpoint_delta_envelope_summary_p140.py'
SOURCE_NAMES = (*study.REQUIRED_SOURCES, BUILDER, 'scripts/evaluate_context_trial.py')


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def build(root):
    # The builder is copied byte-for-byte into this isolated synthetic repo.
    with patch.object(report, '__file__', str(root / BUILDER)):
        return report.build(root)


def closed_fixture(base, *, partial=False, unknown=False, bad_exit=False,
                   missing_completed=False, unevaluated=False, publish=True):
    root, storage = base / 'repo', base / 'storage'
    root.mkdir(); storage.mkdir()
    mapping = {}
    for name in SOURCE_NAMES:
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
        # No real result records are read; the source map binds synthetic bytes.
        path.write_bytes((ROOT / name).read_bytes() if name.startswith('scripts/')
                         else b'{"handwritten_source_fixture":true}\n')
        mapping[name] = sha(path)
    original, _, prototype = worker_fixture.configuration()
    original['api_budget_by_task'] = dict(zip(study.TASKS, (160, 80, 80, 80)))
    items = [dict(prototype, task_id=task, source_run=f'P29_{n:02d}_CODE')
             for n, task in enumerate(study.TASKS, 1)]
    plan = dict(study.fixed_fields(), known_tasks=copy.deepcopy(items), source_sha256=mapping)
    study.validate_plan(plan)
    write(root / study.PLAN, plan)
    pre_rows = []
    for item in items:
        conditions = {}
        for mode in study.MODES:
            cfg = study.config_for(original, plan, item['task_id'], mode)
            initial, _ = study.initial_conversation(original, item['public_task']).for_model(
                cfg['observation_page_characters'])
            conditions[mode] = dict(base_messages_sha256=digest(initial))
        pre_rows.append(dict(task_id=item['task_id'], conditions=conditions))
    write(root / audit.PREFLIGHT, dict(rows=pre_rows))
    write(root / audit.ACTIVATION, dict(source_hashes=mapping,
                                      preflight_sha256=sha(root / audit.PREFLIGHT)))
    order = study.run_order()
    completed, batch_rows = [], []
    for index, (number, mode) in enumerate(order):
        rid = study.cell_id(number, mode)
        trial = storage / 'records/context_pilot' / rid
        if partial and index >= 5:
            if index == 5:
                write(trial / 'plan.json', {'handwritten_incomplete_worker': True})
            continue
        item = items[number - 1]
        options = dict(actions=('echo',) * 7 + ('finish',))
        is_unknown = (unknown and index == 11) or (partial and index == 4)
        if is_unknown:
            options = dict(actions=('echo',) * 7, summary_mode='unknown')
        with patch.object(worker_fixture, 'configuration', return_value=(
                copy.deepcopy(original), copy.deepcopy(plan), copy.deepcopy(item))), \
             patch.object(worker_fixture, 'cell_id', side_effect=lambda _, m, n=number: study.cell_id(n, m)):
            result = worker_fixture.fixture(mode=mode, folder=storage, max_calls=80, **options)
            worker_fixture.write_wire_fixture(storage, result)
        is_evaluated = not ((partial and index == 4) or (unevaluated and index == 11))
        if is_evaluated:
            completed.append(rid)
            db = storage / '.runtime/appworld/r18_probe_01/experiments/outputs' / rid / 'tasks' / item['task_id'] / 'dbs/handwritten.json'
            write(db, {'fixture_only': True})
            write(trial / 'evaluation.json', dict(execution_summary_sha256=sha(trial / 'summary.json'),
                evaluation_returned_to_model=False, official_success=not is_unknown,
                evaluation_script_sha256=sha(root / 'scripts/evaluate_context_trial.py'),
                frozen_database_hashes={db.name: sha(db)}))
        batch_rows.append(dict(run_id=rid, evaluation_started_at='synthetic',
                               **({'evaluation_wall_seconds': 0.1} if is_evaluated else {})))
        write(storage / 'records/context_pilot/P140_batch_v01' / (rid + '_worker_exit.json'),
              dict(run_id=rid, status='exited', returncode=-14 if bad_exit and index == 11 else 0,
                   timed_out=False, forced_group_kill=False))
        if missing_completed and index == 11:
            (trial / 'summary.json').unlink()
    stopped = partial or unevaluated
    pipe = storage / 'records/context_pilot/P140_pipeline_v01'
    record = storage / 'records/p2_servers/handwritten'
    server = dict(status='stopped', stop_reason='synthetic', supervisor_pid=10000001, pid=10000002,
        record_directory=str(record.relative_to(storage)), started_at='synthetic', wall_seconds=1000,
        load_wall_seconds=1, sampled_peak_rss_bytes=100.0, peak_system_swap_bytes=0.0, exit_code=0,
        model_revision='synthetic', runtime='synthetic', ctx_size=64000,
        cache_type_k='f16', cache_type_v='f16', memory_note='synthetic')
    write(record / 'summary.json', server)
    (record / 'memory.jsonl').write_text(json.dumps({'rss_bytes': 100.0, 'swap_used_bytes': 0.0}) + '\n')
    write(pipe / 'server_final.json', server)
    write(pipe / 'status.json', dict(status='stopped' if stopped else 'complete', server_stopped=True,
        server_supervisor_pid=server['supervisor_pid'], wall_seconds=1000,
        stages=[dict(mode='batch', wall_seconds=900)]))
    write(storage / 'records/context_pilot/P140_batch_v01/status.json', dict(phase='P140',
        status='stopped' if stopped else 'complete', planned=[study.cell_id(n, m) for n, m in order],
        completed=completed, rows=batch_rows, active=None))
    with patch.object(audit, 'sources', return_value=(plan, original, [], items)), \
         patch.object(audit, 'frozen_hashes', return_value=mapping), \
         patch.object(audit.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='')):
        audited = audit.run(storage, root)
        inspected = session.inspect(storage, root)
    write(root / SESSION, inspected)
    published = build(root) if publish else None
    return audited, inspected, published, root, storage


class RepresentationReportingTests(unittest.TestCase):
    def test_all_twelve_real_workers_audit_session_report_and_copy_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            checked, measured, published, root, _ = closed_fixture(Path(tmp))
            self.assertEqual(checked['audit_errors'], [])
            self.assertEqual(len(published['conditions']), 12)
            self.assertTrue(published['all_twelve_complete_with_known_usage'])
            self.assertEqual(published['usage_count_missing_conditions'], 0)
            self.assertEqual(published['recorded_unknown_usage_calls'], 0)
            self.assertEqual([(r['task_id'], r['checkpoint_representation_mode']) for r in published['conditions']],
                [(study.TASKS[n - 1], m) for n, m in study.run_order()])
            for row in published['conditions']:
                self.assertEqual(row['known_total_tokens'], row['input_tokens'] + row['output_tokens'])
                self.assertFalse(row['checkpoint_representation_contract_failed'])
                self.assertTrue(row['checkpoint_representation_accounting_complete'])
            self.assertEqual(measured['evaluations_completed'], 12)
            self.assertEqual(measured['unknown_cell_full_wall_count'], 0)
            self.assertEqual(measured['baseline_system_swap_bytes'], 0.0)
            target = root / report.DESTINATION
            with (target / 'model_calls.csv').open() as f:
                calls = list(csv.DictReader(f))
            self.assertEqual(len(calls), sum(r['model_calls'] for r in published['conditions']))
            self.assertEqual({c['role'] for c in calls}, {'agent', 'focus'})
            with (target / 'pairs.csv').open() as f:
                self.assertEqual(len(list(csv.DictReader(f))), 8)
            manifest = read(target / 'build_manifest.json')
            self.assertTrue(all(sha(target / name) == value for name, value in manifest['artifact_sha256'].items()))
            self.assertNotIn('fixture output', (target / 'summary.json').read_text())
            with self.assertRaises(FileExistsError):
                build(root)

    def test_full_evaluation_with_unknown_keeps_lower_bound_and_null_cost_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            checked, _, published, _, _ = closed_fixture(Path(tmp), unknown=True)
            self.assertEqual(checked['audit_errors'], [])
            self.assertEqual(published['recorded_unknown_usage_calls'], 1)
            self.assertEqual(published['usage_count_missing_conditions'], 0)
            self.assertTrue(all(v is None for v in published['total_tokens_by_mode'].values()))
            affected = published['conditions'][-1]
            self.assertEqual(affected['record_status'], 'evaluated')
            self.assertFalse(affected['success'])
            self.assertGreater(affected['known_total_tokens'], 0)
            self.assertEqual(affected['unknown_usage_calls'], 1)
            self.assertFalse(affected['checkpoint_representation_accounting_complete'])
            for comparison in published['comparisons']:
                if affected['checkpoint_representation_mode'] in (comparison['baseline'], comparison['candidate']):
                    self.assertIsNone(comparison['all_task_token_difference'])
                    self.assertIsNone(comparison['common_success_token_difference'])
            self.assertFalse(published['development_gate_met'])

    def test_partial_unknown_incomplete_unrun_remain_distinct_and_times_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            checked, measured, published, _, _ = closed_fixture(Path(tmp), partial=True)
            self.assertEqual(checked['audit_errors'], [])
            statuses = [r['record_status'] for r in published['conditions']]
            self.assertEqual([statuses.count(s) for s in ('evaluated','unevaluated','incomplete_worker','not_run')],
                             [4, 1, 1, 6])
            self.assertEqual(published['usage_count_missing_conditions'], 7)
            self.assertEqual(published['recorded_unknown_usage_calls'], 1)
            self.assertIsNone(measured['cell_full_wall_seconds'])
            self.assertEqual(measured['unknown_cell_full_wall_count'], 1)
            self.assertIsNone(measured['evaluation_wall_seconds'])
            self.assertEqual(measured['unknown_evaluation_wall_count'], 1)
            for row in published['conditions'][5:]:
                self.assertIsNone(row['success'])
                self.assertIsNone(row['known_total_tokens'])
                self.assertIsNone(row['input_tokens'])
                self.assertIsNone(row['actual_delta_actor_calls'])
            self.assertTrue(all(v is None for v in published['total_tokens_by_mode'].values()))
            self.assertFalse(published['development_gate_met'])

    def test_known_unevaluated_retains_cost_without_quality_or_full_cohort_exactness(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, published, _, _ = closed_fixture(Path(tmp), unevaluated=True)
            row = published['conditions'][-1]
            self.assertEqual(row['record_status'], 'unevaluated')
            self.assertIsNone(row['success'])
            self.assertEqual(row['unknown_usage_calls'], 0)
            self.assertGreater(row['known_total_tokens'], 0)
            self.assertTrue(all(v is None for v in published['total_tokens_by_mode'].values()))
            self.assertFalse(published['development_gate_met'])

    def test_failed_exit_after_trace_does_not_leak_uncertified_measurements(self):
        with tempfile.TemporaryDirectory() as tmp:
            checked, _, _, root, _ = closed_fixture(Path(tmp), bad_exit=True, publish=False)
            self.assertTrue(checked['audit_errors'])
            row = checked['rows'][-1]
            self.assertEqual(row['record_status'], 'audit_error')
            for field in ('success','known_total_tokens','unknown_usage_calls','input_tokens',
                          'output_tokens','model_calls','actual_delta_actor_calls'):
                self.assertIsNone(row.get(field), field)
            with self.assertRaises(ValueError):
                build(root)
            self.assertFalse((root / report.DESTINATION).exists())

    def test_completed_missing_summary_is_error_and_all_twelve_are_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            checked, _, _, root, _ = closed_fixture(Path(tmp), missing_completed=True, publish=False)
            self.assertEqual(len(checked['rows']), 12)
            self.assertEqual(checked['rows'][-1]['record_status'], 'incomplete_worker')
            self.assertTrue(checked['audit_errors'])
            with self.assertRaises(ValueError):
                build(root)

    def test_source_drift_and_summary_gate_tamper_fail_before_public_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            checked, _, _, root, _ = closed_fixture(Path(tmp), publish=False)
            source = root / 'scripts/checkpoint_delta_envelope_p140.py'
            original_bytes = source.read_bytes(); source.write_bytes(original_bytes + b'\n# changed\n')
            with self.assertRaisesRegex(ValueError, 'reporting_sources_changed'):
                build(root)
            source.write_bytes(original_bytes)
            checked['development_gate_met'] = not checked['development_gate_met']
            write(root / AUDIT, checked)
            server = read(root / SESSION); server['audit_source_sha256'] = sha(root / AUDIT)
            write(root / SESSION, server)
            with self.assertRaisesRegex(ValueError, 'recalculation_mismatch'):
                build(root)
            self.assertFalse((root / report.DESTINATION).exists())


if __name__ == '__main__':
    unittest.main()
