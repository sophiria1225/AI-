"""Independently recount the complete P41 component diagnostic, not task success."""
import argparse
from pathlib import Path

from budget_signal import digest
from inference_cache_control import cache_measurement
from local_llama import parse_response, payload_for
from code_agent_interface import CODE_TOOLS
from probe_residual_output import SOURCES, sources, syntax_only
from residual_output_budget import admission
from run_context_comparison import write_json
from run_handoff_factors import ROOT, read, sha


def run(storage, root):
    plan, prepared = sources(storage, root)
    folder = storage / 'records/context_pilot' / plan['batch_id']
    state = read(folder / 'status.json')
    activation = read(folder / 'activation.json')
    target = root / 'reports/P41_residual_output_audit.json'
    if target.exists(): raise FileExistsError('preserve audit')
    if (state['status'] != 'complete' or not state['all_three_states_accounted']
            or state['active'] or state['unknown_usage_calls'] or state['not_attempted_sources']
            or len(state['rows']) != 3 or state['environment_api_requests'] or state['evaluator_calls']):
        raise ValueError('full P41 audit requires all three states with known usage')
    if activation['source_sha256'] != {p: sha(root / p) for p in SOURCES}:
        raise ValueError('source implementation changed since activation')
    rows = []
    for item, saved in zip(prepared, state['rows'], strict=True):
        if item['run_id'] != saved['run_id']: raise ValueError('fixed source order differs')
        trial = folder / item['run_id']
        entries = read(trial / 'admissions.json')
        if len(entries) != 1: raise ValueError('not exactly one admission decision per state')
        entry = entries[0]
        choice = admission(item['residual']['remaining_tokens'], entry['input_tokens'],
                           item['residual']['configured_output_limit'], item['residual']['context_limit'], 'residual')
        if choice != item['residual'] or any(entry[k] != v for k, v in choice.items()):
            raise ValueError('measured admission differs from the frozen input')
        row = {'source_run': item['run_id'], 'admission': choice, 'status': saved['status'],
               'model_calls': 0, 'input_tokens': 0, 'output_tokens': 0,
               'source_sha256': {'admissions.json': sha(trial / 'admissions.json')}}
        if not choice['admitted']:
            if (saved['status'] != 'not_admitted' or saved['model_calls'] or entry['model_attempted']
                    or (trial / 'call_001').exists()):
                raise ValueError('rejected state made a model request')
        else:
            request = read(trial / 'call_001/request.json')
            raw = read(trial / 'call_001/raw_response.json')
            response = read(trial / 'call_001/response.json')
            usage = read(trial / 'usage.json')
            parsed = parse_response(raw)
            if (saved['status'] != 'generated' or saved['model_calls'] != 1
                    or not entry['model_attempted'] or len(usage) != 1):
                raise ValueError('admitted state lacks exactly one recorded response')
            if (request['max_tokens'] != choice['selected_output_cap']
                    or request['seed'] != item['config']['seed'] or request['cache_prompt'] is not False
                    or request['temperature'] != item['config']['agent_temperature']
                    or digest(request['messages']) != item['model_messages_sha256']):
                raise ValueError('actual request differs from fixed diagnostic')
            cfg = {**item['config']['model'], 'seed': item['config']['seed'],
                   'temperature': item['config']['agent_temperature'], 'num_predict': choice['selected_output_cap']}
            if request != payload_for(cfg, item['messages'], CODE_TOOLS):
                raise ValueError('complete request or tool schema differs from activation')
            for key in ('input_tokens', 'output_tokens', 'message', 'done_reason', 'usage_details'):
                if response[key] != parsed[key]: raise ValueError('raw response differs: ' + key)
            if (parsed['input_tokens'] != choice['input_tokens']
                    or parsed['output_tokens'] > choice['selected_output_cap']
                    or parsed['input_tokens'] + parsed['output_tokens'] > choice['remaining_tokens']):
                raise ValueError('measured token cost exceeds the input/output reservation')
            if any(usage[0][k] != parsed[k] for k in ('input_tokens', 'output_tokens', 'status')):
                raise ValueError('usage differs from raw server terminal counters')
            measured = cache_measurement('cold_1', response, choice['input_tokens'])
            syntax = syntax_only(parsed['message'], item['known_spans'])
            if not measured['state_confirmed'] or syntax != saved['syntax']:
                raise ValueError('cache or syntax audit disagrees')
            row.update(model_calls=1, input_tokens=parsed['input_tokens'], output_tokens=parsed['output_tokens'],
                       finish_reason=parsed['done_reason'], syntax=syntax,
                       output_limit_reached=parsed['output_tokens'] == choice['selected_output_cap'],
                       generation_wall_seconds=response['wall_seconds'], cache_measurement=measured)
            row['source_sha256'].update({p: sha(trial / p) for p in
                ('call_001/request.json', 'call_001/raw_response.json', 'call_001/response.json', 'usage.json')})
        rows.append(row)
    calls = sum(r['model_calls'] for r in rows)
    tokens = sum(r['input_tokens'] + r['output_tokens'] for r in rows)
    if calls != state['model_calls'] or tokens != state['known_total_tokens'] or calls > plan['max_calls'] or tokens > plan['max_total_tokens']:
        raise ValueError('aggregate diagnostic accounting disagrees')
    result = {'phase': 'P41_audit', 'all_three_states_audited': True, 'audit_errors': [],
              'rows': rows, 'model_calls': calls, 'known_total_tokens': tokens, 'unknown_usage_calls': 0,
              'valid_syntax_responses': sum(r.get('syntax', {}).get('all_tools_valid_envelope_and_syntax', False) for r in rows),
              'environment_api_requests': 0, 'task_evaluations': 0, 'task_success_claim': False,
              'original_remaining_wall_feasibility_claim': False, 'novel_method_claim': False,
              'source_sha256': {'batch_status': sha(folder / 'status.json'),
                                'activation': sha(folder / 'activation.json'),
                                'auditor': sha(root / 'scripts/audit_residual_output.py')},
              'limits': ['Known stopped inputs; posthoc generation-only diagnostic.',
                         'Fresh cache and separate diagnostic time budget; not original task-time feasibility.',
                         'Syntax is not execution, semantic correctness, or task success.',
                         'Original P40 incomplete comparison and results remain unchanged.']}
    write_json(target, result)
    print({k: result[k] for k in ('all_three_states_audited', 'model_calls', 'known_total_tokens', 'valid_syntax_responses')})


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--storage-root', type=Path, required=True)
    p.add_argument('--repo-root', type=Path, default=ROOT); a = p.parse_args()
    run(a.storage_root, a.repo_root)
