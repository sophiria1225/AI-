"""Post-batch format and generation-budget audit; never publish response text."""
import argparse
import collections
import hashlib
import json
from pathlib import Path

from data_export_probe import submission
from local_llama import parse_response


def audit(directory):
    state = json.loads((directory / 'status.json').read_text())
    if state['status'] != 'complete':
        raise ValueError('whole generation batch must be complete')
    plan = json.loads((directory / 'plan.json').read_text())
    usage = json.loads((directory / 'usage.json').read_text())
    original = json.loads((directory / 'results.json').read_text())
    if len(usage) != len(original) or len(usage) != plan['max_calls']:
        raise ValueError('incomplete batch')
    rows = []
    for u, r in zip(usage, original):
        if u['status'] != 'ok' or u['id'] != r['call_id']:
            raise ValueError('unknown usage or call order mismatch')
        raw = json.loads((directory / u['id'] / 'raw_response.json').read_text())
        parsed = parse_response(raw)
        if any(parsed[k] != u[k] for k in ('input_tokens', 'output_tokens')):
            raise ValueError('raw usage mismatch')
        if parsed['done_reason'] != u['finish_reason']:
            raise ValueError('finish reason mismatch')
        m = parsed['message']
        try:
            submission(m, r['variant'])
            shape_valid = True
        except (ValueError, TypeError, KeyError, AttributeError):
            shape_valid = False
        valid = shape_valid and u['finish_reason'] != 'length'
        if valid != r['schema_valid']:
            raise ValueError('recorded schema flag disagrees with raw response')
        rows.append({
            'call_id': u['id'], 'variant': r['variant'], 'seed': r['seed'],
            'input_tokens': u['input_tokens'], 'output_tokens': u['output_tokens'],
            'cached_input_tokens': parsed['cached_input_tokens'],
            'wall_seconds': u['wall_seconds'], 'finish_reason': u['finish_reason'],
            'hit_output_cap': u['output_tokens'] == plan['max_output_tokens'],
            'schema_valid': valid, 'submission_shape_valid_even_if_truncated': shape_valid,
            'final_tool_calls': len(m.get('tool_calls') or []),
            'content_characters': len(m.get('content') or ''),
            'reasoning_characters': len(m.get('reasoning_content') or ''),
        })
    known = sum(r['input_tokens'] + r['output_tokens'] for r in rows)
    if known != state['known_total_tokens']:
        raise ValueError('terminal total mismatch')
    return {
        'phase': plan['phase'], 'outputs': rows, 'model_calls': len(rows),
        'known_total_tokens': known, 'unknown_usage_calls': 0,
        'total_input_tokens': sum(r['input_tokens'] for r in rows),
        'total_output_tokens': sum(r['output_tokens'] for r in rows),
        'summed_generation_seconds': sum(r['wall_seconds'] for r in rows),
        'batch_wall_seconds': state['wall_seconds'],
        'finish_reason_counts': dict(collections.Counter(r['finish_reason'] for r in rows)),
        'schema_disagreements': 0,
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope': 'Post-batch mechanical format, raw-response and budget audit. Character counts are not a reasoning-token decomposition or an explanation of the internal cause.',
    }


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--run-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = audit(a.run_dir)
    with a.output.open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({k: result[k] for k in ('model_calls', 'known_total_tokens', 'finish_reason_counts', 'schema_disagreements')}))
