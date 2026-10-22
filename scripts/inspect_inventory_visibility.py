"""Describe literal API-name visibility in every fixed P55 initial input.

This is not a semantic-memory test or a new task-outcome comparison. API names
can remain in action code even after their descriptive inventory is omitted.
"""
import argparse
import json
from pathlib import Path
import re

from budget_signal import digest
from inventory_display import ARMS, build_condition
from later_handoff_sources import prepare_later_sources
from run_handoff_factors import ROOT, read, sha
from run_context_comparison import write_json


def visible_names(names, messages):
    # Search the actual model-visible strings, not JSON keys or hidden state.
    text = '\n'.join(str(message.get('content') or '') + '\n' +
                     json.dumps(message.get('tool_calls', []), ensure_ascii=False)
                     for message in messages)
    return sorted(name for name in names if re.search(
        r'(?<![A-Za-z0-9_])' + re.escape(name) + r'(?![A-Za-z0-9_])', text))


def inspect(storage, frozen):
    pre = read(frozen / 'reports/P55_prefix_checks.json')
    if pre['status'] != 'complete':
        raise ValueError('complete fixed preflight required')
    _, original, _, _, items = prepare_later_sources(storage, frozen)
    rows = []
    for item, fixed in zip(items, pre['rows'], strict=True):
        views = {}
        for arm in ARMS:
            view, transfer = build_condition(item, arm)
            messages, _ = view.for_model(original['observation_page_characters'])
            if digest(messages) != fixed['conditions'][arm]['base_messages_sha256']:
                raise ValueError('visibility inspection differs from fixed preflight')
            views[arm] = messages
        changes = transfer['selection']['changes']
        selected = sorted({sid for change in changes for sid in change['listing_receipt_ids']})
        listings = []
        for sid in selected:
            span = item['prefix']['spans'][sid]
            if span['action']['name'] != 'api_docs__show_api_descriptions':
                raise ValueError('fixed cohort unexpectedly contains another listing shape')
            value = json.loads(span['observation']['observation'])
            names = [entry['name'] for entry in value]
            if len(names) != len(set(names)) or any(not isinstance(name, str) for name in names):
                raise ValueError('invalid public API-name inventory')
            matched = {arm: visible_names(names, messages) for arm, messages in views.items()}
            listings.append({'receipt_id': sid, 'listed_api_names': len(names),
                'literal_name_counts_in_input': {arm: len(values) for arm, values in matched.items()},
                'names_present_in_D_but_not_B': len(set(matched[ARMS[1]]) - set(matched[ARMS[2]])),
                'source_span_sha256': digest(span),
                'scope': 'Name occurrence anywhere in the supplied messages; not app-qualified semantic access.'})
        rows.append({'source_run': item['source_run'], 'boundary_manifest_sha256': item['boundary_manifest_sha256'],
            'listing_receipts': listings, 'D_B_base_identical': fixed['detail_vs_both_base_equal'],
            'model_input_sha256': {a: digest(v) for a, v in views.items()}})
    return {'phase': 'P55_initial_inventory_visibility', 'rows': rows,
        'preflight_sha256': sha(frozen / 'reports/P55_prefix_checks.json'),
        'inspector_sha256': sha(Path(__file__)), 'model_calls': 0, 'tokenizer_calls': 0,
        'environment_api_requests': 0, 'evaluator_calls': 0, 'reserved_scenarios_read': 0,
        'continuation_outcomes_used': False,
        'limits': ['Literal occurrence does not imply knowledge of meaning or successful use.',
            'Shared short names across apps may produce incidental matches.',
            'Persistent Python, exposed api_schemas, archives, and earlier code remain available.',
            'Counts are name occurrences, not token savings or a causal mediator estimate.']}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--frozen-root', type=Path, required=True)
    args = p.parse_args()
    target = ROOT / 'reports/P55_initial_inventory_visibility.json'
    if target.exists(): raise FileExistsError('preserve prior inspection')
    result = inspect(args.storage_root, args.frozen_root)
    write_json(target, result)
    print(json.dumps([{'source': r['source_run'], 'lists': r['listing_receipts']} for r in result['rows']]))
