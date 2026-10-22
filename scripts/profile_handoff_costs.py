"""Passive cost profile of complete, audited handoff experiments.

Only aggregate lengths, token counts, timings and source hashes leave the private
record. Visible character counts are not token attributions or attainable cost
savings. Unknown terminal usage remains unknown. No tokenizer/model/API calls.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from diagnose_handoff_programs import require_complete
from handoff_factors import ARMS

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def visible_characters(payload):
    """Raw field lengths, counted per exposure, not JSON/template/token lengths."""
    sizes = Counter({k: 0 for k in (
        'system', 'original_task', 'assistant_text', 'function_arguments',
        'tool_receipts', 'other_user_receipts', 'other')})
    inner = Counter({k: 0 for k in ('python_stdout', 'python_code')})
    for index, message in enumerate(payload['messages']):
        role = message['role']
        text = message.get('content') or ''
        if not isinstance(text, str):
            raise ValueError('non-text message outside current profile scope')
        if role == 'system':
            category = 'system'
        elif role == 'user' and index == 1:
            category = 'original_task'
        elif role == 'assistant':
            category = 'assistant_text'
        elif role == 'tool':
            category = 'tool_receipts'
        elif role == 'user':
            category = 'other_user_receipts'
        else:
            category = 'other'
        sizes[category] += len(text)
        if role in ('tool', 'user') and not (role == 'user' and index == 1):
            try:
                observation = json.loads(text).get('observation', {})
                if type(observation) is dict and type(observation.get('stdout')) is str:
                    inner['python_stdout'] += len(observation['stdout'])
            except (ValueError, AttributeError):
                pass
        for call in message.get('tool_calls') or []:
            arguments = call['function']['arguments']
            if type(arguments) is not str:
                raise ValueError('unexpected function arguments')
            sizes['function_arguments'] += len(arguments)
            try:
                value = json.loads(arguments)
                if call['function']['name'] == 'run_python' and type(value.get('code')) is str:
                    inner['python_code'] += len(value['code'])
            except (ValueError, AttributeError):
                pass
    return {'exposed_field_characters': dict(sizes), 'nested_field_characters': dict(inner),
            'total_exposed_field_characters': sum(sizes.values())}


def summarize_calls(calls, response_loader, request_loader):
    totals = Counter({k: 0 for k in (
        'calls', 'known_usage_calls', 'unknown_usage_calls', 'input_tokens',
        'output_tokens', 'cached_input_tokens', 'processed_input_tokens',
        'timed_calls', 'untimed_known_calls', 'prompt_seconds', 'decode_seconds',
        'call_wall_seconds', 'known_call_wall_seconds', 'unknown_call_wall_seconds')})
    characters, nested = Counter(), Counter()
    profiled = []
    for call in calls:
        response = response_loader(call['id'])
        request = request_loader(call['id'])
        if response.get('status') != call['status']:
            raise ValueError('response/usage status mismatch')
        totals['calls'] += 1
        totals['call_wall_seconds'] += call['wall_seconds']
        measured = visible_characters(request)
        characters.update(measured['exposed_field_characters'])
        nested.update(measured['nested_field_characters'])
        row = {'call_id': call['id'], 'status': call['status'],
               'input_tokens': None, 'output_tokens': None,
               'cached_input_tokens': None, 'processed_input_tokens': None,
               'wall_seconds': call['wall_seconds'], **measured}
        if call['status'] == 'ok':
            for key in ('input_tokens', 'output_tokens'):
                if (type(call[key]) is not int or call[key] < 0
                        or response.get(key) != call[key]):
                    raise ValueError('response/usage token mismatch')
                totals[key] += call[key]
                row[key] = call[key]
            totals['known_usage_calls'] += 1
            totals['known_call_wall_seconds'] += call['wall_seconds']
            timing = response.get('timings')
            if timing is None:
                totals['untimed_known_calls'] += 1
            else:
                if (timing['cache_n'] + timing['prompt_n'] != call['input_tokens']
                        or timing['cache_n'] != call['cached_input_tokens']
                        or timing['predicted_n'] != call['output_tokens']):
                    raise ValueError('cache/processed/decode totals mismatch')
                if any(timing[k] < 0 for k in ('cache_n', 'prompt_n', 'prompt_ms', 'predicted_ms')):
                    raise ValueError('negative timing or token count')
                totals['timed_calls'] += 1
                totals['cached_input_tokens'] += timing['cache_n']
                totals['processed_input_tokens'] += timing['prompt_n']
                totals['prompt_seconds'] += timing['prompt_ms'] / 1000
                totals['decode_seconds'] += timing['predicted_ms'] / 1000
                row.update(cached_input_tokens=timing['cache_n'], processed_input_tokens=timing['prompt_n'])
        else:
            totals['unknown_usage_calls'] += 1
            totals['unknown_call_wall_seconds'] += call['wall_seconds']
        profiled.append(row)
    totals['known_total_tokens'] = totals['input_tokens'] + totals['output_tokens']
    return {'totals': dict(totals), 'exposed_field_characters': dict(characters),
            'nested_field_characters': dict(nested), 'calls': profiled}


def profile(storage, root, phase):
    comparison_path = root / f'reports/{phase}_comparison.json'
    comparison = read(comparison_path)
    suffix='output_views' if phase=='P33' else 'handoff_factors'
    plan = read(root / f'configs/{phase}_{suffix}_v01.json')
    base = storage / 'records/context_pilot'
    require_complete(comparison, read(base / plan['batch_id'] / 'status.json'), phase)
    rows = []
    for cell in comparison['rows']:
        trial = base / cell['run_id']
        for name in ('usage.json', 'summary.json'):
            if sha(trial / name) != cell['source_hashes'][name]:
                raise ValueError('audited input changed: ' + name)
        usage = read(trial / 'usage.json')
        row = summarize_calls(usage,
            lambda cid: read(trial / cid / 'response.json'),
            lambda cid: read(trial / cid / 'request.json'))
        for key in ('known_total_tokens', 'unknown_usage_calls'):
            if row['totals'][key] != cell[key]:
                raise ValueError('profile/comparison totals disagree')
        if row['totals']['calls'] != cell['model_calls']:
            raise ValueError('profile/comparison call count disagrees')
        row.update(run_id=cell['run_id'], task_id=cell['task_id'], arm=cell['arm'],
                   success=cell['success'], stop_reason=cell['stop_reason'],
                   source_sha256={name: sha(trial / name) for name in ('usage.json', 'summary.json')})
        for call in row['calls']:
            call['source_sha256'] = {name: sha(trial / call['call_id'] / name)
                                     for name in ('request.json', 'response.json')}
        rows.append(row)
    totals = {}
    arms=ARMS
    if phase=='P33':
        from handoff_output_views import ARMS as arms
    for arm in arms:
        cells = [r for r in rows if r['arm'] == arm]
        totals[arm] = {}
        for group in ('totals', 'exposed_field_characters', 'nested_field_characters'):
            combined = Counter()
            for row in cells:
                combined.update(row[group])
            totals[arm][group] = dict(combined)
        totals[arm]['successes'] = sum(r['success'] for r in cells)
        totals[arm]['trials'] = len(cells)
    flag='all_twelve_profiled' if phase=='P33' else 'all_sixteen_profiled'
    return {'phase': phase, flag: True, 'rows': rows, 'by_arm': totals,
            'model_inference_calls_added': 0, 'api_requests_added': 0,
            'tokenizer_requests_added': 0, 'evaluator_contents_read': False,
            'unnecessary_information_identified': False,
            'scope': 'Passive, closed-cohort profile. Raw exposed characters are NOT tokens and nested fields must NOT be added to their containing fields. Repeated exposures are counted separately. Cache timings describe the recorded run, not a future policy. Unknown usage is excluded from known totals and separately counted. No savings or quality-preservation claim.',
            'comparison_sha256': sha(comparison_path), 'script_sha256': sha(Path(__file__))}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT)
    p.add_argument('--phase', choices=('P31', 'P32', 'P33'), required=True)
    a = p.parse_args()
    target = a.repo_root / f'reports/{a.phase}_cost_profile.json'
    if target.exists():
        raise FileExistsError('preserve completed profile')
    result = profile(a.storage_root, a.repo_root, a.phase)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result['by_arm'], ensure_ascii=False))
