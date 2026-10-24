"""Ensure a stopped P87 batch cannot silently become a complete-case report."""
import contextlib
import csv
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_fixed_reasoning_budget import audit
from build_fixed_reasoning_budget_report import build
from fixed_reasoning_budget_replay import code_completion, equality_summary, output_fingerprints
from run_context_comparison import write_json
from run_handoff_factors import read, sha
from test_fixed_reasoning_budget_audit import fixture


def stopped_fixture(base, attempted):
    root, storage, plan, requests, _ = fixture(base)
    batch_dir = storage / 'records/context_pilot/P87_fixed_reasoning_budget_v01'
    batch = read(batch_dir / 'status.json')
    for row in batch['rows'][attempted:]:
        shutil.rmtree(batch_dir / row['id'])
    batch['rows'] = batch['rows'][:attempted]
    if attempted:
        row = batch['rows'][-1]
        folder = batch_dir / row['id']
        (folder / 'raw_response.json').unlink()
        response = dict(status='error', input_tokens=None, output_tokens=None, wall_seconds=.1)
        write_json(folder / 'response.json', response)
        row.update(status='error', input_tokens=None, output_tokens=None,
                   response_sha256=sha(folder / 'response.json'),
                   **output_fingerprints(response), **code_completion(response))
        for key in ('cache', 'idle', 'done_reason'):
            row.pop(key, None)
    batch.update(status='stopped', model_calls_attempted=attempted,
        known_total_tokens=sum(r['input_tokens'] + r['output_tokens']
                               for r in batch['rows'] if r['status'] == 'ok'),
        unknown_usage_calls=int(attempted > 0), equality_summary=equality_summary(batch['rows']))
    if attempted:
        write_json(batch_dir / 'status.json', batch)
    else:
        shutil.rmtree(batch_dir)
    pipeline_path = storage / 'records/context_pilot/P87_pipeline_v01/status.json'
    write_json(pipeline_path, read(pipeline_path) | {'status': 'stopped'})
    with patch('audit_fixed_reasoning_budget.sources', return_value=(plan, {}, requests)), \
         patch('audit_fixed_reasoning_budget.frozen_hashes', return_value={'synthetic': 'hash'}), \
         patch('audit_fixed_reasoning_budget.subprocess.run') as process, \
         contextlib.redirect_stdout(io.StringIO()):
        process.return_value.returncode = 1
        process.return_value.stdout = ''
        report = audit(storage, root)
    return root, report


class StoppedReasoningBudgetReportingTests(unittest.TestCase):
    def test_first_attempt_unknown_retains_seven_unattempted_slots(self):
        with tempfile.TemporaryDirectory() as temp:
            _, report = stopped_fixture(Path(temp), 1)
        self.assertEqual(report['audit_errors'], [])
        self.assertEqual(report['unknown_usage_calls'], 1)
        self.assertEqual(report['known_total_tokens'], 0)
        self.assertEqual([r['record_status'] for r in report['rows']],
                         ['unknown_usage'] + ['unattempted'] * 7)
        self.assertTrue(all(r['output_tokens'] is None for r in report['rows']))
        self.assertIsNone(report['local_code_completion_improvement_identified'])

    def test_no_generation_is_not_eight_failures(self):
        with tempfile.TemporaryDirectory() as temp:
            _, report = stopped_fixture(Path(temp), 0)
        self.assertEqual(report['audit_errors'], [])
        self.assertEqual(report['model_calls_attempted'], 0)
        self.assertEqual(report['unknown_usage_calls'], 0)
        self.assertEqual([r['record_status'] for r in report['rows']], ['unattempted'] * 8)
        self.assertTrue(all(r['complete_code_submission'] is None for r in report['rows']))
        self.assertFalse(report['diagnostic_usable'])

    def test_csv_preserves_late_unknown_and_unattempted_values(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root, report = stopped_fixture(base, 4)
            self.assertEqual(report['known_total_tokens'], 66615)
            self.assertEqual(report['audit_errors'], [])
            # Source validation is covered by the frozen audit. This test targets
            # rendering of the already-audited synthetic stopped table only.
            with patch('build_fixed_reasoning_budget_report.validated',
                       return_value=({}, {'input_count_requests': 4}, report, {})):
                manifest = build(base / 'output', root)
            with (base / 'output/all_eight_generations.csv').open() as f:
                rows = list(csv.DictReader(f))
            summary = json.loads((base / 'output/all_comparisons.json').read_text())
        self.assertEqual(len(rows), 8)
        self.assertEqual([r['record_status'] for r in rows],
                         ['audited'] * 3 + ['unknown_usage'] + ['unattempted'] * 4)
        for row in rows[3:]:
            self.assertEqual(row['input_tokens'], '')
            self.assertEqual(row['output_tokens'], '')
            self.assertEqual(row['complete_code_submission'], '')
        self.assertEqual(sum(g['known'] for g in summary['groups'].values()), 3)
        self.assertEqual(manifest['unknown_usage_calls'], 1)
        self.assertIsNone(manifest['local_code_completion_improvement_identified'])
        self.assertFalse(manifest['visual_reviewed'])


if __name__ == '__main__':
    unittest.main()
