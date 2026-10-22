"""Apply the unchanged P62 normalization rules to the two new P64 photo traces.

The three original P62 records are parity controls, not additional independent
cases. This inspection never calls a model, API, evaluator, or generated program.
"""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path, PurePosixPath
import signal
import time

from inspect_public_move_scope import TEMPLATE, payload, digest_text
from public_move_evidence import MoveRequirement, assess_moves, canonical
from run_handoff_factors import ROOT, read, sha


def inspect_records(task, spans, prefix, continuation, usage, source):
    """P62 receipt normalization, preserved for this additional fixed population."""
    if task.get('ground_truth_loaded') is not False:
        raise ValueError('public task only')
    if len(prefix)+len(continuation) > 4000:
        raise ValueError('bounded event population exceeded')
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
        name = (span.get('action') or {}).get('name')
        if not event.get('api_request_sent'):
            if name == 'phone__get_current_date_and_time':
                rejected_clock += 1
            return
        if not isinstance(name, str):
            raise ValueError('sent API event must have an action name')
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
        raise ValueError('public event accounting differs from the closed source audit')
    return {'run_id': source['run_id'], 'arm': source['arm'], 'original_official_success': source['success'],
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


def load_records(folder, expected):
    records, hashes = {}, {}
    for name in ('public_task', 'spans', 'events', 'usage'):
        path = folder / (name + '.json'); hashes[name + '.json'] = sha(path)
        if hashes[name + '.json'] != expected[name + '.json']:
            raise ValueError('closed source changed: ' + name)
        records[name] = read(path)
    return records, hashes


def later_cost(boundaries, usage):
    """Describe already observed suffix cost, never counterfactual saved cost."""
    first = next((b['boundary'] for b in boundaries if b['trace_support'] == 'supported'), None)
    if first is None: return None
    positions = {u['id']: n for n, u in enumerate(usage)}
    if first not in positions: raise ValueError('supported boundary must be a model-call boundary')
    remaining = usage[positions[first]+1:]
    known = [c for c in remaining if c['usage_known']]
    return {'first_supported_boundary': first, 'later_model_calls': len(remaining),
        'later_known_tokens': sum(c['input_tokens']+c['output_tokens'] for c in known),
        'later_unknown_usage_calls': len(remaining)-len(known),
        'is_measured_saved_cost': False, 'controller_installed': False}


def inspect(storage):
    began = time.monotonic()
    old_path = ROOT / 'reports/P62_public_move_scope.json'
    if sha(old_path) != '8f99d38b6497c186d170b907ed01881a10d9b37a78fcf4f7c74b3b89084aa6c5':
        raise ValueError('fixed original scope report changed')
    old = read(old_path)
    if (old['checker_sha256'] != sha(ROOT / 'scripts/public_move_evidence.py')
            or old['inspector_sha256'] != sha(ROOT / 'scripts/inspect_public_move_scope.py')):
        raise ValueError('keep the original P62 semantics and code unchanged')
    for app, digest in old['public_implementation_sha256'].items():
        path = storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld/apps' / app / 'apis.py'
        if sha(path) != digest: raise ValueError('public API semantics changed')
    parity = []
    for original in old['rows']:
        folder = storage / 'records/context_pilot' / original['run_id']
        records, _ = load_records(folder, original['public_source_sha256'])
        if sha(folder / 'prefix_events.json') != original['public_source_sha256']['prefix_events.json']:
            raise ValueError('original prefix changed')
        source = {'run_id': original['run_id'], 'arm': original['arm'],
            'success': original['original_official_success'],
            'api_requests': original['sent_api_requests_with_prefix'], 'prefix_api_requests': 0}
        actual = inspect_records(records['public_task'], records['spans'], read(folder / 'prefix_events.json'),
            records['events'], records['usage'], source)
        # Original reports were serialized: JSON object keys are strings.
        # Compare the same representation, preserving all fields and values.
        serialized = json.loads(json.dumps(actual, allow_nan=False))
        differences = [k for k, v in serialized.items() if original[k] != v]
        if differences: raise ValueError('P62 parity failure: ' + ','.join(differences))
        parity.append({'run_id': source['run_id'], 'matched_fields': len(actual), 'differences': differences})
    audit_path = ROOT / 'reports/P64_public_name_audit.json'; audit = read(audit_path)
    if (audit['audit_errors'] or not audit['server_stopped'] or audit['owned_server_processes_present']
            or len(audit['rows']) != 4):
        raise ValueError('closed and reconciled all-four P64 audit required')
    plan = read(ROOT / 'configs/P64_public_name_comparison_v01.json')
    if audit['plan_sha256'] != sha(ROOT / 'configs/P64_public_name_comparison_v01.json'):
        raise ValueError('P64 plan changed')
    rows = []
    for rid in ('P64_01_PHOTO_DOCUMENTED', 'P64_02_PHOTO_NAMED'):
        entry = next(r for r in audit['rows'] if r['run_id'] == rid)
        if entry['task_id'] != '34d9492_1': raise ValueError('known photo task only')
        if entry['status'] == 'not_run':
            rows.append({'run_id': rid, 'arm': entry['arm'], 'status': 'not_run'}); continue
        expected = {name+'.json': digest for name, digest in entry['source_sha256'].items()}
        expected['public_task.json'] = plan['source_public_task_sha256'][0]
        records, hashes = load_records(storage / 'records/context_pilot' / rid, expected)
        source = {'run_id': rid, 'arm': entry['arm'], 'success': entry['official_success'],
            'api_requests': entry['api_requests'], 'prefix_api_requests': 0}
        result = inspect_records(records['public_task'], records['spans'], [], records['events'], records['usage'], source)
        result.update(status=entry['status'], source_sha256=hashes,
            observed_cost_after_first_supported_boundary=later_cost(result['boundaries'], records['usage']))
        rows.append(result)
    return {'phase': 'P65_public_move_scope', 'selection': 'both P64 photo conditions; three P62 normalization parity controls',
        'known_tasks': 1, 'new_conditions': 2, 'old_parity_controls': parity, 'rows': rows,
        'source_report_sha256': {'P62': sha(old_path), 'P64': sha(audit_path)},
        'inspector_sha256': sha(Path(__file__)), 'checker_sha256': sha(ROOT / 'scripts/public_move_evidence.py'),
        'public_implementation_sha256': old['public_implementation_sha256'],
        'wall_seconds': time.monotonic()-began, 'model_generations': 0, 'environment_api_requests': 0,
        'program_executions': 0, 'evaluator_calls': 0, 'task_databases_read': False,
        'reserved_scenarios_read': 0, 'online_finalizer_installed': False, 'novel_method_claim': False,
        'limits': ['Same analyst-authored known instruction template and strict P62 normalizer.',
            'No adaptation for unsupported scopes, mutations or metadata shapes; unsupported remains unknown.',
            'Trace support is conditional on trusted public API semantics and receipt normalization, not a general task verifier.',
            'Later observed cost is not a saving, and no counterfactual suffix or automatic completion was executed.',
            'Official outcomes and original P62/P64 records are unchanged.']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True); a = p.parse_args()
    target = ROOT / 'reports/P65_public_move_scope.json'
    if target.exists(): raise FileExistsError('preserve original inspection')
    def timeout(*_): raise TimeoutError('fixed 120-second passive inspection limit')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(120)
    try: result = inspect(a.storage_root)
    finally: signal.alarm(0)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'phase': result['phase'], 'wall_seconds': result['wall_seconds'],
        'parity_controls': len(result['old_parity_controls']),
        'rows': [{k: r.get(k) for k in ('run_id', 'status', 'final', 'observed_cost_after_first_supported_boundary')} for r in result['rows']]}, ensure_ascii=False))

