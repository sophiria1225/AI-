# Synthetic P135 worker fixture; no model, generated Python, or AppWorld API runs.
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
from run_whole_task_observed_obligations_cell_p135 import run_cell
from whole_task_observed_obligations_p135 import cell_id
from test_public_output_grounding import TASK
from observed_field_obligations import CONTRACT_ID
from appworld_native_tools import NativeCatalog

ROOT = Path(__file__).resolve().parents[1]


def synthetic_tools():
    names=('spotify__login','spotify__show_song_library','spotify__show_album_library',
           'spotify__show_playlist_library','spotify__show_album','spotify__show_artist',
           'phone__get_current_date_and_time','supervisor__complete_task')
    return [{'type':'function','function':{'name':name,'parameters':{'type':'object','properties':{
        key:{} for key in ('username','access_token','page_index','page_limit','is_public','album_id','artist_id','fail')}}}} for name in names]


def configuration():
    original = json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
    original.update(api_budget_by_task={'34d9492_1':8}, max_output_tokens=4096)
    plan = {'experiment':'P135', 'inline_checkpoint_requirement':'required_when_run_python', 'phase':PHASE, 'max_calls':8, 'max_total_tokens':200, 'max_wall_seconds':60,
        'max_setup_seconds':120, 'max_cleanup_seconds':180, 'model_seed':57, 'rolling_checkpoint_max_opportunities':3, 'rolling_min_fresh_turns':3, 'world_seed':42,
        'history_policy':'all_returned_reasoning_from_start', 'automatic_retries':0,
        'reserved_scenarios_read':0}
    public = copy.deepcopy(TASK)
    item = {'task_id':'34d9492_1', 'source_run':'synthetic',
            'known_public_task_sha256':'synthetic-only', 'public_task':public}
    return original, plan, item


def fixture(*, mode='raw_anchor', replication=1, arm='error_exception', actions=('echo','finish'),
            count_delay=0, unknown_api=False, cleanup_ok=True, first_cached=0,
            initial_mismatch=False, token_limit=450000, api_limit=8, stop_after_api=False,
            response_delay=0, folder=None, summary_mode='valid', max_calls=20, focus_input_tokens=10000):
    """Real worker, inference admission and API channel, with external I/O replaced.

    No generated Python executes. The session emits hand-written RPC packets;
    FixtureTransport executes only its existing trusted synthetic API wrapper.
    """
    original, plan, item = configuration()
    original['api_budget_by_task']['34d9492_1'] = 80
    plan['max_total_tokens'] = token_limit
    plan['max_calls'] = max_calls
    clock = [0.0]; captured = []; counted = []; programs = []; raw_instances = []

    class Raw:
        timeout_seconds = 90
        def __init__(self, *args, **kwargs):
            self.commands=[];self.complete=False;raw_instances.append(self)
        def request(self, command):
            self.commands.append(command)
            if command['op'] == 'init':
                public = {**item['public_task'], 'api_result_protocol':PROTOCOL}
                if initial_mismatch: public['instruction'] = 'different fixture'
                return {'ok':True, 'result':public}
            if command['op']=='close':return {'ok':True,'result':{'closed':True}}
            assert command['op']=='call_typed'
            call=command['call'];name=call['app']+'__'+call['api'];args=call['args']
            value={'message':'synthetic'}
            if name=='spotify__login':value={'token_type':'Bearer','access_token':'synthetic-token'}
            elif name in ('spotify__show_song_library','spotify__show_album_library'):value=[]
            elif name=='spotify__show_playlist_library':
                value=[] if args['is_public'] else [{'playlist_id':1,'is_public':False,'song_ids':[11,22]}]
            elif name=='spotify__show_album':value={'album_id':1,'songs':[{'id':11,'title':'Observed title','artist_ids':[9]}],'artists':[]}
            elif name=='spotify__show_artist':value={'artist_id':9,'name':'Observed artist'}
            elif name=='supervisor__complete_task':self.complete=True
            packet={'protocol':PROTOCOL,'nonce':command['nonce'],'status':'returned','value':value}
            if name=='phone__get_current_date_and_time' and args.get('fail'):
                packet={'protocol':PROTOCOL,'nonce':command['nonce'],'status':'raised','error':{'type':'ValueError','message':'synthetic'}}
            raw=json.dumps(packet)
            return {'ok':True,'result':{'protocol':PROTOCOL,'observation':'broken synthetic envelope' if unknown_api else raw,'declared_complete':self.complete}}
        def close(self):
            return {'graceful':cleanup_ok, 'process_stopped':True, 'transport_failed':not cleanup_ok}

    class Session:
        def __init__(self, *args):
            self.state = {'container_removed':False}; self.usable = True
        def run(self, source, observations, channel, **kwargs):
            programs.append(source)
            if source not in ('seed','echo','finish','fail','partial','artist'):
                raise AssertionError('only handwritten fixture actions may run')
            directory = kwargs['record_dir']
            directory.mkdir(parents=True, exist_ok=False)
            (directory / 'input_private.json').write_text(json.dumps(
                {'code':source, 'observations':observations, 'program_index':len(programs), 'api_schemas':{}}))
            commands = [('phone','get_current_date_and_time',{'fail':source=='fail'})]
            if source=='finish':commands=[('supervisor','complete_task',{})]
            if source=='partial':commands=[('spotify','show_album',{'album_id':1})]
            if source=='artist':commands=[('spotify','show_artist',{'artist_id':9})]
            if source=='seed':commands=[
                ('spotify','login',{'username':item['public_task']['supervisor']['email']}),
                ('spotify','show_song_library',{'access_token':'synthetic-token','page_index':0,'page_limit':20}),
                ('spotify','show_album_library',{'access_token':'synthetic-token','page_index':0,'page_limit':20}),
                ('spotify','show_playlist_library',{'access_token':'synthetic-token','page_index':0,'page_limit':20,'is_public':False}),
                ('spotify','show_playlist_library',{'access_token':'synthetic-token','page_index':0,'page_limit':20,'is_public':True})]
            for n,(app,api,args) in enumerate(commands,1):
                packet={'kind':'api','id':n,'app':app,'api':api,'arguments':args}
                reply=channel.exchange(packet);kwargs['on_record'](channel.rows[-1])
                if not reply['ok']:break
            if stop_after_api:
                stop = kwargs['storage_root']/'.runtime/P135.stop'
                stop.parent.mkdir(exist_ok=True); stop.touch()
            return {'status':'ok' if reply['ok'] else 'execution_error', 'stdout':'fixture output',
                'stdout_truncated':False, 'api_requests':sum(r['api_request_sent'] for r in channel.rows),
                'declared_complete':channel.complete, 'unknown_effects':channel.fatal,
                'error':None if reply['ok'] else reply['error']}
        def close(self): self.state['container_removed'] = cleanup_ok

    def agent_tokens(messages, tools):
        extra = 500 if tools and 'checkpoint' in tools[0]['function']['parameters']['properties'] else 0
        return 5000 + 4000 * sum(m['role'] == 'assistant' for m in messages) + extra + len(json.dumps(messages))//40

    def count(cfg, messages, tools, timeout):
        counted.append(copy.deepcopy(messages))
        if len(counted) == 1: clock[0] += count_delay
        return {'input_tokens':(focus_input_tokens if not tools else agent_tokens(messages, tools)), 'wall_seconds':count_delay if len(counted)==1 else 0}

    def send(cfg, messages, output, timeout, tools):
        captured.append({'cfg':copy.deepcopy(cfg), 'messages':copy.deepcopy(messages), 'timeout':timeout, 'role': 'agent' if tools else 'focus', 'tools':copy.deepcopy(tools)})
        if not tools:
            mode = summary_mode if isinstance(summary_mode, str) else summary_mode[sum(c['role']=='focus' for c in captured)-1]
            if mode == 'transport_error':
                raise OSError('synthetic summary transport loss')
            if mode == 'unknown':
                response = {'status':'error', 'input_tokens':None, 'output_tokens':None,
                            'wall_seconds':1, 'error_kind':'request_or_response', 'timeout_scope':None}
                (output/'response.json').write_text(json.dumps(response))
                return response
            response = {'status':'ok', 'input_tokens':focus_input_tokens, 'output_tokens':20, 'wall_seconds':1,
                'done_reason':'stop', 'cached_input_tokens':0,
                'message':{'role':'assistant','content':json.dumps({k:['fixture'] for k in ('completed','usable_state','remaining','uncertainties')})}}
            if mode == 'invalid':
                response['message']['content'] = '{}'
            (output/'response.json').write_text(json.dumps(response))
            return response
        measured_input = agent_tokens(messages, tools)
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
        if action.startswith('query') and response['status']=='ok':
            query_args={'op':'snapshot','handle':None,'cursor':0,'limit':16}
            if action=='query_bad':query_args['cursor']=1
            if action=='query_stale':query_args.update(op='page',handle='0'*64)
            if action=='query_page':
                prior=json.loads((output.parent/'obligation_queries_private.json').read_text())
                query_args.update(op='page',handle=prior[-1]['observation']['snapshot']['handle'] if prior else '0'*64)
            response['message']['tool_calls'][0]['function']={'name':'read_obligations','arguments':json.dumps(query_args)}
            if action=='query_jsonbad':
                response['message']['tool_calls'][0]['function']['arguments']='{'
            if action=='query_then_echo':
                response['message']['tool_calls'].append({'id':f'fixture-second-{len(captured)}','type':'function','function':{'name':'run_python','arguments':json.dumps({'code':'echo','span_ids':[]})}})
        if tools and 'checkpoint' in tools[0]['function']['parameters']['properties'] and response['status'] == 'ok':
            args = json.loads(response['message']['tool_calls'][0]['function']['arguments'])
            if summary_mode != 'missing':
                args['checkpoint'] = {} if summary_mode == 'invalid' else {k:['fixture'] for k in ('completed','usable_state','remaining','uncertainties')}
            response['message']['tool_calls'][0]['function']['arguments'] = json.dumps(args)
            if summary_mode == 'truncated': response['done_reason'] = 'length'
        (output/'response.json').write_text(json.dumps(response))
        clock[0] += response_delay
        return response

    def execute(storage):
        with patch('observed_field_obligations.verify_partitioned_export_sources', return_value=CONTRACT_ID), \
             patch('run_whole_task_observed_obligations_cell_p135.time.monotonic', side_effect=lambda:clock[0]), \
             patch('run_whole_task_observed_obligations_cell_p135.RecordedBridge', side_effect=lambda raw, target, deadline, **kw:
                   RecordedBridge(raw, target, deadline, clock=lambda:clock[0], **kw)), \
             patch('run_whole_task_observed_obligations_cell_p135.TypedBridgeProcess', Raw), \
             patch('run_whole_task_observed_obligations_cell_p135.PersistentApiPython', Session), \
             patch('rolling_checkpoint_inference.count_agent_input', side_effect=count), \
             patch('rolling_checkpoint_inference.count_summary_input', side_effect=count), \
             patch('single_checkpoint_inference.count_agent_input', side_effect=count), \
             patch('single_checkpoint_inference.count_summary_input', side_effect=count), \
             patch('fixed_budget_residual.count_input', side_effect=count), \
             patch('fixed_budget_residual.model_call', side_effect=send), \
             patch('tool_choice_residual.count_input', side_effect=count), \
             patch('tool_choice_residual.model_call', side_effect=send):
            result = run_cell(storage, ROOT, plan, original, synthetic_tools(),
                item, arm, cell_id(replication, 1, mode), obligation_mode=mode, replication=replication)
        trial = storage/'records/context_pilot'/cell_id(replication, 1, mode)
        saved = {p.stem:json.loads(p.read_text()) for p in trial.glob('*.json')}
        return {'result':result,'saved':saved,'captured':captured,'counted':counted,'programs':programs,
                'raw':raw_instances,'storage':storage}

    if folder is not None: return execute(Path(folder))
    with tempfile.TemporaryDirectory() as temporary: return execute(Path(temporary))


def audit_fixture(folder, result):
    from audit_observed_obligation_trace import audit_trace
    from fixed_budget_local_llama import payload_for as summary_payload
    from tool_choice_local_llama import payload_for as agent_payload
    from whole_task_observed_obligations_p135 import initial_conversation
    trial = Path(folder) / 'records/context_pilot' / result['result']['run_id']
    config = json.loads((trial / 'plan.json').read_text())
    public = json.loads((trial / 'public_task.json').read_text())
    original = json.loads((ROOT / 'configs/P29_stateful_code_v01.json').read_text())
    for index, capture in enumerate(result['captured'], 1):
        call = trial / f'call_{index:03d}'
        actor = capture['role'] == 'agent'
        payload = agent_payload if actor else summary_payload
        (call / 'request.json').write_text(json.dumps(payload(
            capture['cfg'], capture['messages'], capture['tools'])))
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
    with patch('observed_field_obligations.verify_partitioned_export_sources', return_value=CONTRACT_ID):
        return audit_trace(trial, config, initial_conversation(original, public, config['obligation_mode']))
