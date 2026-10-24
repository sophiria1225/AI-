"""Guard P88 full-cohort reporting against selective and missing-data claims."""
import csv
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_whole_task_reasoning_budget_report import (FILES, EXECUTED_HEAD, build,
    contributions, cost, totals, validated)
from whole_task_reasoning_budget import POLICIES, cell_id, run_order, summarize
from run_context_comparison import write_json
from run_handoff_factors import read, sha

ROOT = Path(__file__).resolve().parents[1]


def synthetic_rows(plan):
    rows = []
    for n, policy in run_order():
        value = 100 if policy == 'unlimited' else 80
        rows.append(dict(run_id=cell_id(n, policy), task_id=plan['known_tasks'][n-1]['task_id'],
            reasoning_policy=policy, time_visibility='not_exposed', record_status='evaluated',
            success=True, stop_reason='agent_finished', known_total_tokens=value,
            unknown_usage_calls=0, model_calls=1, input_tokens=value-20, output_tokens=20,
            cached_input_tokens=10, api_requests=2, invocation_exceptions=0,
            setup_wall_seconds=.2, wall_seconds=1.1, cleanup_wall_seconds=.1, full_wall_seconds=1.4))
    return rows


def fixture(base, changed_rows=None):
    root = base / 'repo'; plan = read(ROOT / FILES[0]); rows = changed_rows or synthetic_rows(plan)
    for folder in ('configs', 'reports'):
        (root / folder).mkdir(parents=True, exist_ok=True)
    write_json(root / FILES[0], plan)
    frozen = root / 'synthetic_frozen.txt'; frozen.write_text('handwritten synthetic fixture only')
    pre = dict(status='complete', all_eight_inputs_checked=True, input_count_requests=8,
        failed_input_count_requests=0, git_commit=EXECUTED_HEAD,
        source_hashes={'synthetic_frozen.txt': sha(frozen)}, rows=[
            dict(task_id=item['task_id'], conditions={p: dict(input_tokens=10,
                model_messages_sha256='synthetic_input', reasoning_budget_tokens=b)
                for p, b in zip(POLICIES, (-1, 2048))}) for item in plan['known_tasks']])
    write_json(root / FILES[2], pre)
    activation = dict(preflight_sha256=sha(root / FILES[2]), source_hashes=pre['source_hashes'],
        all_eight_conditions_frozen_before_generation=True)
    write_json(root / FILES[4], activation)
    report = dict(rows=rows, audit_errors=[], batch_status='complete',
        plan_sha256=sha(root / FILES[0]), activation_sha256=sha(root / FILES[4]),
        owned_processes_absent=True, pipeline_status_sha256='synthetic_pipeline', **summarize(rows, []))
    write_json(root / FILES[1], report)
    session = dict(status='stopped', owned_processes_absent=True,
        audit_source_sha256=sha(root / FILES[1]), pipeline_source_sha256='synthetic_pipeline',
        wall_seconds=15, load_wall_seconds=2, cell_full_wall_seconds=11.2,
        evaluation_wall_seconds=.8, sampled_peak_rss_bytes=1024, peak_system_swap_bytes=0)
    write_json(root / FILES[3], session)
    return root, plan, rows


def replace_report(root, change):
    report = read(root / FILES[1]); change(report); write_json(root / FILES[1], report)
    session = read(root / FILES[3]); session['audit_source_sha256'] = sha(root / FILES[1])
    write_json(root / FILES[3], session)


class WholeTaskReasoningBudgetReportingTests(unittest.TestCase):
    def test_all_eight_and_stopped_server_are_required(self):
        for kind in ('missing', 'active', 'false_gate', 'changed_source', 'changed_order'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                root, _, _ = fixture(Path(temp)); validated(root)
                if kind == 'missing': replace_report(root, lambda r: r['rows'].pop())
                elif kind == 'active':
                    path = root / FILES[3]; write_json(path, read(path) | {'status': 'ready'})
                elif kind == 'false_gate': replace_report(root, lambda r: r.update(development_gate_met=False))
                elif kind == 'changed_source': (root / 'synthetic_frozen.txt').write_text('changed')
                else: replace_report(root, lambda r: r['rows'].reverse())
                with self.assertRaises(ValueError): validated(root)

    def test_same_success_count_cannot_hide_per_task_loss(self):
        with tempfile.TemporaryDirectory() as temp:
            root, plan, rows = fixture(Path(temp))
            rows[0]['success'] = False  # H gain on task 1.
            rows[2]['success'] = False  # H loss on task 2 (alternating order).
            root, _, _ = fixture(Path(temp), rows)
            _, report, _, _, _ = validated(root)
        a, b = [totals(rows, p) for p in POLICIES]
        self.assertEqual(a['successes'], b['successes'])
        self.assertEqual(report['paired_success_losses'], 1)
        self.assertEqual(report['paired_success_gains'], 1)
        self.assertFalse(report['development_gate_met'])

    def test_whole_cohort_contributions_sum_without_dropping_failures(self):
        plan = read(ROOT / FILES[0]); rows = synthetic_rows(plan)
        for row in rows:
            if row['task_id'] == plan['known_tasks'][1]['task_id']: row['success'] = False
            if row['task_id'] == plan['known_tasks'][2]['task_id'] and row['reasoning_policy'] == 'unlimited': row['success'] = False
        report = summarize(rows, []); parts = contributions(report)
        self.assertEqual([parts[k]['task_count'] for k in parts], [2, 1, 1, 0])
        self.assertEqual([parts[k]['half_minus_unlimited_tokens'] for k in parts], [-40, -20, -20, 0])
        self.assertEqual(sum(p['half_minus_unlimited_tokens'] for p in parts.values()),
            report['half_minus_unlimited_whole_task_tokens'])

    def test_unknown_usage_keeps_known_subtotal_but_no_full_total_or_contribution(self):
        rows = synthetic_rows(read(ROOT / FILES[0])); rows[-1]['unknown_usage_calls'] = 1
        r = totals(rows, 'unlimited')
        self.assertEqual(r['known_total_tokens'], 400)
        self.assertIsNone(r['full_logical_tokens'])
        self.assertIn('＋不明1', cost(r))
        report = summarize(rows, [])
        self.assertTrue(all(x['half_minus_unlimited_tokens'] is None for x in contributions(report).values()))
        self.assertFalse(report['development_gate_met'])

    def test_missing_cache_is_not_zero_cache(self):
        rows = synthetic_rows(read(ROOT / FILES[0])); rows[0]['cached_input_tokens'] = None
        summary = totals(rows, 'unlimited')
        self.assertIsNone(summary['cached_input_tokens'])
        self.assertIsNone(summary['known_uncached_input_tokens'])
        self.assertEqual(summary['input_tokens'], 320)

    def test_unattempted_is_neither_failure_nor_zero_cost_and_csv_keeps_blanks(self):
        plan = read(ROOT / FILES[0]); rows = synthetic_rows(plan)
        for row in rows[3:]:
            for key in list(row):
                if key not in ('run_id', 'task_id', 'reasoning_policy', 'time_visibility'): del row[key]
            row.update(record_status='not_run', success=None, known_total_tokens=None, unknown_usage_calls=None)
        rows[2]['unknown_usage_calls'] = 1
        with tempfile.TemporaryDirectory() as temp:
            root, _, _ = fixture(Path(temp), rows)
            replace_report(root, lambda r: r.update(batch_status='stopped'))
            with patch('build_whole_task_reasoning_budget_report.figure'):
                manifest = build(Path(temp) / 'output', root)
            with (Path(temp) / 'output/all_eight_conditions.csv').open() as f: saved = list(csv.DictReader(f))
        self.assertEqual(len(saved), 8)
        self.assertEqual(manifest['all_planned_rows'], 8)
        self.assertEqual([r['success'] for r in saved[3:]], ['']*5)
        self.assertEqual([r['known_total_tokens'] for r in saved[3:]], ['']*5)
        self.assertEqual(sum(r['failures'] for r in manifest['totals']), 0)
        self.assertEqual(sum(r['evaluated'] for r in manifest['totals']), 3)
        self.assertEqual(sum(r['unmeasured'] for r in manifest['totals']), 5)
        self.assertFalse(manifest['visual_reviewed'])
        self.assertFalse(manifest['development_gate_met'])

    def test_zero_attempts_does_not_become_eight_failures_or_zero_total(self):
        plan = read(ROOT / FILES[0]); rows = [dict(run_id=cell_id(n, p),
            task_id=plan['known_tasks'][n-1]['task_id'], reasoning_policy=p, record_status='not_run',
            success=None, known_total_tokens=None, unknown_usage_calls=None) for n, p in run_order()]
        for p in POLICIES:
            summary = totals(rows, p)
            self.assertEqual(summary['evaluated'], 0); self.assertEqual(summary['failures'], 0)
            self.assertEqual(summary['unmeasured'], 4)
            self.assertIsNone(summary['full_logical_tokens']); self.assertIsNone(summary['known_total_tokens'])
            self.assertEqual(cost(summary), '未計測')
        self.assertEqual(contributions(summarize(rows, []))['unevaluated']['task_count'], 4)


if __name__ == '__main__':
    unittest.main()
