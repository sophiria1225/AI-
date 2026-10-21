"""Seal generation artifacts before any evaluator is allowed to read a label."""
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exclusive_json(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        Path(path).chmod(0o600)
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def write_terminal(folder, summary, response=None, source_call_id=None):
    folder = Path(folder)
    if (folder / 'terminal_manifest.json').exists() or (folder / 'summary.json').exists():
        raise FileExistsError('preserve the original terminal selection')
    if response is not None:
        if not isinstance(response, str) or not response.strip():
            raise ValueError('a submitted answer must be nonempty text')
        if not isinstance(source_call_id, str) or not re.fullmatch(r'call_[0-9]{3,}', source_call_id):
            raise ValueError('submitted answer must identify its model response')
        raw = json.loads((folder / source_call_id / 'response.json').read_text())
        if (raw['status'] != 'ok' or raw['message'].get('tool_calls')
                or raw['message'].get('content') != response or raw['done_reason'] != 'stop'):
            raise ValueError('submitted text is not a complete terminal model response')
        exclusive_json(folder / 'final_answer.json', {
            'query_id': summary['query_id'], 'response': response, 'source_call_id': source_call_id})
    summary = {**summary, 'generation_terminal': True, 'submitted': response is not None,
               'final_answer_sha256': digest(folder / 'final_answer.json') if response is not None else None}
    exclusive_json(folder / 'summary.json', summary)
    paths = sorted(p for p in folder.rglob('*') if p.is_file())
    if any(p.is_symlink() for p in paths):
        raise ValueError('generation records must not contain symlinks')
    exclusive_json(folder / 'terminal_manifest.json', {
        'schema': 1, 'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'files': {str(p.relative_to(folder)): digest(p) for p in paths}})
    return summary


def load_terminal(folder):
    """Call before opening any answer/evidence file. Reject partial or changed runs."""
    folder = Path(folder)
    manifest = json.loads((folder / 'terminal_manifest.json').read_text())
    if manifest['schema'] != 1 or 'summary.json' not in manifest['files']:
        raise ValueError('missing terminal seal')
    for name, expected in manifest['files'].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('invalid sealed path')
        path = folder / name
        if path.is_symlink() or not path.is_file() or digest(path) != expected:
            raise ValueError('generation record changed after terminal selection')
    summary = json.loads((folder / 'summary.json').read_text())
    if summary.get('generation_terminal') is not True:
        raise ValueError('generation has not terminated')
    if not summary['submitted']:
        if summary['final_answer_sha256'] is not None or (folder / 'final_answer.json').exists():
            raise ValueError('unsubmitted run contains an added answer')
        return summary, None
    if ('final_answer.json' not in manifest['files']
            or summary['final_answer_sha256'] != digest(folder / 'final_answer.json')):
        raise ValueError('final answer differs from the selected artifact')
    answer = json.loads((folder / 'final_answer.json').read_text())
    if answer['query_id'] != summary['query_id']:
        raise ValueError('query identity differs from terminal summary')
    return summary, answer
