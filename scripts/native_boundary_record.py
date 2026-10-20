"""Keep immutable local files at an API boundary; not a full process checkpoint.

The caller must be between synchronous API operations. AppWorld has already saved
its DB changes. No DB is queried, no model is called, and these bytes never enter
the generator's context. RNG, Python namespaces and live caches are NOT captured.
"""
import hashlib
import json
from pathlib import Path
import re
import time


SCOPE = ('DB change files and harness records at a synchronous boundary. '
         'Not Python/RNG/process state; full restoration equivalence is unverified.')


def snapshot_boundary(directory, checkpoint_id, files, state, max_new_bytes=134217728):
    if not re.fullmatch(r'(initial|call_[0-9]{3})', checkpoint_id):
        raise ValueError('unsafe checkpoint ID')
    started = time.monotonic()
    directory = Path(directory)
    manifests, objects = directory / 'manifests', directory / 'objects'
    manifests.mkdir(parents=True, exist_ok=True)
    objects.mkdir(exist_ok=True)
    output = manifests / (checkpoint_id + '.json')
    if output.exists():
        raise FileExistsError('refusing to replace a boundary record')
    rows, new_bytes = {}, 0
    for name, path in sorted(files.items()):
        if (not re.fullmatch(r'[a-zA-Z0-9_./-]+', name) or '..' in Path(name).parts
                or Path(name).is_absolute()):
            raise ValueError('unsafe manifest file name')
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise ValueError('source must be an existing regular file')
        before = path.stat()
        if before.st_size > max_new_bytes:
            raise ValueError('boundary file exceeds storage limit')
        content = path.read_bytes()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('source changed while capturing boundary')
        digest = hashlib.sha256(content).hexdigest()
        target = objects / digest
        if target.exists():
            if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError('existing boundary object is corrupt')
        else:
            new_bytes += len(content)
            if new_bytes > max_new_bytes:
                raise ValueError('boundary exceeds storage limit')
            with target.open('xb') as stream:
                stream.write(content)
        rows[name] = {'sha256': digest, 'bytes': len(content)}
    result = {'format_version': 1, 'checkpoint_id': checkpoint_id, 'scope': SCOPE,
              'state': state, 'files': rows, 'new_object_bytes': new_bytes,
              'captured_file_bytes': sum(row['bytes'] for row in rows.values()),
              'capture_seconds': time.monotonic() - started}
    with output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    # Includes the manifest write in the driver's accounting; it is not added to
    # the immutable manifest after publication.
    return {'id': checkpoint_id, 'files': len(rows), 'new_object_bytes': new_bytes,
            'wall_seconds': time.monotonic() - started,
            'manifest_sha256': hashlib.sha256(output.read_bytes()).hexdigest()}


def verify_boundary(directory, checkpoint_id):
    if not re.fullmatch(r'(initial|call_[0-9]{3})', checkpoint_id):
        raise ValueError('unsafe checkpoint ID')
    directory = Path(directory)
    manifest = json.loads((directory / 'manifests' / (checkpoint_id + '.json')).read_text())
    if manifest['checkpoint_id'] != checkpoint_id or manifest['scope'] != SCOPE:
        raise ValueError('unexpected boundary scope')
    for row in manifest['files'].values():
        digest = row['sha256']
        if not re.fullmatch(r'[a-f0-9]{64}', digest):
            raise ValueError('invalid object digest')
        path = directory / 'objects' / digest
        if path.is_symlink():
            raise ValueError('boundary object is a symlink')
        value = path.read_bytes()
        if len(value) != row['bytes'] or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('boundary object differs from manifest')
    return {'files_verified': len(manifest['files']),
            'captured_file_bytes': sum(row['bytes'] for row in manifest['files'].values()),
            'scope': SCOPE}
