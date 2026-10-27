"""P138 launch/closure boundaries with handwritten I/O stubs only."""
from copy import deepcopy
from contextlib import ExitStack
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import run_whole_task_prefix_exposure_p138 as driver
import run_whole_task_prefix_exposure_pipeline_p138 as pipeline
import run_whole_task_prefix_exposure_cell_p138 as worker
import prefix_exposure_server_identity_p138 as identity
from whole_task_prefix_exposure_p138 import (MODES, fixed_fields, run_order, cell_id, config_for,
                                            initial_conversation, make_notification)
from whole_task_rolling_checkpoint import config_for as prior_config
from whole_task_remaining_late_obligations_p137 import run_order as previous_order, cell_id as previous_id
from api_error_comparison import task_snapshot
from public_display import CODE_TOOLS
from tool_choice_local_llama import payload_for


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def plan_and_source():
    prior = json.loads((ROOT/'configs/P123_whole_task_rolling_checkpoint_v01.json').read_text())
    original = json.loads((ROOT/prior['source_plan']).read_text())
    plan = {**fixed_fields(), 'known_tasks': deepcopy(prior['known_tasks'])}
    prepared = [{**task, 'public_task': {'instruction': 'Handwritten synthetic task only.'}}
                for task in plan['known_tasks']]
    return plan, original, prepared, prior


class DriverTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)/'repo'; self.storage = Path(tmp.name)/'storage'
        (self.root/'reports').mkdir(parents=True); self.storage.mkdir()
        self.plan, self.original, self.prepared, self.prior = plan_and_source()

    def prepare(self):
        captured = []
        def count(cfg, messages, tools, timeout):
            captured.append((deepcopy(cfg), deepcopy(messages), deepcopy(tools)))
            return {'input_tokens': 5000, 'wall_seconds': 0}
        stack = ExitStack(); self.addCleanup(stack.close)
        for patched in (
            patch.object(driver, 'sources', return_value=(self.plan,self.original,[],self.prepared)),
            patch.object(driver, 'frozen_hashes', return_value={'synthetic':'a'*64}),
            patch.object(driver, 'frozen_sources', return_value='b'*40),
            patch.object(driver, 'live_identity', return_value=({'synthetic':True}, 'future')),
            patch.object(driver, 'check_resume', return_value={'synthetic':True}),
            patch.object(driver.subprocess, 'check_output', return_value='b'*40),
            patch.object(driver, 'count_input', side_effect=count),
            patch.object(driver, 'count_summary_input', side_effect=count)):
            stack.enter_context(patched)
        pre = driver.preflight(self.storage, self.root)
        return pre, captured

    def validate(self, pre):
        write(self.storage/'records/context_pilot/P138_preflight_v01/status.json', pre)
        return driver.validate_preflight(self.storage,self.root,pre,self.plan,self.original,self.prepared)

    def test_all_twelve_initial_inputs_match_original_P123_and_three_modes(self):
        self.assertEqual(len(run_order()), 12)
        self.assertEqual(len(set(run_order())), 12)
        for task in self.plan['known_tasks']:
            old = prior_config(self.original,self.prior,task['task_id'],'rolling_separate')
            messages,_ = initial_conversation(self.original,{'instruction':'Synthetic only.'}).for_model()
            def request(config, mode):
                supplied,_=make_notification(messages,task_snapshot(config,[],0,0),mode,wall_limit=1800)
                cfg={**config['model'],'temperature':config['agent_temperature'],'seed':config['seed'],
                     'num_predict':config['max_output_tokens'],'cache_prompt':False}
                return payload_for(cfg,supplied,CODE_TOOLS)
            for mode in MODES:
                config=config_for(self.original,self.plan,task['task_id'],mode)
                self.assertEqual(request(config,mode),request(old,'rolling_separate'))
                self.assertEqual(config['seed'],57)

    def test_exact_fifteen_counts_saved_payloads_and_activation_once(self):
        pre,captured=self.prepare()
        self.assertEqual(len(captured),15)
        self.assertEqual((pre['input_count_requests'],pre['summary_input_count_requests']), (12,3))
        self.assertEqual(pre['inline_input_count_requests'],0)
        for start in range(0,12,3):
            self.assertEqual(captured[start],captured[start+1])
            self.assertEqual(captured[start],captured[start+2])
            self.assertFalse(captured[start][0]['cache_prompt'])
        self.validate(pre)
        driver.activate(self.storage,self.root)
        frozen=driver.read(self.root/driver.ACTIVATION)
        driver.validate_activation(self.storage,self.root,frozen,pre)
        with self.assertRaises(FileExistsError):driver.activate(self.storage,self.root)
        with self.assertRaises(FileExistsError):driver.preflight(self.storage,self.root)

    def test_saved_preflight_phase_zero_counts_identity_and_payload_cannot_be_relabelled(self):
        pre,_=self.prepare()
        changes=[('phase','P137_preflight'),('model_generations',1),('environment_api_requests',False),
                 ('evaluator_calls',1),('reserved_scenarios_read',False),('git_commit','c'*40),
                 ('all_twelve_inputs_checked',1),('summary_input_count_requests',2),
                 ('inline_input_count_requests',False),('wall_seconds',float('nan'))]
        for key,value in changes:
            changed=deepcopy(pre);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(changed)
        changed=deepcopy(pre);changed['rows'][0]['conditions'].pop('fixed_interval')
        with self.assertRaises(ValueError):self.validate(changed)
        changed=deepcopy(pre);changed['rows'][1]=deepcopy(changed['rows'][0])
        with self.assertRaises(ValueError):self.validate(changed)
        changed=deepcopy(pre);changed['rows'][0]['conditions']['rolling_separate']['input_tokens']=True
        with self.assertRaises(ValueError):self.validate(changed)
        changed=deepcopy(pre);changed['rolling_transport'][0]['synthetic_only']=1
        with self.assertRaises(ValueError):self.validate(changed)
        self.validate(pre)
        path=self.storage/'records/context_pilot/P138_preflight_v01'/(
            self.prepared[0]['source_run']+'_rolling_separate_request_private.json')
        value=driver.read(path);value['seed']=999;write(path,value)
        with self.assertRaisesRegex(ValueError,'payload_changed'):self.validate(pre)

    def test_saved_activation_exact_phase_all_twelve_source_and_head(self):
        pre,_=self.prepare();driver.activate(self.storage,self.root)
        freeze=driver.read(self.root/driver.ACTIVATION)
        for key,value in [('phase','P137'),('all_twelve_conditions_frozen_before_generation',False),
                          ('git_commit','c'*40),('source_hashes',{}),('preflight_sha256','f'*64),
                          ('research_resume',{})]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                driver.validate_activation(self.storage,self.root,{**freeze,key:value},pre)

    def test_explicit_stop_and_unclosed_predecessor_precede_native_contact(self):
        marker=self.storage/'.runtime/P138.stop';marker.parent.mkdir();marker.touch()
        with patch.object(driver,'sources') as sources,patch.object(driver,'live_identity') as live:
            with self.assertRaises(InterruptedError):driver.preflight(self.storage,self.root)
            sources.assert_not_called();live.assert_not_called()
        marker.unlink()
        with patch.object(driver,'check_resume',return_value={}), \
             patch.object(driver,'sources',side_effect=ValueError('unclosed')), \
             patch.object(driver,'count_input') as count,patch.object(driver,'live_identity') as live:
            with self.assertRaisesRegex(ValueError,'unclosed'):driver.preflight(self.storage,self.root)
            count.assert_not_called();live.assert_not_called()
        self.assertFalse((self.storage/'records/context_pilot/P138_preflight_v01').exists())

    def predecessor(self):
        folder=self.storage/'records/context_pilot/P137_pipeline_v01'
        final={'status':'stopped','pid':124,'supervisor_pid':123}
        state={'status':'complete','server_stopped':True,'server_supervisor_pid':123}
        write(folder/'status.json',state);write(folder/'server_final.json',final)
        audit={'phase':'P137','audit_errors':[],'owned_processes_absent':True,
               'rows':[{'run_id':previous_id(*slot),'record_status':'evaluated','success':False}
                       for slot in previous_order()],
               'pipeline_status_sha256':driver.sha(folder/'status.json'),
               'server_final_sha256':driver.sha(folder/'server_final.json')}
        write(self.root/'reports/P137_comparison.json',audit)
        session={'phase':'P137','status':'stopped','owned_processes_absent':True,
                 'audit_source_sha256':driver.sha(self.root/'reports/P137_comparison.json')}
        write(self.root/'reports/P137_server_session.json',session)
        return folder,audit,session,final

    def test_all_four_failed_predecessor_is_allowed_but_false_zero_duplicate_or_live_pid_rejected(self):
        folder,audit,session,final=self.predecessor()
        with patch.object(driver.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')):
            proof=driver.predecessor_closed(self.storage,self.root)
            self.assertEqual(proof['session_sha256'],driver.sha(self.root/'reports/P137_server_session.json'))
            for change in ({'audit_errors':False},{'audit_errors':0},{'audit_errors':['synthetic error']},
                           {'rows':audit['rows'][:-1]+[audit['rows'][0]]}):
                changed={**audit,**change};write(self.root/'reports/P137_comparison.json',changed)
                write(self.root/'reports/P137_server_session.json',{**session,'audit_source_sha256':driver.sha(self.root/'reports/P137_comparison.json')})
                with self.assertRaises(ValueError):driver.predecessor_closed(self.storage,self.root)
            self.predecessor();write(folder/'server_final.json',{**final,'pid':True})
            current=driver.read(self.root/'reports/P137_comparison.json');current['server_final_sha256']=driver.sha(folder/'server_final.json')
            write(self.root/'reports/P137_comparison.json',current)
            write(self.root/'reports/P137_server_session.json',{**session,'audit_source_sha256':driver.sha(self.root/'reports/P137_comparison.json')})
            with self.assertRaisesRegex(ValueError,'positive_previous'):driver.predecessor_closed(self.storage,self.root)
        self.predecessor()
        with patch.object(driver.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='owned process')):
            with self.assertRaisesRegex(ValueError,'process_present'):driver.predecessor_closed(self.storage,self.root)

    def test_bounded_worker_exit_receipt_captures_failure_and_timeout_no_retry(self):
        folder=self.storage/'batch';folder.mkdir()
        for index,kind in enumerate(('failure','timeout')):
            rid=cell_id(1,MODES[index])
            class Child:
                pid=555
                returncode=None
                calls=0
                def wait(self,timeout):
                    self.calls+=1
                    if kind=='timeout' and self.calls==1:raise subprocess.TimeoutExpired('synthetic',timeout)
                    self.returncode=-15 if kind=='timeout' else 7
                    return self.returncode
                def poll(self):return self.returncode
                def terminate(self):pass
            child=Child()
            with patch.object(driver.subprocess,'Popen',return_value=child) as popen:
                with self.assertRaises((RuntimeError,subprocess.TimeoutExpired)):
                    driver.bounded_cell(self.storage,self.root,self.plan,1,MODES[index],rid,folder)
                self.assertEqual(popen.call_count,1)
            record=driver.read(folder/(rid+'_worker_exit.json'))
            self.assertEqual(record['status'],'exited')
            self.assertEqual(record['wait_timeout_seconds'],2100)
            self.assertEqual(record['timed_out'],kind=='timeout')
            self.assertEqual(record['returncode'],child.returncode)
            with self.assertRaises(FileExistsError):
                driver.bounded_cell(self.storage,self.root,self.plan,1,MODES[index],rid,folder)

    def test_worker_installs_timeout_handler_and_restores_previous_signal_handler(self):
        before=signal.getsignal(signal.SIGALRM)
        def inner(*args,**kwargs):
            handler=signal.getsignal(signal.SIGALRM)
            self.assertTrue(callable(handler))
            handler(signal.SIGALRM,None)
        with patch.object(worker,'_run_cell',side_effect=inner):
            with self.assertRaises(TimeoutError):
                worker.run_cell(None,None,None,None,None,None,None,None,prefix_exposure_mode='prefix_exposure')
        self.assertEqual(signal.getsignal(signal.SIGALRM),before)

    def _started_attempt_failure(self, failed_stage):
        pre,_=self.prepare();driver.activate(self.storage,self.root)
        number,mode=run_order()[0];rid=cell_id(number,mode)
        result=dict(run_id=rid,task_id=self.prepared[0]['task_id'],arm='synthetic',
            prefix_exposure_mode=mode,time_visibility='not_exposed',checkpoint_policy='rolling_separate',
            reasoning_budget_tokens=0,stop_reason='synthetic',model_calls=1,known_total_tokens=10,
            unknown_usage_calls=0,api_requests=0,wall_seconds=1,full_wall_seconds=2,cleanup_confirmed=True)
        status=self.storage/'records/context_pilot'/self.plan['batch_id']/'status.json'
        def idle(*args):
            row=driver.read(status)['rows'][0]
            self.assertIn('idle_recovery_started_at',row)
            self.assertNotIn('evaluation_started_at',row)
            if failed_stage=='idle_recovery':raise RuntimeError('synthetic idle failure')
            return {'wall_seconds':0.25}
        def evaluate(*args,**kwargs):
            row=driver.read(status)['rows'][0]
            self.assertIn('evaluation_started_at',row)
            self.assertEqual(row['idle_recovery'],{'wall_seconds':0.25})
            raise subprocess.TimeoutExpired('synthetic evaluation',kwargs['timeout'])
        with patch.object(driver,'run_order',return_value=[(number,mode)]), \
             patch.object(driver,'bounded_cell',return_value=result), \
             patch.object(driver,'disposition',return_value='continue'), \
             patch.object(driver,'wait_idle',side_effect=idle), \
             patch.object(driver.subprocess,'run',side_effect=evaluate) as evaluation:
            self.assertEqual(driver.run(self.storage,self.root),1)
            self.assertEqual(evaluation.call_count,int(failed_stage=='evaluation'))
        row=driver.read(status)['rows'][0]
        from inspect_whole_task_prefix_exposure_session_p138 import attempt_time_totals
        if failed_stage=='idle_recovery':
            self.assertEqual(attempt_time_totals([row],'idle_recovery')['unknown_attempts'],1)
            self.assertIsNone(attempt_time_totals([row],'idle_recovery')['exact_total'])
            self.assertEqual(attempt_time_totals([row],'evaluation')['attempts'],0)
        else:
            self.assertEqual(attempt_time_totals([row],'evaluation')['attempts'],1)
            self.assertGreaterEqual(row['evaluation_wall_seconds'],0)

    def test_idle_start_is_persisted_before_failed_wait_and_missing_cost_stays_unknown(self):
        self._started_attempt_failure('idle_recovery')

    def test_evaluation_start_is_persisted_before_call_and_timeout_wall_is_saved(self):
        self._started_attempt_failure('evaluation')


class PipelineAndIdentityTests(unittest.TestCase):
    def test_start_boundary_checks_stop_resume_and_absolute_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp);plan=fixed_fields();deadline=dt.datetime.fromisoformat(plan['deadline_jst']).timestamp()
            with patch.object(pipeline,'check_resume',return_value={'ok':True}), \
                 patch.object(pipeline.time,'time',return_value=deadline-32400):
                pipeline.launch_boundary(storage,plan,{'ok':True})
                with self.assertRaises(ValueError):pipeline.launch_boundary(storage,plan,{})
            with patch.object(pipeline,'check_resume',return_value={}), \
                 patch.object(pipeline.time,'time',return_value=deadline-32399):
                with self.assertRaises(ValueError):pipeline.launch_boundary(storage,plan,{})
            (storage/'.runtime').mkdir();(storage/'.runtime/P138.stop').touch()
            with self.assertRaises(InterruptedError):pipeline.launch_boundary(storage,plan,{})

    def test_pipeline_stages_are_finite_and_failed_stage_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'repo';storage=Path(tmp)/'storage';root.mkdir();storage.mkdir()
            plan,original,_,_=plan_and_source();write(root/driver.PLAN,plan)
            runtime=storage/'.runtime/model_server.json';children=[];waits=[]
            class Child:
                def __init__(self,command):
                    self.pid=100+len(children);self.returncode=None;self.server='serve_research_model_recovery.py' in command[1]
                    self.command=command;children.append(self)
                    if self.server:write(runtime,{'status':'ready','supervisor_pid':self.pid,'pid':999,
                                                 'record_directory':'records/p2_servers/synthetic'})
                def poll(self):return self.returncode
                def wait(self,timeout):
                    waits.append(timeout)
                    self.returncode=0 if '--preflight' in self.command or '--activate' in self.command or self.server else 1
                    return self.returncode
                def terminate(self):
                    self.returncode=0
                    if self.server:write(runtime,{'status':'stopped','supervisor_pid':self.pid,'pid':999,
                                                  'record_directory':'records/p2_servers/synthetic'})
            with patch.object(pipeline,'ROOT',root),patch.object(pipeline,'check_resume',return_value={}), \
                 patch.object(pipeline,'checked_ci',return_value={'synthetic':True}), \
                 patch.object(pipeline.subprocess,'check_output',side_effect=['a'*40,'']), \
                 patch.object(pipeline.subprocess,'Popen',side_effect=lambda command,**kw:Child(command)), \
                 patch.object(pipeline.time,'time',return_value=dt.datetime.fromisoformat(plan['deadline_jst']).timestamp()-40000), \
                 patch.object(driver,'sources',return_value=(plan,original,[],[])), \
                 patch.object(driver,'predecessor_closed',return_value={'synthetic':'closed'}):
                self.assertEqual(pipeline.run(storage,'a'*40),1)
            state=driver.read(storage/'records/context_pilot/P138_pipeline_v01/status.json')
            self.assertEqual([s['mode'] for s in state['stages']],['preflight','activation','batch'])
            self.assertEqual([s['wait_timeout_seconds'] for s in state['stages']],[480,60,30000])
            self.assertEqual([s['exit_code'] for s in state['stages']],[0,0,1])
            self.assertEqual(len(children),4)
            self.assertTrue(state['server_stopped'])
            self.assertIn('32400',children[0].command)
            self.assertTrue(all('run_whole_task_prefix_exposure_p138.py' in c.command[1] for c in children[1:]))

    def test_owned_32400_lease_and_same_identity_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'repo';storage=Path(tmp)/'storage';storage.mkdir()
            source=root/identity.SUPERVISOR;source.parent.mkdir(parents=True);source.write_text('synthetic\n')
            plan={'model_selection':'configs/synthetic.json','model':{'num_ctx':65536,'base_url':'http://127.0.0.1:8011'}}
            now=dt.datetime.now(dt.timezone.utc)
            runtime={'pid':12,'supervisor_pid':11,'started_at':(now-dt.timedelta(seconds=10)).isoformat(),
                     'record_directory':'records/p2_servers/synthetic'}
            owner={'phase':'P138_pipeline','status':'batch','server_owned':True,'server_supervisor_pid':11,
                   'server_record_directory':runtime['record_directory']}
            args=['python',str(source),'--storage-root',str(storage.resolve()),'--selection',plan['model_selection'],
                  '--ctx-size','65536','--cache-type-k','q8_0','--cache-type-v','q8_0','--max-seconds','32400']
            with patch.object(identity,'ROOT',root),patch.object(identity,'SUPERVISOR_SHA256',hashlib.sha256(source.read_bytes()).hexdigest()):
                left,_=identity.owned_lease(runtime,shlex.join(args),now,storage=storage,source_plan=plan,owner=owner)
                self.assertEqual(left,32390)
                for variant in (args[:-1]+['21600'],['python',str(root/'scripts/serve_research_model.py')]+args[2:]):
                    with self.assertRaises(ValueError):identity.owned_lease(runtime,shlex.join(variant),now,storage=storage,source_plan=plan,owner=owner)
                with self.assertRaises(ValueError):identity.owned_lease(runtime,shlex.join(args),now,storage=storage,source_plan=plan,owner={**owner,'phase':'P137_pipeline'})
            with patch.object(identity.urllib.request,'urlopen',return_value=io.StringIO('[{"is_processing":false}]')), \
                 patch.object(identity,'live_identity',return_value=({'same':True},'end')) as live:
                identity.wait_idle(storage,plan,{'same':True},1)
                live.assert_called_once_with(storage,plan,1)


if __name__=='__main__':unittest.main()
