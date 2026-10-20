"""Describe update costs under an explicit static-reuse assumption, not causal savings."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage-root', type=Path, required=True)
    parser.add_argument('--memory-sizes', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    measurements = json.loads(args.memory_sizes.read_text())
    trials = []
    for source in measurements['trials']:
        directory = args.storage_root / 'records/context_pilot' / source['run_id']
        usage_path = directory / 'usage.json'
        if digest(usage_path) != source['source_hashes']['usage.json']:
            raise ValueError('memory measurements and recorded calls do not match')
        usage = json.loads(usage_path.read_text())
        positions = {c['id']: i for i, c in enumerate(usage)}
        updates = []
        for index, before_after in enumerate(source['updates']):
            first, last = positions[before_after['first_call']], positions[before_after['last_call']]
            cost = sum(c['input_tokens'] + c['output_tokens'] for c in usage[first:last+1]
                       if c['status'] == 'ok')
            unknown = sum(c['status'] != 'ok' for c in usage[first:last+1])
            after = before_after.get('after_memory_tokens')
            delta = before_after['before_memory_tokens'] - after if after is not None else None
            next_boundary = (positions[source['updates'][index+1]['first_call']]
                             if index + 1 < len(source['updates']) else len(usage))
            reuse = usage[last+1:next_boundary]
            updates.append({
                'update': index + 1, 'first_call': before_after['first_call'],
                'before_memory_tokens': before_after['before_memory_tokens'],
                'after_memory_tokens': after, 'instant_memory_reduction': delta,
                'known_generation_tokens': cost, 'unknown_generation_usage_calls': unknown,
                'static_reuse_calls_to_amortize': math.ceil(cost / delta)
                    if delta is not None and delta > 0 and not unknown else None,
                'following_completed_agent_calls_before_next_update':
                    sum(c['role'] == 'agent' and c['status'] == 'ok' for c in reuse),
                'following_unknown_agent_calls_before_next_update':
                    sum(c['role'] == 'agent' and c['status'] != 'ok' for c in reuse),
                'source_hashes': before_after['source_hashes'],
            })
        trials.append({'run_id': source['run_id'], 'updates': updates,
                       'usage_sha256': digest(usage_path)})
    result = {
        'trials': trials, 'memory_measurements_sha256': digest(args.memory_sizes),
        'script_sha256': digest(Path(__file__)), 'additional_model_calls': 0,
        'formula': 'ceil(update input+output tokens / immediate memory-token reduction), if positive and known',
        'scope': 'Illustrative static reuse horizon. Assumes the same reduction on each future input '
                 'and no changes in actions, outputs, quality or later updates. Reaching the next update '
                 'does not prove previous value is lost. This is neither measured total savings nor a '
                 'causal counterfactual; a negative reduction cannot be amortized under this assumption.',
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'trials': len(trials), 'updates': sum(len(t['updates']) for t in trials)}))


if __name__ == '__main__':
    main()
