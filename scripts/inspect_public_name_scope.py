"""Compare admission checks on saved P29/P55 Python requests without dispatch."""
import argparse
from collections import Counter
from importlib.metadata import distributions
import json
from pathlib import Path
import signal
import time

from appworld_native_tools import NativeCatalog
from inspect_appworld_api_schemas import load_public_tools
from public_name_catalog import PublicNameCatalog
from run_handoff_factors import ROOT, read, sha


def admitted(catalog, action):
    try:
        decoded = catalog.decode(action)
        return set(decoded) == {'app', 'api', 'args'}, decoded
    except (ValueError, KeyError, TypeError):
        return False, None


def inspect_requests(events, spans, public_tools):
    legacy, named = NativeCatalog(public_tools), PublicNameCatalog(public_tools)
    counts = Counter()
    rows, seen = [], set()
    for boundary, event in events:
        sid = event['span_id']
        if sid in seen or sid not in spans or event.get('effects_unknown'):
            raise ValueError('duplicate, missing, or uncertain original event')
        seen.add(sid)
        span = spans[sid]
        if event.get('stage') == 'python_api':
            counts['python_api_events'] += 1
            old_ok, old_call = admitted(legacy, span['action'])
            new_ok, new_call = admitted(named, span['action'])
            if event.get('api_request_sent') and not old_ok:
                raise ValueError('recorded dispatch disagrees with legacy admission')
            if old_ok:
                if not new_ok or new_call != old_call:
                    raise ValueError('named access changed an already admitted request')
                counts['already_argument_valid'] += 1
            else:
                counts['legacy_rejected_requests'] += 1
                raw_name = span['action'].get('name') if isinstance(span['action'], dict) else None
                known_name = isinstance(raw_name, str) and raw_name in legacy.catalog
                unexposed = known_name and raw_name not in legacy.visible
                if new_ok:
                    if not unexposed:
                        raise ValueError('admission changed for a reason other than exposure')
                    counts['named_argument_valid_requests'] += 1
                rows.append({'boundary': boundary, 'call_id': event['call'], 'span_id': sid,
                    'api': raw_name if known_name else 'outside_public_catalog',
                    'public_name_known': known_name, 'definition_exposed': known_name and not unexposed,
                    'eligible_under_named_argument_check': new_ok,
                    'original_request_sent': bool(event.get('api_request_sent')),
                    'is_execution_or_success_prediction': False})
        elif event.get('stage') == 'model_tool':
            counts['outer_model_tool_events'] += 1
        else:
            raise ValueError('not a Python trace')
        added = event['new_tools']
        if type(added) is not list or any(n not in legacy.catalog for n in added):
            raise ValueError('invalid recorded public schema discovery')
        legacy.visible.update(added)
        named.visible.update(added)
        if legacy.tools() != named.tools():
            raise ValueError('the comparison unexpectedly changed presented tool definitions')
    if seen != set(spans):
        raise ValueError('unaccounted original spans')
    for key in ('python_api_events', 'outer_model_tool_events', 'already_argument_valid',
                'legacy_rejected_requests', 'named_argument_valid_requests'):
        counts.setdefault(key, 0)
    return {'event_visits': len(events), 'counts': dict(counts), 'rejected_request_checks': rows}


def inspect(storage):
    started = time.monotonic()
    tools, schema_hashes, _ = load_public_tools(storage / '.runtime/appworld/r18_probe_01/data')
    p50 = read(ROOT / 'configs/P50_baseline_repair_census_v01.json')
    p55 = read(ROOT / 'reports/P55_comparison.json')
    if p55['audit_errors'] or len(p55['rows']) != 12:
        raise ValueError('closed all-twelve P55 audit required')
    specs = []
    for cell in p50['cells']:
        if cell['phase'] == 'P29':
            specs.append((cell['run_id'], cell['task_id'], cell['source_sha256'], False))
    if len(specs) != 4:
        raise ValueError('all four P29 source cells required')
    specs += [(r['run_id'], r['task_id'], r['source_sha256'], True) for r in p55['rows']]
    rows = []
    for run, task, expected, has_prefix in specs:
        folder = storage / 'records/context_pilot' / run
        names = ['spans.json', 'events.json'] + (['prefix_events.json', 'source_identity.json'] if has_prefix else ['provenance.json'])
        hashes = {name: sha(folder / name) for name in names}
        if any(hashes[name] != expected[name] for name in names):
            raise ValueError('original closed Python trace changed')
        if has_prefix:
            identity = read(folder / 'source_identity.json')
            provenance_path = storage / 'records/context_pilot' / identity['source_run'] / 'provenance.json'
            if sha(provenance_path) != identity['source_sha256']['provenance.json']:
                raise ValueError('source provenance changed')
        else:
            provenance_path = folder / 'provenance.json'
        if read(provenance_path)['public_schema_hashes'] != schema_hashes:
            raise ValueError('original public schemas changed')
        events = ([('prefix', e) for e in read(folder / 'prefix_events.json')] if has_prefix else [])
        events += [('continuation' if has_prefix else 'whole_task', e) for e in read(folder / 'events.json')]
        if sum(r['event_visits'] for r in rows) + len(events) > 6000:
            raise ValueError('finite source-event limit')
        result = inspect_requests(events, read(folder / 'spans.json'), tools)
        rows.append({'run_id': run, 'task_id': task, 'source_sha256': hashes, **result})
    groups = {}
    for prefix in ('P29_', 'P55_'):
        selected = [r for r in rows if r['run_id'].startswith(prefix)]
        counts = Counter()
        for row in selected:
            counts.update(row['counts'])
        eligible = [c for r in selected for c in r['rejected_request_checks'] if c['eligible_under_named_argument_check']]
        groups[prefix[:3]] = {'recorded_runs': len(selected), 'event_visits': sum(r['event_visits'] for r in selected),
            **dict(counts), 'newly_argument_valid_api_counts': dict(Counter(c['api'] for c in eligible))}
    public_source = storage / '.runtime/appworld/venv/lib/python3.12/site-packages/appworld'
    versions = [d.version for d in distributions(path=[str(public_source.parent)])
                if d.metadata.get('Name', '').lower() == 'appworld']
    if versions != ['0.1.3.post1']:
        raise ValueError('installed AppWorld distribution differs from the inspected version')
    return {'phase': 'P63_public_name_scope', 'selection': 'all four known P29 Python baselines and all twelve P55 continuations with their repeated prefixes',
        'rows': rows, 'groups': groups, 'distinct_known_tasks': len({r['task_id'] for r in rows}),
        'source_hashes': {p: sha(ROOT / p) for p in ('configs/P50_baseline_repair_census_v01.json', 'reports/P55_comparison.json')},
        'public_schema_hashes': schema_hashes,
        'installed_public_implementation': {'package_version': versions[0],
            'files': {p: sha(public_source / p) for p in ('collections/apis.py', 'environment.py')},
            'read_scope': 'ApiCollection.load binds permitted public names on construction; environment initializes this collection. No hidden tests or task databases.'},
        'inspector_sha256': sha(Path(__file__)), 'catalog_sha256': sha(ROOT / 'scripts/public_name_catalog.py'),
        'wall_seconds': time.monotonic() - started, 'model_generations': 0, 'environment_api_requests': 0,
        'evaluator_calls': 0, 'program_reexecutions': 0, 'reserved_scenarios_read': 0,
        'old_native_policy_changed': False, 'old_python_policy_changed': False,
        'measured_savings': None, 'novel_method_claim': False,
        'limits': ['Fixed recorded requests only; newly accepted actions are not executed or predicted successful.',
            'P55 repeats P29 source prefixes; event visits are not distinct actual requests or independent tasks.',
            'Public metadata visibility remains unchanged; named admission does not provide missing arguments or credentials.',
            'The environment still validates required parameters, types, authorization, and task-specific app availability.',
            'This is an opt-in ordinary comparator, not proof of task-quality improvement or token savings.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root', type=Path, required=True)
    args = parser.parse_args()
    target = ROOT / 'reports/P63_public_name_scope.json'
    if target.exists():
        raise FileExistsError('preserve the prior inspection')
    def timeout(signum, frame):
        raise TimeoutError('120-second read-only inspection bound')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(120)
    try:
        result = inspect(args.storage_root)
    finally:
        signal.alarm(0)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'groups': result['groups'], 'wall_seconds': result['wall_seconds']}))
