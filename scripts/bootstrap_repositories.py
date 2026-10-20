"""Acquire immutable dependency checkouts without resetting existing work."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(path, *arguments):
    return subprocess.check_output(['git', '-C', str(path), *arguments], text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', default='.')
    parser.add_argument('--only', choices=['mini-swe-agent', 'SWE-bench', 'swe-bench-tasks'])
    args = parser.parse_args()
    destination = (ROOT / args.destination).resolve()
    if not destination.is_relative_to(ROOT):
        raise ValueError('destination must be inside this repository')
    manifest = json.loads((ROOT / 'configs/dependencies.json').read_text())
    out = ROOT / 'records/environment/repository_bootstrap' / datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    out.mkdir(parents=True)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (out / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    record = {'status': 'running', 'destination': args.destination, 'repositories': [], 'error': None}
    try:
        for entry in manifest['repositories']:
            if args.only and Path(entry['directory']).name != args.only:
                continue
            path = destination / entry['directory']
            existed = path.exists()
            if not existed:
                if not path.resolve().is_relative_to(ROOT):
                    raise ValueError('new checkout would traverse an external symlink')
                path.mkdir(parents=True)
                with (out / (path.name + '.log')).open('w') as log:
                    for argv in [('init',), ('remote', 'add', 'origin', entry['url']),
                                 ('fetch', '--depth', '1', 'origin', entry['commit']),
                                 ('checkout', '--detach', 'FETCH_HEAD')]:
                        subprocess.run(['git', '-C', str(path), *argv], check=True,
                                       stdout=log, stderr=subprocess.STDOUT, timeout=180)
            commit = git(path, 'rev-parse', 'HEAD')
            remote = git(path, 'remote', 'get-url', 'origin')
            clean = not git(path, 'status', '--porcelain')
            row = {'path': entry['directory'], 'existed': existed, 'commit': commit,
                   'remote': remote, 'clean': clean,
                   'matches': commit == entry['commit'] and remote == entry['url'] and clean}
            record['repositories'].append(row)
            if not row['matches']:
                raise RuntimeError('existing checkout differs; preserved without reset: ' + entry['directory'])
        record['status'] = 'verified'
    except Exception as error:
        record.update(status='failed', error=repr(error))
    finally:
        (out / 'summary.json').write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps({'record': str(out.relative_to(ROOT)), **record}), flush=True)
    return record['status'] == 'verified'


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
