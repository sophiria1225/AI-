"""Handwritten diagnostic rows and closed-report files; no external actions."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import whole_task_object_timing_p141 as study

BUILDER = 'scripts/build_object_timing_summary_p141.py'


def rows():
    return [dict(run_id=study.cell_id(1, mode), task_id=study.TASKS[0],
        object_timing_mode=mode, checkpoint_representation_mode=mode, model_seed=57,
        record_status='evaluated', success=True, known_total_tokens=tokens,
        unknown_usage_calls=0, request_checks=[])
        for mode, tokens in zip(study.MODES, (300, 200, 100))]


def plan():
    return dict(study.fixed_fields(), known_tasks=[dict(task_id=study.TASKS[0],
        source_run='P29_04_CODE')], source_sha256={name: 'a' * 64 for name in study.REQUIRED_SOURCES})


def closed_fixture(root, data, errors=()):
    for name in study.REQUIRED_SOURCES:
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((ROOT / name).read_bytes() if name == BUILDER else b'synthetic source only\n')
    p = plan()
    p['source_sha256'] = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                         for name in study.REQUIRED_SOURCES}
    pp = root / study.PLAN
    pp.parent.mkdir(parents=True, exist_ok=True)
    pp.write_text(json.dumps(p))
    audit = dict(phase='P141', batch_status='stopped', owned_processes_absent=True,
        rows=data, audit_errors=list(errors), plan_sha256=hashlib.sha256(pp.read_bytes()).hexdigest(),
        **study.summarize(data, list(errors)))
    reports = root / 'reports'
    reports.mkdir()
    ap = reports / 'P141_comparison.json'
    ap.write_text(json.dumps(audit))
    (reports / 'P141_server_session.json').write_text(json.dumps(dict(phase='P141',
        status='stopped', owned_processes_absent=True,
        audit_source_sha256=hashlib.sha256(ap.read_bytes()).hexdigest())))
    spec = importlib.util.spec_from_file_location('synthetic_P141_builder', root / BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ObjectTimingReportingTests(unittest.TestCase):
    def test_improving_successful_all_known_still_never_adopts(self):
        out = study.summarize(rows(), [])
        self.assertEqual([c['all_task_token_difference'] for c in out['comparisons']], [-100, -200, -100])
        self.assertTrue(out['all_three_complete_with_known_usage'])
        self.assertFalse(out['development_gate_met'])
        self.assertFalse(out['scientific_adoption_evaluated'])
        self.assertTrue(all(not c['comparison_gate_met'] for c in out['comparisons']))
        self.assertIsNone(out['comparisons'][0]['timing_prefix_identity']['canonical_match'])

    def test_unknown_pair_and_empty_common_remain_null(self):
        data = rows()
        data[2].update(success=False, unknown_usage_calls=1)
        out = study.summarize(data, [])
        self.assertEqual(out['recorded_unknown_usage_calls'], 1)
        self.assertTrue(all(x is None for x in out['total_tokens_by_mode'].values()))
        self.assertIsNone(out['comparisons'][0]['all_task_token_difference'])
        self.assertIsNone(out['comparisons'][0]['common_success_token_difference'])
        data[2]['unknown_usage_calls'] = 0
        self.assertIsNone(study.summarize(data, [])['comparisons'][0]['common_success_token_difference'])

    def test_notrun_cost_is_not_imputed_and_errors_remain(self):
        data = rows()
        data[1].update(record_status='not_run', success=None, known_total_tokens=None,
                       unknown_usage_calls=None)
        out = study.summarize(data, ['synthetic audit error'])
        self.assertEqual(out['planned_rows'], 3)
        self.assertIsNone(out['known_token_subtotals_by_mode'][study.MODES[1]])
        self.assertEqual(out['unevaluated_counts'][study.MODES[1]], 1)
        self.assertEqual(out['usage_count_missing_conditions'], 1)
        self.assertEqual(out['audit_errors_count'], 1)

    def test_partial_duplicate_old_mode_and_order_rejected(self):
        invalid = [rows()[:2], [rows()[0], rows()[1], rows()[1]], list(reversed(rows()))]
        old = rows()
        old[1]['object_timing_mode'] = 'exposure_delta'
        invalid.append(old)
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                study.summarize(value, [])

    def test_plan_original_task4_caps_and_diagnostic_scope_fixed(self):
        good = plan()
        study.validate_plan(good)
        self.assertEqual(good['source_runs'], ['P29_04_CODE'])
        self.assertEqual(good['api_budget_by_task_slot'], [80])
        for key, value in [('max_cells', 1), ('model_seed', 157),
                           ('scientific_adoption_evaluated', True), ('max_wall_seconds', 3600)]:
            bad = copy.deepcopy(good)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                study.validate_plan(bad)
        good['known_tasks'][0]['source_run'] = 'P29_01_CODE'
        with self.assertRaises(ValueError):
            study.validate_plan(good)

    def test_partial_closed_build_retains_all_slots_errors_and_exclusivity(self):
        data = rows()
        data[1].update(record_status='audit_error', success=None, known_total_tokens=None,
                       unknown_usage_calls=None)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            builder = closed_fixture(root, data, ['synthetic audit error'])
            result = builder.build(root)
            self.assertEqual(len(result['conditions']), 3)
            self.assertIsNone(result['conditions'][1]['known_total_tokens'])
            self.assertEqual(result['audit_errors_count'], 1)
            self.assertFalse(result['scientific_adoption_evaluated'])
            self.assertFalse(result['development_gate_met'])
            with self.assertRaises(FileExistsError):
                builder.build(root)

    def test_wrong_phase_live_session_or_changed_source_cannot_publish(self):
        for kind in ('phase', 'live', 'source'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                builder = closed_fixture(root, rows())
                if kind == 'source':
                    (root / study.REQUIRED_SOURCES[0]).write_text('changed')
                else:
                    p = root / 'reports/P141_server_session.json'
                    value = json.loads(p.read_text())
                    value['phase' if kind == 'phase' else 'owned_processes_absent'] = 'P140' if kind == 'phase' else False
                    p.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    builder.build(root)
                self.assertFalse((root / study.MATERIAL).exists())


if __name__ == '__main__':
    unittest.main()
