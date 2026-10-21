"""Select development query IDs before question/answer access; no task text export."""
import argparse
import hashlib
import json
from pathlib import Path


def choose(rows, policy, revision):
    if revision != policy['revision']:
        raise ValueError('source revision differs from precommitted selection policy')
    ids = []
    for row in rows:
        if set(row) != {'query_id'}:
            raise ValueError('selection input must contain only query_id')
        value = row['query_id']
        if (not isinstance(value, str) or not value or len(value) > 128 or
                any(ord(char) < 32 for char in value)):
            raise ValueError('invalid ID')
        ids.append(value)
    if len(ids) != len(set(ids)) or len(ids) != policy['expected_unique_ids']:
        raise ValueError('duplicate IDs or unexpected cohort size')
    n = policy['development_count']
    if type(n) is not int or not 0 < n < len(ids):
        raise ValueError('invalid development count')
    ranking = lambda value: (hashlib.sha256((policy['salt']+'\0'+value).encode()).hexdigest(), value)
    ranked = sorted(ids, key=ranking)
    return {'selected_ids': ranked[:n], 'unused_candidate_ids': ranked[n:],
            'unique_ids': len(ids), 'selection_used_text_or_outcomes': False,
            'model_calls': 0, 'evaluator_accessed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--ids', type=Path, required=True, help='JSONL containing query_id only')
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('refusing to overwrite an existing selection')
    rows = [json.loads(line) for line in args.ids.read_text().splitlines() if line.strip()]
    result = choose(rows, json.loads(args.policy.read_text()), args.source_revision)
    result.update(source_revision=args.source_revision,
                  id_source_sha256=hashlib.sha256(args.ids.read_bytes()).hexdigest(),
                  policy_sha256=hashlib.sha256(args.policy.read_bytes()).hexdigest(),
                  selector_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ('selected_ids', 'unique_ids', 'model_calls')}))
