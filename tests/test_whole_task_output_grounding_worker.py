"""Actual P129 worker with handwritten code and synthetic model/typed replies."""
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
from run_whole_task_output_grounding_cell import run_cell
from whole_task_output_grounding import cell_id
from test_public_name_catalog import tool
from test_public_output_grounding import Fixture, TASK, SONGS
from test_region_projection_runtime import TrustedRegionSession
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
            incomplete=False,stop=False,corrupt_record=False,raised_write=False,checkpoint=False):
    original=(checkpoint_configuration()[0] if checkpoint else
              json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text()))
    task=next(iter(original['api_budget_by_task']))
    plan=dict(phase='budget_observation_connection',experiment='P129',known_tasks=[{'task_id':task,'source_run':'synthetic'}],
        model_seeds=[57,157],world_seed=42,api_budget_by_task_slot=[120],
        max_calls=12 if checkpoint else 8,max_total_tokens=450000 if checkpoint else 500,
        max_wall_seconds=60,max_setup_seconds=120,max_cleanup_seconds=180,automatic_retries=0,
        reserved_scenarios_read=0,history_policy='all_returned_reasoning_from_start')
    item=dict(task_id=task,source_run='synthetic',known_public_task_sha256='synthetic',public_task=deepcopy(TASK))
    proof=Fixture().ready();good=proof.proposal(mode='repair')['replacement_args']['content']
    reads=READS if not incomplete else READS.replace("call_api('spotify','show_playlist_library',access_token=spotify_token,page_limit=2)\n",'')
    programs=[DISCOVER,reads]+(["print('synthetic checkpoint turn one')","print('synthetic checkpoint turn two')"] if checkpoint else [])
    programs.append(write_program(Fixture().arguments()['content']))
    if mode=='feedback' and not incomplete:programs.append(write_program(good))
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
    class Session(TrustedRegionSession):
        def __init__(self,storage_root,folder,*,policy):super().__init__(folder,policy);self.storage_root=storage_root
        def run(self,source,*args,**kwargs):
            result=super().run(source,*args,**kwargs)
            if stop and source==DISCOVER:
                marker=storage/'.runtime/P129.stop';marker.parent.mkdir(exist_ok=True);marker.touch()
            return result
        def close(self):
            result=super().close();self.state.update(status='closed',container_removed=True);self._save();return result
    def count(config,messages,tools,timeout):
        tokens=(5000+4000*sum(m['role']=='assistant' for m in messages) if tools else 10000) if checkpoint else 30
        return dict(input_tokens=tokens,wall_seconds=0)
    def send(config,messages,output,timeout,tools):
        captured.append(deepcopy(messages))
        captured_requests.append(dict(config=deepcopy(config),messages=deepcopy(messages),role='agent' if tools else 'focus'))
        if unknown_model and len(captured)==2:raise OSError('synthetic lost model reply')
        agent_index=sum(r['role']=='agent' for r in captured_requests)-1
        message=(dict(role='assistant',content=None,reasoning_content='synthetic',tool_calls=[dict(
            id='fixture-'+str(len(captured)),type='function',function=dict(name='run_python',
                arguments=json.dumps({'code':programs[agent_index],'span_ids':[]})))]) if tools else deepcopy(VALID_CHECKPOINT))
        tokens=count(config,messages,tools,timeout)['input_tokens']
        response=dict(status='ok',input_tokens=tokens,output_tokens=20,wall_seconds=0,cached_input_tokens=0,
                      message=message,done_reason='tool_calls',
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
    with patch('run_whole_task_output_grounding_cell.TypedBridgeProcess',Raw), \
         patch('run_whole_task_output_grounding_cell.RegionProjectionPython',Session), \
         patch('run_whole_task_output_grounding_cell.verify_joined_implementation',return_value=JOINED_CONTRACT_ID), \
         patch('run_whole_task_output_grounding_cell.verify_public_export_sources',return_value=PUBLIC_CONTRACT_ID), \
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
                        grounding_mode=mode,replication=replication)
    return dict(result=result,folder=storage/'records/context_pilot'/cell_id(replication,1,mode),
                raw=raws[0],captured=captured,captured_requests=captured_requests,
                original=original,public=deepcopy(TASK),tools=tools,plan=plan,item=item)


class OutputGroundingWorkerTests(unittest.TestCase):
    def test_real_rolling_path_keeps_focus_and_grounding_costs_in_one_ledger(self):
        with tempfile.TemporaryDirectory() as temp:
            d=fixture(Path(temp),'repair',checkpoint=True);r=d['result']
            self.assertEqual(r['stop_reason'],'agent_declared_complete')
            self.assertGreater(r['usage_by_role']['focus']['calls'],0)
            self.assertEqual(r['output_grounding']['grounding_repairs'],1)
            self.assertEqual(r['known_total_tokens'],sum(v['input_tokens']+v['output_tokens'] for v in r['usage_by_role'].values()))
            self.assertEqual(r['model_calls'],len(d['captured_requests']))

    def test_three_modes_both_seeds_keep_initial_input_common_and_actual_write_truthful(self):
        for rep in (1,2):
            initial=[]
            for mode in ('off','feedback','repair'):
                with self.subTest(rep=rep,mode=mode),tempfile.TemporaryDirectory() as temp:
                    d=fixture(Path(temp),mode,replication=rep);r=d['result']
                    error=d['folder']/'error_private.json'
                    self.assertEqual(r['stop_reason'],'agent_declared_complete',error.read_text() if error.exists() else r)
                    self.assertEqual((r['replication'],r['model_seed'],r['grounding_mode']),(rep,(57,157)[rep-1],mode))
                    g=r['output_grounding'];self.assertTrue(g['contract_intact']);self.assertTrue(r['cleanup_confirmed'])
                    self.assertEqual(g['grounding_repairs'],int(mode=='repair'))
                    self.assertEqual(g['feedback_blocks'],int(mode=='feedback'))
                    writes=[c for c in d['raw'].calls if c['api']=='create_file']
                    self.assertEqual(len(writes),1)
                    expected='contradicted' if mode=='off' else 'supported'
                    self.assertEqual(csv_compare(writes[0]['args']['content'],[(SONGS[0]['title'],'A|B'),(SONGS[1]['title'],'日本語')])['status'],expected)
                    self.assertEqual(sum(c['api']=='delete_account' for c in d['raw'].calls),1)
                    self.assertEqual(g['deletion_interventions'],0)
                    self.assertEqual(r['api_requests'],len(d['raw'].calls))
                    events=json.loads((d['folder']/'events.json').read_text())
                    self.assertEqual(r['request_budget']['spent'],sum(e['api_request_sent'] for e in events))
                    self.assertEqual(g['observed_records'],len(events))
                    notices=json.loads((d['folder']/'output_grounding_notices_private.json').read_text())
                    self.assertEqual(len(notices),int(mode!='off'));initial.append(d['captured'][0])
            self.assertEqual(initial[0],initial[1]);self.assertEqual(initial[1],initial[2])

    def test_unknown_source_retains_payload_and_has_no_intervention(self):
        with tempfile.TemporaryDirectory() as temp:
            d=fixture(Path(temp),'repair',incomplete=True);r=d['result']
            self.assertEqual(r['stop_reason'],'agent_declared_complete')
            self.assertEqual(r['output_grounding']['grounding_repairs'],0)
            self.assertEqual(r['output_grounding']['repair_attempts'],0)
            self.assertEqual(json.loads((d['folder']/'output_grounding_events_private.json').read_text())[0]['assessment']['status'],'unknown')

    def test_unknown_model_cost_and_archive_are_retained_without_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            d=fixture(Path(temp),'repair',unknown_model=True);r=d['result']
            self.assertEqual((r['stop_reason'],r['model_calls'],r['known_total_tokens'],r['unknown_usage_calls']),
                             ('model_usage_unknown',2,50,1))
            self.assertTrue((d['folder']/'conversation_private.json').is_file())
            self.assertEqual(r['output_grounding']['write_checks'],0)

    def test_unknown_write_is_paid_failed_repair_and_stops(self):
        with tempfile.TemporaryDirectory() as temp:
            d=fixture(Path(temp),'repair',unknown_write=True);r=d['result']
            self.assertGreater(r['unknown_effect_requests'],0)
            self.assertEqual(r['output_grounding']['grounding_repairs'],0)
            self.assertEqual(r['output_grounding']['grounding_sent_repairs'],1)
            self.assertEqual(r['model_calls'],3)
            self.assertEqual(sum(c['api']=='delete_account' for c in d['raw'].calls),0)

    def test_known_raised_write_keeps_paid_cost_and_never_claims_successful_repair(self):
        with tempfile.TemporaryDirectory() as temp:
            d=fixture(Path(temp),'repair',raised_write=True);r=d['result']
            self.assertEqual(r['unknown_effect_requests'],0)
            self.assertEqual(r['output_grounding']['grounding_repairs'],0)
            self.assertEqual(r['output_grounding']['grounding_sent_repairs'],1)
            self.assertEqual(sum(c['api']=='delete_account' for c in d['raw'].calls),0)

    def test_record_binding_failure_retains_paid_effect_and_stops_before_next_model(self):
        with tempfile.TemporaryDirectory() as temp:
            d=fixture(Path(temp),'repair',corrupt_record=True);r=d['result']
            self.assertEqual(r['stop_reason'],'output_grounding_contract_stopped')
            self.assertFalse(r['output_grounding']['contract_intact'])
            self.assertEqual(r['model_calls'],3)
            self.assertEqual(sum(c['api']=='create_file' for c in d['raw'].calls),1)
            self.assertEqual(sum(c['api']=='delete_account' for c in d['raw'].calls),0)
            self.assertTrue((d['folder']/'usage.json').is_file())

    def test_user_stop_has_no_write_and_preserves_first_paid_turn(self):
        with tempfile.TemporaryDirectory() as temp:
            d=fixture(Path(temp),'repair',stop=True);r=d['result']
            self.assertEqual(r['stop_reason'],'user_stop');self.assertEqual(r['model_calls'],1)
            self.assertEqual(r['known_total_tokens'],50);self.assertEqual(r['output_grounding']['write_checks'],0)


if __name__=='__main__':unittest.main()
