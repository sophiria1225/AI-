"""P144 finite ownership, 21 fake counts and dispatch/closure boundaries."""
from copy import deepcopy
import datetime as dt
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_whole_task_state_update_pipeline_p144 as pipeline
import state_update_server_identity_p144 as identity
from checkpoint_state_update_preflight_p144 import synthetic_transport_cases
from public_display import CODE_TOOLS


def finite_plan():
    return dict(server_max_lifetime_seconds=24900, batch_timeout_seconds=24240,
        latest_launch_jst='2026-10-28T16:15:00+09:00',
        deadline_jst='2026-10-28T23:15:00+09:00')


class PipelineTests(unittest.TestCase):
    def test_twelve_full_cells_and_all_startup_stages_fit_finite_lease(self):
        pipeline.validate_timing_limits(finite_plan())
        for changes in ({'batch_timeout_seconds':24119}, {'batch_timeout_seconds':24391},
                        {'batch_timeout_seconds':float('inf')}, {'batch_timeout_seconds':True},
                        {'server_max_lifetime_seconds':24901}, {'server_max_lifetime_seconds':9000}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                pipeline.validate_timing_limits(finite_plan() | changes)

    def test_deadlines_cannot_be_extended_or_naive(self):
        for changes in ({'latest_launch_jst':'2026-10-28T16:16:00+09:00'},
                        {'deadline_jst':'2026-10-29T00:00:00+09:00'},
                        {'deadline_jst':'2026-10-28T23:15:00'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                pipeline.validate_timing_limits(finite_plan() | changes)

    def test_last_launch_boundary_rechecks_stop_authority_and_time(self):
        plan = finite_plan(); resume = {'synthetic_authority':True}
        now = dt.datetime.fromisoformat(plan['latest_launch_jst']).timestamp()
        with tempfile.TemporaryDirectory() as temporary:
            storage = Path(temporary); (storage/'.runtime').mkdir()
            with patch.object(pipeline, 'check_resume', return_value=resume), patch.object(pipeline.time, 'time', return_value=now):
                pipeline.launch_boundary(storage, plan, resume)
                with patch.object(pipeline.time, 'time', return_value=now+1), self.assertRaises(ValueError):
                    pipeline.launch_boundary(storage, plan, resume)
                with patch.object(pipeline, 'check_resume', return_value={'changed':True}), self.assertRaises(ValueError):
                    pipeline.launch_boundary(storage, plan, resume)
                (storage/'.runtime/P144.stop').write_text('stop')
                with self.assertRaises(InterruptedError):
                    pipeline.launch_boundary(storage, plan, resume)

    def test_owned_lease_rejects_wrong_namespace_options_and_parent_claim(self):
        now = dt.datetime(2026,10,28,0,0,tzinfo=dt.timezone.utc)
        runtime = dict(supervisor_pid=1234,pid=1235,
            record_directory='records/p2_servers/SYNTHETIC',started_at=now.isoformat())
        owner = dict(phase='P144_pipeline',status='preflight',server_owned=True,
            server_supervisor_pid=1234,server_record_directory=runtime['record_directory'])
        source = dict(model_selection='synthetic-selection',model={'num_ctx':65536})
        storage = Path('/synthetic-storage')
        args = ['synthetic-python', str(identity.ROOT/identity.SUPERVISOR),
            '--storage-root',str(storage),'--selection','synthetic-selection',
            '--ctx-size','65536','--cache-type-k','q8_0','--cache-type-v','q8_0',
            '--max-seconds','24900']
        remaining, _ = identity.owned_lease(runtime, shlex.join(args), now,
            storage=storage,source_plan=source,owner=owner)
        self.assertEqual(remaining,24900)
        for changed in (owner | {'phase':'P142_pipeline'}, owner | {'server_supervisor_pid':999},
                        owner | {'server_owned':False}):
            with self.assertRaises(ValueError):
                identity.owned_lease(runtime,shlex.join(args),now,storage=storage,source_plan=source,owner=changed)
        for tail in ('9000','24901'):
            with self.assertRaises(ValueError):
                identity.owned_lease(runtime,shlex.join(args[:-1]+[tail]),now,
                    storage=storage,source_plan=source,owner=owner)

    def test_pipeline_stage_failure_timeout_and_forced_cleanup_never_retry(self):
        from contextlib import redirect_stdout
        for kind in ('failure', 'timeout', 'kill_timeout'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)/'repo';storage=Path(temporary)/'storage'
                root.mkdir();(storage/'.runtime').mkdir(parents=True)
                plan=finite_plan();write(root/driver.PLAN,plan)
                runtime_path=storage/'.runtime/model_server.json'
                runtime=dict(supervisor_pid=111,record_directory='records/p2_servers/SYNTHETIC',status='ready')
                class Server:
                    pid=111
                    returncode=None
                    def poll(self):return self.returncode
                    def terminate(self):
                        self.returncode=0;write(runtime_path,{**runtime,'status':'stopped'})
                    def wait(self,timeout):return self.returncode
                class Child:
                    pid=222
                    returncode=None
                    waits=0
                    def poll(self):return self.returncode
                    def terminate(self):pass
                    def wait(self,timeout):
                        self.waits+=1
                        if kind!='failure' and self.waits==1:
                            raise subprocess.TimeoutExpired('synthetic stage',timeout)
                        if kind=='kill_timeout' and self.waits==2:
                            raise subprocess.TimeoutExpired('synthetic termination',timeout)
                        self.returncode=7 if kind=='failure' else (-9 if kind=='kill_timeout' else -15)
                        return self.returncode
                server,child=Server(),Child()
                def spawn(command,**kwargs):
                    if command[1].endswith('serve_research_model_recovery.py'):
                        write(runtime_path,runtime);return server
                    self.assertIn('--preflight',command)
                    return child
                def git(command,**kwargs):
                    return '' if 'status' in command else 'a'*40
                now=dt.datetime.fromisoformat(plan['latest_launch_jst']).timestamp()
                with (patch.object(pipeline,'ROOT',root),
                      patch.object(pipeline,'check_resume',return_value={'synthetic':True}),
                      patch.object(pipeline,'checked_ci',return_value={'synthetic':True}),
                      patch.object(pipeline.subprocess,'check_output',side_effect=git),
                      patch.object(pipeline.subprocess,'Popen',side_effect=spawn) as popen,
                      patch.object(pipeline.os,'killpg') as kill,
                      patch.object(pipeline.time,'time',return_value=now),
                      patch.object(driver,'sources',return_value=(plan,{'model_selection':'synthetic'},[],[])),
                      patch.object(driver,'predecessor_closed',return_value={'synthetic':True}),
                      redirect_stdout(io.StringIO())):
                    self.assertEqual(pipeline.run(storage,'a'*40),1)
                result=driver.read(storage/'records/context_pilot/P144_pipeline_v01/status.json')
                self.assertEqual(popen.call_count,2)
                self.assertEqual(result['status'],'stopped');self.assertTrue(result['server_stopped'])
                self.assertEqual(len(result['stages']),1)
                stage=result['stages'][0]
                self.assertEqual(stage['mode'],'preflight');self.assertEqual(stage['wait_timeout_seconds'],180)
                self.assertEqual(stage['timed_out'],kind!='failure')
                self.assertEqual(stage['forced_group_kill'],kind=='kill_timeout')
                self.assertEqual(stage['exit_code'],child.returncode)
                if kind=='kill_timeout':kill.assert_called_once_with(child.pid,signal.SIGKILL)
                else:kill.assert_not_called()

    def test_preflight_150_second_limit_preserves_failed_attempt_before_next_count(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        storage=Path(tmp.name)/'storage';root=Path(tmp.name)/'repo'
        storage.mkdir();(root/'reports').mkdir(parents=True)
        plan,original,prepared,_=plan_and_source();clock=[0.0];calls=[]
        def count(*args,**kwargs):
            calls.append(kwargs['timeout']);clock[0]=151
            return {'input_tokens':5000,'wall_seconds':151}
        with (patch.object(driver,'sources',return_value=(plan,original,[],prepared)),
              patch.object(driver,'frozen_hashes',return_value={'synthetic':'a'*64}),
              patch.object(driver,'frozen_sources',return_value='b'*40),
              patch.object(driver,'live_identity',return_value=({'synthetic':True},'future')),
              patch.object(driver,'check_resume',return_value={'synthetic':True}),
              patch.object(driver,'count_input',side_effect=count),
              patch.object(driver.time,'monotonic',side_effect=lambda:clock[0])):
            with self.assertRaisesRegex(TimeoutError,'P144_preflight_deadline'):
                driver.preflight(storage,root)
        result=driver.read(root/driver.PREFLIGHT)
        self.assertEqual(calls,[30]);self.assertEqual(result['status'],'failed')
        self.assertFalse(result['all_twelve_inputs_checked']);self.assertEqual(result['input_count_requests'],1)
        self.assertEqual(result['model_generations'],0)
        with self.assertRaises(FileExistsError):driver.preflight(storage,root)

    def test_nine_genuine_pure_shapes_have_three_first_second_and_actor_views(self):
        with (patch('subprocess.Popen',side_effect=AssertionError('NO_PROCESS')),
              patch('urllib.request.urlopen',side_effect=AssertionError('NO_NETWORK'))):
            cases=synthetic_transport_cases()
        self.assertEqual(len(cases),9)
        self.assertEqual(len({c['name'] for c in cases}),9)
        self.assertEqual(sum(c['role']=='focus' for c in cases),6)
        self.assertEqual(sum(c['role']=='agent' for c in cases),3)
        self.assertTrue(all(c['synthetic_only'] for c in cases))
        self.assertEqual({c['mode'] for c in cases},set(MODES))
        self.assertEqual([c['messages'] for c in cases[:3]],[cases[0]['messages']]*3)
        self.assertEqual([c['messages'][1] for c in cases[3:6]],[cases[3]['messages'][1]]*3)
        self.assertEqual(len({c['messages'][0]['content'] for c in cases[3:6]}),3)
        self.assertTrue(all(c['tools']==([] if c['role']=='focus' else CODE_TOOLS) for c in cases))
        counts=[sum(m.get('role')=='user' and '"checkpoint_kind"' in m.get('content','')
                    for m in c['messages']) for c in cases[6:]]
        self.assertEqual(counts,[1,2,1])
        before=deepcopy(cases);cases[0]['messages'][0]['content']='changed'
        self.assertEqual(synthetic_transport_cases(),before)


"""P144 launch/closure boundaries with handwritten I/O stubs only."""
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
import run_whole_task_state_update_p144 as driver
import run_whole_task_state_update_cell_p144 as worker
from whole_task_state_update_p144 import (MODES, fixed_fields, run_order, cell_id, config_for,
                                            initial_conversation, make_notification)
from whole_task_rolling_checkpoint import config_for as prior_config
from whole_task_threshold_object_p143 import run_order as previous_order, cell_id as previous_id
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
        # This new fixture fixes its own driver wall clock; no historical wrapper.
        from run_research_tests import FixedWallClock
        instant=dt.datetime(2026,10,28,7,0,tzinfo=dt.timezone.utc).timestamp()
        clock=patch.object(driver,'time',FixedWallClock(driver.time,instant))
        clock.start();self.addCleanup(clock.stop)
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
        write(self.storage/'records/context_pilot/P144_preflight_v01/status.json', pre)
        return driver.validate_preflight(self.storage,self.root,pre,self.plan,self.original,self.prepared)

    def test_all_twelve_initial_inputs_match_seed257_and_three_modes(self):
        self.assertEqual(len(run_order()), 12)
        self.assertEqual(len(set(run_order())), 12)
        for task in self.plan['known_tasks']:
            old = prior_config(self.original,self.prior,task['task_id'],'rolling_separate')
            old['seed']=257
            messages,_ = initial_conversation(self.original,{'instruction':'Synthetic only.'}).for_model()
            def request(config, mode):
                supplied,_=make_notification(messages,task_snapshot(config,[],0,0),mode,wall_limit=1800)
                cfg={**config['model'],'temperature':config['agent_temperature'],'seed':config['seed'],
                     'num_predict':config['max_output_tokens'],'cache_prompt':False}
                return payload_for(cfg,supplied,CODE_TOOLS)
            for mode in MODES:
                config=config_for(self.original,self.plan,task['task_id'],mode)
                self.assertEqual(request(config,mode),request(old,MODES[0]))
                self.assertEqual(config['seed'],257)
                self.assertEqual(config['checkpoint_trigger_input_tokens'],8192)
                self.assertEqual(config['max_wall_seconds'],1800)

    def test_exact_twentyone_counts_saved_payloads_and_activation_once(self):
        pre,captured=self.prepare()
        self.assertEqual(len(captured),21)
        self.assertEqual((pre['input_count_requests'],pre['summary_input_count_requests']), (12,6))
        self.assertEqual(pre['representation_actor_input_count_requests'],3)
        for start in range(0,12,3):
            self.assertEqual(captured[start:start+3],[captured[start]]*3)
            self.assertFalse(captured[start][0]['cache_prompt'])
        self.validate(pre)
        driver.activate(self.storage,self.root)
        frozen=driver.read(self.root/driver.ACTIVATION)
        driver.validate_activation(self.storage,self.root,frozen,pre)
        with self.assertRaises(FileExistsError):driver.activate(self.storage,self.root)
        with self.assertRaises(FileExistsError):driver.preflight(self.storage,self.root)

    def test_saved_preflight_phase_zero_counts_identity_and_payload_cannot_be_relabelled(self):
        pre,_=self.prepare()
        changes=[('phase','P140_preflight'),('model_generations',1),('environment_api_requests',False),
                 ('evaluator_calls',1),('reserved_scenarios_read',False),('git_commit','c'*40),
                 ('all_twelve_inputs_checked',1),('summary_input_count_requests',2),
                 ('representation_actor_input_count_requests',False),('wall_seconds',float('nan'))]
        for key,value in changes:
            changed=deepcopy(pre);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(changed)
        changed=deepcopy(pre);changed['rows'][0]['conditions'].pop('threshold_delta_object')
        with self.assertRaises(ValueError):self.validate(changed)
        changed=deepcopy(pre);changed['rows'].append(deepcopy(changed['rows'][0]))
        with self.assertRaises(ValueError):self.validate(changed)
        changed=deepcopy(pre);changed['rows'][0]['conditions']['threshold_recursive']['input_tokens']=True
        with self.assertRaises(ValueError):self.validate(changed)
        changed=deepcopy(pre);changed['representation_transport'][0]['synthetic_only']=1
        with self.assertRaises(ValueError):self.validate(changed)
        self.validate(pre)
        path=self.storage/'records/context_pilot/P144_preflight_v01'/(
            self.prepared[0]['source_run']+'_threshold_recursive_request_private.json')
        value=driver.read(path);value['seed']=999;write(path,value)
        with self.assertRaisesRegex(ValueError,'payload_changed'):self.validate(pre)

    def test_saved_activation_exact_phase_all_twelve_source_and_head(self):
        pre,_=self.prepare();driver.activate(self.storage,self.root)
        freeze=driver.read(self.root/driver.ACTIVATION)
        for key,value in [('phase','P143'),('all_twelve_conditions_frozen_before_generation',False),
                          ('git_commit','c'*40),('source_hashes',{}),('preflight_sha256','f'*64),
                          ('research_resume',{})]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                driver.validate_activation(self.storage,self.root,{**freeze,key:value},pre)

    def test_explicit_stop_and_unclosed_predecessor_precede_native_contact(self):
        marker=self.storage/'.runtime/P144.stop';marker.parent.mkdir();marker.touch()
        with patch.object(driver,'sources') as sources,patch.object(driver,'live_identity') as live:
            with self.assertRaises(InterruptedError):driver.preflight(self.storage,self.root)
            sources.assert_not_called();live.assert_not_called()
        marker.unlink()
        with patch.object(driver,'check_resume',return_value={}), \
             patch.object(driver,'sources',side_effect=ValueError('unclosed')), \
             patch.object(driver,'count_input') as count,patch.object(driver,'live_identity') as live:
            with self.assertRaisesRegex(ValueError,'unclosed'):driver.preflight(self.storage,self.root)
            count.assert_not_called();live.assert_not_called()
        self.assertFalse((self.storage/'records/context_pilot/P144_preflight_v01').exists())

    def predecessor(self):
        folder=self.storage/'records/context_pilot/P143_pipeline_v01'
        final={'status':'stopped','pid':124,'supervisor_pid':123}
        state={'status':'complete','server_stopped':True,'server_supervisor_pid':123}
        write(folder/'status.json',state);write(folder/'server_final.json',final)
        audit={'phase':'P143','audit_errors':[],'owned_processes_absent':True,
               'rows':[{'run_id':previous_id(*slot),'record_status':'evaluated','success':False}
                       for slot in previous_order()],
               'pipeline_status_sha256':driver.sha(folder/'status.json'),
               'server_final_sha256':driver.sha(folder/'server_final.json')}
        write(self.root/'reports/P143_comparison.json',audit)
        session={'phase':'P143','status':'stopped','owned_processes_absent':True,
                 'audit_source_sha256':driver.sha(self.root/'reports/P143_comparison.json')}
        write(self.root/'reports/P143_server_session.json',session)
        return folder,audit,session,final

    def test_all_eight_evaluated_predecessor_is_allowed_but_false_zero_duplicate_or_live_pid_rejected(self):
        folder,audit,session,final=self.predecessor()
        with patch.object(driver.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')):
            proof=driver.predecessor_closed(self.storage,self.root)
            self.assertEqual(proof['session_sha256'],driver.sha(self.root/'reports/P143_server_session.json'))
            for change in ({'audit_errors':False},{'audit_errors':0},{'audit_errors':['synthetic error']},
                           {'rows':audit['rows'][:-1]+[audit['rows'][0]]}):
                changed={**audit,**change};write(self.root/'reports/P143_comparison.json',changed)
                write(self.root/'reports/P143_server_session.json',{**session,'audit_source_sha256':driver.sha(self.root/'reports/P143_comparison.json')})
                with self.assertRaises(ValueError):driver.predecessor_closed(self.storage,self.root)
            self.predecessor();write(folder/'server_final.json',{**final,'pid':True})
            current=driver.read(self.root/'reports/P143_comparison.json');current['server_final_sha256']=driver.sha(folder/'server_final.json')
            write(self.root/'reports/P143_comparison.json',current)
            write(self.root/'reports/P143_server_session.json',{**session,'audit_source_sha256':driver.sha(self.root/'reports/P143_comparison.json')})
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
            self.assertEqual(record['wait_timeout_seconds'],1920)
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
                worker.run_cell(None,None,None,None,None,None,None,None,checkpoint_representation_mode='threshold_delta_object')
        self.assertEqual(signal.getsignal(signal.SIGALRM),before)

    def test_absolute_deadline_rejects_worker_before_spawn(self):
        end=dt.datetime.fromisoformat(self.plan['deadline_jst']).timestamp()
        folder=self.storage/'batch';folder.mkdir()
        with patch.object(driver.time,'time',return_value=end-1920), \
             patch.object(driver.subprocess,'Popen') as spawn:
            with self.assertRaisesRegex(TimeoutError,'absolute_deadline'):
                driver.bounded_cell(self.storage,self.root,self.plan,1,MODES[0],cell_id(1,MODES[0]),folder)
            spawn.assert_not_called()

    def test_partial_constructors_preserve_failed_summary_and_no_model_dispatch(self):
        from state_update_worker_fixture_p144 import fixture
        for stage in ('bridge','session'):
            with self.subTest(stage=stage):
                result=fixture(constructor_error=stage)
                row=result['result']
                self.assertEqual(row['phase'],'P144');self.assertEqual(row['model_seed'],257)
                self.assertEqual(row['stop_reason'],'setup_failure');self.assertEqual(result['captured'],[])
                self.assertFalse(row['cleanup_confirmed']);self.assertIsNone(row['final_success'])
                self.assertIn('summary',result['saved'])

    def test_local_setup_and_cleanup_deadlines_preserve_failed_attempt(self):
        from state_update_worker_fixture_p144 import fixture
        setup=fixture(setup_delay=61)
        self.assertEqual(setup['result']['stop_reason'],'setup_failure')
        self.assertEqual(setup['captured'],[])
        cleanup=fixture(actions=('finish',),cleanup_delay=61)
        self.assertFalse(cleanup['result']['cleanup_confirmed'])
        self.assertEqual(cleanup['result']['stop_reason'],'cleanup_error')
        self.assertEqual(cleanup['result']['model_calls'],1)
        self.assertGreater(cleanup['result']['known_total_tokens'],0)
        self.assertIsNone(cleanup['result']['final_success'])

    def test_unknown_focus_stays_unknown_with_seed257_and_genuine_8192_controller(self):
        from state_update_worker_fixture_p144 import fixture
        result=fixture(mode='threshold_delta_object',actions=('echo',)*6,summary_mode='unknown')
        self.assertEqual(result['captured'][-1]['role'],'focus')
        self.assertEqual(result['result']['model_seed'],257)
        self.assertEqual(result['result']['unknown_usage_calls'],1)
        self.assertIsNone(result['result']['final_success'])
        self.assertTrue(result['result']['cleanup_confirmed'])

    def _started_attempt_failure(self, failed_stage):
        pre,_=self.prepare();driver.activate(self.storage,self.root)
        number,mode=run_order()[0];rid=cell_id(number,mode)
        result=dict(run_id=rid,task_id=self.prepared[0]['task_id'],arm='synthetic',
            checkpoint_representation_mode=mode,time_visibility='not_exposed',checkpoint_policy='rolling_separate',
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
        from inspect_whole_task_object_timing_session_p141 import attempt_time_totals
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




if __name__ == "__main__": unittest.main()
