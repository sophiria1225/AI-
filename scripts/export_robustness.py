"""Task-specific supplementary checks, not a learned or autonomous contract.

These transformations apply only to this static, complete Spotify export packet.
They neither query the environment nor generate/repair model code. Keep them out
of the frozen P21 primary generation and evaluation path.
"""
import copy
import json

from data_export_probe import APIS
from data_python import run_program
from evaluate_data_export_probe_v02 import check_csv, expected_from_observations


TRANSFORMS = ('reverse_order', 'duplicate_observations', 'irrelevant_metadata', 'rename_title')


def metadata_rows(observations):
    for obs in observations:
        if obs['api'] == 'spotify__show_song_library':
            yield from obs['result']
        elif obs['api'] == 'spotify__show_song':
            yield obs['result']


def static_case(case):
    """Reject conflicting metadata; order invariance needs a static world."""
    observations = case['observations']
    if not observations or any(o['api'] not in APIS for o in observations):
        raise ValueError('unsupported observation packet')
    known, wanted = {}, set()
    for row in metadata_rows(observations):
        sid = row['song_id']
        if type(sid) not in (int, str):
            raise ValueError('unsupported identifier type')
        pair = (row['title'], tuple(sorted(a['name'] for a in row['artists'])))
        if sid in known and known[sid] != pair:
            raise ValueError('metadata changed; static transformations not applicable')
        known[sid] = pair
    for obs in observations:
        if obs['api'] == 'spotify__show_song_library':
            wanted.update(r['song_id'] for r in obs['result'])
        elif obs['api'] in ('spotify__show_album_library', 'spotify__show_playlist_library'):
            wanted.update(sid for r in obs['result'] for sid in r['song_ids'])
    if not wanted:
        raise ValueError('nonempty target required')
    expected = expected_from_observations(case)
    return known, wanted, expected


def transformed_cases(case):
    known, wanted, expected = static_case(case)
    examples = []

    reordered = copy.deepcopy(case)
    reordered['observations'].reverse()
    for obs in reordered['observations']:
        if type(obs['result']) is list:
            obs['result'].reverse()
            if obs['api'] in ('spotify__show_album_library', 'spotify__show_playlist_library'):
                for row in obs['result']:
                    row['song_ids'].reverse()
    examples.append(('reverse_order', reordered, expected))

    duplicated = copy.deepcopy(case)
    # Duplicate the whole finite static packet, preserving each record's identity.
    duplicated['observations'] += copy.deepcopy(case['observations'])
    examples.append(('duplicate_observations', duplicated, expected))

    outside = copy.deepcopy(case)
    sample = copy.deepcopy(next(metadata_rows(case['observations'])))
    if type(sample['song_id']) is int:
        sid = max([i for i in known.keys() | wanted if type(i) is int], default=0) + 1
    else:
        sid = 'supplementary-outside'
        while sid in known or sid in wanted:
            sid += '-x'
    title = 'SUPPLEMENTARY_OUTSIDE_TARGET'
    while any(pair[0] == title for pair in known.values()):
        title += '_X'
    sample.update(song_id=sid, title=title)
    outside['observations'].append({'span_id': 'supplementary_outside',
                                   'api': 'spotify__show_song', 'result': sample})
    examples.append(('irrelevant_metadata', outside, expected))

    renamed = copy.deepcopy(case)
    # Fixed canonical ordering, independent of model output or which row P18 lost.
    sid = sorted(wanted, key=lambda i: (type(i).__name__, json.dumps(i)))[0]
    old_pair = known[sid]
    title = 'SUPPLEMENTARY_RENAMED_TITLE'
    while any(pair[0] == title for pair in known.values()):
        title += '_X'
    for row in metadata_rows(renamed['observations']):
        if row['song_id'] == sid:
            row['title'] = title
    renamed_expected = (expected - {old_pair}) | {(title, old_pair[1])}
    examples.append(('rename_title', renamed, renamed_expected))

    # Check transformations against the independently declared set relation.
    for name, transformed, target in examples:
        _, _, checked = static_case(transformed)
        if checked != target:
            raise ValueError('invalid transformation: ' + name)
    return examples


def inspect_program(source, case):
    """All checks are reported, including programs that fail nominal evaluation."""
    result = []
    for name, transformed, expected in transformed_cases(case):
        row = {'transformation': name, 'executed': False, 'complete_export': False,
               'error_type': None, 'steps': None}
        try:
            program = run_program(source, transformed['observations'])
            row.update(executed=True, steps=program['steps'])
            row.update(check_csv(program['content'], expected))
        except Exception as exc:
            # Do not publish exception messages, data values or model code.
            row['error_type'] = type(exc).__name__
        result.append(row)
    return result
