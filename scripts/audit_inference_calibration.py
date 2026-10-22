"""Recompute P39 from immutable requests and terminal raw responses."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

from diagnose_projected_misses import model_payload
from field_read_contract import canonical
from inference_cache_control import SCHEDULE, cache_measurement
from local_llama import parse_response

ROOT = Path(__file__).resolve().parents[1]


def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def run(storage, root):
    source = root / 'reports/P39_inference_cache_v02.json'
    report = read(source)
    folder = storage / 'records/context_pilot/P39_inference_cache_v02'
    if (report['status'] != 'complete' or report['unknown_usage_calls']
            or [r['label'] for r in report['rows']] != list(SCHEDULE)):
        raise ValueError('require the closed six-call calibration')
    rows = []
    reference = None
    for original in report['rows']:
        p = folder / original['label']
        request = read(p / 'request.json')
        normalized = dict(request)
        normalized.pop('cache_prompt')
        if reference is None: reference = normalized
        if normalized != reference:
            raise ValueError('conditions differ in more than the cache policy')
        if request['cache_prompt'] != original['label'].startswith('warm_'):
            raise ValueError('wrong per-call reuse flag')
        if sha(p / 'request.json') != original['request_sha256'] or sha(p / 'response.json') != original['response_sha256']:
            raise ValueError('closed request/response changed')
        record = read(p / 'response.json')
        parsed = parse_response(read(p / 'raw_response.json'))
        if any(record[k] != v for k, v in parsed.items()):
            raise ValueError('parsed response differs from raw terminal response')
        measured = cache_measurement(original['label'], parsed, 13552)
        if not measured['state_confirmed'] or any(original[k] != v for k, v in measured.items()):
            raise ValueError('measured condition differs')
        digest = hashlib.sha256(canonical(model_payload(parsed['message'])).encode()).hexdigest()
        if digest != original['model_payload_sha256']:
            raise ValueError('message equality digest differs')
        rows.append({'label': original['label'], **measured, 'wall_seconds': record['wall_seconds'],
                     'message_sha256': digest, 'finish_reason': parsed['done_reason'],
                     'source_sha256': {n: sha(p / n) for n in ('request.json', 'raw_response.json', 'response.json')}})
    total = sum(r['input_tokens'] + r['output_tokens'] for r in rows)
    if total != report['known_total_tokens']:
        raise ValueError('token total differs')
    groups = {k: [r for r in rows if r['label'].startswith(k + '_')] for k in ('cold', 'warm')}
    aggregate = {k: {'calls': len(v), 'mean_wall_seconds': statistics.mean(r['wall_seconds'] for r in v),
                     'unique_messages': len({r['message_sha256'] for r in v}),
                     'processed_tokens': sum(r['processed_tokens'] for r in v),
                     'cached_tokens': sum(r['cached_tokens'] for r in v)} for k, v in groups.items()}
    pairs = [(a, b) for a in groups['cold'] for b in groups['warm']]
    result = {'phase': 'P39_audit_v02', 'all_six_validated': True, 'rows': rows, 'groups': aggregate,
              'cross_equal_pairs': sum(a['message_sha256'] == b['message_sha256'] for a, b in pairs),
              'cross_pairs': len(pairs), 'known_total_tokens': total, 'unknown_usage_calls': 0,
              'source_report_sha256': sha(source), 'audit_script_sha256': sha(Path(__file__)),
              'additional_model_calls': 0, 'additional_environment_api_requests': 0,
              'additional_final_evaluator_calls': 0,
              'interpretation': 'One fixed input with 256-token truncation; message equality and physical processing differ by observed cache condition. No task-quality or novelty claim.'}
    target = root / 'reports/P39_calibration_audit.json'
    if target.exists(): raise FileExistsError('preserve calibration audit')
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'groups': aggregate, 'known_total_tokens': total, 'cross_equal_pairs': result['cross_equal_pairs']}, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT)
    a = p.parse_args(); run(a.storage_root, a.repo_root)
