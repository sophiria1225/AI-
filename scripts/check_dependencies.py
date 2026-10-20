"""Read-only check of pinned dependencies without downloading or upgrading."""
import hashlib
import json
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = json.loads((ROOT / 'configs/dependencies.json').read_text())
    rows = []
    for entry in config['repositories']:
        path = ROOT / entry['directory']
        commit = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
        remote = subprocess.check_output(['git', '-C', str(path), 'remote', 'get-url', 'origin'], text=True).strip()
        changes = subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain'], text=True).strip()
        rows.append({'path': entry['directory'], 'commit': commit,
                     'revision_matches': commit == entry['commit'], 'remote': remote,
                     'clean': not changes, 'resolved_path': str(path.resolve())})
    raw = ROOT / 'private_eval/verified.parquet'
    dataset_matches = hashlib.sha256(raw.read_bytes()).hexdigest() == config['dataset']['private_parquet_sha256']
    report = {'python': platform.python_version(), 'expected_python': config['python'],
              'repositories': rows, 'dataset_hash_matches': dataset_matches}
    destination = ROOT / 'records/environment/p2_dependency_check.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return (platform.python_version() == config['python'] and dataset_matches and
            all(r['revision_matches'] and r['clean'] for r in rows))


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
