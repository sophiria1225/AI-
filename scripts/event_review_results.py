"""Seal complete local annotations before unmasking; publish counts, never prose."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def validate_annotations(review, annotations):
    """Does not open the condition mapping. Checks completeness, not semantics."""
    manifest, rubric = read(review/'manifest.json'), read(review/'rubric.json')
    if sha(review/'rubric.json') != manifest['prepared_rubric_sha256']:
        raise ValueError('prepared rubric changed')
    expected = {}
    packets = {}
    for name, digest in manifest['packets_sha256'].items():
        path = review/name
        if path.parent != review or not name.startswith('review_') or sha(path) != digest:
            raise ValueError('review packet changed')
        packet = read(path)
        packets[packet['packet_id']] = packet
        for row in packet['items']:
            key = (packet['packet_id'], row['item_index'])
            if key in expected:
                raise ValueError('duplicate packet item')
            expected[key] = row
    if len(packets) != manifest['counts']['outputs'] or len(expected) != manifest['counts']['items']:
        raise ValueError('review manifest counts differ')
    seen = set()
    for annotation in annotations:
        if not set(rubric['required_annotation_fields']) <= set(annotation):
            raise ValueError('annotation fields missing')
        key = (annotation['packet_id'], annotation['item_index'])
        if key in seen or key not in expected:
            raise ValueError('duplicate or unexpected annotation')
        seen.add(key)
        if annotation['item_sha256'] != expected[key]['item_sha256']:
            raise ValueError('annotation attached to a different item')
        if annotation['label'] not in rubric['labels']:
            raise ValueError('unknown semantic label')
        if annotation['rationale_category'] not in rubric['rationale_categories']:
            raise ValueError('unknown rationale category')
        if annotation['uncertainty'] not in ('low', 'medium', 'high'):
            raise ValueError('uncertainty must be low, medium or high')
        evidence = annotation['evidence_span_ids']
        if not isinstance(evidence, list) or not set(evidence) <= set(packets[key[0]]['spans']):
            raise ValueError('evidence outside the permitted prefix')
    if seen != set(expected):
        raise ValueError('every item, including non-done items, needs a label')
    return packets


def seal(review, annotations_path, output):
    annotations = read(annotations_path)
    validate_annotations(review, annotations)
    result = {'sealed_at': datetime.now(timezone.utc).isoformat(),
              'annotation_count': len(annotations),
              'annotations_sha256': sha(annotations_path),
              'manifest_sha256': sha(review/'manifest.json'),
              'rubric_sha256': sha(review/'rubric.json'),
              'mapping_sha256': sha(review/'mapping_private.json'),
              'scope': 'Completeness and hashes checked before aggregate mapping is read. '
                       'Hash lock does not independently certify reviewer blinding or label correctness.'}
    write_new(output, result)
    return result


def aggregate(review, annotations_path, seal_path, structural_path):
    locked, manifest = read(seal_path), read(review/'manifest.json')
    for path, key in ((annotations_path, 'annotations_sha256'),
                      (review/'manifest.json', 'manifest_sha256'),
                      (review/'rubric.json', 'rubric_sha256'),
                      (review/'mapping_private.json', 'mapping_sha256')):
        if sha(path) != locked[key]:
            raise ValueError('sealed review changed: '+key)
    annotations = read(annotations_path)
    packets = validate_annotations(review, annotations)
    structural = read(structural_path)
    if structural['audit_errors'] or structural['source_hashes']['results.json'] != manifest['results_sha256']:
        raise ValueError('structural audit must pass for the same run')
    mapping = read(review/'mapping_private.json')
    if (len(mapping) != len(packets) or len({m['packet_id'] for m in mapping}) != len(mapping)
            or len({m['call_id'] for m in mapping}) != len(mapping)
            or {m['packet_id'] for m in mapping} != set(packets)):
        raise ValueError('mapping does not cover packets exactly')
    labels = defaultdict(list)
    for a in annotations:
        labels[a['packet_id']].append(a)
    calls = {row['call_id']: row for row in structural['rows']}
    outputs = []
    for m in mapping:
        p, call = packets[m['packet_id']], calls[m['call_id']]
        if any(m[key] != call[key] for key in ('case_id', 'variant')):
            raise ValueError('mapping and audited call differ')
        if p['schema_valid'] != call['schema_valid']:
            raise ValueError('packet validity differs from audit')
        items = {row['item_index']: row['item'] for row in p['items']}
        done = [a for a in labels[m['packet_id']] if items[a['item_index']]['status'] == 'done']
        counts = Counter(a['label'] for a in labels[m['packet_id']])
        done_counts = Counter(a['label'] for a in done)
        outputs.append({'case_id': m['case_id'], 'variant': m['variant'],
                        'condition': call['condition'], 'call_id': m['call_id'],
                        'schema_valid': p['schema_valid'], 'items': len(items), 'done_items': len(done),
                        'all_item_labels': dict(counts), 'done_item_labels': dict(done_counts),
                        'unsupported_done_action': done_counts['unsupported_action_completion'],
                        'ambiguous_done': done_counts['ambiguous']})
    groups = []
    for g in structural['groups']:
        rows = [r for r in outputs if (r['condition'], r['variant']) == (g['condition'], g['variant'])]
        valid = [r for r in rows if r['schema_valid']]
        groups.append({**g, 'reviewed_outputs': len(rows), 'valid_reviewed_outputs': len(valid),
                       'outputs_with_unsupported_done_action': sum(r['unsupported_done_action'] > 0 for r in valid),
                       'outputs_with_unsupported_or_ambiguous_done': sum(r['unsupported_done_action'] + r['ambiguous_done'] > 0 for r in valid),
                       'unsupported_done_action_items': sum(r['unsupported_done_action'] for r in valid),
                       'ambiguous_done_items': sum(r['ambiguous_done'] for r in valid),
                       'done_items': sum(r['done_items'] for r in valid),
                       'all_item_labels': dict(sum((Counter(r['all_item_labels']) for r in valid), Counter()))})
    return {'run_id': structural['run_id'], 'review_complete': True,
            'reviewer': 'one assistant; exploratory, not independent human review',
            'timing': read(review/'rubric.json')['timing'],
            'counts': manifest['counts'], 'groups': groups, 'outputs': outputs,
            'calls': structural['calls'], 'known_total_tokens': structural['known_total_tokens'],
            'unknown_usage_calls': structural['unknown_usage_calls'],
            'annotation_seal': locked, 'structural_audit_sha256': sha(structural_path),
            'scope': 'Four source tasks, one seed per view. Items and repeated controls are not independent tasks. '
                     'Invalid schemas and missing outputs are separate from semantic successes. '
                     'Unsupported completion is not proof of false world state. No repair or task-success claim.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('seal', 'aggregate'))
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--annotations', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal', type=Path)
    parser.add_argument('--structural', type=Path)
    args = parser.parse_args()
    if args.command == 'seal':
        result = seal(args.review, args.annotations, args.output)
        print(json.dumps({'sealed': True, 'annotation_count': result['annotation_count']}))
    else:
        if args.seal is None or args.structural is None:
            parser.error('aggregate needs --seal and --structural')
        result = aggregate(args.review, args.annotations, args.seal, args.structural)
        write_new(args.output, result)
        print(json.dumps({'review_complete': True, 'counts': result['counts']}))


if __name__ == '__main__':
    main()
