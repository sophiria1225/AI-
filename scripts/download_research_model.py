"""Download one pinned quantization, preserving hashes and resumable progress.

Weights and complete operational records are deliberately excluded from Git.
No private Hub token or mutable model revision is used.
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import urllib.request
import uuid

from model_provenance import load_selection, local_path, stable_manifest, validate_manifest

ROOT = Path(__file__).resolve().parents[1]


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='configs/models/minimax_m3_selection.json')
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--metadata-only', action='store_true')
    args = parser.parse_args()
    config = load_selection(args.config)
    repo, revision, subdir = (config[k] for k in ('repo_id', 'revision', 'subdirectory'))
    url = f'https://huggingface.co/api/models/{repo}/tree/{revision}/{subdir}?recursive=true'
    with urllib.request.urlopen(url, timeout=60) as response:
        entries = json.load(response)
    files = [{'path': e['path'], 'bytes': e['size'], 'sha256': e['lfs']['oid']}
             for e in entries if e.get('type') == 'file' and e['path'].endswith('.gguf')]
    if not files or sum(f['bytes'] for f in files) != config['total_bytes']:
        raise ValueError('remote manifest disagrees with selected size')
    if any(len(f['sha256']) != 64 for f in files):
        raise ValueError('SHA256 missing')
    manifest = {'repo_id': repo, 'revision': revision, 'files': files,
                'total_bytes': sum(f['bytes'] for f in files), 'retrieved_at': now()}
    manifest = stable_manifest(config, manifest)
    if args.metadata_only:
        print(json.dumps(manifest), flush=True)
        return
    target = ROOT / 'models' / repo.split('/')[-1] / revision
    target.mkdir(parents=True, exist_ok=True)
    remaining = sum(f['bytes'] for f in files
                    if not (target / f['path']).is_file() or (target / f['path']).stat().st_size != f['bytes'])
    if shutil.disk_usage(target).free < remaining + 100 * 1024**3:
        raise RuntimeError('less than the planned 100 GiB disk reserve after download')
    # Bound the local cache and suppress signed URLs/progress noise in public output.
    os.environ.setdefault('HF_HUB_DISABLE_PROGRESS_BARS', '1')
    os.environ.setdefault('HF_XET_CACHE', str(ROOT / '.runtime/hf_xet'))
    from huggingface_hub import hf_hub_download
    record_path = local_path(config['download_record'])
    if record_path.exists():
        previous = json.loads(record_path.read_text())
        validate_manifest(config, previous['manifest'])
        if previous['status'] == 'running':
            raise RuntimeError('a download is marked running; inspect its process before retrying')
    attempt = ROOT / 'records/models/downloads' / (datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8])
    attempt.mkdir(parents=True)
    (attempt / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    (attempt / 'model_provenance.py').write_bytes((ROOT / 'scripts/model_provenance.py').read_bytes())
    write_json(attempt / 'selection.json', config)
    if record_path.exists():
        (attempt / 'previous_record.json').write_bytes(record_path.read_bytes())
    state = {'started_at': now(), 'status': 'running', 'manifest': manifest,
             'files': {}, 'destination': str(target.relative_to(ROOT)),
             'attempt_record': str((attempt / 'summary.json').relative_to(ROOT)),
             'selection': args.config, 'pid': os.getpid()}
    lock = threading.Lock()

    def persist():
        write_json(attempt / 'summary.json', state)
        write_json(record_path, state)

    persist()

    def download(item):
        with lock:
            state['files'][item['path']] = {'status': 'downloading', 'started_at': now()}
            persist()
        try:
            path = Path(hf_hub_download(repo_id=repo, filename=item['path'], revision=revision,
                                       local_dir=target, token=False))
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(16 * 1024**2), b''):
                    digest.update(block)
            actual = digest.hexdigest()
            if path.stat().st_size != item['bytes'] or actual != item['sha256']:
                raise RuntimeError('download size/hash mismatch')
            result = {'status': 'verified', 'finished_at': now(),
                      'bytes': path.stat().st_size, 'sha256': actual}
        except Exception as error:
            # Detailed HTTP exceptions may contain signed download URLs.
            result = {'status': 'failed', 'finished_at': now(), 'error_type': type(error).__name__}
        with lock:
            state['files'][item['path']].update(result)
            persist()
            print(json.dumps({'file': item['path'], **result}), flush=True)
        return result['status'] == 'verified'

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(args.workers, 4))) as pool:
            outcomes = list(pool.map(download, files))
        state.update(status='verified' if all(outcomes) else 'failed', finished_at=now())
    except BaseException as error:
        state.update(status='interrupted', error_type=type(error).__name__, finished_at=now())
        raise
    finally:
        persist()
    if not all(outcomes):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
