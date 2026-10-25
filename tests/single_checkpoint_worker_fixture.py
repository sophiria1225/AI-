# Synthetic P118 worker fixture; no model, generated Python, or AppWorld API runs.
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from budget_observation_worker import PHASE, attempt_usage, worker_config
from preflight_public_api_live import RecordedBridge
from public_api_envelope import PROTOCOL
from run_whole_task_single_checkpoint_cell import run_cell
from test_public_api_result_transport import FixtureTransport, catalog

ROOT = Path(__file__).resolve().parents[1]


def configuration():
    original = json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
    original.update(api_budget_by_task={'fixture':8}, max_output_tokens=4096)
    plan = {'phase':PHASE, 'max_calls':8, 'max_total_tokens':200, 'max_wall_seconds':60,
        'max_setup_seconds':120, 'max_cleanup_seconds':180, 'model_seed':42, 'world_seed':42,
        'history_policy':'all_returned_reasoning_from_start', 'automatic_retries':0,
        'reserved_scenarios_read':0}
    public = {'instruction':'Complete the synthetic fixture', 'ground_truth_loaded':False}
    item = {'task_id':'fixture', 'source_run':'synthetic',
            'known_public_task_sha256':'synthetic-only', 'public_task':public}
    return original, plan, item


def fixture(*, policy='full', arm='error_exception', actions=('echo','finish'),
            count_delay=0, unknown_api=False, cleanup_ok=True, first_cached=0,
            initial_mismatch=False, token_limit=450000, api_limit=8, stop_after_api=False,
            response_delay=0, folder=None, summary_mode='valid'):
    """Real worker, inference admission and API channel, with external I/O replaced.

    No generated Python executes. The session emits hand-written RPC packets;
    FixtureTransport executes only its existing trusted synthetic API wrapper.
    """
    original, plan, item = configuration()
    original['api_budget_by_task']['fixture'] = api_limit
    plan['max_total_tokens'] = token_limit
    clock = [0.0]; captured = []; counted = []; programs = []; raw_instances = []

    class Raw(FixtureTransport):
        timeout_seconds = 90
        def __init__(self, *args, **kwargs):
            super().__init__(); raw_instances.append(self)
        def request(self, command):
            if command['op'] == 'init':
                self.commands.append(command)
                public = {**item['public_task'], 'api_result_protocol':PROTOCOL}
                if initial_mismatch: public['instruction'] = 'different fixture'
                return {'ok':True, 'result':public}
            response = super().request(command)
            if unknown_api: response['result']['observation'] = 'broken synthetic envelope'
            return response
        def close(self):
            return {'graceful':cleanup_ok, 'process_stopped':True, 'transport_failed':not cleanup_ok}

    class Session:
        def __init__(self, *args):
            self.state = {'container_removed':False}; self.usable = True
        def run(self, source, observations, channel, **kwargs):
            programs.append(source)
            if source not in ('echo','finish','fail'):
                raise AssertionError('only handwritten fixture actions may run')
            packet = {'kind':'api', 'id':1, 'app':'fixture', 'api':source, 'arguments':{'value':7}}
            reply = channel.exchange(packet)
            kwargs['on_record'](channel.rows[-1])
            if stop_after_api:
                stop = kwargs['storage_root']/'.runtime/P118.stop'
                stop.parent.mkdir(exist_ok=True); stop.touch()
            return {'status':'ok' if reply['ok'] else 'execution_error', 'stdout':'fixture output',
                'stdout_truncated':False, 'api_requests':sum(r['api_request_sent'] for r in channel.rows),
                'declared_complete':channel.complete, 'unknown_effects':channel.fatal,
                'error':None if reply['ok'] else reply['error']}
        def close(self): self.state['container_removed'] = cleanup_ok

    def count(cfg, messages, tools, timeout):
        counted.append(copy.deepcopy(messages))
        if len(counted) == 1: clock[0] += count_delay
        return {'input_tokens':(10000 if not tools else 5000 + 4000 * sum(m['role'] == 'assistant' for m in messages)), 'wall_seconds':count_delay if len(counted)==1 else 0}

    def send(cfg, messages, output, timeout, tools):
        captured.append({'cfg':copy.deepcopy(cfg), 'messages':copy.deepcopy(messages), 'timeout':timeout, 'role': 'agent' if tools else 'focus'})
        if not tools:
            if summary_mode == 'transport_error':
                raise OSError('synthetic summary transport loss')
            if summary_mode == 'unknown':
                response = {'status':'error', 'input_tokens':None, 'output_tokens':None,
                            'wall_seconds':1, 'error_kind':'request_or_response', 'timeout_scope':None}
                (output/'response.json').write_text(json.dumps(response))
                return response
            response = {'status':'ok', 'input_tokens':10000, 'output_tokens':20, 'wall_seconds':1,
                'done_reason':'stop', 'cached_input_tokens':0,
                'message':{'role':'assistant','content':json.dumps({k:['fixture'] for k in ('completed','usable_state','remaining','uncertainties')})}}
            if summary_mode == 'invalid':
                response['message']['content'] = '{}'
            (output/'response.json').write_text(json.dumps(response))
            return response
        measured_input = 5000 + 4000 * sum(m['role'] == 'assistant' for m in messages)
        action = actions[sum(c['role'] == 'agent' for c in captured)-1]
        if action == 'transport_error': raise OSError('synthetic model transport loss')
        if action == 'unknown':
            response = {'status':'error', 'input_tokens':None, 'output_tokens':None,
                'wall_seconds':1, 'error_kind':'timeout', 'timeout_scope':'run_wall'}
        else:
            cached = first_cached if len(captured)==1 else 20
            response = {'status':'ok', 'input_tokens':measured_input, 'output_tokens':20,
                'wall_seconds':1, 'done_reason':'tool_calls', 'cached_input_tokens':cached,
                'message':{'role':'assistant','content':None,'reasoning_content':'synthetic test text',
                    'tool_calls':[{'id':f'fixture-{len(captured)}','type':'function','function':{
                        'name':'run_python','arguments':json.dumps({'code':action,'span_ids':[]})}}]},
                'timings':{'cache_n':cached,'prompt_n':measured_input-cached,'predicted_n':20,
                           'prompt_ms':100,'predicted_ms':100}}
        (output/'response.json').write_text(json.dumps(response))
        clock[0] += response_delay
        return response

    def execute(storage):
        with patch('run_whole_task_single_checkpoint_cell.time.monotonic', side_effect=lambda:clock[0]), \
             patch('run_whole_task_single_checkpoint_cell.RecordedBridge', side_effect=lambda raw, target, deadline, **kw:
                   RecordedBridge(raw, target, deadline, clock=lambda:clock[0], **kw)), \
             patch('run_whole_task_single_checkpoint_cell.TypedBridgeProcess', Raw), \
             patch('run_whole_task_single_checkpoint_cell.PersistentApiPython', Session), \
             patch('single_checkpoint_inference.count_agent_input', side_effect=count), \
             patch('single_checkpoint_inference.count_summary_input', side_effect=count), \
             patch('fixed_budget_residual.count_input', side_effect=count), \
             patch('fixed_budget_residual.model_call', side_effect=send), \
             patch('tool_choice_residual.count_input', side_effect=count), \
             patch('tool_choice_residual.model_call', side_effect=send):
            result = run_cell(storage, ROOT, plan, original, list(catalog().catalog.values()),
                item, arm, 'BOC_P118_fixture', checkpoint_policy=policy)
        trial = storage/'records/context_pilot/BOC_P118_fixture'
        saved = {p.stem:json.loads(p.read_text()) for p in trial.glob('*.json')}
        return {'result':result,'saved':saved,'captured':captured,'counted':counted,'programs':programs,
                'raw':raw_instances,'storage':storage}

    if folder is not None: return execute(Path(folder))
    with tempfile.TemporaryDirectory() as temporary: return execute(Path(temporary))


def audit_fixture(folder, result):
    from audit_single_checkpoint_trace import audit_trace
    from fixed_budget_local_llama import payload_for as summary_payload
    from tool_choice_local_llama import payload_for as agent_payload
    from public_display import CODE_TOOLS
    from whole_task_single_checkpoint import initial_conversation
    trial = Path(folder) / 'records/context_pilot/BOC_P118_fixture'
    config = json.loads((trial / 'plan.json').read_text())
    public = json.loads((trial / 'public_task.json').read_text())
    original = json.loads((ROOT / 'configs/P29_stateful_code_v01.json').read_text())
    for index, capture in enumerate(result['captured'], 1):
        call = trial / f'call_{index:03d}'
        actor = capture['role'] == 'agent'
        payload = agent_payload if actor else summary_payload
        (call / 'request.json').write_text(json.dumps(payload(
            capture['cfg'], capture['messages'], CODE_TOOLS if actor else [])))
        path = call / 'response.json'
        if path.exists():
            response = json.loads(path.read_text())
            if response['status'] == 'ok':
                usage = {'prompt_tokens': response['input_tokens'], 'completion_tokens': response['output_tokens'],
                         'total_tokens': response['input_tokens'] + response['output_tokens'],
                         'prompt_tokens_details': {'cached_tokens': response['cached_input_tokens']}}
                raw = {'usage': usage, 'timings': response.get('timings'), 'choices': [
                    {'message': response['message'], 'finish_reason': response['done_reason']}]}
                response.update(usage_details=usage, timings=response.get('timings'))
                path.write_text(json.dumps(response))
                (call / 'raw_response.json').write_text(json.dumps(raw))
    return audit_trace(trial, config, initial_conversation(original, public))
