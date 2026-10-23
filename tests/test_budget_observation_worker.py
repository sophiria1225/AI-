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
from run_budget_observation_cell import run_cell
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
                stop = kwargs['storage_root']/'.runtime/budget_observation.stop'
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
        with patch('run_budget_observation_cell.time.monotonic', side_effect=lambda:clock[0]), \
             patch('run_budget_observation_cell.RecordedBridge', side_effect=lambda raw, target, deadline, **kw:
                   RecordedBridge(raw, target, deadline, clock=lambda:clock[0], **kw)), \
             patch('run_budget_observation_cell.TypedBridgeProcess', Raw), \
             patch('run_budget_observation_cell.PersistentApiPython', Session), \
             patch('residual_output_budget.count_input', side_effect=count), \
             patch('residual_output_budget.model_call', side_effect=send):
            result = run_cell(storage, ROOT, plan, original, list(catalog().catalog.values()),
                item, arm, 'BOC_fixture', time_visibility=policy)
        trial = storage/'records/context_pilot/BOC_fixture'
        saved = {p.stem:json.loads(p.read_text()) for p in trial.glob('*.json')}
        return {'result':result,'saved':saved,'captured':captured,'counted':counted,'programs':programs,
                'raw':raw_instances,'storage':storage}

    if folder is not None: return execute(Path(folder))
    with tempfile.TemporaryDirectory() as temporary: return execute(Path(temporary))


class BudgetObservationWorkerTests(unittest.TestCase):
    def test_whole_loop_counts_cached_tokens_API_and_completion_for_both_policies(self):
        for policy in ('measured','not_exposed'):
            for arm in ('error_value','error_exception'):
                with self.subTest(policy=policy,arm=arm):
                    f = fixture(policy=policy,arm=arm); r=f['result']
                    self.assertEqual(r['stop_reason'],'agent_declared_complete')
                    self.assertEqual(r['model_calls'],2); self.assertEqual(r['terminal_model_responses'],2)
                    self.assertEqual(r['known_total_tokens'],100); self.assertEqual(r['api_requests'],2)
                    self.assertEqual(r['unknown_usage_calls'],0); self.assertTrue(r['cleanup_confirmed'])
                    self.assertEqual(r['time_visibility'],policy)
                    self.assertEqual(r['evaluation'],'not_run'); self.assertIsNone(r['final_success'])
                    self.assertEqual([c['cfg']['cache_prompt'] for c in f['captured']],[False,True])
                    self.assertEqual(f['saved']['usage'][1]['cached_input_tokens'],20)
                    self.assertEqual(f['counted'],[c['messages'] for c in f['captured']])
                    self.assertTrue(any(m.get('reasoning_content')=='synthetic test text'
                        for m in f['captured'][1]['messages']))
                    notice=f['saved']['budget_observations'][1]
                    self.assertEqual(notice['measured_state']['used']['api_calls'],1)
                    self.assertEqual(notice['measured_state']['used']['logical_input_plus_output_tokens'],50)

    def test_clock_perturbation_changes_timeout_but_only_measured_notice(self):
        for policy in ('measured','not_exposed'):
            a,b=[fixture(policy=policy,count_delay=d) for d in (10,11)]
            self.assertEqual(a['captured'][0]['messages'],b['captured'][0]['messages'])
            left,right=[f['captured'][1] for f in (a,b)]
            self.assertEqual([left['timeout'],right['timeout']],[50,49])
            self.assertEqual(left['messages'][:-1],right['messages'][:-1])
            self.assertEqual(left['messages']==right['messages'],policy=='not_exposed')
            self.assertEqual([f['saved']['budget_observations'][1]['measured_state']['remaining']
                ['wall_seconds_at_snapshot'] for f in (a,b)],[50,49])

    def test_dispatched_transport_loss_survives_summary_and_cleanup(self):
        for actions in (('transport_error',),('echo','transport_error')):
            f=fixture(actions=actions); r=f['result']; known=len(actions)-1
            self.assertEqual(r['stop_reason'],'runtime_error')
            self.assertEqual(r['model_calls'],len(actions)); self.assertEqual(r['unknown_usage_calls'],1)
            self.assertEqual(r['terminal_model_responses'],known)
            self.assertEqual(r['dispatched_without_terminal_usage'],1)
            self.assertEqual(r['known_total_tokens'],50*known); self.assertEqual(r['api_requests'],known)
            self.assertEqual(len(f['captured']),len(actions)); self.assertEqual(len(f['programs']),known)
            self.assertEqual(len(f['saved']['terminal_usage']),known)
            self.assertIsNone(f['saved']['usage'][-1]['input_tokens'])
            self.assertIsNone(f['saved']['usage'][-1]['output_tokens'])
            self.assertEqual(f['saved']['usage'][-1]['usage_record_source'],'budget_observation_dispatch_record')
            self.assertTrue(r['cleanup_confirmed'])

    def test_reported_unknown_usage_is_counted_once_and_never_executed(self):
        for actions in (('unknown',),('echo','unknown')):
            f=fixture(actions=actions); r=f['result']
            self.assertEqual(r['stop_reason'],'wall_limit_during_model_call')
            self.assertEqual(r['model_calls'],len(actions)); self.assertEqual(r['unknown_usage_calls'],1)
            self.assertEqual(r['terminal_model_responses'],len(actions))
            self.assertEqual(r['dispatched_without_terminal_usage'],0)
            self.assertEqual(r['known_total_tokens'],50*(len(actions)-1))
            self.assertEqual(len(f['programs']),len(actions)-1); self.assertTrue(r['cleanup_confirmed'])

    def test_no_output_reservation_has_no_dispatch_or_unknown_usage(self):
        f=fixture(token_limit=30); r=f['result']
        self.assertEqual(r['stop_reason'],'token_reservation_limit')
        self.assertEqual(r['model_calls'],0); self.assertEqual(r['unknown_usage_calls'],0)
        self.assertEqual(f['captured'],[]); self.assertEqual(f['programs'],[])
        self.assertTrue(r['cleanup_confirmed'])
        self.assertFalse(f['saved']['budget_observations'][0]['model_attempted'])

    def test_real_deadline_during_count_blocks_generation_and_tools(self):
        for policy in ('measured','not_exposed'):
            f=fixture(policy=policy,count_delay=61)
            self.assertEqual(f['result']['stop_reason'],'wall_limit')
            self.assertEqual(f['result']['model_calls'],0); self.assertEqual(f['programs'],[])
            self.assertTrue(f['result']['cleanup_confirmed'])

    def test_unknown_API_effect_stops_next_model_call(self):
        f=fixture(unknown_api=True); r=f['result']
        self.assertEqual(r['stop_reason'],'runtime_error'); self.assertEqual(r['api_requests'],1)
        self.assertEqual(r['model_calls'],1); self.assertEqual(r['unknown_usage_calls'],0)
        # The inner API and enclosing Python receipt both carry the uncertainty.
        # Only the actual API request belongs in the request count.
        self.assertEqual(r['unknown_effect_requests'],1)
        self.assertEqual(r['api_execution_receipts'][0]['status'],'unknown')
        self.assertEqual(len(f['captured']),1); self.assertTrue(r['cleanup_confirmed'])

    def test_late_known_response_is_charged_but_not_executed(self):
        for policy in ('measured','not_exposed'):
            f=fixture(policy=policy,response_delay=61); r=f['result']
            self.assertEqual(r['stop_reason'],'wall_limit')
            self.assertEqual(r['model_calls'],1); self.assertEqual(r['known_total_tokens'],50)
            self.assertEqual(r['api_requests'],0); self.assertEqual(f['programs'],[])
            self.assertTrue(r['cleanup_confirmed'])

    def test_error_presentation_remains_explicit_through_the_worker(self):
        for arm in ('error_value','error_exception'):
            f=fixture(arm=arm,actions=('fail','finish')); r=f['result']
            self.assertEqual(r['model_calls'],2); self.assertEqual(r['api_requests'],2)
            self.assertEqual(r['api_execution_receipts'][0]['status'],'raised')
            outer=[e for e in f['saved']['events'] if e['stage']=='model_tool'][0]
            observed=f['saved']['spans'][outer['span_id']]['observation']['status']
            self.assertEqual(observed,'ok' if arm=='error_value' else 'execution_error')
            self.assertEqual(r['stop_reason'],'agent_declared_complete')

    def test_cleanup_failure_does_not_erase_unknown_generation(self):
        f=fixture(actions=('transport_error',),cleanup_ok=False); r=f['result']
        self.assertEqual(r['stop_reason'],'cleanup_error'); self.assertFalse(r['cleanup_confirmed'])
        self.assertEqual(r['model_calls'],1); self.assertEqual(r['unknown_usage_calls'],1)
        self.assertIsNone(f['saved']['usage'][0]['input_tokens'])

    def test_initial_public_state_mismatch_never_starts_inference(self):
        f=fixture(initial_mismatch=True); r=f['result']
        self.assertEqual(r['stop_reason'],'setup_failure'); self.assertEqual(r['model_calls'],0)
        self.assertEqual(f['captured'],[]); self.assertEqual(f['programs'],[])
        self.assertEqual(r['bridge_cleanup']['process_stopped'],True)

    def test_first_cache_violation_preserves_cost_without_executing_output(self):
        f=fixture(first_cached=1); r=f['result']
        self.assertEqual(r['stop_reason'],'runtime_error'); self.assertEqual(r['known_total_tokens'],50)
        self.assertEqual(r['model_calls'],1); self.assertEqual(r['unknown_usage_calls'],0)
        self.assertEqual(f['programs'],[]); self.assertTrue(r['cleanup_confirmed'])

    def test_user_stop_after_API_preserves_work_and_blocks_next_generation(self):
        f=fixture(stop_after_api=True); r=f['result']
        self.assertEqual(r['stop_reason'],'user_stop'); self.assertEqual(r['model_calls'],1)
        self.assertEqual(r['api_requests'],1); self.assertEqual(r['known_total_tokens'],50)
        self.assertTrue(r['cleanup_confirmed'])

    def test_API_limit_prevents_next_generation(self):
        f=fixture(api_limit=1); r=f['result']
        self.assertEqual(r['stop_reason'],'api_request_limit'); self.assertEqual(r['model_calls'],1)
        self.assertEqual(r['api_requests'],1); self.assertFalse(r['declared_complete'])

    def test_closed_phase_unsafe_path_and_unbounded_limits_are_rejected_before_setup(self):
        original,plan,item=configuration()
        changes=[{'phase':'P78'},{'max_calls':0},{'max_total_tokens':450001},
            {'max_wall_seconds':float('inf')},{'max_cleanup_seconds':True},
            {'automatic_retries':1},{'reserved_scenarios_read':1}, {'history_policy':'drop'}]
        with tempfile.TemporaryDirectory() as folder:
            for change in changes:
                with self.subTest(change=change), self.assertRaises(ValueError):
                    run_cell(Path(folder),ROOT,{**plan,**change},original,[],item,
                        'error_exception','BOC_fixture',time_visibility='not_exposed')
            self.assertEqual(list(Path(folder).iterdir()),[])
        for rid in ('P78_01_ERROR_EXCEPTION','BOC_../escape','BOC_'):
            with self.subTest(rid=rid), self.assertRaises(ValueError):
                worker_config(original,plan,'fixture','error_exception',rid,'measured')

    def test_existing_attempt_cannot_be_overwritten_or_rerun(self):
        with tempfile.TemporaryDirectory() as folder:
            f=fixture(folder=folder); trial=Path(folder)/'records/context_pilot/BOC_fixture'
            before=(trial/'summary.json').read_bytes()
            with self.assertRaises(FileExistsError): fixture(folder=folder)
            self.assertEqual((trial/'summary.json').read_bytes(),before)
            self.assertTrue(f['result']['cleanup_confirmed'])

    def test_missing_or_inconsistent_dispatch_provenance_is_rejected(self):
        c={'id':'call_001','role':'agent','status':'ok','input_tokens':30,'output_tokens':20}
        s={'next_call_id':'call_001','model_attempted':True,'terminal_usage_recorded':True,'usage_unknown':False}
        valid=SimpleNamespace(calls=[c],snapshots=[s]); self.assertEqual(attempt_usage(valid),[c])
        cases=[SimpleNamespace(calls=[c],snapshots=[]), SimpleNamespace(calls=[c,c],snapshots=[s]),
            SimpleNamespace(calls=[c],snapshots=[s,s]),
            SimpleNamespace(calls=[],snapshots=[s]),
            SimpleNamespace(calls=[c],snapshots=[{**s,'usage_unknown':True}]),
            SimpleNamespace(calls=[],snapshots=[{**s,'terminal_usage_recorded':False}])]
        for invalid in cases:
            with self.assertRaises(ValueError): attempt_usage(invalid)
        self.assertEqual(valid.calls,[c]); self.assertEqual(valid.snapshots,[s])


if __name__ == '__main__':
    unittest.main()
