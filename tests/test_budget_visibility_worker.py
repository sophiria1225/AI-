# Synthetic I/O fixture derived from the closed budget-observation worker tests.
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
from run_budget_visibility_cell import run_cell
from test_public_api_result_transport import FixtureTransport, catalog

ROOT = Path(__file__).resolve().parents[1]


def configuration():
    original = json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
    original.update(api_budget_by_task={'fixture':8}, max_output_tokens=40)
    plan = {'phase':PHASE, 'max_calls':4, 'max_total_tokens':200, 'max_wall_seconds':60,
        'max_setup_seconds':120, 'max_cleanup_seconds':180, 'model_seed':42, 'world_seed':42,
        'history_policy':'all_returned_reasoning_from_start', 'automatic_retries':0,
        'reserved_scenarios_read':0}
    public = {'instruction':'Complete the synthetic fixture', 'ground_truth_loaded':False}
    item = {'task_id':'fixture', 'source_run':'synthetic',
            'known_public_task_sha256':'synthetic-only', 'public_task':public}
    return original, plan, item


def fixture(*, policy='not_exposed', arm='error_exception', actions=('echo','finish'),
            count_delay=0, unknown_api=False, cleanup_ok=True, first_cached=0,
            initial_mismatch=False, token_limit=200, api_limit=8, stop_after_api=False,
            response_delay=0, folder=None):
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
                stop = kwargs['storage_root']/'.runtime/P80.stop'
                stop.parent.mkdir(exist_ok=True); stop.touch()
            return {'status':'ok' if reply['ok'] else 'execution_error', 'stdout':'fixture output',
                'stdout_truncated':False, 'api_requests':sum(r['api_request_sent'] for r in channel.rows),
                'declared_complete':channel.complete, 'unknown_effects':channel.fatal,
                'error':None if reply['ok'] else reply['error']}
        def close(self): self.state['container_removed'] = cleanup_ok

    def count(cfg, messages, tools, timeout):
        counted.append(copy.deepcopy(messages))
        if len(counted) == 1: clock[0] += count_delay
        return {'input_tokens':30, 'wall_seconds':count_delay if len(counted)==1 else 0}

    def send(cfg, messages, output, timeout, tools):
        captured.append({'cfg':copy.deepcopy(cfg), 'messages':copy.deepcopy(messages), 'timeout':timeout})
        action = actions[len(captured)-1]
        if action == 'transport_error': raise OSError('synthetic model transport loss')
        if action == 'unknown':
            response = {'status':'error', 'input_tokens':None, 'output_tokens':None,
                'wall_seconds':1, 'error_kind':'timeout', 'timeout_scope':'run_wall'}
        else:
            cached = first_cached if len(captured)==1 else 20
            response = {'status':'ok', 'input_tokens':30, 'output_tokens':20,
                'wall_seconds':1, 'done_reason':'tool_calls', 'cached_input_tokens':cached,
                'message':{'role':'assistant','content':None,'reasoning_content':'synthetic test text',
                    'tool_calls':[{'id':f'fixture-{len(captured)}','type':'function','function':{
                        'name':'run_python','arguments':json.dumps({'code':action,'span_ids':[]})}}]},
                'timings':{'cache_n':cached,'prompt_n':30-cached,'predicted_n':20,
                           'prompt_ms':100,'predicted_ms':100}}
        (output/'response.json').write_text(json.dumps(response))
        clock[0] += response_delay
        return response

    def execute(storage):
        with patch('run_budget_visibility_cell.time.monotonic', side_effect=lambda:clock[0]), \
             patch('run_budget_visibility_cell.RecordedBridge', side_effect=lambda raw, target, deadline, **kw:
                   RecordedBridge(raw, target, deadline, clock=lambda:clock[0], **kw)), \
             patch('run_budget_visibility_cell.TypedBridgeProcess', Raw), \
             patch('run_budget_visibility_cell.PersistentApiPython', Session), \
             patch('residual_output_budget.count_input', side_effect=count), \
             patch('residual_output_budget.model_call', side_effect=send):
            result = run_cell(storage, ROOT, plan, original, list(catalog().catalog.values()),
                item, arm, 'BOC_P80_fixture', time_visibility=policy)
        trial = storage/'records/context_pilot/BOC_P80_fixture'
        saved = {p.stem:json.loads(p.read_text()) for p in trial.glob('*.json')}
        return {'result':result,'saved':saved,'captured':captured,'counted':counted,'programs':programs,
                'raw':raw_instances,'storage':storage}

    if folder is not None: return execute(Path(folder))
    with tempfile.TemporaryDirectory() as temporary: return execute(Path(temporary))


class VisibilityWorkerTests(unittest.TestCase):
    def test_both_policies_execute_and_account_for_complete_fixture(self):
        for policy in ('measured','not_exposed'):
            with self.subTest(policy=policy):
                result=fixture(policy=policy)
                self.assertEqual(result['result']['phase'],'P80')
                self.assertEqual(result['result']['stop_reason'],'agent_declared_complete')
                self.assertTrue(result['result']['cleanup_confirmed'])
                self.assertEqual(result['result']['known_total_tokens'],100)
                self.assertEqual(result['result']['api_requests'],2)
                second=result['captured'][1]['messages']
                prior=[m for m in second if m.get('tool_calls')][0]
                self.assertEqual(prior['tool_calls'][0]['id'],'transport_reference_1')
                self.assertEqual(len(result['saved']['protocol_reference_views']),2)
                self.assertEqual(result['saved']['budget_observations'][1]['time_visibility'],policy)

    def test_dispatched_unknown_after_known_cost_stops_without_retry(self):
        result=fixture(actions=('echo','transport_error'))
        self.assertEqual(result['result']['model_calls'],2)
        self.assertEqual(result['result']['known_total_tokens'],50)
        self.assertEqual(result['result']['unknown_usage_calls'],1)
        self.assertEqual(result['result']['terminal_model_responses'],1)
        self.assertEqual(result['programs'],['echo'])
        self.assertEqual(len(result['captured']),2)

    def test_stop_and_unknown_api_are_preserved_with_cleanup(self):
        stopped=fixture(stop_after_api=True)
        self.assertEqual(stopped['result']['stop_reason'],'user_stop')
        self.assertEqual(stopped['result']['model_calls'],1)
        unknown=fixture(unknown_api=True)
        self.assertEqual(unknown['result']['unknown_effect_requests'],1)
        self.assertEqual(unknown['result']['model_calls'],1)
        self.assertEqual(unknown['result']['known_total_tokens'],50)
        self.assertTrue(unknown['result']['cleanup_confirmed'])

if __name__=='__main__': unittest.main()
