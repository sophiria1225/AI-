"""Post-hoc accounting of all P55 calls; no stopping policy or new execution.

A last mutation request is an accounting boundary, not evidence of completion.
Likewise, a call whose only sent API is completion can still contain reasoning
and local computation. Neither subtotal is a measured saving.
"""
import argparse
from collections import Counter
from pathlib import Path
import time

from inspect_appworld_api_schemas import load_public_tools
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


CATEGORIES = {
    'task_mutation_request': ('file_system__create_directory', 'file_system__move_file',
                              'venmo__create_transaction'),
    'completion_request': ('supervisor__complete_task',),
    'authentication_request': ('phone__login', 'venmo__login'),
    'documentation_request': ('api_docs__show_api_descriptions', 'api_docs__show_api_doc',
                              'api_docs__search_api_docs'),
    'information_request': ('file_system__show_file', 'file_system__show_directory',
        'supervisor__show_profile', 'supervisor__show_active_task',
        'phone__get_current_date_and_time', 'phone__show_contact_relationships',
        'phone__search_contacts', 'venmo__show_transaction',
        'venmo__show_venmo_balance', 'spotify__show_song'),
}


def classify(name):
    matches = [kind for kind, names in CATEGORIES.items() if name in names]
    if len(matches) != 1:
        raise ValueError('unclassified or ambiguous public API: ' + name)
    return matches[0]


def cost(calls):
    known = [c for c in calls if c['known_total_tokens'] is not None]
    return {'model_calls': len(calls), 'known_total_tokens': sum(c['known_total_tokens'] for c in known),
        'known_input_tokens': sum(c['input_tokens'] for c in known),
        'known_output_tokens': sum(c['output_tokens'] for c in known),
        'known_cached_input_tokens': sum(c['cached_input_tokens'] for c in known),
        'known_uncached_input_plus_output_tokens': sum(c['input_tokens'] - c['cached_input_tokens']
                                                      + c['output_tokens'] for c in known),
        'unknown_usage_calls': len(calls) - len(known),
        'model_request_wall_seconds': sum(c['model_request_wall_seconds'] for c in calls),
        'sent_api_requests': sum(c['sent_api_requests'] for c in calls)}


def mutation_tail(calls):
    indices = [i for i, c in enumerate(calls) if c['sent_categories'].get('task_mutation_request', 0)]
    if not indices:
        return {'boundary_call': None, 'cost_after_boundary': None,
                'reason': 'No classified task-mutation request in this continuation.'}
    index = indices[-1]
    return {'boundary_call': calls[index]['call_id'], 'cost_after_boundary': cost(calls[index + 1:]),
            'is_completion_or_safely_removable_boundary': False}


def inspect(storage):
    started = time.monotonic()
    source = ROOT / 'reports/P55_comparison.json'
    report = read(source)
    if (report['audit_errors'] or len(report['rows']) != 12
            or any(r['record_status'] != 'evaluated' for r in report['rows'])):
        raise ValueError('closed all-twelve audited results required')
    tools, schema_hashes, _ = load_public_tools(storage / '.runtime/appworld/r18_probe_01/data')
    catalog = {t['function']['name']: t['function'] for t in tools}
    mapped = {n for names in CATEGORIES.values() for n in names}
    if not mapped <= catalog.keys():
        raise ValueError('classified API is absent from the public schema')
    # Reuse the original audit linkage, not a fresh task/evaluator run.
    cells, all_calls, source_hashes = [], [], {}
    for row in report['rows']:
        folder = storage / 'records/context_pilot' / row['run_id']
        names = ('events.json', 'spans.json', 'usage.json', 'summary.json', 'source_identity.json')
        digests = {name: sha(folder / name) for name in names}
        if any(digests[name] != row['source_sha256'][name] for name in names):
            raise ValueError('original audited records changed')
        source_hashes[row['run_id']] = digests
        events, spans, usage, summary, identity = [read(folder / name) for name in names]
        provenance = storage / 'records/context_pilot' / identity['source_run'] / 'provenance.json'
        if (sha(provenance) != identity['source_sha256']['provenance.json']
                or read(provenance)['public_schema_hashes'] != schema_hashes):
            raise ValueError('public API schema differs from original execution')
        ids = [u['id'] for u in usage]
        if len(set(ids)) != len(ids) or any(e['call'] not in ids or e.get('effects_unknown') for e in events):
            raise ValueError('unlinked event or unknown API effects')
        calls = []
        for u in usage:
            entries = [e for e in events if e['call'] == u['id']]
            sent = [e for e in entries if e.get('api_request_sent')]
            counts = Counter(spans[e['span_id']]['action']['name'] for e in sent)
            categories = Counter()
            for name, count in counts.items():
                categories[classify(name)] += count
            known = u['status'] == 'ok'
            if known:
                if (any(type(u[k]) is not int or u[k] < 0 for k in
                        ('input_tokens', 'output_tokens', 'cached_input_tokens'))
                        or u['cached_input_tokens'] > u['input_tokens']):
                    raise ValueError('invalid known token accounting')
            elif u['input_tokens'] is not None or u['output_tokens'] is not None:
                raise ValueError('unknown usage must remain unknown')
            c = {'call_id': u['id'], 'usage_status': u['status'],
                'input_tokens': u['input_tokens'], 'output_tokens': u['output_tokens'],
                'cached_input_tokens': u['cached_input_tokens'],
                'known_total_tokens': u['input_tokens'] + u['output_tokens'] if known else None,
                'model_request_wall_seconds': u['wall_seconds'],
                'sent_api_requests': len(sent), 'sent_api_names': dict(sorted(counts.items())),
                'sent_categories': dict(sorted(categories.items())),
                'unsent_events': len(entries) - len(sent),
                'only_sent_api_is_completion': bool(sent) and set(counts) == {'supervisor__complete_task'},
                'no_sent_environment_api': not sent}
            calls.append(c)
        totals = cost(calls)
        if (totals['model_calls'] != row['model_calls'] or totals['known_total_tokens'] != row['known_total_tokens']
                or totals['unknown_usage_calls'] != row['unknown_usage_calls']
                or totals['sent_api_requests'] != row['api_requests']):
            raise ValueError('all-call accounting differs from original audit')
        cells.append({'run_id': row['run_id'], 'task_id': row['task_id'], 'arm': row['arm'],
            'original_success': row['success'], 'stop_reason': summary['stop_reason'],
            'calls': calls, 'total': totals, 'after_last_classified_mutation_request': mutation_tail(calls),
            'completion_only_sent_api_cost': cost([c for c in calls if c['only_sent_api_is_completion']]),
            'no_sent_api_call_cost': cost([c for c in calls if c['no_sent_environment_api']])})
        all_calls.extend(calls)
    completion = [c for c in all_calls if c['only_sent_api_is_completion']]
    return {'phase': 'P57_terminal_cost_scope', 'inspection': 'post_hoc_read_only',
        'all_twelve_cells_accounted': True, 'rows': cells, 'total': cost(all_calls),
        'completion_only_sent_api_cost': cost(completion),
        'no_sent_api_call_cost': cost([c for c in all_calls if c['no_sent_environment_api']]),
        'public_api_categories': CATEGORIES, 'public_schema_hashes': schema_hashes,
        'source_audit_sha256': sha(source), 'source_sha256': source_hashes,
        'inspector_sha256': sha(Path(__file__)), 'inspection_wall_seconds': time.monotonic() - started,
        'model_generations': 0, 'environment_api_requests': 0, 'evaluator_calls': 0,
        'hidden_test_details_read': False, 'reserved_scenarios_read': 0,
        'safe_online_stopping_rule_established': False, 'measured_token_savings': None,
        'limits': ['Every P55 call is retained; this is not a new independent task or agent trial.',
            'API categories use the public descriptions, not observed per-call database deltas.',
            'A sent mutation request does not establish success, task completion, or lack of collateral effects.',
            'Information requests may be necessary verification; zero sent APIs may include needed local computation or repair.',
            'Only-sent-API completion still includes the model reasoning and local execution in that call.',
            'Primary tokens include cached input. Uncached-input-plus-output is descriptive, not billed cost.',
            'Model-request time is not whole-work time and is not proven removable.',
            'No runtime finalizer, replay, original outcome relabeling, or imputation of unknown usage.']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    args = p.parse_args(); target = ROOT / 'reports/P57_terminal_cost_scope.json'
    if target.exists(): raise FileExistsError('preserve prior inspection')
    result = inspect(args.storage_root); write_json(target, result)
    print({k: result[k] for k in ('total', 'completion_only_sent_api_cost', 'inspection_wall_seconds')})
