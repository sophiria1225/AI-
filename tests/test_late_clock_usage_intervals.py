import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import inspect_late_clock_usage_intervals as intervals
from late_clock_comparison import cell_id, run_order, summarize


def fixture():
    plan = json.loads((ROOT / intervals.PLAN).read_text())
    cells, rows = [], []
    for rep, number, policy in run_order():
        cost = {'measured': 100, 'not_exposed': 90, 'late_half': 80}[policy]
        c = dict(run_id=cell_id(rep, number, policy), repetition=rep,
                 task_id=plan['known_tasks'][number - 1]['task_id'], time_visibility=policy,
                 record_status='evaluated', success=number != 4, model_calls=1,
                 known_total_tokens=cost, unknown_usage_calls=0, api_requests=1)
        cells.append(c)
        rows.append({**{k: c[k] for k in ('run_id', 'repetition', 'task_id', 'time_visibility', 'success')},
                     'call_id': 'call_01', 'complete_usage': True, 'terminal_usage_imputed': False,
                     'logical_tokens_lower_bound': cost, 'logical_tokens_upper_bound': cost})
    return cells, rows, plan


def unknown(cells, rows, *, policy='late_half', lower=0, upper=1000):
    i = next(i for i, c in enumerate(cells)
             if c['run_id'] == cell_id(1, 4, policy))
    cells[i].update(unknown_usage_calls=1, known_total_tokens=0)
    rows[i].update(complete_usage=False, logical_tokens_lower_bound=lower,
                   logical_tokens_upper_bound=upper)


def closure(cells):
    ids = [c['run_id'] for c in cells]
    pipeline = dict(status='complete', finished_at='closed', server_stopped=True,
                    git_commit=intervals.P82_COMMIT)
    batch = dict(status='complete', active=None, git_commit=intervals.P82_COMMIT,
                 rows=copy.deepcopy(cells), planned=ids, completed=ids)
    report = dict(phase='P82', batch_status='complete', audit_errors=[], rows=cells,
                  **summarize(cells, []))
    return pipeline, batch, report


class LateClockIntervalTests(unittest.TestCase):
    def test_all_24_and_failed_task_costs_remain(self):
        cells, rows, _ = fixture()
        before = copy.deepcopy((cells, rows))
        result = intervals.summarize_intervals(rows, cells)
        self.assertEqual(len(result['cells']), 24)
        m, h = result['combined']
        self.assertEqual(m['total']['late_half_minus_baseline'], [-160, -160])
        self.assertEqual(h['total']['late_half_minus_baseline'], [-80, -80])
        self.assertEqual(m['both_success']['late_half_minus_baseline'], [-120, -120])
        self.assertEqual(m['both_failure']['late_half_minus_baseline'], [-40, -40])
        self.assertEqual(m['both_failure']['paired_task_observations'], 2)
        self.assertEqual(result['independent_tasks'], 4)
        self.assertFalse(result['repetitions_are_independent_tasks'])
        self.assertEqual((cells, rows), before)

    def test_unknown_in_late_or_baseline_is_propagated_with_correct_sign(self):
        for policy, expected in (('late_half', [-160, 840]), ('measured', [-980, 20])):
            cells, rows, _ = fixture()
            unknown(cells, rows, policy=policy)
            result = intervals.summarize_intervals(rows, cells)
            pair = result['repetitions'][0]['comparisons'][0]
            self.assertEqual(pair['total']['late_half_minus_baseline'], expected)
            self.assertEqual(pair['total']['original_unknown_usage_calls'], 1)
            self.assertEqual(pair['both_failure']['original_unknown_usage_calls'], 1)

    def test_even_wholly_lower_interval_does_not_replace_original_gate(self):
        cells, rows, plan = fixture()
        unknown(cells, rows, lower=70, upper=80)
        p, b, r = closure(cells)
        original = intervals.validate_closure(p, b, r, plan)
        result = intervals.summarize_intervals(rows, cells)
        self.assertEqual(result['repetitions'][0]['comparisons'][0]['total']['late_half_minus_baseline'], [-90, -80])
        self.assertFalse(original['all_repetition_gates_met'])
        self.assertEqual(result['original_decisions'], original)
        self.assertFalse(original['repetitions'][0]['comparisons'][0]['all_eight_complete_with_known_usage'])

    def test_missing_reordered_duplicate_or_wrong_task_cells_are_rejected(self):
        for kind in ('missing', 'reordered', 'duplicate', 'wrong_task'):
            cells, rows, _ = fixture()
            if kind == 'missing': cells.pop()
            if kind == 'reordered': cells.reverse()
            if kind == 'duplicate': cells[-1] = cells[0]
            if kind == 'wrong_task': cells[-1]['task_id'] = cells[0]['task_id']
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                intervals.summarize_intervals(rows, cells)

    def test_missing_duplicate_or_misaccounted_calls_are_rejected(self):
        for kind in ('missing', 'duplicate', 'known_sum', 'unknown_count', 'metadata'):
            cells, rows, _ = fixture()
            if kind == 'missing': rows.pop()
            if kind == 'duplicate': rows.append(copy.deepcopy(rows[0]))
            if kind == 'known_sum': cells[0]['known_total_tokens'] += 1
            if kind == 'unknown_count': cells[0]['unknown_usage_calls'] = 1
            if kind == 'metadata': rows[0]['time_visibility'] = 'late_half'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                intervals.summarize_intervals(rows, cells)

    def test_invalid_or_imputed_intervals_are_rejected(self):
        for change in ({'logical_tokens_lower_bound': True}, {'logical_tokens_lower_bound': -1},
                       {'logical_tokens_upper_bound': 99}, {'logical_tokens_upper_bound': 101},
                       {'complete_usage': 1}, {'terminal_usage_imputed': True}, {'success': None}):
            cells, rows, _ = fixture()
            rows[0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                intervals.summarize_intervals(rows, cells)

    def test_discordant_outcomes_do_not_enter_success_or_failure_pairs(self):
        cells, rows, _ = fixture()
        i = next(i for i, c in enumerate(cells) if c['run_id'] == cell_id(1, 1, 'late_half'))
        cells[i]['success'] = rows[i]['success'] = False
        result = intervals.summarize_intervals(rows, cells)['repetitions'][0]['comparisons'][0]
        self.assertEqual(result['both_success']['paired_task_observations'], 2)
        self.assertEqual(result['both_failure']['paired_task_observations'], 1)
        self.assertEqual(result['discordant']['paired_task_observations'], 1)

    def test_running_changed_or_unaudited_closure_cannot_be_used(self):
        for kind in ('running', 'server', 'active', 'commit', 'audit', 'gate', 'batch'):
            cells, _, plan = fixture()
            p, b, r = closure(cells)
            if kind == 'running': p['status'] = 'running'
            if kind == 'server': p['server_stopped'] = False
            if kind == 'active': b['active'] = cells[-1]['run_id']
            if kind == 'commit': b['git_commit'] = 'other'
            if kind == 'audit': r['audit_errors'] = ['error']
            if kind == 'gate': r['all_repetition_gates_met'] = False
            if kind == 'batch': b['rows'][0]['known_total_tokens'] += 1
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                intervals.validate_closure(p, b, r, plan)

    def test_live_run_rejected_before_log_read_or_process_checks(self):
        cells, _, plan = fixture()
        p, b, r = closure(cells)
        p['status'] = 'running'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(intervals, 'read', side_effect=[p, b, r, plan, {}]) as reads, \
                    patch.object(intervals, 'parse_numeric_log') as parse, \
                    patch.object(intervals.subprocess, 'run') as proc:
                with self.assertRaisesRegex(ValueError, 'closed_frozen_audited'):
                    intervals.run(root, root, root)
                self.assertEqual(reads.call_count, 5)
                parse.assert_not_called()
                proc.assert_not_called()


if __name__ == '__main__':
    unittest.main()
