"""Protect pending/failed distinctions and the declared scope of the analysis."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from summarize_pro_comparison import collect_trial, comparison_status, load_batch


class ComparisonReportingTests(unittest.TestCase):
    def test_missing_trial_is_not_a_zero_cost_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            row = collect_trial(Path(folder), {
                'trial_id': 'P5_PRO_SINGLE_01', 'strategy': 'single', 'plan_sha256': 'unused'})
        self.assertEqual(row['stage'], 'not_started')
        self.assertIsNone(row['result'])
        self.assertNotIn('recorded_tokens', row)
        self.assertNotIn('resolved', row)

    def test_wrong_phase_cannot_be_used_as_the_matched_control(self):
        with tempfile.TemporaryDirectory() as folder:
            storage = Path(folder)
            directory = storage/'records/pro_pilot/P5_PRO_SINGLE_01'
            directory.mkdir(parents=True)
            (directory/'summary.json').write_text(json.dumps({
                'phase': 'P4', 'strategy': 'single', 'plan_sha256': 'same',
                'calls': [], 'total_recorded_tokens': 586166,
                'usage_complete': True, 'started_at': '2026-10-20T09:10:44+00:00'}))
            with self.assertRaisesRegex(ValueError, 'identity or plan differs'):
                collect_trial(storage, {
                    'trial_id': 'P5_PRO_SINGLE_01', 'strategy': 'single', 'plan_sha256': 'same'})

    def test_pending_evaluation_does_not_complete_comparison(self):
        rows = [{'stage': 'evaluated'}, {'stage': 'awaiting_evaluation'}]
        self.assertEqual(comparison_status(rows, {'status': 'running'}), 'in_progress')
        self.assertEqual(comparison_status(rows, {'status': 'error'}), 'requires_review')
        self.assertEqual(comparison_status(
            [{'stage': 'evaluated'}, {'stage': 'evaluated'}], {'status': 'completed'}), 'completed')
        self.assertEqual(comparison_status(
            [{'stage': 'evaluated'}, {'stage': 'record_error'}], {'status': 'completed'}), 'requires_review')

    def test_saved_batch_tampering_and_outside_identifiers_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            storage = Path(folder)
            directory = storage/'records/pro_batches/P5_01'
            directory.mkdir(parents=True)
            plan = {'batch_id': 'P5_01', 'trial_count': 2, 'trials': [
                {'trial_id': 'pair', 'strategy': 'fixed_pair'},
                {'trial_id': 'single', 'strategy': 'single'}]}
            path = directory/'plan.json'
            path.write_text(json.dumps(plan))
            (directory/'summary.json').write_text(json.dumps({
                'plan_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}))
            self.assertEqual(load_batch(storage, 'P5_01')[0], plan)
            plan['trials'][1]['trial_id'] = '../P4'
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, 'hash differs'):
                load_batch(storage, 'P5_01')
            with self.assertRaisesRegex(ValueError, 'identifier'):
                load_batch(storage, '../P4')


if __name__ == '__main__':
    unittest.main()
