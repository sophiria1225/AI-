"""Actual pilot worker with synthetic model replies and handwritten local code."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from public_api_envelope import PROTOCOL
from run_whole_task_read_view_cell import run_cell
from whole_task_read_views import POLICIES,TASK_ID,cell_id,fixed_parameters,initial_conversation
from test_agent_read_view_runtime import ForwardingFixtureSession
from test_public_name_catalog import tool
from test_public_read_views_live_probe import Fixture,catalog

ROOT=Path(__file__).resolve().parents[1]
PROGRAMS=("library=call_api('spotify','show_song_library',access_token='synthetic-token',page_index=0,page_limit=3)\n"
          "v=read_view('spotify','show_song',song_id=10)\nprint(v['title'])",
          "print(v['genre'])\ndel v\ncall_api('supervisor','complete_task')")


def fixture(storage,policy,*,unknown=False,stop=False,no_tool=False):
    original=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
    plan={**fixed_parameters(),'max_calls':3,'max_total_tokens':200,'max_wall_seconds':60}
    public=dict(instruction='Complete only the synthetic fixture',ground_truth_loaded=False)
    item=dict(task_id=TASK_ID,source_run='synthetic',known_public_task_sha256='synthetic',public_task=public)
    captured=[]
    class Raw(Fixture):
        timeout_seconds=90
        def __init__(self,*args,**kwargs):super().__init__()
        def request(self,command):
            if command['op']=='init':return {'ok':True,'result':{**public,'api_result_protocol':PROTOCOL}}
            if command['call']['api']=='complete_task':
                self.calls.append(copy.deepcopy(command['call']))
                envelope=dict(protocol=PROTOCOL,nonce=command['nonce'],status='returned',value={'done':True})
                return {'ok':True,'result':dict(protocol=PROTOCOL,observation=json.dumps(envelope),declared_complete=True)}
            return super().request(command)
        def close(self):return dict(graceful=True,process_stopped=True,transport_failed=False)
    class Session(ForwardingFixtureSession):
        def __init__(self,storage,folder):super().__init__(folder,storage_root=storage)
        def run(self,source,*args,**kwargs):
            result=super().run(source,*args,**kwargs)
            if stop and source==PROGRAMS[0]:
                marker=storage/'.runtime/P107.stop';marker.parent.mkdir(exist_ok=True);marker.touch()
            return result
        def close(self):
            result=super().close();self.usable=False
            self.state.update(container_removed=True,status='closed');self._save();return result
    def count(cfg,messages,tools,timeout):return dict(input_tokens=30,wall_seconds=0)
    def send(cfg,messages,output,timeout,tools):
        captured.append(dict(cfg=copy.deepcopy(cfg),messages=copy.deepcopy(messages)))
        if unknown and len(captured)==2:raise OSError('synthetic model transport loss')
        index=len(captured)-1
        message=dict(role='assistant',content=None,reasoning_content='synthetic fixture')
        if not no_tool:
            message['tool_calls']=[dict(id=f'fixture-{index}',type='function',function=dict(name='run_python',
                arguments=json.dumps(dict(code=PROGRAMS[index],span_ids=[]))))]
        cached=0 if index==0 else 20
        response=dict(status='ok',input_tokens=30,output_tokens=20,wall_seconds=0,
            done_reason='tool_calls' if not no_tool else 'stop',cached_input_tokens=cached,message=message,
            timings=dict(cache_n=cached,prompt_n=30-cached,predicted_n=20,prompt_ms=1,predicted_ms=1))
        (output/'response.json').write_text(json.dumps(response));return response
    tools=list(catalog().catalog.values())+[tool('supervisor__complete_task')]
    with patch('run_whole_task_read_view_cell.TypedBridgeProcess',Raw), \
         patch('run_whole_task_read_view_cell.AgentReadViewPython',Session), \
         patch('tool_choice_residual.count_input',side_effect=count), \
         patch('tool_choice_residual.model_call',side_effect=send):
        result=run_cell(storage,ROOT,plan,original,tools,item,'error_exception',cell_id(1,policy),read_view_policy=policy)
    folder=storage/'records/context_pilot'/cell_id(1,policy)
    return dict(result=result,captured=captured,folder=folder,original=original,item=item,plan=plan)


def audit_fixture(data,policy):
    from tool_choice_local_llama import payload_for
    from public_display import CODE_TOOLS
    from budget_signal import digest
    import audit_whole_task_read_views as auditor
    folder=data['folder']
    for i,capture in enumerate(data['captured'],1):
        call=folder/f'call_{i:03d}'
        (call/'request.json').write_text(json.dumps(payload_for(capture['cfg'],capture['messages'],CODE_TOOLS)))
        if (call/'response.json').exists():
            (call/'raw_response.json').write_text((call/'response.json').read_text())
    base,_=initial_conversation(data['original'],data['item']['public_task']).for_model()
    with patch.object(auditor,'parse_response',side_effect=lambda x:x):
        return auditor.audit_cell(folder,ROOT,data['plan'],data['original'],data['item'],policy,
                                  {'base_messages_sha256':digest(base)},False)


class WholeTaskReadViewWorkerTests(unittest.TestCase):
    def test_real_worker_tracks_pending_reads_and_has_identical_initial_requests(self):
        starts=[]
        for policy in POLICIES:
            with tempfile.TemporaryDirectory() as tmp:
                data=fixture(Path(tmp),policy);r=data['result'];checked=audit_fixture(data,policy)
                self.assertEqual(r['stop_reason'],'agent_declared_complete')
                self.assertTrue(r['cleanup_confirmed'])
                self.assertEqual((r['known_total_tokens'],r['api_requests']),(100,3))
                self.assertEqual(checked['read_view_runtime']['read_requests'],1)
                signals=json.loads((data['folder']/'budget_observations.json').read_text())
                self.assertEqual(signals[1]['request_budget']['pending'],int(policy=='coalesced_cached'))
                self.assertEqual(signals[1]['request_budget']['available'],78)
                self.assertEqual([x['cfg']['cache_prompt'] for x in data['captured']],[False,True])
                starts.append(data['captured'][0])
        self.assertEqual(starts[0],starts[1])

    def test_unknown_model_usage_does_not_materialize_or_execute_a_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=fixture(Path(tmp),'coalesced_cached',unknown=True)
            checked=audit_fixture(data,'coalesced_cached')
            self.assertEqual((checked['model_calls'],checked['unknown_usage_calls']),(2,1))
            self.assertEqual((checked['api_requests'],checked['read_view_runtime']['budget']['pending']),(1,1))
            self.assertEqual(checked['known_total_tokens'],50)

    def test_explicit_stop_retains_pending_cost_without_forced_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=fixture(Path(tmp),'coalesced_cached',stop=True)
            checked=audit_fixture(data,'coalesced_cached')
            self.assertEqual(checked['stop_reason'],'user_stop')
            self.assertEqual((checked['model_calls'],checked['api_requests']),(1,1))
            self.assertEqual(checked['read_view_runtime']['budget']['pending'],1)

    def test_no_tool_outputs_remain_failed_adoption_with_zero_API(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=fixture(Path(tmp),'coalesced_cached',no_tool=True)
            checked=audit_fixture(data,'coalesced_cached')
            self.assertEqual((checked['model_calls'],checked['api_requests']),(3,0))
            self.assertEqual(checked['read_view_runtime']['read_requests'],0)
            self.assertEqual(sum(r['format_rejections'] for r in checked['request_checks']),3)

    def test_changed_pending_reservation_notice_is_rejected_by_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=fixture(Path(tmp),'coalesced_cached')
            path=data['folder']/'budget_observations.json'
            signals=json.loads(path.read_text())
            signals[1]['request_budget'].update(pending=0,available=79)
            path.write_text(json.dumps(signals))
            with self.assertRaisesRegex(ValueError,'reservation_history_differs'):
                audit_fixture(data,'coalesced_cached')


if __name__=='__main__':unittest.main()
