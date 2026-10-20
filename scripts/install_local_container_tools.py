"""Install pinned official clients into a fresh project directory."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prefix', default='.tools')
    parser.add_argument('--cache', default='.runtime/container_downloads')
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'configs/container_tools.json').read_text())
    if (platform.system(), platform.machine()) != (manifest['platform'], manifest['machine']):
        raise RuntimeError('this manifest targets macOS arm64 only')
    prefix = ROOT / args.prefix
    if not prefix.resolve().is_relative_to(ROOT) or prefix.exists() or prefix.is_symlink():
        raise RuntimeError('installation prefix must be a new directory inside the repository; existing tools are preserved')
    cache = ROOT / args.cache
    if not args.offline:
        if not cache.resolve().is_relative_to(ROOT):
            raise RuntimeError('writable download cache must be inside the repository')
        cache.mkdir(parents=True, exist_ok=True)
    out = ROOT / 'records/environment/tool_bootstrap' / datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    out.mkdir(parents=True)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (out / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    record = {'status': 'preparing', 'prefix': args.prefix, 'offline': args.offline,
              'downloads': [], 'versions': [], 'error': None}
    try:
        assets = []
        for item in manifest['tools']:
            path = cache / item['filename']
            if not path.exists():
                if args.offline:
                    raise FileNotFoundError('offline archive missing: ' + item['filename'])
                temporary = path.with_suffix(path.suffix + '.part')
                size = 0
                with urllib.request.urlopen(item['url'], timeout=60) as source, temporary.open('wb') as target:
                    while block := source.read(1024 * 1024):
                        size += len(block)
                        if size > item['bytes']:
                            raise ValueError('archive exceeds pinned byte count')
                        target.write(block)
                temporary.replace(path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if path.stat().st_size != item['bytes'] or digest != item['sha256']:
                raise ValueError('archive differs from pinned content: ' + item['tool'])
            assets.append((item, path))
            record['downloads'].append({'tool': item['tool'], 'sha256': digest,
                                         'bytes': path.stat().st_size,
                                         'published_digest_verified': item['published_digest_verified']})
        prefix.mkdir(parents=True)
        for item, path in assets:
            target = prefix / item['destination']
            target.parent.mkdir(parents=True, exist_ok=True)
            if item['kind'] == 'lima_archive':
                with tarfile.open(path) as archive:
                    archive.extractall(prefix, filter='data')
            elif item['kind'] == 'docker_archive':
                with tarfile.open(path) as archive:
                    member = archive.getmember('docker/docker')
                    if not member.isfile():
                        raise ValueError('Docker client is not a regular archive member')
                    with archive.extractfile(member) as source, target.open('wb') as destination:
                        shutil.copyfileobj(source, destination)
                target.chmod(0o755)
            else:
                shutil.copy2(path, target)
                target.chmod(0o755)
        commands = [('colima', ['bin/colima', 'version']), ('lima', ['bin/limactl', '--version']),
                    ('docker', ['bin/docker', '--version']),
                    ('buildx', ['lib/docker/cli-plugins/docker-buildx', 'version'])]
        for name, argv in commands:
            argv[0] = str(prefix / argv[0])
            result = subprocess.run(argv, text=True, capture_output=True, timeout=30,
                                    env=os.environ | {'PATH': str(prefix / 'bin') + ':' + os.environ['PATH']})
            record['versions'].append({'tool': name, 'exit_code': result.returncode,
                                        'stdout': result.stdout, 'stderr': result.stderr})
            if result.returncode:
                raise RuntimeError('version command failed: ' + name)
        record['status'] = 'installed'
    except Exception as error:
        record.update(status='failed', error=repr(error))
    finally:
        (out / 'summary.json').write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps({'record': str(out.relative_to(ROOT)), **record}), flush=True)
    return record['status'] == 'installed'


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
