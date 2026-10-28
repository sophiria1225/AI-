"""Synthetic P146 gating, fixed-cohort accounting and owned-cleanup tests.

No live model, tokenizer, task API, evaluator or subprocess is invoked.
"""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run_schema_update_p146 as driver
import schema_update_server_p146 as server_contract
from run_update_transport_p145 import schedule as diagnostic_schedule


def good_rows():
    return [dict(run_id=driver.cell_id(n,m),task_id=driver.TASKS[n-1],task_slot=n,mode=m,
        comparison_arm='TR' if m==driver.MODES[0] else 'UPDATE_SCHEMA',
        known_total_tokens=100 if m==driver.MODES[0] else 90,unknown_usage_calls=0,
        model_calls=2,api_requests=2,usage_coverage_known=True,
        success=True,cleanup_confirmed=True,actual_changed_old_known_actor_calls=int(m==driver.MODES[1]))
        for n,m in driver.run_order()]


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value)+'\n')


class SummaryTests(unittest.TestCase):
    def test_all_eight_fixed_cells_and_changed_candidate_support_observed_gain_only(self):
        result=driver.summarize(good_rows(),'complete')
        self.assertTrue(result['all_eight_evaluated_known_usage'])
        self.assertEqual(result['total_tokens_by_mode'],dict(zip(driver.MODES,[400,360])))
        self.assertEqual(result['paired_successful_token_difference'],-40)
        self.assertTrue(result['development_gate_met'])
        self.assertFalse(result['novelty_established'])
        self.assertFalse(result['general_quality_preservation_established'])
        self.assertFalse(result['selected_candidate_from_P145_results'])

    def test_unknown_usage_missing_row_unevaluated_or_unclean_never_become_exact_totals(self):
        variants=[]
        rows=good_rows();rows[-1]['unknown_usage_calls']=1;variants.append(rows)
        rows=good_rows();rows[-1].pop('success');variants.append(rows)
        rows=good_rows();rows[-1]['cleanup_confirmed']=False;variants.append(rows)
        variants.append(good_rows()[:-1])
        for rows in variants:
            with self.subTest(rows=rows):
                result=driver.summarize(rows,'complete')
                self.assertFalse(result['all_eight_evaluated_known_usage'])
                self.assertFalse(result['development_gate_met'])
                self.assertTrue(all(v is None for v in result['total_tokens_by_mode'].values()))
                self.assertTrue(all(p['difference'] is None for p in result['paired_results']))
        stopped=driver.summarize(good_rows(),'stopped')
        self.assertFalse(stopped['all_eight_evaluated_known_usage'])

    def test_success_loss_or_no_common_success_or_no_changed_candidate_blocks_gain(self):
        for kind in ('success_loss','no_common','unchanged_candidate','more_cost','zero_cost_difference'):
            rows=good_rows()
            for row in rows:
                if kind=='success_loss' and row['mode']==driver.MODES[1]:row['success']=False
                if kind=='no_common':row['success']=False
                if kind=='unchanged_candidate' and row['mode']==driver.MODES[1]:
                    row['actual_changed_old_known_actor_calls']=0
                if kind in ('more_cost','zero_cost_difference') and row['mode']==driver.MODES[1]:
                    row['known_total_tokens']=101 if kind=='more_cost' else 100
            with self.subTest(kind=kind):
                self.assertFalse(driver.summarize(rows,'complete')['development_gate_met'])

    def test_savings_only_on_failed_tasks_do_not_count_as_successful_utility(self):
        rows=good_rows()
        for row in rows:
            if row['task_slot']==4:
                row['success']=False
                row['known_total_tokens']=1000 if row['mode']==driver.MODES[0] else 1
            elif row['mode']==driver.MODES[1]:row['known_total_tokens']=110
        result=driver.summarize(rows,'complete')
        self.assertGreater(result['paired_successful_token_difference'],0)
        self.assertFalse(result['development_gate_met'])

    def test_exact_ids_do_not_mask_wrong_mode_task_mapping_or_noninteger_usage(self):
        for field,value in [('task_id','wrong'),('task_slot',4),('mode',driver.MODES[1]),
                ('comparison_arm','UPDATE_SCHEMA'),('unknown_usage_calls',False),
                ('known_total_tokens',True),('known_total_tokens',-1),('known_total_tokens',1.5)]:
            rows=good_rows();rows[0][field]=value
            with self.subTest(field=field,value=value):
                result=driver.summarize(rows,'complete')
                self.assertFalse(result['all_eight_evaluated_known_usage'])
                self.assertFalse(result['development_gate_met'])


class PredecessorTests(unittest.TestCase):
    def fixture(self,storage):
        pipeline=dict(status='complete',server_stopped=True,plan_sha256='a'*64,server_supervisor_pid=71)
        final=dict(status='stopped',supervisor_pid=71,pid=72)
        rows=[dict(task_slot=n,arm=arm,status='ok',usage_verified=True,finished_at='synthetic',
            input_tokens=100,output_tokens=10,model_dispatched=True,patch_valid=True,
            shorter_full_actor_input=True,changed_old_items=1,old_state_changed=True)
            for n,arm in diagnostic_schedule()]
        batch=dict(status='complete',rows=rows)
        p=storage/'records/context_pilot/P145_pipeline_v01'
        write(p/'status.json',pipeline);write(p/'server_final.json',final)
        write(storage/'records/context_pilot/P145_replay_v01/status.json',batch)
        return pipeline,final,batch

    def test_closed_fixed_candidate_gate_is_recomputed_before_successor(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp);self.fixture(storage)
            with patch.object(driver.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')) as ps:
                value=driver.predecessor(storage,dict(required_P145_plan_sha256='a'*64))
            self.assertTrue(value['gate']['mechanism_preflight_passed']);self.assertEqual(ps.call_count,2)

    def test_gate_failure_incomplete_close_changed_plan_or_live_owner_is_rejected(self):
        for kind in ('candidate_failed','batch_stopped','pipeline_running','server_live','plan_changed','owner_changed','pid_live'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                storage=Path(tmp);state,final,batch=self.fixture(storage)
                if kind=='candidate_failed':
                    for r in batch['rows']:
                        if r['arm']=='schema_bounded':r['patch_valid']=False
                if kind=='batch_stopped':batch['status']='stopped'
                if kind=='pipeline_running':state['status']='batch'
                if kind=='server_live':state['server_stopped']=False
                if kind=='plan_changed':state['plan_sha256']='b'*64
                if kind=='owner_changed':final['supervisor_pid']=99
                p=storage/'records/context_pilot/P145_pipeline_v01'
                write(p/'status.json',state);write(p/'server_final.json',final)
                write(storage/'records/context_pilot/P145_replay_v01/status.json',batch)
                fake=SimpleNamespace(returncode=0,stdout='71') if kind=='pid_live' else SimpleNamespace(returncode=1,stdout='')
                with patch.object(driver.subprocess,'run',return_value=fake),self.assertRaises(ValueError):
                    driver.predecessor(storage,dict(required_P145_plan_sha256='a'*64))


class BatchTests(unittest.TestCase):
    def run_batch(self,kind):
        stages=[]
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp);(storage/'records/context_pilot').mkdir(parents=True)
            if kind=='explicit_stop':
                (storage/'.runtime').mkdir();(storage/'.runtime/P146.stop').touch()
            if kind=='old_output':
                (storage/'records/context_pilot'/driver.cell_id(*driver.run_order()[0])).mkdir()
            def bounded(command,log,record,save,timeout,**kwargs):
                stages.append(command)
                rid=record['run_id'];trial=storage/'records/context_pilot'/rid
                record.update(status='exited',returncode=0);save()
                if '--cell' in command:
                    n=int(command[command.index('--cell')+1]);mode=command[command.index('--arm')+1]
                    result=dict(run_id=rid,task_id=driver.TASKS[n-1],stop_reason='agent_declared_complete',
                        model_calls=2,known_total_tokens=100 if mode==driver.MODES[0] else 90,
                        unknown_usage_calls=0,api_requests=2,cleanup_confirmed=True,
                        setup={'status':'initial_public_state_matched'},unknown_effect_requests=0,
                        state_update_control={'actual_changed_old_known_actor_calls':int(mode==driver.MODES[1])})
                    if kind=='unknown_first' and len(stages)==1:
                        result.update(unknown_usage_calls=1,stop_reason='model_usage_unknown')
                    if kind=='cleanup_failure' and len(stages)==1:
                        result.update(cleanup_confirmed=False,stop_reason='cleanup_error')
                    write(trial/'summary.json',result)
                    if kind=='worker_failed_after_summary':
                        record['returncode']=1;save()
                        raise RuntimeError('synthetic nonzero worker; summary already saved')
                else:
                    if kind=='evaluation_failure':raise RuntimeError('synthetic evaluator failure')
                    write(trial/'evaluation.json',{'official_success':True})
            end=datetime.now(timezone.utc)+timedelta(seconds=30 if kind=='short_lease' else 18000)
            with patch.object(driver,'bounded_process',side_effect=bounded), \
                 patch.object(driver,'live_identity',return_value=({'owned':True},end.isoformat())), \
                 patch.object(driver,'wait_idle',return_value={'one_slot_idle':True}),redirect_stdout(io.StringIO()):
                result=driver.batch(storage,ROOT,{}, {},{'owned':True},end.isoformat())
            saved=json.loads((storage/driver.BATCH/'status.json').read_text());self.assertEqual(saved,result)
            return result,stages

    def test_all_eight_run_once_and_unknown_usage_does_not_create_free_retry(self):
        for kind in ('good','unknown_first'):
            with self.subTest(kind=kind):
                result,stages=self.run_batch(kind)
                self.assertEqual(len(stages),16);self.assertEqual(result['status'],'complete')
                self.assertEqual(result['completed'],[driver.cell_id(n,m) for n,m in driver.run_order()])
                self.assertEqual(len(result['rows']),8)
                if kind=='unknown_first':
                    self.assertFalse(result['all_eight_evaluated_known_usage'])
                    self.assertTrue(all(v is None for v in result['total_tokens_by_mode'].values()))
                    self.assertEqual(result['rows'][0]['unknown_usage_calls'],1)

    def test_explicit_stop_short_lease_and_existing_output_never_dispatch(self):
        for kind in ('explicit_stop','short_lease','old_output'):
            with self.subTest(kind=kind):
                result,stages=self.run_batch(kind)
                self.assertEqual(stages,[]);self.assertEqual(result['status'],'stopped')
                self.assertFalse(result['development_gate_met'])

    def test_worker_cleanup_and_evaluation_failure_stop_without_next_condition(self):
        for kind,count in [('cleanup_failure',1),('evaluation_failure',2)]:
            with self.subTest(kind=kind):
                result,stages=self.run_batch(kind)
                self.assertEqual(len(stages),count);self.assertEqual(result['status'],'stopped')
                self.assertEqual(len(result['rows']),1)
                self.assertEqual(result['rows'][0]['known_total_tokens'],100)
                self.assertFalse(result['development_gate_met'])

    def test_nonzero_worker_preserves_its_already_saved_paid_summary(self):
        result,stages=self.run_batch('worker_failed_after_summary')
        self.assertEqual(len(stages),1);self.assertEqual(result['status'],'stopped')
        self.assertEqual(len(result['rows']),1)
        self.assertEqual(result['rows'][0]['known_total_tokens'],100)
        self.assertEqual(result['known_token_subtotals'][driver.MODES[0]],100)
        self.assertFalse(result['development_gate_met'])

    def test_partial_worker_ledger_retains_known_cost_and_missing_terminal_as_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial=Path(tmp)
            admissions=[dict(next_call_id='call_001',role='agent',model_request_started=True),
                        dict(next_call_id='call_002',role='focus',model_request_started=True)]
            terminal=[dict(id='call_001',role='agent',status='ok',input_tokens=100,output_tokens=20)]
            write(trial/'admissions.json',admissions);write(trial/'usage.json',terminal)
            row=dict(run_id='synthetic',task_id='synthetic',known_total_tokens=0)
            driver.retain_worker_attempt(trial,row,dict(status='exited',returncode=1))
            self.assertTrue(row['usage_coverage_known']);self.assertEqual(row['known_total_tokens'],120)
            self.assertEqual(row['unknown_usage_calls'],1);self.assertEqual(row['model_calls'],2)
            self.assertEqual(row['disposition'],'stop_batch')

    def test_foreign_summary_identity_cannot_supply_paid_success_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial=Path(tmp);write(trial/'summary.json',{'run_id':'foreign','task_id':'foreign'})
            row=dict(run_id='expected',task_id='expected',known_total_tokens=0)
            driver.retain_worker_attempt(trial,row,dict(status='exited',returncode=1))
            self.assertFalse(row['usage_coverage_known']);self.assertEqual(row['known_total_tokens'],0)
            self.assertEqual(row['disposition'],'stop_batch')


class CleanupTests(unittest.TestCase):
    def test_failure_reading_server_final_does_not_skip_caffeinate_or_terminal_status(self):
        class Process:
            def __init__(self,pid):self.pid=pid;self.returncode=None;self.terminated=False
            def poll(self):return self.returncode
            def terminate(self):self.terminated=True;self.returncode=0
            def wait(self,timeout):return self.returncode
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp);root=storage/'source';(root/'reports').mkdir(parents=True)
            write(root/driver.PLAN,{'synthetic':True});(storage/'records/context_pilot').mkdir(parents=True)
            server,caffeinate=Process(72),Process(71)
            runtime=dict(supervisor_pid=72,status='ready',record_directory='records/p2_servers/synthetic')
            original_read=driver.read
            def read(path):
                if str(path).endswith('.runtime/model_server.json'):
                    if server.terminated:raise ValueError('synthetic final runtime read failure')
                    return runtime
                return original_read(path)
            head='a'*40
            plan={'latest_launch_jst':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}
            with patch.object(driver.subprocess,'check_output',side_effect=[head+'\n','']), \
                 patch.object(driver,'sources',return_value=(plan,{'model_selection':'synthetic'},[],[])), \
                 patch.object(driver,'predecessor',return_value={}),patch.object(driver,'checked_ci',return_value={}), \
                 patch.object(driver.subprocess,'Popen',side_effect=[caffeinate,server]), \
                 patch.object(driver,'read',side_effect=read), \
                 patch.object(driver,'live_identity',return_value=({},'synthetic')), \
                 patch.object(driver,'preflight',side_effect=RuntimeError('synthetic preflight failure')):
                result=driver.run(storage,root,head)
            self.assertEqual(result,1);self.assertTrue(server.terminated);self.assertTrue(caffeinate.terminated)
            state=original_read(storage/driver.PIPELINE/'status.json')
            self.assertEqual(state['status'],'stopped');self.assertIn('finished_at',state)
            self.assertFalse(state['server_stopped'])
            self.assertTrue(state.get('cleanup_errors'))

    def test_failed_cleanup_cannot_publish_a_complete_or_qualifying_result(self):
        class Process:
            def __init__(self,pid):self.pid=pid;self.returncode=None
            def poll(self):return self.returncode
            def terminate(self):self.returncode=0
            def wait(self,timeout):return self.returncode
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp);root=storage/'source';(root/'reports').mkdir(parents=True)
            write(root/driver.PLAN,{'synthetic':True});(storage/'records/context_pilot').mkdir(parents=True)
            server,caffeinate=Process(72),Process(71)
            runtime=dict(supervisor_pid=72,status='ready',record_directory='records/p2_servers/synthetic')
            original_read=driver.read
            def read(path):
                return runtime if str(path).endswith('.runtime/model_server.json') else original_read(path)
            head='a'*40
            plan={'latest_launch_jst':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}
            def cleanup(server,caffeinate,storage,out,state):
                state.update(status='stopped',server_stopped=False,cleanup_errors=['synthetic'],finished_at='synthetic')
                write(out/'status.json',state)
            with patch.object(driver.subprocess,'check_output',side_effect=[head+'\n','']), \
                 patch.object(driver,'sources',return_value=(plan,{'model_selection':'synthetic'},[],[])), \
                 patch.object(driver,'predecessor',return_value={}),patch.object(driver,'checked_ci',return_value={}), \
                 patch.object(driver.subprocess,'Popen',side_effect=[caffeinate,server]), \
                 patch.object(driver,'read',side_effect=read),patch.object(driver,'preflight'), \
                 patch.object(driver,'live_identity',return_value=({},'synthetic')), \
                 patch.object(driver,'batch',return_value={'status':'complete','rows':good_rows()}), \
                 patch.object(driver,'cleanup_owned',side_effect=cleanup):
                self.assertEqual(driver.run(storage,root,head),1)
            report=original_read(root/'reports/P146_comparison.json')
            self.assertEqual(report['status'],'stopped')
            self.assertFalse(report['development_gate_met'])
            self.assertFalse(report['server_stopped'])

    def test_cleanup_fallback_targets_only_owned_group_and_owned_caffeinate(self):
        class Process:
            def __init__(self,pid):self.pid=pid;self.returncode=None;self.killed=False
            def poll(self):return self.returncode
            def terminate(self):raise OSError('synthetic terminate failure')
            def wait(self,timeout):return self.returncode
            def kill(self):self.killed=True;self.returncode=-9
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp);out=storage/'out';out.mkdir()
            server,caffeinate=Process(71),Process(72)
            write(storage/'.runtime/model_server.json',dict(supervisor_pid=71,status='stopped'))
            state=dict(status='complete',server_stopped=False)
            def killpg(pid,sig):
                self.assertEqual(pid,server.pid);server.returncode=-9
            with patch.object(driver.os,'killpg',side_effect=killpg) as kill:
                driver.cleanup_owned(server,caffeinate,storage,out,state)
            kill.assert_called_once();self.assertTrue(caffeinate.killed)
            self.assertEqual(state['status'],'stopped');self.assertTrue(state['caffeinate_stopped'])
            self.assertTrue(state['cleanup_errors']);self.assertIn('finished_at',state)


class ServerOwnershipTests(unittest.TestCase):
    def test_foreign_owner_or_lease_cannot_authenticate_a_new_server(self):
        now=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp).resolve()
            original=dict(model_selection='synthetic',model={'num_ctx':65536})
            runtime=dict(supervisor_pid=71,pid=72,record_directory='records/p2_servers/synthetic',
                started_at=(now-timedelta(seconds=2)).isoformat())
            owner=dict(phase='P146_pipeline',status='batch',server_owned=True,server_supervisor_pid=71,
                server_record_directory=runtime['record_directory'])
            command=f'/usr/bin/python {ROOT / server_contract.SUPERVISOR} --storage-root {storage} --selection synthetic --ctx-size 65536 --cache-type-k q8_0 --cache-type-v q8_0 --max-seconds 18000'
            remaining,_=server_contract.owned_lease(runtime,command,now,storage=storage,source_plan=original,owner=owner)
            self.assertEqual(remaining,17998)
            for modified,cmd in [({**owner,'phase':'P145_pipeline'},command),
                    ({**owner,'server_supervisor_pid':99},command),
                    (owner,command.replace('--max-seconds 18000','--max-seconds 8100'))]:
                with self.assertRaises(ValueError):
                    server_contract.owned_lease(runtime,cmd,now,storage=storage,source_plan=original,owner=modified)


if __name__=='__main__':unittest.main()
