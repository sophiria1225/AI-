"""Render tasks and optionally reconcile GitHub issues and a Project.

gh owns authentication. Unrelated issues, items and human comments are untouched.
"""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LINKS = ROOT / 'tracking/github_links.json'
LABELS = {'todo': '未着手', 'in_progress': '進行中', 'blocked': '待ち', 'done': '完了'}
ALLOWED_REPOSITORY = 'sophiria1225/AI-'
ALLOWED_PROJECT_TITLE = 'AIハーネス研究 2026–2027'


def check_repository_scope(data):
    if data.get('repository') != ALLOWED_REPOSITORY:
        raise RuntimeError('GitHub writes are restricted to ' + ALLOWED_REPOSITORY)
    if data.get('project_title') != ALLOWED_PROJECT_TITLE:
        raise RuntimeError('Only the dedicated AI- research Project may be updated')


def check_project_scope(project):
    """Read every page before allowing any Project mutation; never skip unknown content."""
    counts = {}
    selections = {
        'repositories': 'nodes { nameWithOwner }',
        'items': '''nodes { content {
            ... on Issue { repository { nameWithOwner } }
            ... on PullRequest { repository { nameWithOwner } }
        } }''',
    }
    for name, selection in selections.items():
        query = ('query($id: ID!, $cursor: String) { node(id: $id) { ... on ProjectV2 { '
                 + name + '(first: 100, after: $cursor) { ' + selection
                 + ' pageInfo { hasNextPage endCursor } } } } }')
        cursor = None; seen = set(); count = 0
        while True:
            args = ['api', 'graphql', '-f', 'query=' + query, '-f', 'id=' + project['id']]
            if cursor is not None:
                args += ['-f', 'cursor=' + cursor]
            result = gh(*args, json_output=True)
            if not isinstance(result, dict):
                raise RuntimeError('Unable to verify Project scope')
            node = (result.get('data') or {}).get('node')
            connection = node.get(name) if isinstance(node, dict) else None
            if result.get('errors') or not isinstance(connection, dict):
                raise RuntimeError('Unable to verify Project scope')
            nodes = connection.get('nodes'); page = connection.get('pageInfo')
            if (not isinstance(nodes, list) or not isinstance(page, dict)
                    or type(page.get('hasNextPage')) is not bool):
                raise RuntimeError('Unable to verify Project scope page')
            for item in nodes:
                if not isinstance(item, dict):
                    raise RuntimeError('Unable to verify Project scope item')
                content = item.get('content')
                repository = item if name == 'repositories' else (
                    content.get('repository') if isinstance(content, dict) else None)
                if not isinstance(repository, dict) or repository.get('nameWithOwner') != ALLOWED_REPOSITORY:
                    raise RuntimeError('Project contains content outside ' + ALLOWED_REPOSITORY)
            count += len(nodes)
            if not page['hasNextPage']:
                break
            next_cursor = page.get('endCursor')
            if (not nodes or type(next_cursor) is not str or not next_cursor or next_cursor in seen):
                raise RuntimeError('Unable to verify Project scope pagination')
            seen.add(next_cursor); cursor = next_cursor
        counts[name] = count
    return counts


def gh(*args, json_output=False):
    result = subprocess.run(['gh', *map(str, args)], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f'gh exited {result.returncode}')
    return json.loads(result.stdout) if json_output else result.stdout.strip()


def issue_body(task):
    completed = set(task.get('completed_steps', []))
    steps = '\n'.join(f"- [{'x' if s in completed else ' '}] {s}" for s in task['steps'])
    checks = '\n'.join('- ' + s for s in task['acceptance'])
    return (f"<!-- harness-task:{task['id']} -->\n"
            f"優先度: {task['priority']} / 状態: {LABELS[task['status']]}\n\n"
            f"## 目的\n\n{task['why']}\n\n"
            f"## 代替案を先に選ばない理由\n\n{task['alternatives']}\n\n"
            f"## 作業\n\n{steps}\n\n## 完了条件\n\n{checks}\n\n"
            f"## 現在の記録\n\n{task['progress']}\n\n"
            "実装・詳細記録は研究ブランチとdocs/へ保存する。"
            "状態の更新元はtracking/tasks.json。人の補足はコメントに残す。\n")


def render(data, links):
    lines = ['# 研究の作業ボード', '', f"更新日: {data['updated_at']}", '',
             '番号はIssueに対応する固定ID。前段の結果に応じて段階的に進める。', '',
             '| 優先 | ID | 作業 | 状態 | GitHub |', '|---|---|---|---|---|']
    for task in data['tasks']:
        link = links.get('issues', {}).get(task['id'], {}).get('url')
        remote = f'[Issue]({link})' if link else '未同期'
        lines.append(f"| {task['priority']} | {task['id']} | {task['title']} | {LABELS[task['status']]} | {remote} |")
    project = links.get('project', {})
    lines += ['', '[GitHub Project](' + project['url'] + ')' if project.get('url') else
              'GitHub Projectは認証後に作成・同期する。作業定義と投稿内容は準備済み。']
    for task in data['tasks']:
        lines += ['', f"## {task['id']} {task['title']}", '', task['progress'], '',
                  '**なぜ行うか**: ' + task['why'], '', '**他候補の扱い**: ' + task['alternatives']]
    (ROOT / 'docs/task_board.md').write_text('\n'.join(lines) + '\n')
    directory = ROOT / '.runtime/issue_bodies'
    directory.mkdir(parents=True, exist_ok=True)
    for task in data['tasks']:
        (directory / (task['id'] + '.md')).write_text(issue_body(task))


def save_links(links):
    LINKS.write_text(json.dumps(links, ensure_ascii=False, indent=2) + '\n')


def publish_issues(data, links):
    """Save each Issue before Project work, so missing Project scope is recoverable."""
    check_repository_scope(data)
    repo = data['repository']
    existing = gh('issue', 'list', '--repo', repo, '--state', 'all', '--limit', 200,
                  '--json', 'number,title,url,body,state', json_output=True)
    for task in data['tasks']:
        marker = f"<!-- harness-task:{task['id']} -->"
        matches = [i for i in existing if marker in (i.get('body') or '')]
        if len(matches) > 1:
            raise RuntimeError('multiple issues for ' + task['id'])
        body = issue_body(task)
        title = f"[{task['id']}] {task['title']}"
        body_path = ROOT / '.runtime/issue_bodies' / (task['id'] + '.md')
        if matches:
            issue = matches[0]
            if issue['body'].strip() != body.strip() or issue['title'] != title:
                gh('issue', 'edit', issue['number'], '--repo', repo, '--title', title, '--body-file', body_path)
        else:
            url = gh('issue', 'create', '--repo', repo, '--title', title, '--body-file', body_path)
            issue = {'number': int(url.rsplit('/', 1)[-1]), 'url': url, 'state': 'OPEN'}
        links.setdefault('issues', {})[task['id']] = {'number': issue['number'], 'url': issue['url']}
        save_links(links)
        if task['status'] == 'done' and issue['state'] == 'OPEN':
            gh('issue', 'close', issue['number'], '--repo', repo, '--reason', 'completed')
        print(json.dumps({'task': task['id'], 'issue': issue['url'], 'status': task['status']}, ensure_ascii=False), flush=True)


def publish_project(data, links):
    check_repository_scope(data)
    repo = data['repository']
    owner = repo.split('/')[0]
    projects = gh('project', 'list', '--owner', owner, '--limit', 100, '--format', 'json', json_output=True)
    matches = [p for p in projects['projects'] if p['title'] == data['project_title']]
    if len(matches) > 1:
        raise RuntimeError('multiple Projects have the requested title; preserve them')
    project = matches[0] if matches else None
    if not project:
        project = gh('project', 'create', '--owner', owner, '--title', data['project_title'],
                     '--format', 'json', json_output=True)
    check_project_scope(project)
    links['project'] = {k: project[k] for k in ('id', 'number', 'url', 'title')}
    save_links(links)
    gh('project', 'link', project['number'], '--owner', owner, '--repo', repo)
    fields = gh('project', 'field-list', project['number'], '--owner', owner,
                '--format', 'json', json_output=True)['fields']
    status_field = next(f for f in fields if f['name'] == 'Status')
    options = {v['name'].lower(): v['id'] for v in status_field['options']}
    todo = options.get('todo') or options.get('to do')
    if not todo or not options.get('in progress') or not options.get('done'):
        raise RuntimeError('project status options require an explicit mapping')
    items = gh('project', 'item-list', project['number'], '--owner', owner,
               '--limit', 500, '--format', 'json', json_output=True)['items']
    item_by_url = {i.get('content', {}).get('url'): i for i in items}
    for task in data['tasks']:
        issue = links['issues'][task['id']]
        item = item_by_url.get(issue['url'])
        if not item:
            item = gh('project', 'item-add', project['number'], '--owner', owner,
                      '--url', issue['url'], '--format', 'json', json_output=True)
        option = {'todo': todo, 'blocked': todo, 'in_progress': options['in progress'],
                  'done': options['done']}[task['status']]
        gh('project', 'item-edit', '--id', item['id'], '--project-id', project['id'],
           '--field-id', status_field['id'], '--single-select-option-id', option)
    print(json.dumps({'project': project['url'], 'items_synced': len(data['tasks'])}, ensure_ascii=False), flush=True)


def publish(data, links, issues_only=False):
    check_repository_scope(data)
    gh('auth', 'status')
    publish_issues(data, links)
    if not issues_only:
        publish_project(data, links)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--issues-only', action='store_true', help='Publish Issues without requiring Project scope')
    args = parser.parse_args()
    data = json.loads((ROOT / 'tracking/tasks.json').read_text())
    links = json.loads(LINKS.read_text()) if LINKS.exists() else {}
    render(data, links)
    if args.publish:
        try:
            publish(data, links, issues_only=args.issues_only)
        finally:
            render(data, links)
    print('Rendered docs/task_board.md')


if __name__ == '__main__':
    main()
