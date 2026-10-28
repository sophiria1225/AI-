"""Synthetic two-stage P147 dispatch/accounting/lifecycle tests.

Only temporary synthetic data are used. Every model/network/process boundary is
mocked; no saved private request, model, tokenizer, task API, or evaluator runs.
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
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
import run_indexed_update_p147 as driver
import indexed_update_server_p147 as server_contract
from run_update_transport_p145 import schedule as diagnostic_schedule
from test_checkpoint_update_schema_p145 import request as saved_request, old_state
from test_checkpoint_indexed_update_p147 import keep_all, message

def good_rows():
    return [dict(run_id=driver.cell_id(n,m),task_id=driver.TASKS[n-1],task_slot=n,mode=m,
        comparison_arm='TR' if m==driver.MODES[0] else 'UPDATE_INDEXED',
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
                ('comparison_arm','UPDATE_INDEXED'),('unknown_usage_calls',False),
                ('known_total_tokens',True),('known_total_tokens',-1),('known_total_tokens',1.5)]:
            rows=good_rows();rows[0][field]=value
            with self.subTest(field=field,value=value):
                result=driver.summarize(rows,'complete')
                self.assertFalse(result['all_eight_evaluated_known_usage'])
                self.assertFalse(result['development_gate_met'])

class BatchTests(unittest.TestCase):
    def run_batch(self,kind):
        stages=[]
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp);(storage/'records/context_pilot').mkdir(parents=True)
            if kind=='explicit_stop':
                (storage/'.runtime').mkdir();(storage/'.runtime/P147.stop').touch()
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

    def test_all_eight_fixed_tasks_run_once_after_the_probe_gate(self):
        result,stages=self.run_batch('good')
        self.assertEqual(len(stages),16);self.assertEqual(result['status'],'complete')
        self.assertEqual(result['completed'],[driver.cell_id(n,m) for n,m in driver.run_order()])
        self.assertEqual(len(result['rows']),8)
        self.assertEqual(len({r['run_id'] for r in result['rows']}),8)

    def test_unknown_usage_stops_later_model_dispatch_without_a_free_retry(self):
        result,stages=self.run_batch('unknown_first')
        self.assertEqual(len([s for s in stages if '--cell' in s]),1)
        self.assertEqual(result['status'],'stopped')
        self.assertEqual(len(result['rows']),1)
        self.assertEqual(result['rows'][0]['unknown_usage_calls'],1)
        self.assertEqual(result['rows'][0]['known_total_tokens'],100)
        self.assertTrue(all(v is None for v in result['total_tokens_by_mode'].values()))
        self.assertFalse(result['development_gate_met'])

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

class ServerOwnershipTests(unittest.TestCase):
    def test_foreign_owner_or_lease_cannot_authenticate_a_new_server(self):
        now=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp).resolve()
            original=dict(model_selection='synthetic',model={'num_ctx':65536})
            runtime=dict(supervisor_pid=71,pid=72,record_directory='records/p2_servers/synthetic',
                started_at=(now-timedelta(seconds=2)).isoformat())
            owner=dict(phase='P147_pipeline',status='batch',server_owned=True,server_supervisor_pid=71,
                server_record_directory=runtime['record_directory'])
            command=f'/usr/bin/python {ROOT / server_contract.SUPERVISOR} --storage-root {storage} --selection synthetic --ctx-size 65536 --cache-type-k q8_0 --cache-type-v q8_0 --max-seconds 21600'
            remaining,_=server_contract.owned_lease(runtime,command,now,storage=storage,source_plan=original,owner=owner)
            self.assertEqual(remaining,21598)
            for status in ('probe','preflight','batch'):
                with self.subTest(status=status):
                    remaining,_=server_contract.owned_lease(runtime,command,now,storage=storage,source_plan=original,owner={**owner,'status':status})
                    self.assertEqual(remaining,21598)
            for modified,cmd in [({**owner,'phase':'P145_pipeline'},command),
                    ({**owner,'server_supervisor_pid':99},command),
                    (owner,command.replace('--max-seconds 21600','--max-seconds 8100'))]:
                with self.assertRaises(ValueError):
                    server_contract.owned_lease(runtime,cmd,now,storage=storage,source_plan=original,owner=modified)


def probe_rows():
    return [dict(task_slot=n,status='ok',usage_verified=True,finished_at='synthetic',
        input_tokens=100,output_tokens=10,model_dispatched=True,patch_valid=True,
        shorter_full_actor_input=True,changed_old_items=int(n==2),old_state_changed=n==2)
        for n in (1,2,4)]


class PredecessorTests(unittest.TestCase):
    def fixture(self,storage,kind):
        pipeline=dict(status='complete',server_stopped=True,plan_sha256='a'*64,server_supervisor_pid=71)
        final=dict(status='stopped',supervisor_pid=71,pid=72)
        rows=[dict(task_slot=n,arm=arm,status='ok',usage_verified=True,finished_at='synthetic',
            input_tokens=100,output_tokens=10,model_dispatched=True,patch_valid=False,
            shorter_full_actor_input=False,changed_old_items=0,old_state_changed=False)
            for n,arm in diagnostic_schedule()]
        batch=dict(status='complete',rows=rows)
        if kind=='eleven_only':batch['rows']=rows[:11]
        if kind=='three_only':batch['rows']=rows[:3]
        if kind=='duplicate_row':batch['rows'][-1]=deepcopy(rows[0])
        if kind=='batch_running':batch['status']='running'
        if kind=='pipeline_running':pipeline['status']='batch'
        if kind=='unknown':rows[-1]['status']='unknown'
        if kind=='usage_unverified':rows[-1]['usage_verified']=False
        if kind=='row_unfinished':rows[-1].pop('finished_at')
        if kind=='server_live':pipeline['server_stopped']=False
        if kind=='plan_changed':pipeline['plan_sha256']='b'*64
        if kind=='owner_changed':final['supervisor_pid']=99
        p=storage/'records/context_pilot/P145_pipeline_v01'
        write(p/'status.json',pipeline);write(p/'server_final.json',final)
        write(storage/'records/context_pilot/P145_replay_v01/status.json',batch)

    def test_twelve_closed_failed_parser_results_allow_the_new_diagnostic_not_adoption(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp);self.fixture(storage,'closed_failures')
            with patch.object(driver.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')) as ps:
                result=driver.predecessor(storage,dict(required_P145_plan_sha256='a'*64))
            self.assertFalse(result['gate']['mechanism_preflight_passed'])
            self.assertEqual(ps.call_count,2)

    def test_incomplete_unknown_wrong_schedule_or_live_predecessor_rejects(self):
        for kind in ('eleven_only','three_only','duplicate_row','batch_running','pipeline_running',
                     'unknown','usage_unverified','row_unfinished','server_live','plan_changed',
                     'owner_changed','pid_live'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                storage=Path(tmp);self.fixture(storage,kind)
                fake=SimpleNamespace(returncode=0,stdout='71') if kind=='pid_live' else SimpleNamespace(returncode=1,stdout='')
                with patch.object(driver.subprocess,'run',return_value=fake),self.assertRaises((ValueError,TypeError)):
                    driver.predecessor(storage,dict(required_P145_plan_sha256='a'*64))


class ProbeGateTests(unittest.TestCase):
    def test_exact_three_slots_known_valid_shorter_with_a_real_old_change_pass(self):
        value=driver.probe_gate(probe_rows(),'complete')
        self.assertTrue(value['probe_gate_passed']);self.assertTrue(value['probe_all_three_complete_known'])
        self.assertEqual(value['known_total_tokens'],330);self.assertEqual(value['unknown_usage_calls'],0)
        self.assertFalse(value['whole_task_savings_established']);self.assertFalse(value['task_success_evaluated'])

    def test_invalid_usage_types_ranges_or_output_cap_never_pass_the_probe(self):
        for field,value in [('input_tokens',True),('input_tokens',0),('input_tokens',-1),
                ('input_tokens',100.5),('input_tokens',None),('output_tokens',True),
                ('output_tokens',-1),('output_tokens',4097),('output_tokens',None)]:
            rows=probe_rows();rows[0][field]=value
            with self.subTest(field=field,value=value):
                result=driver.probe_gate(rows,'complete')
                self.assertFalse(result['probe_gate_passed'])
                self.assertFalse(result['probe_all_three_complete_known'])

    def test_any_incomplete_or_nonqualifying_probe_blocks_full_stage(self):
        for kind in ('missing','duplicate','reordered','all_twelve','unverified','unknown','unfinished',
                     'parse_reject','not_shorter','only_additions','no_materialized_change','stopped'):
            rows=probe_rows();status='complete'
            if kind=='missing':rows=rows[:2]
            if kind=='duplicate':rows[2]=deepcopy(rows[0])
            if kind=='reordered':rows=rows[::-1]
            if kind=='all_twelve':rows=rows*4
            if kind=='unverified':rows[0]['usage_verified']=False
            if kind=='unknown':rows[0].update(status='unknown',input_tokens=None,output_tokens=None)
            if kind=='unfinished':rows[0].pop('finished_at')
            if kind=='parse_reject':rows[0]['patch_valid']=False
            if kind=='not_shorter':rows[0]['shorter_full_actor_input']=False
            if kind=='only_additions':rows[1]['changed_old_items']=0
            if kind=='no_materialized_change':rows[1]['old_state_changed']=False
            if kind=='stopped':status='stopped'
            with self.subTest(kind=kind):self.assertFalse(driver.probe_gate(rows,status)['probe_gate_passed'])


class ProbeExecutionTests(unittest.TestCase):
    def run_probe(self,kind):
        old=old_state();saved=saved_request(old)
        packet=json.loads(saved['messages'][1]['content'])
        packet['original_instructions_and_task']=[dict(role='system',content='synthetic task')]
        saved['messages'][1]['content']=json.dumps(packet)
        ordinary=dict(messages=packet['original_instructions_and_task']+
            [dict(role='user',content='ordinary full history'),dict(role='user',content='<budget>')])
        data={n:dict(old=deepcopy(old),saved=deepcopy(saved),packet=deepcopy(packet),ordinary=deepcopy(ordinary)) for n in (1,2,4)}
        payloads=[];counts=[]
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp);(storage/'records/context_pilot').mkdir(parents=True)
            if kind=='explicit_stop':
                (storage/'.runtime').mkdir();(storage/'.runtime/P147.stop').touch()
            def count(req):
                counts.append(deepcopy(req))
                if 'response_format' in req:return 45000 if kind=='reservation' else 100
                if kind=='actor_count_failure':raise ValueError('synthetic actor count failure')
                return 200 if req['messages'][1]['content']=='ordinary full history' else 150
            def post(base,endpoint,request,timeout):
                self.assertEqual(endpoint,'/v1/chat/completions');self.assertEqual(timeout,480)
                self.assertEqual(request['max_tokens'],4096);self.assertEqual(request['reasoning_budget_tokens'],2048)
                payloads.append(deepcopy(request))
                if kind=='unknown_first' or (kind=='unknown_second' and len(payloads)==2):
                    raise TimeoutError('synthetic generation timeout')
                if kind=='stop_after_first':
                    (storage/'.runtime').mkdir(exist_ok=True);(storage/'.runtime/P147.stop').touch()
                value=keep_all(old)
                if kind!='no_change':value['usable_state']['by_index']['1']={'action':'update','text':'updated'}
                msg=message(value)
                if kind=='parse_reject':msg={'role':'assistant','content':'[]'}
                return dict(status='ok',input_tokens=101 if kind=='usage_mismatch' else 100,
                    output_tokens=10,cached_input_tokens=0,done_reason='stop',message=msg)
            original_payload=driver.indexed_payload
            calls=0
            def payload(saved,old):
                nonlocal calls
                calls+=1;result=original_payload(saved,old)
                if kind=='payload_changed' and calls>3:result['seed']+=1
                return result
            with patch.object(driver,'native_count',side_effect=count), \
                 patch.object(driver,'post',side_effect=post),patch.object(driver,'parse_response',side_effect=lambda x:x), \
                 patch.object(driver,'indexed_payload',side_effect=payload), \
                 patch.object(driver,'live_identity',return_value=({'owned':True},'synthetic')), \
                 patch.object(driver,'wait_idle',side_effect=ValueError('synthetic idle failure') if kind=='idle_failure' else None), \
                 patch.object(driver.signal,'alarm'),redirect_stdout(io.StringIO()):
                result=driver.probe(storage,ROOT,{},data,{'owned':True},{},datetime.now(timezone.utc).timestamp()+3000)
            saved_state=json.loads((storage/'records/context_pilot/P147_probe_v01/status.json').read_text())
            self.assertEqual(saved_state,result)
            request_files=list((storage/'records/context_pilot/P147_probe_v01').glob('*/request_private.json'))
            self.assertEqual(len(request_files),len(payloads))
            return result,payloads,counts

    def test_three_identical_counted_payloads_dispatch_once_and_gate_is_local_only(self):
        result,payloads,counts=self.run_probe('good')
        self.assertEqual(result['status'],'complete');self.assertTrue(result['probe_gate_passed'])
        self.assertEqual([r['task_slot'] for r in result['rows']],[1,2,4])
        self.assertEqual(result['reserved_tokens'],3*(100+4096))
        self.assertEqual(result['known_total_tokens'],330);self.assertEqual(len(payloads),3)
        self.assertEqual(payloads,counts[:3]);self.assertEqual(len(counts),9)

    def test_all_three_parser_rejections_still_retain_every_paid_probe(self):
        result,payloads,_=self.run_probe('parse_reject')
        self.assertEqual(result['status'],'complete');self.assertEqual(len(payloads),3)
        self.assertEqual(result['known_total_tokens'],330);self.assertFalse(result['probe_gate_passed'])
        self.assertTrue(all(r['patch_valid'] is False for r in result['rows']))

    def test_no_actual_old_change_is_not_rescued_by_shortening(self):
        result,payloads,_=self.run_probe('no_change')
        self.assertEqual(len(payloads),3);self.assertFalse(result['probe_gate_passed'])
        self.assertTrue(all(r['shorter_full_actor_input'] for r in result['rows']))
        self.assertEqual(result['known_total_tokens'],330)

    def test_reservation_or_changed_payload_or_initial_stop_prevents_generation(self):
        for kind in ('reservation','payload_changed','explicit_stop'):
            with self.subTest(kind=kind):
                result,payloads,_=self.run_probe(kind)
                self.assertEqual(payloads,[]);self.assertEqual(result['status'],'stopped')
                self.assertFalse(result['probe_gate_passed']);self.assertEqual(result['known_total_tokens'],0)

    def test_unknown_generation_stops_later_dispatch_but_preserves_prior_cost(self):
        for kind,expected_calls,known in [('unknown_first',1,0),('unknown_second',2,110)]:
            with self.subTest(kind=kind):
                result,payloads,_=self.run_probe(kind)
                self.assertEqual(len(payloads),expected_calls);self.assertEqual(result['status'],'stopped')
                self.assertEqual(result['known_total_tokens'],known);self.assertEqual(result['unknown_usage_calls'],1)
                self.assertFalse(result['probe_gate_passed'])

    def test_stop_mismatch_idle_or_count_failure_keeps_paid_cost_and_stops(self):
        for kind in ('stop_after_first','usage_mismatch','idle_failure','actor_count_failure'):
            with self.subTest(kind=kind):
                result,payloads,_=self.run_probe(kind)
                self.assertEqual(len(payloads),1);self.assertEqual(result['status'],'stopped')
                self.assertGreaterEqual(result['known_total_tokens'],110)
                self.assertFalse(result['probe_gate_passed'])


class TwoStagePipelineTests(unittest.TestCase):
    def run_pipeline(self,kind):
        stages=[]
        class Process:
            def __init__(self,pid):self.pid=pid;self.returncode=None;self.terminated=False
            def poll(self):return self.returncode
            def terminate(self):self.terminated=True;self.returncode=0
            def wait(self,timeout):return self.returncode
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp);root=storage/'source';(root/'reports').mkdir(parents=True)
            write(root/driver.PLAN,{'synthetic':True});(storage/'records/context_pilot').mkdir(parents=True)
            server,caffeinate=Process(72),Process(71)
            original_read=driver.read
            def read(path):
                if str(path).endswith('.runtime/model_server.json'):
                    if kind=='cleanup_failure' and server.terminated:raise ValueError('synthetic final read failure')
                    return dict(supervisor_pid=72,pid=73,status='stopped' if server.terminated else 'ready',record_directory='records/p2_servers/synthetic')
                return original_read(path)
            def probe(*args):
                stages.append('probe');rows=probe_rows();status='complete'
                if kind=='probe_reject':
                    for row in rows:row['patch_valid']=False
                if kind=='probe_unknown':
                    rows=rows[:2];rows[-1].update(status='unknown',input_tokens=None,output_tokens=None,usage_verified=False)
                    status='stopped'
                if kind=='stop_after_probe':
                    (storage/'.runtime').mkdir(exist_ok=True);(storage/'.runtime/P147.stop').touch()
                return dict(rows=rows,status=status,**driver.probe_gate(rows,status))
            def preflight(*args):
                stages.append('preflight')
                if kind=='preflight_failure':raise ValueError('synthetic pair count mismatch')
            def batch(*args):
                stages.append('batch');rows=good_rows();status='complete'
                if kind=='full_partial':
                    rows=rows[:1];rows[0]['success']=None;rows[0]['unknown_usage_calls']=1;status='stopped'
                return dict(rows=rows,status=status)
            head='a'*40
            end=(datetime.now(timezone.utc)+timedelta(hours=6)).isoformat()
            plan={'latest_launch_jst':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}
            with patch.object(driver.subprocess,'check_output',side_effect=[head+'\n','']), \
                 patch.object(driver,'sources',return_value=(plan,{'model_selection':'synthetic'},[],[])), \
                 patch.object(driver,'saved_sources',return_value=({}, {}, {})), \
                 patch.object(driver,'predecessor',return_value={}),patch.object(driver,'checked_ci',return_value={}), \
                 patch.object(driver.subprocess,'Popen',side_effect=[caffeinate,server]), \
                 patch.object(driver,'read',side_effect=read),patch.object(driver,'probe',side_effect=probe), \
                 patch.object(driver,'preflight',side_effect=preflight),patch.object(driver,'batch',side_effect=batch), \
                 patch.object(driver,'live_identity',return_value=({'owned':True},end)):
                code=driver.run(storage,root,head)
            report=original_read(root/'reports/P147_comparison.json')
            state=original_read(storage/driver.PIPELINE/'status.json')
            self.assertTrue(server.terminated);self.assertTrue(caffeinate.terminated)
            return code,report,state,stages

    def test_gate_pass_runs_preflight_and_eight_cell_batch_exactly_once_and_adds_probe_cost(self):
        code,report,state,stages=self.run_pipeline('good')
        self.assertEqual(code,0);self.assertEqual(stages,['probe','preflight','batch'])
        self.assertEqual(len(report['probe_rows']),3);self.assertEqual(len(report['rows']),8)
        self.assertTrue(state['full_task_stage_started']);self.assertEqual(report['status'],'complete')
        self.assertEqual(report['probe_known_total_tokens'],330)
        self.assertEqual(report['overall_known_total_tokens'],1090)
        self.assertEqual(report['known_token_subtotals'],dict(zip(driver.MODES,[400,360])))

    def test_three_known_probe_failures_publish_ineligible_without_full_dispatch(self):
        code,report,state,stages=self.run_pipeline('probe_reject')
        self.assertEqual(code,0);self.assertEqual(stages,['probe'])
        self.assertEqual(report['status'],'ineligible');self.assertEqual(report['batch_status'],'not_started')
        self.assertEqual(len(report['probe_rows']),3);self.assertEqual(report['rows'],[])
        self.assertEqual(report['probe_known_total_tokens'],330);self.assertEqual(report['overall_known_total_tokens'],330)
        self.assertFalse(state['full_task_stage_started']);self.assertFalse(report['development_gate_met'])

    def test_unknown_probe_stops_with_known_subtotal_and_unknown_retained(self):
        code,report,state,stages=self.run_pipeline('probe_unknown')
        self.assertEqual(code,1);self.assertEqual(stages,['probe'])
        self.assertEqual(report['status'],'stopped');self.assertEqual(report['rows'],[])
        self.assertEqual(report['probe']['unknown_usage_calls'],1)
        self.assertEqual(report['overall_known_total_tokens'],110)
        self.assertFalse(report['development_gate_met']);self.assertFalse(state['full_task_stage_started'])

    def test_stop_or_preflight_failure_after_probe_keeps_probe_cost_without_task(self):
        for kind in ('stop_after_probe','preflight_failure'):
            with self.subTest(kind=kind):
                code,report,state,stages=self.run_pipeline(kind)
                self.assertEqual(code,1);self.assertNotIn('batch',stages)
                self.assertEqual(report['status'],'stopped');self.assertEqual(report['overall_known_total_tokens'],330)
                self.assertEqual(report['rows'],[]);self.assertFalse(state['full_task_stage_started'])

    def test_cleanup_or_partial_batch_failure_cannot_publish_successful_adoption(self):
        for kind in ('cleanup_failure','full_partial'):
            with self.subTest(kind=kind):
                code,report,state,stages=self.run_pipeline(kind)
                self.assertEqual(code,1);self.assertEqual(stages,['probe','preflight','batch'])
                self.assertEqual(report['status'],'stopped');self.assertFalse(report['development_gate_met'])
                self.assertTrue(all(v is None for v in report['total_tokens_by_mode'].values()))
                self.assertEqual(report['probe_known_total_tokens'],330)
                self.assertEqual(report['overall_known_total_tokens'],1090 if kind=='cleanup_failure' else 430)


class InitialRefusalAndCleanupTests(unittest.TestCase):
    def test_not_all_twelve_predecessor_rows_refuses_before_server_or_probe_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp);root=storage/'source';root.mkdir()
            PredecessorTests().fixture(storage,'eleven_only')
            head='a'*40;plan={'required_P145_plan_sha256':'a'*64}
            with patch.object(driver.subprocess,'check_output',side_effect=[head+'\n','']), \
                 patch.object(driver,'sources',return_value=(plan,{},[],[])), \
                 patch.object(driver,'saved_sources',return_value=({}, {}, {})), \
                 patch.object(driver.subprocess,'Popen') as launch,patch.object(driver,'probe') as probe, \
                 self.assertRaises(ValueError):
                driver.run(storage,root,head)
            launch.assert_not_called();probe.assert_not_called()
            self.assertFalse((storage/driver.PIPELINE).exists())

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


if __name__=='__main__':unittest.main()
