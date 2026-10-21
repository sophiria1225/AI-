"""Post-run diagnosis using recorded public receipts, never evaluator contents.

The task-specific set computation is an analyst diagnostic, not a runtime
controller or an automatically generated verifier. Values stay local.
"""
import argparse
import collections
import csv
import hashlib
import io
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def args_of(span):
    value = span['action']['arguments']
    return json.loads(value) if isinstance(value, str) else value


def body(span):
    value = span['observation'].get('observation')
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return None


def recorded_operations(spans, events):
    sent = {e['span_id'] for e in events if e['api_request_sent']}
    return {
        'sent_counts': dict(collections.Counter(
            spans[s]['action']['name'] for s in sent)),
        'not_sent_spans': [s for s in spans if s not in sent],
        'text_failure_spans': [s for s in spans if s in sent and
            str(spans[s]['observation'].get('observation', '')).startswith('Execution failed')],
    }


def photo_counts(spans, events):
    sent = {e['span_id'] for e in events if e['api_request_sent']}
    listed, read, moved = set(), [], []
    aliases, canonical_moved, unmapped_moves = {}, [], 0
    for sid, span in spans.items():
        if sid not in sent:
            continue
        value, name = body(span), span['action']['name']
        if name == 'file_system__show_directory' and isinstance(value, list):
            listed.update(value)
        if name == 'file_system__show_file' and isinstance(value, dict) and 'path' in value:
            read.append(value['path'])
            requested_path = args_of(span)['file_path']
            if requested_path in aliases and aliases[requested_path] != value['path']:
                raise ValueError('recorded path alias changed identity')
            aliases[requested_path] = value['path']
        if name == 'file_system__move_file' and isinstance(value, dict) and 'message' in value:
            requested_path = args_of(span)['source_file_path']
            moved.append(requested_path)
            canonical = aliases.get(requested_path, requested_path if requested_path in listed else None)
            if canonical is None:
                unmapped_moves += 1
            else:
                canonical_moved.append(canonical)
    return {'listed_unique_paths': len(listed), 'successful_metadata_reads': len(read),
            'unique_metadata_paths': len(set(read)), 'listed_without_metadata': len(listed-set(read)),
            'move_requests_with_json_receipt': len(moved), 'unique_moved_source_paths': len(set(moved)),
            'unique_canonical_moved_source_paths': len(set(canonical_moved)),
            'unmapped_move_source_paths': unmapped_moves,
            'listed_without_move_receipt': len(listed-set(canonical_moved)) if not unmapped_moves else None,
            'individual_read_and_move_count_for_this_strategy': 2*len(listed),
            'scope': 'Counts of this individual-file strategy, not a minimum over all possible strategies. '
                     'Path aliases use earlier successful public metadata receipts, not host filesystem expansion. '
                     'JSON receipt counts alone do not establish correct destination or final success.'}


def song_coverage(spans):
    sets = {key: set() for key in ('song', 'album', 'playlist')}
    metadata, metadata_span, csv_records, exhausted = {}, {}, [], set()
    create_span = None
    for sid, span in spans.items():
        name, value = span['action']['name'], body(span)
        if name in ('spotify__show_song_library', 'spotify__show_album_library',
                    'spotify__show_playlist_library') and isinstance(value, list):
            kind = name.removeprefix('spotify__show_').removesuffix('_library')
            if not value:
                exhausted.add(kind)
            for row in value:
                if kind == 'song':
                    sets[kind].add(row['song_id'])
                    metadata[row['song_id']] = row
                    metadata_span[row['song_id']] = sid
                else:
                    sets[kind].update(row['song_ids'])
        elif name == 'spotify__show_song' and isinstance(value, dict) and 'song_id' in value:
            metadata[value['song_id']] = value
            metadata_span[value['song_id']] = sid
        elif name == 'file_system__create_file':
            if create_span is not None:
                raise ValueError('diagnostic assumes one export creation')
            create_span = sid
            create_content = args_of(span)['content']
            known_before_export = set(metadata)
        elif name == 'file_system__show_file' and isinstance(value, dict) and 'content' in value:
            csv_records.append(value['content'])
    if len(csv_records) != 1 or create_span is None:
        raise ValueError('one created and reread export is required')
    requested = set.union(*sets.values())
    if requested - known_before_export:
        raise ValueError('cannot claim complete known metadata before export')
    if csv_records[0] != create_content:
        raise ValueError('reread differs from the submitted export')
    reader = csv.DictReader(io.StringIO(csv_records[0]))
    if reader.fieldnames != ['Title', 'Artists']:
        raise ValueError('unexpected export schema')
    rows = list(reader)
    if any(set(row) != {'Title', 'Artists'} or None in row.values() for row in rows):
        raise ValueError('malformed CSV row')
    pairs = {i: (metadata[i]['title'], '|'.join(a['name'] for a in metadata[i]['artists']))
             for i in requested}
    expected, actual = set(pairs.values()), {(r['Title'], r['Artists']) for r in rows}
    missing_ids = {i for i, value in pairs.items() if value not in actual}
    return {'source_unique_id_counts': {k: len(v) for k, v in sets.items()},
            'source_kinds_with_recorded_empty_next_page': sorted(exhausted),
            'union_unique_ids': len(requested), 'known_metadata_before_export': len(requested & known_before_export),
            'unique_known_title_artist_pairs': len(expected), 'export_rows': len(rows),
            'export_unique_pairs': len(actual), 'matching_pairs': len(expected & actual),
            'missing_known_pairs': len(expected-actual), 'unmatched_export_pairs': len(actual-expected),
            'missing_id_membership_counts': {k: len(v & missing_ids) for k, v in sets.items()},
            'missing_metadata_receipt_spans': sorted({metadata_span[i] for i in missing_ids}),
            'export_create_span': create_span, 'export_reread_identical': True,
            'scope': 'Analyst-derived set from public observed IDs and fields, not hidden truth. '
                     'No output values or missing title exported. All metadata was received before creation. '
                     'One observed omission is not a causal account of all independent evaluation failures.'}


def analyze(storage_root, plan_path):
    plan = json.loads(plan_path.read_text())
    if plan['phase'] != 'P18':
        raise ValueError('P18 plan required')
    batch_path = storage_root / 'records/context_pilot/P18_batch_v01/status.json'
    batch = json.loads(batch_path.read_text())
    if batch['status'] != 'complete':
        raise ValueError('whole P18 batch must finish first')
    expected = [f'P18_{i:02d}_ROLES' for i in range(1, 5)]
    trials = []
    for name in expected:
        directory = storage_root / 'records/context_pilot' / name
        if sha(directory/'plan.json') != sha(plan_path):
            raise ValueError('plan changed')
        spans = json.loads((directory/'spans.json').read_text())
        events = json.loads((directory/'events.json').read_text())
        row = {'run_id': name, **recorded_operations(spans, events),
               'source_sha256': {f: sha(directory/f) for f in ('spans.json', 'events.json', 'summary.json')}}
        if name == expected[0]:
            row['photo_counts'] = photo_counts(spans, events)
        if name == expected[3]:
            row['song_coverage'] = song_coverage(spans)
        trials.append(row)
    return {'phase': 'P18', 'trials': trials, 'plan_sha256': sha(plan_path),
            'script_sha256': sha(Path(__file__)), 'model_calls': 0, 'environment_requests': 0,
            'evaluator_contents_read': False, 'reserved_tasks_read': 0,
            'scope': 'Post-run public-evidence diagnosis of four development cases. Task-specific analyst '
                     'checks are not a proposed autonomous verifier or proof of a novel mechanism.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = analyze(a.storage_root, a.plan)
    with a.output.open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({'trials': len(result['trials']), 'model_calls': 0,
                      'missing_known_pairs': result['trials'][3]['song_coverage']['missing_known_pairs']}))
