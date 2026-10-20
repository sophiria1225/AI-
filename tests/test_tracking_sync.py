"""Failure recovery controls; these do not claim a live GitHub integration test."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import sync_tracking as sync


class TrackingRecovery(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'docs').mkdir()
        (self.root / 'tracking').mkdir()
        self.task = {'id': 'R01', 'title': 'fixture', 'priority': 'P0', 'status': 'in_progress',
                     'steps': ['work'], 'acceptance': ['check'], 'why': 'purpose',
                     'alternatives': 'reason', 'progress': 'running'}
        self.data = {'repository': 'fixture/repo', 'project_title': 'fixture project',
                     'updated_at': '2026-10-20', 'tasks': [self.task]}
        self.links = {}
        self.existing = [{'number': 99, 'title': 'human issue', 'body': 'Do not alter',
                          'url': 'https://github.com/fixture/repo/issues/99', 'state': 'OPEN'}]
        self.calls = []
        for item in (patch.object(sync, 'ROOT', self.root),
                     patch.object(sync, 'LINKS', self.root / 'tracking/github_links.json'),
                     patch.object(sync, 'gh', self.fake_gh)):
            item.start()
            self.addCleanup(item.stop)
        sync.render(self.data, self.links)

    def fake_gh(self, *args, json_output=False):
        self.calls.append(args)
        if args[:2] == ('auth', 'status'):
            return ''
        if args[:2] == ('issue', 'list'):
            return self.existing
        if args[:2] == ('issue', 'create'):
            body = Path(args[args.index('--body-file') + 1]).read_text()
            issue = {'number': 100, 'title': '[R01] fixture', 'body': body,
                     'url': 'https://github.com/fixture/repo/issues/100', 'state': 'OPEN'}
            self.existing.append(issue)
            return issue['url']
        if args[:2] == ('project', 'list'):
            raise RuntimeError('fixture: missing Project scope')
        raise AssertionError('Unexpected mutation or request: ' + repr(args))

    def test_project_failure_keeps_issue_and_retry_does_not_duplicate(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'Project scope'):
                sync.publish(self.data, self.links)
            saved = json.loads(sync.LINKS.read_text())
            sync.publish(self.data, saved, issues_only=True)
        self.assertEqual(saved['issues']['R01']['number'], 100)
        self.assertEqual(sum(c[:2] == ('issue', 'create') for c in self.calls), 1)
        self.assertEqual(self.existing[0]['body'], 'Do not alter')

    def test_duplicate_task_markers_stop_without_mutation(self):
        for number in (101, 102):
            self.existing.append({'number': number, 'body': '<!-- harness-task:R01 -->'})
        with self.assertRaisesRegex(RuntimeError, 'multiple issues'):
            sync.publish(self.data, self.links)
        self.assertFalse(any(c[0] == 'issue' and c[1] in ('create', 'edit', 'close') for c in self.calls))


if __name__ == '__main__':
    unittest.main()
