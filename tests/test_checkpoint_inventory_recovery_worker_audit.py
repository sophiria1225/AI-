"""Actual P131 worker with handwritten code and synthetic model/typed replies."""
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
from run_whole_task_checkpoint_inventory_recovery_cell import run_cell
from whole_task_checkpoint_inventory_recovery import cell_id
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
    plan=dict(phase='budget_observation_connection',experiment='P131',known_tasks=[{'task_id':task,'source_run':'synthetic'}],
        model_seeds=[57],world_seed=42,api_budget_by_task_slot=[120],
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
                marker=storage/'.runtime/P131.stop';marker.parent.mkdir(exist_ok=True);marker.touch()
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
    with patch('run_whole_task_checkpoint_inventory_recovery_cell.TypedBridgeProcess',Raw), \
         patch('run_whole_task_checkpoint_inventory_recovery_cell.CheckpointInventoryPython',Session), \
         patch('checkpoint_inventory_runtime.CheckpointInventoryPython',Session), \
         patch('run_whole_task_checkpoint_inventory_recovery_cell.verify_joined_implementation',return_value=JOINED_CONTRACT_ID), \
         patch('run_whole_task_checkpoint_inventory_recovery_cell.verify_public_export_sources',return_value=PUBLIC_CONTRACT_ID), \
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



class RecoveryWorkerAuditTests(unittest.TestCase):
    def test_actual_synthetic_worker_audit_and_public_rows_share_new_identity(self):
        from test_whole_task_output_grounding_audit import transport_records
        from audit_whole_task_checkpoint_inventory_recovery import audit_cell
        from whole_task_checkpoint_inventory_recovery import initial_conversation
        from build_p131_report import public_row
        from budget_signal import digest
        for mode,unknown in [('off',False),('checkpoint_inventory',False),('checkpoint_inventory',True)]:
            with self.subTest(mode=mode,unknown=unknown),tempfile.TemporaryDirectory() as temp:
                data=fixture(Path(temp),mode,checkpoint=True,unknown_after_inventory=unknown)
                transport_records(data);folder=data['folder'];config=json.loads((folder/'plan.json').read_text())
                self.assertTrue(folder.name.startswith('BOC_P131_R01_01_'))
                conv=initial_conversation(data['original'],data['public'])
                pre=dict(base_messages_sha256=digest(conv.for_model(config['observation_page_characters'])[0]))
                with patch('region_projection_runtime.verify_joined_implementation',return_value=JOINED_CONTRACT_ID), \
                     patch('demand_joined_read_adapter.verify_joined_implementation',return_value=JOINED_CONTRACT_ID), \
                     patch('audit_output_grounding_runtime.verify_public_export_sources',return_value=PUBLIC_CONTRACT_ID), \
                     patch('audit_checkpoint_inventory_trace.expected_inventory_python',return_value=sys.version.split()[0]):
                    row=audit_cell(folder,ROOT,data['plan'],data['original'],data['item'],mode,1,pre,False,tools=data['tools'])
                result=public_row(row)
                self.assertEqual(result['model_seed'],57)
                self.assertEqual(result['grounding_mode'],'feedback')
                self.assertGreater(row['inventory_captures'],0)
                self.assertEqual(result['inventory_notice_actor_calls'],0 if mode=='off' else row['inventory_captures'])
                self.assertEqual(result['unknown_usage_calls'],int(unknown))
                self.assertEqual(result['exact_total_tokens'],None if unknown else row['known_total_tokens'])
                self.assertNotIn('inventory_runtime',result)

if __name__=='__main__':unittest.main()
