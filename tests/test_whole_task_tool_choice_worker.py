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
from run_whole_task_tool_choice_cell import run_cell
from test_public_api_result_transport import FixtureTransport, catalog

ROOT = Path(__file__).resolve().parents[1]


def configuration():
    original = json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
    original.update(api_budget_by_task={'fixture':8}, max_output_tokens=4096)
    plan = {'phase':PHASE, 'max_calls':4, 'max_total_tokens':200, 'max_wall_seconds':60,
        'max_setup_seconds':120, 'max_cleanup_seconds':180, 'model_seed':42, 'world_seed':42,
        'history_policy':'all_returned_reasoning_from_start', 'automatic_retries':0,
        'reserved_scenarios_read':0}
    public = {'instruction':'Complete the synthetic fixture', 'ground_truth_loaded':False}
    item = {'task_id':'fixture', 'source_run':'synthetic',
            'known_public_task_sha256':'synthetic-only', 'public_task':public}
    return original, plan, item


def fixture(*, policy='required', arm='error_exception', actions=('echo','finish'),
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
                stop = kwargs['storage_root']/'.runtime/P99.stop'
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
        with patch('run_whole_task_tool_choice_cell.time.monotonic', side_effect=lambda:clock[0]), \
             patch('run_whole_task_tool_choice_cell.RecordedBridge', side_effect=lambda raw, target, deadline, **kw:
                   RecordedBridge(raw, target, deadline, clock=lambda:clock[0], **kw)), \
             patch('run_whole_task_tool_choice_cell.TypedBridgeProcess', Raw), \
             patch('run_whole_task_tool_choice_cell.PersistentApiPython', Session), \
             patch('tool_choice_residual.count_input', side_effect=count), \
             patch('tool_choice_residual.model_call', side_effect=send):
            result = run_cell(storage, ROOT, plan, original, list(catalog().catalog.values()),
                item, arm, 'BOC_P99_fixture', tool_choice_policy=policy)
        trial = storage/'records/context_pilot/BOC_P99_fixture'
        saved = {p.stem:json.loads(p.read_text()) for p in trial.glob('*.json')}
        return {'result':result,'saved':saved,'captured':captured,'counted':counted,'programs':programs,
                'raw':raw_instances,'storage':storage}

    if folder is not None: return execute(Path(folder))
    with tempfile.TemporaryDirectory() as temporary: return execute(Path(temporary))


from tool_choice_local_llama import payload_for
from public_display import CODE_TOOLS
from whole_task_tool_choice import initial_conversation
from budget_signal import digest
import audit_whole_task_tool_choice as auditor


def audit_fixture(folder, result, policy):
    trial = Path(folder) / 'records/context_pilot/BOC_P99_fixture'
    read = lambda name: json.loads((trial / (name + '.json')).read_text())
    config, comparison, public = read('plan'), read('comparison_plan'), read('public_task')
    original = json.loads((ROOT / 'configs/P29_stateful_code_v01.json').read_text())
    base, _ = initial_conversation(original, public).for_model(config['observation_page_characters'])
    for i, capture in enumerate(result['captured'], 1):
        call = trial / f'call_{i:03d}'
        (call / 'request.json').write_text(json.dumps(payload_for(capture['cfg'], capture['messages'], CODE_TOOLS)))
        response = call / 'response.json'
        if response.exists():
            (call / 'raw_response.json').write_text(response.read_text())
    with patch.object(auditor, 'config_for', return_value=config), \
         patch.object(auditor, 'parse_response', side_effect=lambda x: x):
        return auditor.audit_cell(trial, ROOT, comparison, original,
            {'task_id': 'fixture', 'public_task': public}, policy,
            {'base_messages_sha256': digest(base)}, False)


class WholeTaskToolChoiceWorkerTests(unittest.TestCase):
    def test_both_choices_use_the_real_worker_and_same_hidden_notifications(self):
        starts = []
        for policy, budget in [('auto', -1), ('required', -1)]:
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as folder:
                result = fixture(policy=policy, folder=folder)
                self.assertEqual(result['result']['phase'], 'P99')
                self.assertEqual(result['result']['tool_choice_policy'], policy)
                self.assertEqual(result['result']['reasoning_budget_tokens'], budget)
                self.assertEqual(result['result']['stop_reason'], 'agent_declared_complete')
                self.assertEqual(result['result']['known_total_tokens'], 100)
                self.assertEqual(result['result']['api_requests'], 2)
                self.assertTrue(result['result']['cleanup_confirmed'])
                self.assertEqual([c['cfg']['reasoning_budget_tokens'] for c in result['captured']], [budget] * 2)
                self.assertEqual([c['cfg']['tool_choice'] for c in result['captured']], [policy] * 2)
                self.assertEqual([c['cfg']['cache_prompt'] for c in result['captured']], [False, True])
                for signal in result['saved']['budget_observations']:
                    self.assertEqual(signal['effective_time_visibility'], 'not_exposed')
                    self.assertNotIn('wall_seconds_at_snapshot', signal['visible_state']['remaining'])
                starts.append(result['captured'][0]['messages'])
                checked = audit_fixture(folder, result, policy)
                self.assertEqual(checked['known_total_tokens'], 100)
                self.assertEqual(checked['tool_choice_policy'], policy)
                self.assertEqual([r['structured_tool_calls'] for r in checked['request_checks']], [1, 1])
                self.assertEqual([r['API_requests'] for r in checked['request_checks']], [1, 1])
                self.assertEqual(sum(r['format_rejections'] for r in checked['request_checks']), 0)
        self.assertEqual(starts[0], starts[1])

    def test_dispatched_unknown_is_counted_and_never_executed_or_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            result = fixture(actions=('echo', 'transport_error'), folder=folder)
            checked = audit_fixture(folder, result, 'required')
        self.assertEqual(checked['known_total_tokens'], 50)
        self.assertEqual(checked['unknown_usage_calls'], 1)
        self.assertEqual(checked['model_calls'], 2)
        self.assertEqual(result['programs'], ['echo'])
        self.assertEqual(result['result']['terminal_model_responses'], 1)
        self.assertIsNone(checked['request_checks'][-1]['structured_tool_calls'])
        self.assertEqual(checked['request_checks'][-1]['API_requests'], 0)

    def test_terminal_unknown_and_expired_output_do_not_execute(self):
        for actions, delay in [(('unknown',), 0), (('finish',), 61)]:
            with self.subTest(actions=actions), tempfile.TemporaryDirectory() as folder:
                result = fixture(actions=actions, response_delay=delay, folder=folder)
                checked = audit_fixture(folder, result, 'required')
                self.assertEqual(result['programs'], [])
                self.assertEqual(checked['api_requests'], 0)
                self.assertEqual(checked['unknown_usage_calls'], int(actions[0] == 'unknown'))

    def test_changed_actual_request_choice_is_rejected_by_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            result = fixture(folder=folder)
            # Materialize the same request archive the real transport writes.
            audit_fixture(folder, result, 'required')
            trial = Path(folder) / 'records/context_pilot/BOC_P99_fixture'
            path = trial / 'call_001/request.json'
            request = json.loads(path.read_text())
            request['tool_choice'] = 'auto'
            path.write_text(json.dumps(request))
            config = json.loads((trial / 'plan.json').read_text())
            comparison = json.loads((trial / 'comparison_plan.json').read_text())
            public = json.loads((trial / 'public_task.json').read_text())
            original = json.loads((ROOT / 'configs/P29_stateful_code_v01.json').read_text())
            base, _ = initial_conversation(original, public).for_model(config['observation_page_characters'])
            with patch.object(auditor, 'config_for', return_value=config), \
                 patch.object(auditor, 'parse_response', side_effect=lambda x: x), \
                 self.assertRaisesRegex(ValueError, 'actual_request_differs'):
                auditor.audit_cell(trial, ROOT, comparison, original,
                    {'task_id': 'fixture', 'public_task': public}, 'required',
                    {'base_messages_sha256': digest(base)}, False)

    def test_unknown_api_effect_or_user_stop_ends_worker(self):
        stopped = fixture(stop_after_api=True)
        self.assertEqual(stopped['result']['stop_reason'], 'user_stop')
        self.assertEqual(stopped['result']['model_calls'], 1)
        unknown = fixture(unknown_api=True)
        self.assertEqual(unknown['result']['unknown_effect_requests'], 1)
        self.assertEqual(unknown['result']['model_calls'], 1)


if __name__ == '__main__':
    unittest.main()

