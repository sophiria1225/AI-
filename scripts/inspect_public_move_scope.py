"""Posthoc public-receipt coverage of the three known P55 photo conditions.

Never loads task databases, evaluator details, generated programs, or a model.
The single task-template parser is analyst supplied after inspecting this case;
it is not a general natural-language contract generator or a new finalizer.
"""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import signal
import time

from inspect_appworld_api_schemas import load_public_tools
from public_move_evidence import MoveRequirement, assess_moves, canonical
from run_handoff_factors import ROOT, read, sha


RUNS = ('P55_01_FULL_KEEP', 'P55_01_DETAILS_OMITTED_KEEP',
        'P55_01_DETAILS_AND_LISTINGS_OMITTED_KEEP')
SOURCE_FILES = ('public_task.json', 'spans.json', 'prefix_events.json', 'events.json',
                'source_identity.json', 'usage.json')
TEMPLATE = re.compile(
    r'Arrange my "([^"]+)" directory by organizing the photos from three vacations\. '
    r'The files created in February and March of this year correspond to (\w+) and (\w+), '
    r'respectively, while the others are from (\w+)\. Move them into sub-directories '
    r'named after their respective vacation spots, maintaining the original file names\.')


def payload(span):
    value = span['observation'].get('observation')
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def digest_text(value):
    return hashlib.sha256(value.encode()).hexdigest()


def inspect_cell(storage, source, schema_hashes):
    folder = storage / 'records/context_pilot' / source['run_id']
    hashes = {name: sha(folder / name) for name in SOURCE_FILES}
    if any(hashes[name] != source['source_sha256'][name] for name in SOURCE_FILES):
        raise ValueError('closed P55 receipt source changed')
    task, spans, prefix, continuation, identity, usage = [read(folder / name) for name in SOURCE_FILES]
    provenance = storage / 'records/context_pilot' / identity['source_run'] / 'provenance.json'
    if (sha(provenance) != identity['source_sha256']['provenance.json']
            or read(provenance)['public_schema_hashes'] != schema_hashes):
        raise ValueError('original public-schema identity changed')
    if task.get('ground_truth_loaded') is not False:
        raise ValueError('only the public task descriptor is allowed')
    match = TEMPLATE.fullmatch(task['instruction'])
    if not match:
        raise ValueError('outside the declared single known instruction template')
    relative_root, february, march, other = match.groups()
    root, home, principal_digest = None, None, None
    requirement = None
    inventory, metadata, moves, clock_years = [], {}, [], []
    taint_reasons, ignored_failed_mutations = [], 0
    seen_spans, sent_names, rejected_clock = set(), Counter(), 0
    first_move_seen = False
    boundaries = []
    state = {'inventory_complete': False}

    def resolve(path):
        if path.startswith('~/') and home is not None:
            path = home + path[1:]
        return str(canonical(path.rstrip('/')))

    def snapshot(label):
        if requirement is None:
            return {'boundary': label, 'trace_support': 'unknown', 'reasons': ['no_complete_initial_inventory']}
        observed_year = clock_years[0] if len(set(clock_years)) == 1 else None
        result = assess_moves(requirement, inventory, list(metadata.values()), moves,
            inventory_complete=state['inventory_complete'], evidence_tainted=bool(taint_reasons),
            current_year=observed_year)
        result['boundary'] = label
        return result

    def consume(event):
        nonlocal root, home, principal_digest, requirement, rejected_clock, first_move_seen, ignored_failed_mutations
        sid = event['span_id']
        if sid in seen_spans or sid not in spans or event.get('effects_unknown'):
            raise ValueError('duplicate, missing, or uncertain public event')
        seen_spans.add(sid)
        span = spans[sid]
        name = span['action']['name']
        if not event.get('api_request_sent'):
            if name == 'phone__get_current_date_and_time':
                rejected_clock += 1
            return
        sent_names[name] += 1
        if name != 'phone__get_current_date_and_time' and not name.startswith('file_system__'):
            return
        raw = span['action']['arguments']
        args = json.loads(raw) if isinstance(raw, str) else raw
        response = payload(span)
        if name == 'phone__get_current_date_and_time':
            # The installed public API formats its simulated date in English.
            # Neither the host clock nor a model's inferred year is evidence.
            if (not isinstance(response, dict) or not isinstance(response.get('date'), str)
                    or not isinstance(response.get('time'), str)):
                taint_reasons.append('unrecognized_public_clock_receipt')
                return
            clock_years.append(datetime.strptime(response['date'], '%A, %B %d, %Y').year)
            return
        if name == 'file_system__login':
            return
        if root is None and name == 'file_system__show_directory':
            if (args.get('directory_path') != relative_root or args.get('substring')
                    or args.get('entry_type', 'all') not in ('all', 'files')
                    or args.get('recursive', True) is not True
                    or not isinstance(response, list) or not response
                    or not all(isinstance(p, str) for p in response)):
                taint_reasons.append('initial_inventory_is_not_the_declared_full_scope')
                return
            parents = {str(canonical(p).parent) for p in response}
            suffix = relative_root[1:].rstrip('/')
            if len(parents) != 1 or not relative_root.startswith('~/'):
                raise ValueError('outside flat, home-relative source scope')
            root = next(iter(parents))
            if not root.endswith(suffix) or not args.get('access_token'):
                raise ValueError('public inventory cannot bind the requested source root')
            home = root[:-len(suffix)]
            canonical(home)
            principal_digest = digest_text(args['access_token'])
            requirement = MoveRequirement(root, ((2, february), (3, march)), other)
            inventory.extend(response)
            state['inventory_complete'] = True
        if root is None:
            if name not in ('file_system__show_file', 'file_system__show_directory'):
                taint_reasons.append('file_mutation_before_source_inventory')
            return
        if digest_text(args.get('access_token', '')) != principal_digest:
            taint_reasons.append('changed_file_credential_scope')
            return
        if name == 'file_system__show_file':
            if not first_move_seen and isinstance(response, dict) and all(k in response for k in ('path', 'file_id', 'created_at')):
                path = resolve(args['file_path'])
                if path == response['path'] and path in inventory:
                    record = {k: response[k] for k in ('path', 'file_id', 'created_at')}
                    if path in metadata and metadata[path] != record:
                        taint_reasons.append('changed_source_metadata_before_moves')
                    metadata[path] = record
        elif name == 'file_system__move_file':
            first_move_seen = True
            if (not isinstance(response, dict) or response.get('message') != 'File moved.'
                    or not isinstance(response.get('destination_file_path'), str)):
                ignored_failed_mutations += 1
                taint_reasons.append('sent_move_without_confirmed_success')
                return
            moves.append({'source': resolve(args['source_file_path']),
                'destination': resolve(args['destination_file_path']),
                'response_destination': resolve(response['destination_file_path']),
                'overwrite': args.get('overwrite', False)})
        elif name == 'file_system__create_directory':
            allowed = {str(PurePosixPath(root) / x) for x in (february, march, other)}
            if resolve(args['directory_path']) not in allowed:
                taint_reasons.append('directory_mutation_outside_declared_destinations')
        elif name != 'file_system__show_directory':
            taint_reasons.append('unhandled_file_system_effect')

    for event in prefix:
        consume(event)
    boundaries.append(snapshot('prefix'))
    for item in usage:
        for event in continuation:
            if event['call'] == item['id']:
                consume(event)
        boundaries.append(snapshot(item['id']))
    if len(seen_spans) != len(prefix) + len(continuation):
        raise ValueError('continuation contains an unaccounted call')
    if sum(sent_names.values()) != source['api_requests'] + source['prefix_api_requests']:
        raise ValueError('public event accounting differs from the closed P55 audit')
    return {'run_id': source['run_id'], 'arm': source['arm'], 'original_official_success': source['success'],
        'public_source_sha256': hashes, 'public_task_sha256': hashes['public_task.json'],
        'public_clock_requests_sent': sent_names['phone__get_current_date_and_time'],
        'undispatched_clock_attempts': rejected_clock, 'public_clock_years_observed': len(clock_years),
        'sent_api_requests_with_prefix': sum(sent_names.values()), 'boundaries': boundaries,
        'final': boundaries[-1], 'taint_reasons': sorted(set(taint_reasons)),
        'sent_moves_without_confirmed_success': ignored_failed_mutations,
        'pre_move_creation_year_counts': dict(sorted(Counter(datetime.fromisoformat(r['created_at']).year for r in metadata.values()).items())),
        'contract_origin': 'analyst-authored parser for one previously inspected public instruction template',
        'first_source_set_covered_boundary': next((b['boundary'] for b in boundaries if b.get('missing_sources') == 0 and b.get('extra_sources') == 0), None),
        'autonomous_completion_validated': False,
        'original_outcome_relabelled': False}


def inspect(storage):
    started = time.monotonic()
    source_path = ROOT / 'reports/P55_comparison.json'
    source = read(source_path)
    if source['audit_errors'] or len(source['rows']) != 12:
        raise ValueError('closed P55 audit required')
    _, schema_hashes, _ = load_public_tools(storage / '.runtime/appworld/r18_probe_01/data')
    rows = []
    for run in RUNS:
        if time.monotonic() - started > 60:
            raise TimeoutError('finite read-only inspection limit')
        row = next(r for r in source['rows'] if r['run_id'] == run)
        rows.append(inspect_cell(storage, row, schema_hashes))
    return {'phase': 'P62_public_move_scope', 'selection': 'posthoc known photo task, all three P55 conditions',
        'rows': rows, 'source_audit_sha256': sha(source_path), 'public_schema_hashes': schema_hashes,
        'public_implementation_sha256': {app: sha(storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps' / app / 'apis.py') for app in ('file_system', 'phone')},
        'inspector_sha256': sha(Path(__file__)), 'checker_sha256': sha(ROOT / 'scripts/public_move_evidence.py'),
        'inspection_wall_seconds': time.monotonic() - started, 'model_generations': 0,
        'environment_api_requests': 0, 'evaluator_calls': 0, 'reserved_scenarios_read': 0,
        'hidden_test_details_read': False, 'task_databases_read': False,
        'autonomous_task_interpreter': False, 'online_finalizer_installed': False,
        'measured_token_savings': None, 'novel_method_claim': False,
        'limits': [
            'Known instruction template and requirements are analyst selected after outcomes were inspected.',
            'This checks normalized recorded support under public API semantics, not external truth or task success.',
            'Successful execution and file credential scope are adapter assumptions, not remote attestation.',
            'A conditional year match never supplies missing current-year evidence.',
            'Source dates are frozen before moves; later current metadata does not replace task-relative historical facts.',
            'No automatic completion, task replay, fresh public clock lookup, or outcome relabelling.',
        ]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, required=True)
    args = parser.parse_args()
    target = ROOT / 'reports/P62_public_move_scope.json'
    if target.exists():
        raise FileExistsError('preserve the prior closed inspection')
    def timeout(signum, frame):
        raise TimeoutError('60-second read-only inspection limit')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(60)
    try:
        result = inspect(args.storage_root)
    finally:
        signal.alarm(0)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'phase': result['phase'], 'wall_seconds': result['inspection_wall_seconds'],
        'rows': [{k: r[k] for k in ('run_id', 'public_clock_requests_sent', 'undispatched_clock_attempts', 'first_source_set_covered_boundary', 'final')} for r in result['rows']]}, ensure_ascii=False))
