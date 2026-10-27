"""P142 launch/closure boundaries with handwritten I/O stubs only."""
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
import run_whole_task_threshold_object_p142 as driver
import run_whole_task_threshold_object_cell_p142 as worker
from whole_task_threshold_object_p142 import (MODES, fixed_fields, run_order, cell_id, config_for,
                                            initial_conversation, make_notification)
from whole_task_rolling_checkpoint import config_for as prior_config
from whole_task_object_timing_p141 import run_order as previous_order, cell_id as previous_id
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
        write(self.storage/'records/context_pilot/P142_preflight_v01/status.json', pre)
        return driver.validate_preflight(self.storage,self.root,pre,self.plan,self.original,self.prepared)

    def test_all_eight_initial_inputs_match_seed157_and_two_modes(self):
        self.assertEqual(len(run_order()), 8)
        self.assertEqual(len(set(run_order())), 8)
        for task in self.plan['known_tasks']:
            old = prior_config(self.original,self.prior,task['task_id'],'rolling_separate')
            old['seed']=157
            messages,_ = initial_conversation(self.original,{'instruction':'Synthetic only.'}).for_model()
            def request(config, mode):
                supplied,_=make_notification(messages,task_snapshot(config,[],0,0),mode,wall_limit=1800)
                cfg={**config['model'],'temperature':config['agent_temperature'],'seed':config['seed'],
                     'num_predict':config['max_output_tokens'],'cache_prompt':False}
                return payload_for(cfg,supplied,CODE_TOOLS)
            for mode in MODES:
                config=config_for(self.original,self.plan,task['task_id'],mode)
                self.assertEqual(request(config,mode),request(old,MODES[0]))
                self.assertEqual(config['seed'],157)

    def test_exact_fourteen_counts_saved_payloads_and_activation_once(self):
        pre,captured=self.prepare()
        self.assertEqual(len(captured),14)
        self.assertEqual((pre['input_count_requests'],pre['summary_input_count_requests']), (8,4))
        self.assertEqual(pre['representation_actor_input_count_requests'],2)
        for start in range(0,8,2):
            self.assertEqual(captured[start],captured[start+1])
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
                 ('all_eight_inputs_checked',1),('summary_input_count_requests',2),
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
        path=self.storage/'records/context_pilot/P142_preflight_v01'/(
            self.prepared[0]['source_run']+'_threshold_recursive_request_private.json')
        value=driver.read(path);value['seed']=999;write(path,value)
        with self.assertRaisesRegex(ValueError,'payload_changed'):self.validate(pre)

    def test_saved_activation_exact_phase_all_three_source_and_head(self):
        pre,_=self.prepare();driver.activate(self.storage,self.root)
        freeze=driver.read(self.root/driver.ACTIVATION)
        for key,value in [('phase','P140'),('all_eight_conditions_frozen_before_generation',False),
                          ('git_commit','c'*40),('source_hashes',{}),('preflight_sha256','f'*64),
                          ('research_resume',{})]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                driver.validate_activation(self.storage,self.root,{**freeze,key:value},pre)

    def test_explicit_stop_and_unclosed_predecessor_precede_native_contact(self):
        marker=self.storage/'.runtime/P142.stop';marker.parent.mkdir();marker.touch()
        with patch.object(driver,'sources') as sources,patch.object(driver,'live_identity') as live:
            with self.assertRaises(InterruptedError):driver.preflight(self.storage,self.root)
            sources.assert_not_called();live.assert_not_called()
        marker.unlink()
        with patch.object(driver,'check_resume',return_value={}), \
             patch.object(driver,'sources',side_effect=ValueError('unclosed')), \
             patch.object(driver,'count_input') as count,patch.object(driver,'live_identity') as live:
            with self.assertRaisesRegex(ValueError,'unclosed'):driver.preflight(self.storage,self.root)
            count.assert_not_called();live.assert_not_called()
        self.assertFalse((self.storage/'records/context_pilot/P142_preflight_v01').exists())

    def predecessor(self):
        folder=self.storage/'records/context_pilot/P141_pipeline_v01'
        final={'status':'stopped','pid':124,'supervisor_pid':123}
        state={'status':'complete','server_stopped':True,'server_supervisor_pid':123}
        write(folder/'status.json',state);write(folder/'server_final.json',final)
        audit={'phase':'P141','audit_errors':[],'owned_processes_absent':True,
               'rows':[{'run_id':previous_id(*slot),'record_status':'evaluated','success':False}
                       for slot in previous_order()],
               'pipeline_status_sha256':driver.sha(folder/'status.json'),
               'server_final_sha256':driver.sha(folder/'server_final.json')}
        write(self.root/'reports/P141_comparison.json',audit)
        session={'phase':'P141','status':'stopped','owned_processes_absent':True,
                 'audit_source_sha256':driver.sha(self.root/'reports/P141_comparison.json')}
        write(self.root/'reports/P141_server_session.json',session)
        return folder,audit,session,final

    def test_all_three_evaluated_predecessor_is_allowed_but_false_zero_duplicate_or_live_pid_rejected(self):
        folder,audit,session,final=self.predecessor()
        with patch.object(driver.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')):
            proof=driver.predecessor_closed(self.storage,self.root)
            self.assertEqual(proof['session_sha256'],driver.sha(self.root/'reports/P141_server_session.json'))
            for change in ({'audit_errors':False},{'audit_errors':0},{'audit_errors':['synthetic error']},
                           {'rows':audit['rows'][:-1]+[audit['rows'][0]]}):
                changed={**audit,**change};write(self.root/'reports/P141_comparison.json',changed)
                write(self.root/'reports/P141_server_session.json',{**session,'audit_source_sha256':driver.sha(self.root/'reports/P141_comparison.json')})
                with self.assertRaises(ValueError):driver.predecessor_closed(self.storage,self.root)
            self.predecessor();write(folder/'server_final.json',{**final,'pid':True})
            current=driver.read(self.root/'reports/P141_comparison.json');current['server_final_sha256']=driver.sha(folder/'server_final.json')
            write(self.root/'reports/P141_comparison.json',current)
            write(self.root/'reports/P141_server_session.json',{**session,'audit_source_sha256':driver.sha(self.root/'reports/P141_comparison.json')})
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
        from threshold_object_worker_fixture_p142 import fixture
        for stage in ('bridge','session'):
            with self.subTest(stage=stage):
                result=fixture(constructor_error=stage)
                row=result['result']
                self.assertEqual(row['phase'],'P142');self.assertEqual(row['model_seed'],157)
                self.assertEqual(row['stop_reason'],'setup_failure');self.assertEqual(result['captured'],[])
                self.assertFalse(row['cleanup_confirmed']);self.assertIsNone(row['final_success'])
                self.assertIn('summary',result['saved'])

    def test_local_setup_and_cleanup_deadlines_preserve_failed_attempt(self):
        from threshold_object_worker_fixture_p142 import fixture
        setup=fixture(setup_delay=61)
        self.assertEqual(setup['result']['stop_reason'],'setup_failure')
        self.assertEqual(setup['captured'],[])
        cleanup=fixture(actions=('finish',),cleanup_delay=61)
        self.assertFalse(cleanup['result']['cleanup_confirmed'])
        self.assertEqual(cleanup['result']['stop_reason'],'cleanup_error')
        self.assertEqual(cleanup['result']['model_calls'],1)
        self.assertGreater(cleanup['result']['known_total_tokens'],0)
        self.assertIsNone(cleanup['result']['final_success'])

    def test_unknown_focus_stays_unknown_with_new_seed_and_unchanged_controller(self):
        from threshold_object_worker_fixture_p142 import fixture
        result=fixture(mode='threshold_delta_object',actions=('echo',)*6,summary_mode='unknown')
        self.assertEqual(result['captured'][-1]['role'],'focus')
        self.assertEqual(result['result']['model_seed'],157)
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
