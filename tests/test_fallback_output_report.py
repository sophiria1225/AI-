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
from audit_fallback_output import audit
from build_fallback_output_report import build, comparison_matrix, validated
from fallback_output_replay import equality_summary
from run_context_comparison import write_json
from run_handoff_factors import sha
from test_fallback_output_audit import fixture

ROOT = Path(__file__).resolve().parents[1]


def report_fixture(base, unknown=False, attempted=18, truncated=False):
    root, storage, plan, requests, _ = fixture(base, unknown=unknown)
    (root / 'scripts').mkdir(); (root / 'configs').mkdir()
    shutil.copyfile(ROOT / 'scripts/audit_fallback_output.py', root / 'scripts/audit_fallback_output.py')
    full_plan = json.loads((ROOT / 'configs/P84_fallback_output_v01.json').read_text())
    for target, source in zip(full_plan['cases'], plan['cases'], strict=True):
        target['source_request_sha256'] = source['source_request_sha256']
    write_json(root / 'configs/P84_fallback_output_v01.json', full_plan)
    hashes = {name: sha(root / name) for name in ('scripts/audit_fallback_output.py', 'configs/P84_fallback_output_v01.json')}
    write_json(root / 'reports/P84_initial_checks.json', dict(status='complete', input_count_requests=6, source_sha256=hashes))
    batch_path = storage / 'records/context_pilot/P84_fallback_output_v01/status.json'
    batch = json.loads(batch_path.read_text())
    if attempted < 18:
        batch['rows'] = batch['rows'][:attempted]
        batch.update(status='stopped', model_calls_attempted=attempted,
            known_total_tokens=sum(r['input_tokens'] + r['output_tokens'] for r in batch['rows']),
            equality_summary=equality_summary(batch['rows']))
        write_json(batch_path, batch)
        pipeline_path = storage / 'records/context_pilot/P84_pipeline_v01/status.json'
        pipeline = json.loads(pipeline_path.read_text()); pipeline['status'] = 'stopped'
        write_json(pipeline_path, pipeline)
    with patch('audit_fallback_output.sources', return_value=(plan, {}, requests)), \
         patch('audit_fallback_output.frozen_hashes', return_value=hashes), \
         patch('audit_fallback_output.subprocess.run') as process, \
         contextlib.redirect_stdout(io.StringIO()):
        process.return_value.returncode = 1; process.return_value.stdout = ''
        result = audit(storage, root)
    if truncated:
        # A valid audited receipt may be token-capped: preserve its known cost,
        # but remove eligibility for a complete-output diagnostic conclusion.
        result['rows'][0].update(done_reason='length', complete_generation=False)
        result['equality_summary'] = equality_summary(result['rows'])
        result.update(diagnostic_usable=False, local_public_output_difference_identified=None)
        write_json(root / 'reports/P84_fallback_output_replay.json', result)
    return root, result


class FallbackOutputReportTests(unittest.TestCase):
    def test_full_report_retains_all_slots_contrasts_and_cost(self):
        with tempfile.TemporaryDirectory() as temp:
            root, report = report_fixture(Path(temp))
            output = root / 'output'; result = build(output, root)
            rows = list(csv.DictReader(io.StringIO((output / 'all_eighteen_generations.csv').read_text())))
            self.assertEqual(len(rows), 18)
            self.assertEqual(sum(int(r['known_total_tokens']) for r in rows), 408015)
            self.assertEqual(result['known_total_tokens'], 408015)
            self.assertEqual(len(json.loads((output / 'all_output_comparisons.json').read_text())['cross']), 15)
            self.assertTrue(result['diagnostic_usable'])
            self.assertTrue(result['local_public_output_difference_identified'])
            self.assertEqual(result['pages'], 5)
            missing = {**report['equality_summary'], 'cross': report['equality_summary']['cross'][:-1]}
            with self.assertRaisesRegex(ValueError, 'all_fifteen'):
                comparison_matrix(missing, 'equal_public_pairs')

    def test_unknown_usage_is_blank_and_blocks_effect_without_dropping_slot(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _ = report_fixture(Path(temp), unknown=True)
            output = root / 'output'; result = build(output, root)
            rows = list(csv.DictReader(io.StringIO((output / 'all_eighteen_generations.csv').read_text())))
            self.assertEqual(len(rows), 18)
            self.assertEqual(rows[-1]['record_status'], 'unknown_usage')
            self.assertEqual(rows[-1]['known_total_tokens'], '')
            self.assertEqual(rows[-1]['output_tokens'], '')
            self.assertEqual(result['unknown_usage_calls'], 1)
            self.assertIsNone(result['local_public_output_difference_identified'])
            self.assertIn('使用量不明', (output / 'index.html').read_text())

    def test_partial_cohort_keeps_seventeen_unattempted_slots(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _ = report_fixture(Path(temp), attempted=1)
            output = root / 'output'; result = build(output, root)
            rows = list(csv.DictReader(io.StringIO((output / 'all_eighteen_generations.csv').read_text())))
            self.assertEqual(len(rows), 18)
            self.assertEqual(sum(r['record_status'] == 'unattempted' for r in rows), 17)
            self.assertFalse(result['diagnostic_usable'])
            self.assertEqual(result['known_total_tokens'], 22673)
            self.assertEqual(result['unknown_usage_calls'], 0)

    def test_known_truncation_retains_cost_but_does_not_support_effect(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _ = report_fixture(Path(temp), truncated=True)
            result = build(root / 'output', root)
            self.assertTrue(result['all_eighteen_audited'])
            self.assertEqual(result['known_total_tokens'], 408015)
            self.assertFalse(result['diagnostic_usable'])
            self.assertIsNone(result['local_public_output_difference_identified'])
            self.assertIn('途中切れ', (root / 'output/index.html').read_text())

    def test_forged_completeness_or_unknown_count_is_rejected(self):
        for field, value in [('all_eighteen_audited', True), ('unknown_usage_calls', 0)]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                root, report = report_fixture(Path(temp), unknown=True)
                report[field] = value
                write_json(root / 'reports/P84_fallback_output_replay.json', report)
                with self.assertRaisesRegex(ValueError, 'aggregation_mismatch'):
                    validated(root)

    def test_changed_frozen_input_is_rejected_before_export(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _ = report_fixture(Path(temp))
            source = root / 'configs/P84_fallback_output_v01.json'
            source.write_text(source.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'frozen_P84_source_changed'):
                build(root / 'output', root)
            self.assertFalse((root / 'output').exists())


if __name__ == '__main__':
    unittest.main()
