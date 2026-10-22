"""P61 fixed known prefix and ordinary interfaces; no task-specific solution."""
import copy
import json
import time

from handoff_factors import boundary_object, split_turns
from inference_cache_control import cache_measurement
from local_llama import count_input
from local_llama_stream import model_call_stream
from native_boundary_record import verify_boundary
from native_conversation import NativeConversation, recover_turn
from residual_output_budget import admission
from run_context_comparison import BudgetStop, write_json
from run_handoff_factors import ROOT, read, sha
from stateful_code_prompts import stateful_system_prompt

PLAN = 'configs/P61_ordinary_continuation_v01.json'
ARMS = ('native', 'python')
COMMON = '''
Continue the original task from this saved public interaction boundary. The
simulated environment and all prior public API receipts are preserved. No task
solution, evaluator result or future observation has been added. Continuation
limits are 8 model calls, 197398 full input plus output tokens, 900 seconds and
60 further environment API calls, including completion. Maximum output per
call is 4096 tokens. All original task requirements still apply. Do not declare
success while required work is unfinished. No extra budget will be granted.
'''
PYTHON = '''
The interface now uses the ordinary task-local Python runtime described above.
There were no prior Python programs, so no user-defined variables exist yet.
Prior public API calls in the history remain valid receipts; select their span
IDs when using observations. Previously discovered API schemas remain available
in api_schemas. Subsequent Python programs share the same task-local namespace.
'''


def sources(storage):
    plan = read(ROOT / PLAN)
    required = {'phase': 'P61', 'source_run': 'P24_02_GUIDED', 'task_id': '6ea6792_1',
        'boundary_after_model_calls': 12, 'arms': list(ARMS),
        'run_ids': ['P61_01_NATIVE', 'P61_02_PYTHON'], 'max_calls': 8,
        'max_total_tokens': 197398, 'max_wall_seconds': 900, 'max_setup_seconds': 120,
        'max_api_requests_including_prefix': 80, 'max_output_tokens': 4096,
        'prefix_model_calls': 12, 'prefix_logical_tokens': 252602, 'prefix_api_requests': 20,
        'continuation_seed': 54, 'reserved_scenarios_read': 0, 'output_reservation': 'fixed'}
    if any(plan.get(k) != v for k, v in required.items()):
        raise ValueError('fixed P61 selection or budgets changed')
    trial = storage / 'records/context_pilot' / plan['source_run']
    for name, key in [('boundaries/manifests/call_012.json', 'boundary_sha256'),
                      ('plan.json', 'source_trial_plan_sha256'), ('provenance.json', 'source_provenance_sha256')]:
        if sha(trial / name) != plan[key]: raise ValueError('frozen source changed')
    verify_boundary(trial / 'boundaries', 'call_012')
    manifest = read(trial / 'boundaries/manifests/call_012.json')
    prefix = {'manifest': manifest}
    for name in ('spans', 'events', 'usage', 'conversation_private', 'public_task'):
        prefix[name] = boundary_object(trial, manifest, 'harness/' + name + '.json')
    state = manifest['state']
    if (state['task_id'] != plan['task_id'] or state['declared_complete']
            or state['model_calls'] != 12 or state['api_requests'] != 20
            or state['known_total_tokens'] != 252602 or len(prefix['usage']) != 12
            or any(c['status'] != 'ok' for c in prefix['usage'])
            or sum(c['input_tokens'] + c['output_tokens'] for c in prefix['usage']) != 252602
            or len(split_turns(prefix['conversation_private'])) != 12
            or any(e.get('effects_unknown') for e in prefix['events'])
            or sum(e['api_request_sent'] for e in prefix['events']) != 20
            or set(prefix['spans']) != {e['span_id'] for e in prefix['events']}):
        raise ValueError('fixed public prefix is incomplete or inconsistent')
    original = read(trial / 'plan.json')
    provenance = read(trial / 'provenance.json')
    data = storage / '.runtime/appworld/r18_probe_01/data'
    if sha(data / 'tasks' / plan['task_id'] / 'specs.json') != provenance['spec_sha256']:
        raise ValueError('known task specification changed')
    from inspect_appworld_api_schemas import load_public_tools
    tools, schema_hashes, _ = load_public_tools(data)
    if schema_hashes != provenance['public_schema_hashes']:
        raise ValueError('original public API schemas changed')
    return plan, original, prefix, tools


def conversation(prefix, arm):
    if arm not in ARMS: raise ValueError('unknown ordinary interface')
    messages = prefix['conversation_private']
    system = messages[0]['content'] if arm == 'native' else stateful_system_prompt(
        read(ROOT / 'configs/P29_stateful_code_v01.json'))
    view = NativeConversation(system + COMMON + (PYTHON if arm == 'python' else ''), prefix['public_task'])
    if view.messages()[1] != messages[1]: raise ValueError('original task changed')
    for turn in split_turns(messages): view.append(turn[0], recover_turn(turn))
    if view.messages()[1:] != messages[1:]: raise ValueError('public history changed')
    return view


class OrdinaryInference:
    """Fixed reservation, cold first request, exact terminal stream accounting."""
    def __init__(self, config, output):
        self.config = copy.deepcopy(config); self.output = output
        self.started = time.monotonic(); self.calls = []; self.admissions = []

    @property
    def tokens(self):
        return sum(c['input_tokens'] + c['output_tokens'] for c in self.calls if c['usage_known'])

    def call(self, messages, tools):
        if any(not c['usage_known'] or c['status'] != 'ok' for c in self.calls):
            raise RuntimeError('failed or unknown prior generation; no further request')
        elapsed = time.monotonic() - self.started
        if len(self.calls) >= self.config['max_calls']: raise BudgetStop('call_limit')
        if elapsed >= self.config['max_wall_seconds']: raise BudgetStop('wall_limit')
        cfg = {**self.config['model'], 'temperature': self.config['agent_temperature'],
            'seed': self.config['seed'] + len(self.calls), 'num_predict': self.config['max_output_tokens'],
            'cache_prompt': bool(self.calls), 'expected_system_fingerprint': 'b11669-620d2225c'}
        cid = f'call_{len(self.calls)+1:03d}'
        entry = {'call_id': cid, 'model_request_started': False, 'count_started': True}
        self.admissions.append(entry)
        write_json(self.output / 'admissions.json', self.admissions)
        counted = count_input(cfg, messages, tools, timeout=min(60, self.config['max_wall_seconds']-elapsed))
        entry.update(input_tokens=counted['input_tokens'], count_wall_seconds=counted.get('wall_seconds'))
        choice = admission(self.config['max_total_tokens']-self.tokens, counted['input_tokens'],
                           cfg['num_predict'], cfg['num_ctx'], 'fixed')
        entry.update(choice)
        write_json(self.output / 'admissions.json', self.admissions)
        if not choice['admitted']: raise BudgetStop(choice['stop_reason'])
        remaining = self.config['max_wall_seconds']-(time.monotonic()-self.started)
        if remaining <= 0: raise BudgetStop('wall_limit')
        out = self.output / cid
        entry['model_request_started'] = True
        write_json(self.output / 'admissions.json', self.admissions)
        response = None
        try:
            response = model_call_stream(cfg, messages, out, remaining, tools)
        finally:
            # The stream adapter saves its receipt even on explicit interruption.
            if response is None and (out / 'response.json').exists(): response = read(out / 'response.json')
            response = response or {'status': 'error', 'input_tokens': None, 'output_tokens': None}
            known = all(type(response.get(k)) is int and response[k] >= 0 for k in ('input_tokens', 'output_tokens'))
            row = {k: response.get(k) for k in ('status', 'input_tokens', 'output_tokens',
                'cached_input_tokens', 'wall_seconds', 'error_kind', 'timeout_scope', 'done_reason')}
            row.update(id=cid, role='agent', usage_known=known, predicted_input_tokens=counted['input_tokens'],
                       cache_prompt=cfg['cache_prompt'], seed=cfg['seed'], output_cap=cfg['num_predict'])
            self.calls.append(row); write_json(self.output / 'usage.json', self.calls)
        if response['status'] != 'ok': raise BudgetStop('model_usage_unknown' if not known else 'model_response_unusable')
        if (not known or response['input_tokens'] != counted['input_tokens']
                or response['output_tokens'] > cfg['num_predict'] or self.tokens > self.config['max_total_tokens']):
            raise RuntimeError('terminal usage differs from admission')
        if len(self.calls) == 1:
            check = cache_measurement('cold_1', response, response['input_tokens'])
            self.calls[0]['first_cache_measurement'] = check
            write_json(self.output / 'usage.json', self.calls)
            if not check['state_confirmed']: raise RuntimeError('first generation was not cold')
        return response['message']
