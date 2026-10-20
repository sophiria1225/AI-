"""Freeze a worktree diff and separately retain explicitly excluded diagnostics."""
import hashlib
import json
import pathlib

CAPTURE_SCRIPT = r'''
import hashlib, json, pathlib, subprocess, sys
base = sys.argv[1]
def git(*args):
    return subprocess.check_output(['git', *args], cwd='/testbed')
untracked = git('ls-files', '--others', '--exclude-standard', '-z').decode().split('\0')
excluded, include = [], []
for name in filter(None, untracked):
    path = pathlib.Path('/testbed') / name
    reason = None
    if pathlib.PurePosixPath(name).parts[0] == '.harness_notes':
        reason = 'reserved_working_notes'
    elif path.is_file() and not path.is_symlink():
        with path.open('rb') as stream:
            header = stream.read(20)
        if (header[:4] == b'\x7fELF' and len(header) >= 18 and header[5] in (1, 2)
                and int.from_bytes(header[16:18], 'little' if header[5] == 1 else 'big') == 4):
            reason = 'ELF_core_dump'
    if reason:
        record = {'path': name, 'reason': reason, 'bytes': path.lstat().st_size}
        if path.is_file() and not path.is_symlink():
            with path.open('rb') as stream:
                record['sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else None
            if record['sha256'] is None:
                h = hashlib.sha256()
                with path.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(1024*1024), b''):
                        h.update(chunk)
                record['sha256'] = h.hexdigest()
        excluded.append(record)
    else:
        include.append(name)
for name in include:
    subprocess.run(['git', 'add', '-N', '--', name], cwd='/testbed', check=True)
print(json.dumps({'excluded': excluded, 'included_new_files': include}))
'''


def capture_artifact(container, base_commit, out):
    result = container.exec_run(
        ['/opt/miniconda3/envs/testbed/bin/python', '-c', CAPTURE_SCRIPT, base_commit],
        workdir='/testbed')
    if result.exit_code != 0:
        raise RuntimeError('artifact discovery or git add failed: ' + result.output.decode(errors='replace'))
    manifest = json.loads(result.output)
    exclusions = [':(exclude,literal).harness_notes']
    for item in manifest['excluded']:
        exclusions.append(':(exclude,literal)' + item['path'])
        if item['reason'] == 'ELF_core_dump' and item['bytes'] <= 16*1024*1024:
            diagnostic_dir = out / 'excluded_diagnostics'
            diagnostic_dir.mkdir(exist_ok=True)
            destination = diagnostic_dir / (item['sha256'] + '.tar')
            stream, _ = container.get_archive('/testbed/' + item['path'])
            with destination.open('wb') as target:
                for chunk in stream:
                    target.write(chunk)
            item['archive_path'] = str(destination.relative_to(out))
        else:
            item['archive_path'] = None
            item['archive_note'] = 'metadata retained; notes or diagnostic above 16 MiB'
    artifact = container.exec_run(
        ['git', 'diff', '--binary', base_commit, '--', '.', *exclusions], workdir='/testbed')
    if artifact.exit_code != 0:
        raise RuntimeError('could not capture final artifact')
    (out / 'artifact_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (out / 'final.patch').write_bytes(artifact.output)
    return {'artifact_sha256': hashlib.sha256(artifact.output).hexdigest(),
            'artifact_bytes': len(artifact.output), 'artifact_manifest': 'artifact_manifest.json'}
