"""Install official container clients under this project without modifying Homebrew."""
import hashlib
import json
import pathlib
import shutil
import tarfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
PREFIX = ROOT / '.tools'
CACHE = PREFIX / 'downloads'
BIN = PREFIX / 'bin'
for p in [CACHE, BIN, PREFIX / 'lib/docker/cli-plugins']:
    p.mkdir(parents=True, exist_ok=True)
entries = [
    ('colima', 'abiosoft_colima_release_full.json', 'colima-Darwin-arm64', BIN / 'colima'),
    ('lima', 'lima-vm_lima_release_full.json', 'lima-2.2.1-Darwin-arm64.tar.gz', PREFIX),
    ('buildx', 'docker_buildx_release_full.json', 'buildx-v0.38.0.darwin-arm64', PREFIX / 'lib/docker/cli-plugins/docker-buildx'),
]
records = []

def download(url, name, maximum):
    path = CACHE / name
    size = 0
    with urllib.request.urlopen(url, timeout=30) as response, path.open('wb') as f:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            if size > maximum:
                raise ValueError('download size cap exceeded: ' + name)
            f.write(block)
    return path

for name, metadata, asset_name, destination in entries:
    data = json.loads((ROOT / 'records/sources' / metadata).read_text())
    asset = next(a for a in data['assets'] if a['name'] == asset_name)
    path = download(asset['browser_download_url'], asset_name, 100_000_000)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if 'sha256:' + digest != asset['digest']:
        raise ValueError('published digest mismatch: ' + name)
    if name == 'lima':
        with tarfile.open(path) as archive:
            archive.extractall(PREFIX, filter='data')
    else:
        shutil.copy2(path, destination)
        destination.chmod(0o755)
    records.append({'tool': name, 'version': data['tag_name'], 'url': asset['browser_download_url'],
                    'bytes': path.stat().st_size, 'sha256': digest, 'published_digest_verified': True})
    print(json.dumps(records[-1]), flush=True)

url = 'https://download.docker.com/mac/static/stable/aarch64/docker-29.9.0.tgz'
path = download(url, 'docker-29.9.0.tgz', 100_000_000)
with tarfile.open(path) as archive:
    member = next(m for m in archive.getmembers() if m.name == 'docker/docker' and m.isfile())
    with archive.extractfile(member) as source, (BIN / 'docker').open('wb') as target:
        shutil.copyfileobj(source, target)
(BIN / 'docker').chmod(0o755)
records.append({'tool':'docker','version':'29.9.0','url':url,'bytes':path.stat().st_size,
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'published_digest_verified':False})
(ROOT / 'records/environment/local_container_tools.json').write_text(json.dumps(records, indent=2) + '\n')
print(json.dumps(records[-1]), flush=True)
