"""Actual P130 worker with handwritten code and synthetic model/typed replies."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from joined_public_read_views import JOINED_CONTRACT_ID
from public_api_envelope import PROTOCOL
from public_output_grounding import PUBLIC_CONTRACT_ID, csv_compare
from run_whole_task_checkpoint_inventory_cell import run_cell
from whole_task_checkpoint_inventory import cell_id
from test_public_name_catalog import tool
from test_public_output_grounding import Fixture, TASK, SONGS
from test_region_projection_runtime import TrustedRegionSession
from test_persistent_read_view_python import TrustedSubprocessSession
from checkpoint_inventory_runtime import CheckpointInventoryPython, derived_inventory_bootstrap
import hashlib
import selectors
import subprocess
import time
from single_checkpoint_worker_fixture import configuration as checkpoint_configuration
from test_single_checkpoint import VALID as VALID_CHECKPOINT

ROOT=Path(__file__).resolve().parents[1]
FIELDS={'spotify__login':['username','password'],'file_system__login':['username','password'],
    'spotify__show_song_library':['access_token','page_limit'],
    'spotify__show_album_library':['access_token','page_limit'],
    'spotify__show_playlist_library':['access_token','page_limit'],
    'spotify__show_song':['song_id'],
    'file_system__create_file':['access_token','file_path','content','overwrite'],
    'spotify__delete_account':['access_token']}
DISCOVER='\n'.join(f"call_api('api_docs','show_api_doc',app_name={name.split('__')[0]!r},api_name={name.split('__')[1]!r})"
                   for name in FIELDS)
READS="""spotify_token=call_api('spotify','login',username='synthetic@example.test',password='synthetic')['access_token']
file_token=call_api('file_system','login',username='synthetic@example.test',password='synthetic')['access_token']
call_api('spotify','show_song_library',access_token=spotify_token,page_limit=2)
call_api('spotify','show_album_library',access_token=spotify_token,page_limit=2)
call_api('spotify','show_playlist_library',access_token=spotify_token,page_limit=2)
call_api('spotify','show_song',song_id=2)
"""


def write_program(content):
    return ("print(call_api('file_system','create_file',access_token=file_token,file_path='~/backup/export.csv',"
            f"content={content!r},overwrite=False))\n"
            "print(call_api('spotify','delete_account',access_token=spotify_token))")


def fixture(storage,mode,*,replication=1,unknown_model=False,unknown_write=False,
            incomplete=False,stop=False,corrupt_record=False,raised_write=False,checkpoint=False,capture_fail=False,reject_checkpoint=False,unknown_after_inventory=False):
    original=(checkpoint_configuration()[0] if checkpoint else
              json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text()))
    task=next(iter(original['api_budget_by_task']))
    plan=dict(phase='budget_observation_connection',experiment='P130',known_tasks=[{'task_id':task,'source_run':'synthetic'}],
        model_seeds=[57,157],world_seed=42,api_budget_by_task_slot=[120],
        max_calls=12 if checkpoint else 8,max_total_tokens=450000 if checkpoint else 500,
        max_wall_seconds=60,max_setup_seconds=120,max_cleanup_seconds=180,automatic_retries=0,
        reserved_scenarios_read=0,history_policy='all_returned_reasoning_from_start')
    item=dict(task_id=task,source_run='synthetic',known_public_task_sha256='synthetic',public_task=deepcopy(TASK))
    proof=Fixture().ready();good=proof.proposal(mode='repair')['replacement_args']['content']
    reads=READS if not incomplete else READS.replace("call_api('spotify','show_playlist_library',access_token=spotify_token,page_limit=2)\n",'')
    programs=[DISCOVER,reads]+(["print('synthetic checkpoint turn one')","print('synthetic checkpoint turn two')"] if checkpoint else [])
    programs.append(write_program(Fixture().arguments()['content']))
    if not incomplete:programs.append(write_program(good))
    programs.append("call_api('supervisor','complete_task')")
    captured=[];captured_requests=[];raws=[]
    class Raw:
        timeout_seconds=90
        def __init__(self,*args,**kwargs):self.calls=[];raws.append(self)
        def request(self,command):
            if command['op']=='init':return {'ok':True,'result':{**TASK,'api_result_protocol':PROTOCOL}}
            action=command['call'];self.calls.append(deepcopy(action));name=action['app']+'__'+action['api']
            if name=='file_system__create_file' and unknown_write:raise OSError('synthetic lost write receipt')
            if name=='file_system__create_file' and raised_write:
                envelope=dict(protocol=PROTOCOL,nonce=command['nonce'],status='raised',
                    error={'type':'ValueError','message':'synthetic rejected write'})
                return {'ok':True,'result':{'protocol':PROTOCOL,'observation':json.dumps(envelope),'declared_complete':False}}
            if name=='api_docs__show_api_doc':value={}
            elif name=='supervisor__complete_task':value={'done':True}
            elif name=='file_system__create_file':value={'message':'File created.','file_path':'/home/synthetic/backup/export.csv'}
            elif name=='spotify__delete_account':value={'message':'Account terminated.'}
            else:
                matches=[json.loads(span['observation']['observation']) for event,span in proof.rows if span['action']['name']==name]
                assert len(matches)==1,name
                value=matches[0]
            envelope=dict(protocol=PROTOCOL,nonce=command['nonce'],status='returned',value=value)
            return {'ok':True,'result':{'protocol':PROTOCOL,'observation':json.dumps(envelope),
                'declared_complete':name=='supervisor__complete_task'}}
        def close(self):return dict(graceful=True,process_stopped=True,transport_failed=False)
    class Session(CheckpointInventoryPython):
        def __init__(self,storage_root,folder,*,policy,execution_scope):
            TrustedSubprocessSession.__init__(self,folder,storage_root)
            self.policy=policy
            self.inventory_scope_sha256=hashlib.sha256(execution_scope.encode()).hexdigest()
        def _start(self):
            self.stderr=(self.folder/'stderr.txt').open('wb')
            self.process=subprocess.Popen([sys.executable,'-I','-S','-u','-c',
                derived_inventory_bootstrap(self.policy,self.inventory_scope_sha256)],stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=self.stderr)
            self.selector=selectors.DefaultSelector();self.selector.register(self.process.stdout,selectors.EVENT_READ)
            self.created_monotonic=time.monotonic()
        def capture_inventory(self,**kwargs):
            if capture_fail:
                self.usable=False
                raise TimeoutError('synthetic inventory capture failure')
            return super().capture_inventory(**kwargs)
        def run(self,source,*args,**kwargs):
            result=super().run(source,*args,**kwargs)
            if stop and source==DISCOVER:
                marker=storage/'.runtime/P130.stop';marker.parent.mkdir(exist_ok=True);marker.touch()
            return result
        def close(self):
            result=TrustedSubprocessSession.close(self);self.usable=False;self.state.update(status='closed',container_removed=True);self._save();return result
    def count(config,messages,tools,timeout):
        tokens=(5000+4000*sum(m['role']=='assistant' for m in messages) if tools else 10000) if checkpoint else 30
        tokens+=sum(len(m.get('content',''))//4 for m in messages if m.get('role')=='system' and 'checkpoint_runtime_inventory_v1' in m.get('content',''))
        return dict(input_tokens=tokens,wall_seconds=0)
    def send(config,messages,output,timeout,tools):
        captured.append(deepcopy(messages))
        captured_requests.append(dict(config=deepcopy(config),messages=deepcopy(messages),role='agent' if tools else 'focus'))
        if (unknown_model and len(captured)==2) or (unknown_after_inventory and any(m.get('role')=='system' and 'checkpoint_runtime_inventory_v1' in m.get('content','') for m in messages)):
            raise OSError('synthetic lost model reply')
        agent_index=sum(r['role']=='agent' for r in captured_requests)-1
        message=(dict(role='assistant',content=None,reasoning_content='synthetic',tool_calls=[dict(
            id='fixture-'+str(len(captured)),type='function',function=dict(name='run_python',
                arguments=json.dumps({'code':programs[agent_index],'span_ids':[]})))]) if tools else deepcopy(VALID_CHECKPOINT))
        if not tools and reject_checkpoint:message={'role':'assistant','content':'synthetic invalid checkpoint'}
        tokens=count(config,messages,tools,timeout)['input_tokens']
        response=dict(status='ok',input_tokens=tokens,output_tokens=20,wall_seconds=0,cached_input_tokens=0,
                      message=message,done_reason='tool_calls' if tools else 'stop',
                      timings=dict(cache_n=0,prompt_n=tokens,predicted_n=20,prompt_ms=1,predicted_ms=1))
        (output/'response.json').write_text(json.dumps(response));return response
    tools=[tool(name,{k:{} for k in fields}) for name,fields in FIELDS.items()]
    tools += [tool('api_docs__show_api_doc',{'app_name':{},'api_name':{}}),tool('supervisor__complete_task')]
    from output_grounding_runtime import OutputGroundingController
    observe=OutputGroundingController.observe
    def observed(self,event,span,**kwargs):
        if corrupt_record and event.get('output_grounding_entry') is not None:
            span={**span,'id':'synthetic-mismatch'}
        return observe(self,event,span,**kwargs)
    with patch('run_whole_task_checkpoint_inventory_cell.TypedBridgeProcess',Raw), \
         patch('run_whole_task_checkpoint_inventory_cell.CheckpointInventoryPython',Session), \
         patch('checkpoint_inventory_runtime.CheckpointInventoryPython',Session), \
         patch('run_whole_task_checkpoint_inventory_cell.verify_joined_implementation',return_value=JOINED_CONTRACT_ID), \
         patch('run_whole_task_checkpoint_inventory_cell.verify_public_export_sources',return_value=PUBLIC_CONTRACT_ID), \
         patch('region_projection_runtime.verify_joined_implementation',return_value=JOINED_CONTRACT_ID), \
         patch('demand_joined_read_adapter.verify_joined_implementation',return_value=JOINED_CONTRACT_ID), \
         patch('rolling_checkpoint_inference.count_agent_input',side_effect=count), \
         patch('rolling_checkpoint_inference.count_summary_input',side_effect=count), \
         patch('fixed_budget_residual.count_input',side_effect=count), \
         patch('fixed_budget_residual.model_call',side_effect=send), \
         patch('tool_choice_residual.count_input',side_effect=count), \
         patch('tool_choice_residual.model_call',side_effect=send), \
         patch.object(OutputGroundingController,'observe',observed):
        result=run_cell(storage,ROOT,plan,original,tools,item,'error_exception',cell_id(replication,1,mode),
                        inventory_mode=mode,replication=replication)
    return dict(result=result,folder=storage/'records/context_pilot'/cell_id(replication,1,mode),
                raw=raws[0],captured=captured,captured_requests=captured_requests,
                original=original,public=deepcopy(TASK),tools=tools,plan=plan,item=item)


class CheckpointInventoryWorkerTests(unittest.TestCase):
    def test_both_modes_capture_once_per_accepted_checkpoint_and_share_feedback(self):
        by_mode={}
        for mode in ('off','checkpoint_inventory'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                d=fixture(Path(temp),mode,checkpoint=True);r=d['result'];p=d['folder']/'error_private.json'
                self.assertEqual(r['stop_reason'],'agent_declared_complete',p.read_text() if p.exists() else r)
                self.assertEqual(r['grounding_mode'],'feedback');self.assertEqual(r['inventory_mode'],mode)
                self.assertEqual(r['output_grounding']['feedback_blocks'],1)
                self.assertEqual(r['output_grounding']['grounding_repairs'],0)
                self.assertEqual(r['api_requests'],len(d['raw'].calls));self.assertTrue(r['cleanup_confirmed'])
                inv=r['checkpoint_inventory'];capture=inv['capture'];installs=r['checkpoint_control']['installations']
                self.assertGreater(installs,0);self.assertEqual(capture['captures'],installs)
                self.assertEqual(capture['successful_captures'],installs);self.assertFalse(inv['contract_failed'])
                self.assertEqual(capture['environment_API_requests'],0);self.assertEqual(capture['model_calls'],0)
                self.assertEqual(inv['actual_inventory_exposures'],installs if mode=='checkpoint_inventory' else 0)
                messages=json.loads((d['folder']/'conversation_private.json').read_text())
                self.assertNotIn('checkpoint_runtime_inventory_v1',json.dumps(messages))
                views=json.loads((d['folder']/'checkpoint_inventory_inference_views.json').read_text())
                self.assertEqual(sum(v['inventory_included'] and v['model_attempted'] for v in views),inv['actual_inventory_exposures'])
                calls=json.loads((d['folder']/'usage.json').read_text())
                self.assertEqual(r['known_total_tokens'],sum(c['input_tokens']+c['output_tokens'] for c in calls))
                self.assertGreater(r['usage_by_role']['focus']['calls'],0)
                self.assertEqual(r['model_calls'],len(d['captured_requests']))
                by_mode[mode]=dict(initial=d['captured'][0],focus=[v['messages'] for v in d['captured_requests'] if v['role']=='focus'],
                    packets=json.loads((d['folder']/'checkpoint_inventory_packets_private.json').read_text()))
                for packet in by_mode[mode]['packets']:
                    self.assertFalse(packet['values_included']);self.assertFalse(packet['scalar_lengths_included'])
                    self.assertTrue(all(set(b)=={'name','type','length'} for b in packet['inventory']['bindings']))
        self.assertEqual(by_mode['off']['initial'],by_mode['checkpoint_inventory']['initial'])
        # Later grounding notices legitimately bind a different execution scope.
        self.assertEqual(by_mode['off']['focus'][0],by_mode['checkpoint_inventory']['focus'][0])
        for mode in by_mode:
            self.assertNotIn('checkpoint_runtime_inventory_v1',json.dumps(by_mode[mode]['focus']))
        self.assertEqual([p['inventory'] for p in by_mode['off']['packets']],
                         [p['inventory'] for p in by_mode['checkpoint_inventory']['packets']])

    def test_no_checkpoint_means_no_capture_or_exposure_both_seeds(self):
        for rep in (1,2):
            for mode in ('off','checkpoint_inventory'):
                with self.subTest(rep=rep,mode=mode),tempfile.TemporaryDirectory() as temp:
                    d=fixture(Path(temp),mode,replication=rep);r=d['result']
                    self.assertEqual(r['stop_reason'],'agent_declared_complete')
                    self.assertEqual((r['replication'],r['model_seed']),(rep,(57,157)[rep-1]))
                    self.assertEqual(r['checkpoint_inventory']['capture']['captures'],0)
                    self.assertEqual(r['checkpoint_inventory']['actual_inventory_exposures'],0)
                    self.assertEqual(r['output_grounding']['feedback_blocks'],1)

    def test_rejected_checkpoint_keeps_focus_cost_without_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            d=fixture(Path(temp),'checkpoint_inventory',checkpoint=True,reject_checkpoint=True);r=d['result']
            self.assertEqual(r['stop_reason'],'agent_declared_complete')
            self.assertGreater(r['usage_by_role']['focus']['calls'],0)
            self.assertEqual(r['checkpoint_control']['installations'],0)
            self.assertEqual(r['checkpoint_inventory']['capture']['captures'],0)
            self.assertEqual(r['checkpoint_inventory']['actual_inventory_exposures'],0)

    def test_capture_failure_stops_before_next_actor_and_preserves_paid_focus(self):
        for mode in ('off','checkpoint_inventory'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                d=fixture(Path(temp),mode,checkpoint=True,capture_fail=True);r=d['result']
                p=d['folder']/'error_private.json'
                self.assertEqual(r['stop_reason'],'checkpoint_inventory_contract_stopped',p.read_text() if p.exists() else r)
                self.assertTrue(r['checkpoint_inventory']['contract_failed'])
                self.assertEqual(r['checkpoint_inventory']['capture']['captures'],1)
                self.assertEqual(r['checkpoint_inventory']['capture']['successful_captures'],0)
                self.assertEqual(d['captured_requests'][-1]['role'],'focus')
                self.assertEqual(r['checkpoint_inventory']['actual_inventory_exposures'],0)
                self.assertGreater(r['usage_by_role']['focus']['calls'],0)
                self.assertTrue((d['folder']/'usage.json').is_file())

    def test_paid_unknown_inventory_actor_counts_exposure_and_retains_unknown_cost(self):
        with tempfile.TemporaryDirectory() as temp:
            d=fixture(Path(temp),'checkpoint_inventory',checkpoint=True,unknown_after_inventory=True);r=d['result']
            self.assertEqual(r['stop_reason'],'model_usage_unknown');self.assertEqual(r['unknown_usage_calls'],1)
            self.assertEqual(r['checkpoint_inventory']['actual_inventory_exposures'],1)
            self.assertTrue(r['checkpoint_inventory']['capture']['capture_accounting_complete'])
            self.assertEqual(r['model_calls'],len(d['captured_requests']))
            self.assertEqual(d['captured_requests'][-1]['role'],'agent')

    def test_shared_feedback_binding_failure_keeps_actual_records(self):
        with tempfile.TemporaryDirectory() as temp:
            d=fixture(Path(temp),'off',corrupt_record=True);r=d['result']
            self.assertEqual(r['stop_reason'],'output_grounding_contract_stopped')
            self.assertFalse(r['output_grounding']['contract_intact'])
            self.assertEqual(r['output_grounding']['grounding_repairs'],0)
            self.assertTrue((d['folder']/'events.json').is_file());self.assertGreater(r['known_total_tokens'],0)

    def test_user_stop_preserves_paid_usage_without_capture(self):
        with tempfile.TemporaryDirectory() as temp:
            d=fixture(Path(temp),'checkpoint_inventory',stop=True);r=d['result']
            self.assertEqual(r['stop_reason'],'user_stop');self.assertEqual(r['model_calls'],1)
            self.assertEqual(r['known_total_tokens'],50);self.assertEqual(r['checkpoint_inventory']['capture']['captures'],0)


if __name__=='__main__':unittest.main()
