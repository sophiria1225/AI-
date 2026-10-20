"""Bind assistant-reviewed semantic annotations to P7 outputs; never infer truth from IDs alone.

Packets and annotation templates stay private. Public exports contain only
fixed categories, counts and hashes. No evaluator or post-checkpoint evidence
is included in the review packet.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path

from context_preservation import parse_submission, validate_ledger

CATEGORIES = {'operation_done', 'observation_done', 'requirement_text', 'ambiguous'}
SUPPORT = {'supported', 'unsupported', 'ambiguous'}
REASONS = {'observed_success', 'no_execution', 'observation_contradicts',
           'description_not_completion', 'insufficient_specificity',
           'earlier_valid_evidence', 'error_acknowledgement'}
FAMILIES = {'authentication', 'target_mutation', 'task_completion',
            'documentation', 'retrieval', 'description', 'ambiguous'}


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def item_hash(item):
    return hashlib.sha256(json.dumps(item, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def build_packet(storage, probe_id):
    if probe_id != 'P7_01':
        raise ValueError('only the predeclared P7 probe is supported')
    directory = storage / 'records/memory_probe' / probe_id
    state = read(directory / 'status.json')
    if state['status'] in ('waiting', 'running'):
        raise ValueError('wait for terminal probe status')
    plan = read(directory / 'plan.json')
    source = storage / 'records/context_pilot' / plan['source_run_id']
    source_request = source / plan['source_call_id'] / 'request.json'
    if digest(source_request) != plan['source_request_sha256']:
        raise ValueError('source checkpoint request changed')
    body = json.loads(read(source_request)['messages'][-1]['content'])
    allowed = body['memory']['available_archive_ids']
    # The final source file also contains later turns: filter before exposure.
    saved_spans = read(source / 'spans.json')
    prefix = {key: saved_spans[key] for key in allowed}
    calls = []
    for row in read(directory / 'results.json'):
        request_path = directory / row['call_id'] / 'request.json'
        response_path = directory / row['call_id'] / 'response.json'
        response = read(response_path)
        request_body = json.loads(read(request_path)['messages'][-1]['content'])
        memory = request_body['memory']
        permitted = {span['id'] for span in memory['visible_spans']}
        permitted |= {sid for item in memory.get('working_ledger', {}).get('items', [])
                      for sid in item['source_ids']}
        try:
            ledger = validate_ledger(parse_submission(response['message'], 'submit_ledger'), permitted)
            schema_valid = True
        except (ValueError, KeyError, TypeError, AttributeError):
            ledger, schema_valid = None, False
        if schema_valid != row['schema_valid']:
            raise ValueError('saved schema classification changed')
        calls.append({
            'call_id': row['call_id'], 'variant': row['variant'], 'seed': row['seed'],
            'schema_valid': schema_valid, 'known_tokens': row['known_tokens'],
            'request_sha256': digest(request_path), 'response_sha256': digest(response_path),
            'done_items': [{'index': i, 'item_sha256': item_hash(item), 'item': item}
                           for i, item in enumerate((ledger or {}).get('items', []))
                           if item['status'] == 'done'],
        })
    return {'probe_id': probe_id, 'terminal_status': state['status'],
            'source_request_sha256': digest(source_request), 'task': body['task'],
            'previous_ledger': body['memory'].get('working_ledger'),
            'prefix_spans': prefix, 'calls': calls,
            'known_total_tokens': state['known_total_tokens'],
            'unknown_usage_calls': state['unknown_usage_calls'],
            'scope': 'Single selected development checkpoint. Public prefix only, no evaluator '
                     'and no later environment action. Prior ledger is not ground truth.'}


def template(packet):
    return {'source_request_sha256': packet['source_request_sha256'],
            'reviewer': 'single_assistant_unblinded_exploratory',
            'claims': [{
                'call_id': call['call_id'], 'index': item['index'],
                'response_sha256': call['response_sha256'], 'item_sha256': item['item_sha256'],
                'category': None, 'family': None, 'state_support': None,
                'cited_source_support': None, 'reason': None, 'evidence_span_ids': [],
            } for call in packet['calls'] for item in call['done_items']]}


def export_review(packet, annotations):
    if (annotations['source_request_sha256'] != packet['source_request_sha256']
            or annotations['reviewer'] != 'single_assistant_unblinded_exploratory'):
        raise ValueError('review identity or source changed')
    expected = {(call['call_id'], item['index']): (call, item)
                for call in packet['calls'] for item in call['done_items']}
    actual = {(row['call_id'], row['index']): row for row in annotations['claims']}
    if set(actual) != set(expected) or len(actual) != len(annotations['claims']):
        raise ValueError('every done item needs exactly one bound annotation')
    rows = []
    for key, annotation in actual.items():
        call, item = expected[key]
        if (annotation['response_sha256'] != call['response_sha256']
                or annotation['item_sha256'] != item['item_sha256']):
            raise ValueError('annotation does not match the generated item')
        for field, choices in [('category', CATEGORIES), ('family', FAMILIES),
                               ('state_support', SUPPORT), ('cited_source_support', SUPPORT),
                               ('reason', REASONS)]:
            if annotation.get(field) not in choices:
                raise ValueError('unreviewed or unknown category: ' + field)
        evidence = annotation['evidence_span_ids']
        if (not isinstance(evidence, list) or len(evidence) != len(set(evidence))
                or not set(evidence) <= set(packet['prefix_spans'])):
            raise ValueError('evidence lies outside the reviewed prefix')
        rows.append({key: annotation[key] for key in (
            'call_id', 'index', 'response_sha256', 'item_sha256', 'category', 'family',
            'state_support', 'cited_source_support', 'reason', 'evidence_span_ids')})
    calls = []
    for call in packet['calls']:
        items = [row for row in rows if row['call_id'] == call['call_id']]
        calls.append({key: call[key] for key in (
            'call_id', 'variant', 'seed', 'schema_valid', 'known_tokens',
            'request_sha256', 'response_sha256')} | {
                'reviewed_done_items': len(items),
                'unsupported_operation_done': sum(row['category'] == 'operation_done'
                                                  and row['state_support'] == 'unsupported'
                                                  for row in items),
                'ambiguous_done_items': sum(row['category'] in ('requirement_text', 'ambiguous')
                                            or row['state_support'] == 'ambiguous' for row in items),
                'supported_state_wrong_citation': sum(row['state_support'] == 'supported'
                                                     and row['cited_source_support'] == 'unsupported'
                                                     for row in items),
                'semantic_measurement_available': call['schema_valid'],
            })
    return {'probe_id': packet['probe_id'], 'terminal_status': packet['terminal_status'],
            'source_request_sha256': packet['source_request_sha256'], 'calls': calls,
            'claims': rows, 'reviewer': annotations['reviewer'],
            'known_total_tokens': packet['known_total_tokens'],
            'unknown_usage_calls': packet['unknown_usage_calls'],
            'scope': 'Assistant-reviewed non-blinded exploratory semantic annotation, one selected input, '
                     'three seeds per variant. Not inter-rater agreement, independent tasks, '
                     'task success improvement or validation of a novel mechanism.',
            'evaluators_loaded': False, 'post_checkpoint_evidence_used': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--probe-id', default='P7_01')
    parser.add_argument('--annotations', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    packet = build_packet(args.storage_root, args.probe_id)
    private = args.storage_root / 'records/memory_probe' / args.probe_id / 'semantic_review'
    private.mkdir(exist_ok=True)
    (private / 'packet.json').write_text(json.dumps(packet, ensure_ascii=False, indent=2) + '\n')
    if not args.annotations:
        path = private / 'annotation_template.json'
        if path.exists():
            raise FileExistsError('refuse to replace an existing review template')
        path.write_text(json.dumps(template(packet), ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'calls': len(packet['calls']),
                          'done_items': sum(len(c['done_items']) for c in packet['calls'])}))
        return
    if not args.output:
        raise ValueError('public output path required for completed annotation export')
    report = export_review(packet, read(args.annotations))
    report.update(reviewed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  annotations_sha256=digest(args.annotations), script_sha256=digest(Path(__file__)))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'calls': len(report['calls']), 'reviewed_items': len(report['claims'])}))


if __name__ == '__main__':
    main()
