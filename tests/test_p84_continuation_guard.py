import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from late_clock_comparison import cell_id, run_order, summarize
from p84_continuation_guard import P82_COMMIT, validate_closure
from wait_for_p84_continuation import read_pending
import wait_for_p84_continuation as waiter

ROOT = Path(__file__).resolve().parents[1]


def fixture(late_cost=80):
    plan = json.loads((ROOT / 'configs/P82_late_clock_comparison_v01.json').read_text())
    rows = [{'run_id': cell_id(rep, n, policy), 'repetition': rep,
        'task_id': plan['known_tasks'][n - 1]['task_id'], 'time_visibility': policy,
        'record_status': 'evaluated', 'success': n < 4, 'unknown_usage_calls': 0,
        'known_total_tokens': {'measured': 100, 'not_exposed': 90, 'late_half': late_cost}[policy],
        'model_calls': 1, 'api_requests': 1} for rep, n, policy in run_order()]
    report = {'phase': 'P82', 'batch_status': 'complete', 'rows': rows,
              'audit_errors': [], **summarize(rows, [])}
    ids = [r['run_id'] for r in rows]
    batch = {'status': 'complete', 'git_commit': P82_COMMIT, 'active': None,
             'planned': ids, 'completed': list(ids), 'rows': copy.deepcopy(rows)}
    pipeline = {'status': 'complete', 'finished_at': 'fixture', 'server_stopped': True,
                'git_commit': P82_COMMIT}
    return pipeline, batch, report, plan


class P84ContinuationTests(unittest.TestCase):
    def test_p84_question_does_not_select_on_whether_late_half_wins(self):
        for cost, wins in ((80, True), (95, False), (110, False)):
            decision = validate_closure(*fixture(cost))
            self.assertEqual(decision['P82_all_repetition_gates_met'], wins)
            self.assertFalse(decision['P82_gates_used_to_select_P84'])
            self.assertEqual(sum(len(r['comparisons']) for r in decision['P82_repetitions']), 4)
            self.assertEqual(decision['P84_max_generations'], 18)

    def test_active_failed_unclosed_or_different_pipeline_cannot_allocate(self):
        for key, value in [('status', 'stopped'), ('finished_at', None),
                           ('server_stopped', False), ('git_commit', 'other')]:
            args = fixture(); args[0][key] = value
            with self.assertRaises(ValueError): validate_closure(*args)
        args = fixture(); args[1]['active'] = args[1]['planned'][-1]
        with self.assertRaises(ValueError): validate_closure(*args)

    def test_missing_duplicate_reordered_or_wrong_task_rows_are_rejected(self):
        for kind in ('missing', 'duplicate', 'reordered', 'wrong_task'):
            args = fixture()
            if kind == 'missing': args[1]['completed'].pop()
            if kind == 'duplicate': args[2]['rows'][-1] = args[2]['rows'][0]
            if kind == 'reordered': args[2]['rows'].reverse()
            if kind == 'wrong_task': args[2]['rows'][0]['task_id'] = 'outside'
            with self.assertRaises(ValueError): validate_closure(*args)

    def test_unknown_or_unevaluated_conditions_remain_pending_manual_review(self):
        for field, value in [('unknown_usage_calls', 1), ('success', None),
                              ('record_status', 'unevaluated'), ('known_total_tokens', None)]:
            args = fixture(); args[2]['rows'][0][field] = value
            with self.assertRaises(ValueError): validate_closure(*args)

    def test_audit_errors_stale_gates_and_disagreeing_accounting_are_rejected(self):
        for kind in ('audit_error', 'gate', 'batch_cost', 'gate_detail'):
            args = fixture()
            if kind == 'audit_error': args[2]['audit_errors'] = ['fixture discrepancy']
            if kind == 'gate': args[2]['all_repetition_gates_met'] = False
            if kind == 'batch_cost': args[1]['rows'][0]['known_total_tokens'] += 1
            if kind == 'gate_detail': args[2]['repetitions'][0]['comparisons'][0]['development_gate_met'] = False
            with self.assertRaises(ValueError): validate_closure(*args)

    def test_missing_or_partial_status_never_authorizes_a_start(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'status.json'
            self.assertIsNone(read_pending(path))
            path.write_text('{"status":')
            self.assertIsNone(read_pending(path))
            path.write_text('{"status":"complete"}')
            self.assertEqual(read_pending(path), {'status': 'complete'})

    def test_stop_marker_prevents_CI_or_exec_and_leaves_one_shot_record(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(waiter, 'checked_ci') as ci, \
                patch.object(waiter.os, 'execv') as execute:
            root = Path(folder); (root / '.runtime').mkdir()
            (root / '.runtime/P84.stop').touch()
            self.assertEqual(waiter.run(root, root, root, root, 'fixture'), 1)
            ci.assert_not_called(); execute.assert_not_called()
            state = json.loads((root / '.runtime/P84_continuation_status.json').read_text())
            self.assertEqual(state['status'], 'stopped')
            self.assertEqual(state['error_type'], 'InterruptedError')
            original = (root / '.runtime/P84_continuation.lock').read_bytes()
            with self.assertRaises(FileExistsError): waiter.run(root, root, root, root, 'fixture')
            self.assertEqual((root / '.runtime/P84_continuation.lock').read_bytes(), original)

    def test_failed_closed_evidence_does_not_write_decision_or_exec_pipeline(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / '.runtime').mkdir()
            p82, p84 = root / 'p82', root / 'p84'
            def git_output(command, cwd, **_):
                if command[1] == 'status': return ''
                return {p82: waiter.P82_COMMIT, p84: waiter.P84_COMMIT}.get(cwd, 'fixture')
            with patch.object(waiter.subprocess, 'check_output', side_effect=git_output), \
                 patch.object(waiter, 'checked_ci', return_value=[]), \
                 patch.object(waiter, 'read_pending', return_value={'status': 'complete', 'finished_at': 'fixture'}), \
                 patch.object(waiter, 'bind_closed_evidence', side_effect=ValueError('changed_source')), \
                 patch.object(waiter.os, 'execv') as execute:
                self.assertEqual(waiter.run(root, p82, root, p84, 'fixture'), 1)
                execute.assert_not_called()
            self.assertFalse((root / '.runtime/P84_execution_decision.json').exists())


if __name__ == '__main__': unittest.main()
