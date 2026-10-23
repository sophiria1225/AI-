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
        self.data = {'repository': sync.ALLOWED_REPOSITORY,
                     'project_title': sync.ALLOWED_PROJECT_TITLE,
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

    def test_other_repository_is_rejected_before_any_request(self):
        self.data['repository'] = 'fixture/other'
        with self.assertRaisesRegex(RuntimeError, 'restricted'):
            sync.publish(self.data, self.links)
        self.assertEqual(self.calls, [])

    def test_project_with_other_repository_is_rejected(self):
        result = {'data': {'node': {
            'repositories': {'nodes': [{'nameWithOwner': 'fixture/other'}],
                             'pageInfo': {'hasNextPage': False}},
            'items': {'nodes': [], 'pageInfo': {'hasNextPage': False}}}}}
        with patch.object(sync, 'gh', return_value=result):
            with self.assertRaisesRegex(RuntimeError, 'outside'):
                sync.check_project_scope({'id': 'fixture-project'})

    def test_dedicated_project_is_allowed(self):
        result = {'data': {'node': {
            'repositories': {'nodes': [{'nameWithOwner': sync.ALLOWED_REPOSITORY}],
                             'pageInfo': {'hasNextPage': False}},
            'items': {'nodes': [{'content': {'repository': {
                'nameWithOwner': sync.ALLOWED_REPOSITORY}}}],
                'pageInfo': {'hasNextPage': False}}}}}
        with patch.object(sync, 'gh', return_value=result):
            sync.check_project_scope({'id': 'fixture-project'})


class TrackingScopePagination(unittest.TestCase):
    def connection(self, kind, repositories, more=False, cursor=None):
        nodes = [{'nameWithOwner': r} if kind == 'repositories' else
                 {'content': {'repository': {'nameWithOwner': r}}} for r in repositories]
        return {'data': {'node': {kind: {'nodes': nodes,
            'pageInfo': {'hasNextPage': more, 'endCursor': cursor}}}}}

    def scan(self, pages):
        with patch.object(sync, 'gh', side_effect=pages) as gh:
            counts = sync.check_project_scope({'id': 'fixture-project'})
            return counts, gh.call_args_list

    def test_all_items_after_the_first_hundred_are_checked(self):
        own = sync.ALLOWED_REPOSITORY
        counts, calls = self.scan([
            self.connection('repositories', [own]),
            self.connection('items', [own] * 100, True, 'after100'),
            self.connection('items', [own]),
        ])
        self.assertEqual(counts, {'repositories': 1, 'items': 101})
        self.assertNotIn('cursor=after100', calls[1].args)
        self.assertIn('cursor=after100', calls[2].args)
        self.assertTrue(all(c.args[:2] == ('api', 'graphql') for c in calls))

    def test_unrelated_item_on_a_later_page_is_rejected(self):
        own = sync.ALLOWED_REPOSITORY
        with self.assertRaisesRegex(RuntimeError, 'outside'):
            self.scan([self.connection('repositories', [own]),
                       self.connection('items', [own], True, 'next'),
                       self.connection('items', ['fixture/other'])])

    def test_repository_connection_is_also_fully_paged(self):
        own = sync.ALLOWED_REPOSITORY
        with self.assertRaisesRegex(RuntimeError, 'outside'):
            self.scan([self.connection('repositories', [own], True, 'repo-next'),
                       self.connection('repositories', ['fixture/other'])])

    def test_missing_or_repeated_cursor_and_empty_continuation_stop(self):
        own = sync.ALLOWED_REPOSITORY
        for bad in (self.connection('items', [own], True),
                    self.connection('items', [], True, 'next')):
            with self.assertRaisesRegex(RuntimeError, 'pagination'):
                self.scan([self.connection('repositories', [own]), bad])
        with self.assertRaisesRegex(RuntimeError, 'pagination'):
            self.scan([self.connection('repositories', [own]),
                       self.connection('items', [own], True, 'same'),
                       self.connection('items', [own], True, 'same')])

    def test_partial_graphql_error_and_unknown_content_are_rejected(self):
        own = sync.ALLOWED_REPOSITORY
        page = self.connection('items', [own]); page['errors'] = [{'message': 'partial response'}]
        with self.assertRaisesRegex(RuntimeError, 'Unable'):
            self.scan([self.connection('repositories', [own]), page])
        for content in (None, {}, {'title': 'unscoped draft'}):
            page = self.connection('items', [own]); page['data']['node']['items']['nodes'][0]['content'] = content
            with self.assertRaisesRegex(RuntimeError, 'outside'):
                self.scan([self.connection('repositories', [own]), page])

    def test_missing_page_metadata_never_counts_as_last_page(self):
        own = sync.ALLOWED_REPOSITORY
        for metadata in (None, {}, {'hasNextPage': 0}):
            page = self.connection('repositories', [own]);page['data']['node']['repositories']['pageInfo'] = metadata
            with self.assertRaisesRegex(RuntimeError, 'Unable'):
                self.scan([page])

    def test_no_project_mutation_precedes_complete_scope_check(self):
        own = sync.ALLOWED_REPOSITORY
        project = {'id': 'fixture-project', 'number': 1, 'url': 'fixture', 'title': sync.ALLOWED_PROJECT_TITLE}
        with patch.object(sync, 'gh', side_effect=[{'projects': [project]},
            self.connection('repositories', [own]), self.connection('items', [own], True, 'next'),
            self.connection('items', ['fixture/other'])]) as gh:
            with self.assertRaisesRegex(RuntimeError, 'outside'):
                sync.publish_project({'repository': own, 'project_title': sync.ALLOWED_PROJECT_TITLE}, {})
            self.assertEqual(gh.call_args_list[0].args[:2], ('project', 'list'))
            self.assertTrue(all(c.args[:2] == ('api', 'graphql') for c in gh.call_args_list[1:]))


if __name__ == '__main__':
    unittest.main()
