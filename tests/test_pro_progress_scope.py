"""Ensure unattended progress stays in the allowed Issue and excludes raw text."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import watch_pro_comparison as progress


class ProgressScopeTests(unittest.TestCase):
    def test_body_does_not_publish_model_or_evaluator_text(self):
        report = {'batch_id': 'P5_01', 'at': '2026-10-20T10:20:00+00:00', 'runs': [
            {'strategy': 'fixed_pair', 'stage': 'running', 'recorded_calls': 10,
             'recorded_tokens': 56318, 'model_text': 'PRIVATE_MODEL_SENTINEL'},
            {'strategy': 'single', 'stage': 'not_started', 'private_tests': 'PRIVATE_EVALUATOR_SENTINEL'}]}
        body = progress.public_body(report)
        self.assertIn('56,318', body)
        self.assertIn('| 単一 | 未開始 | — | — | 未確定 |', body)
        self.assertNotIn('PRIVATE_', body)
        self.assertNotIn('未解決 |', body)
        report['batch_id'] = 'another_batch'
        with self.assertRaises(ValueError):
            progress.public_body(report)

    def test_outside_repository_never_reaches_cli(self):
        with patch.object(progress.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                progress.gh_api('repos/another/repository/issues/24', method='POST', payload={})
            run.assert_not_called()

    def test_another_issue_comment_cannot_be_modified(self):
        state = {'comment_id': 123}
        with patch.object(progress, 'gh_api', return_value={
            'issue_url': 'https://api.github.com/repos/sophiria1225/AI-/issues/22',
            'body': '<!-- harness-batch:P5_01 -->'}) as api:
            with self.assertRaisesRegex(ValueError, 'another Issue'):
                progress.publish('update', state)
            self.assertEqual(api.call_count, 1)
            self.assertEqual(api.call_args.kwargs, {})

    def test_a_human_comment_without_marker_is_never_overwritten(self):
        with patch.object(progress, 'gh_api', return_value={
            'issue_url': 'https://api.github.com/repos/sophiria1225/AI-/issues/24',
            'body': 'a human comment'}) as api:
            with self.assertRaisesRegex(ValueError, 'marker'):
                progress.publish('update', {'comment_id': 123})
            self.assertEqual(api.call_count, 1)


if __name__ == '__main__':
    unittest.main()
