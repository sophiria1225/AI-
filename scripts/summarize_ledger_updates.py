"""Aggregate completed ledger trials without exporting ledger text or task truth."""
import argparse
from collections import Counter
import json
from pathlib import Path

from browsecomp_terminal import digest


def summarize(trial):
    summary = json.loads((trial / 'summary.json').read_text())
    if summary['arm'] != 'native_ledger':
        raise ValueError('completed native ledger run required')
    events = json.loads((trial / 'generated_memory_events.json').read_text())
    views = json.loads((trial / 'memory_views.json').read_text())
    rows = []
    for i, event in enumerate(events, 1):
        before, after = event['visible_before'], event['visible_after']
        items = (event.get('ledger_after') or {}).get('items', [])
        rows.append({'update': i, 'status': event['status'],
                     'known_tokens': event['known_tokens'],
                     'unknown_usage_calls': event['unknown_usage_calls'],
                     'original_spans_before': len(before), 'original_spans_after': len(after),
                     'removed_spans': len(set(before) - set(after)),
                     'ledger_items': len(items), 'item_status_counts': dict(Counter(item['status'] for item in items))})
    return {'run_id': trial.name, 'updates': rows,
            'update_status_counts': dict(Counter(r['status'] for r in rows)),
            'updates_removing_original_spans': sum(r['removed_spans'] > 0 for r in rows),
            'executor_inputs_with_removed_turns': sum(v['selection']['retained_turns'] < v['selection']['original_turns'] for v in views),
            'executor_inputs_with_memory_note': sum(v['selection']['memory_note_added'] for v in views),
            'known_memory_tokens': sum(r['known_tokens'] for r in rows),
            'unknown_memory_usage_calls': sum(r['unknown_usage_calls'] for r in rows),
            'source_hashes': {name: digest(trial / name) for name in ('summary.json','generated_memory_events.json','memory_views.json')},
            'scope': 'Completed-run structural counts only. Done labels and references are not semantic proof. No generation or environment execution.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.trial)
    result['script_sha256'] = digest(Path(__file__))
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('updates','source_hashes','scope')}))
