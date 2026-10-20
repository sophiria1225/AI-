"""Install a checksum-pinned official binary into the project, without sudo."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = json.loads((ROOT / 'configs/models/minimax_m3_selection.json').read_text())['runtime']
    destination = ROOT / '.runtime/llama.cpp' / config['binary_tag']
    destination.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(config['asset_url'], timeout=60) as response:
        raw = response.read()
    if hashlib.sha256(raw).hexdigest() != config['asset_sha256']:
        raise RuntimeError('runtime asset hash mismatch')
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        archive.extractall(destination, filter='data')
    servers = list(destination.rglob('llama-server'))
    if len(servers) != 1:
        raise RuntimeError('unexpected runtime layout')
    check = subprocess.run([str(servers[0]), '--version'], text=True, capture_output=True, check=True)
    record = {'runtime': config, 'server_path': str(servers[0].relative_to(ROOT)),
              'archive_bytes': len(raw), 'version_exit': check.returncode,
              'stdout': check.stdout, 'stderr': check.stderr}
    target = ROOT / 'records/models/p2_runtime_install.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2) + '\n')
    print(check.stdout + check.stderr)


if __name__ == '__main__':
    main()
