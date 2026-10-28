"""Synthetic replication tests; no models, task APIs or evaluator calls."""
import ast
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import shlex
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import indexed_update_config_p148 as config
import indexed_update_config_p147 as previous_config
import indexed_update_server_p148 as server
import run_indexed_update_p148 as driver


def plan():
    result=json.loads((ROOT/'configs/P147_indexed_update_v01.json').read_text())
    result.update(config.fixed_fields())
    result['schedule']=[dict(task_slot=n,mode=m,run_id=config.cell_id(n,m)) for n,m in config.run_order()]
    return result


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data)+'\n')


class ReplicationConfigTests(unittest.TestCase):
    def test_all_eight_configs_only_change_seed_and_phase_metadata(self):
        original=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
        prior=json.loads((ROOT/'configs/P147_indexed_update_v01.json').read_text())
        for n,mode in config.run_order():
            with self.subTest(task=n,mode=mode):
                before=previous_config.worker_config(original,prior,config.TASKS[n-1],
                    config.ERROR_POLICY,previous_config.cell_id(n,mode),mode)
                after=config.worker_config(original,plan(),config.TASKS[n-1],
                    config.ERROR_POLICY,config.cell_id(n,mode),mode)
                before.update(phase='P148',experiment='P148',seed=357)
                self.assertEqual(before,after)

    def test_initial_actor_and_first_focus_payloads_only_change_seed(self):
        from tool_choice_local_llama import payload_for as actor_payload
        from fixed_budget_local_llama import payload_for as focus_payload
        from public_display import CODE_TOOLS
        original=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
        prior=json.loads((ROOT/'configs/P147_indexed_update_v01.json').read_text())
        messages=[{'role':'system','content':'Synthetic fixed instruction'},
                  {'role':'user','content':'Synthetic fixed packet'}]
        for n,mode in config.run_order():
            before=previous_config.worker_config(original,prior,config.TASKS[n-1],
                config.ERROR_POLICY,previous_config.cell_id(n,mode),mode)
            after=config.worker_config(original,plan(),config.TASKS[n-1],
                config.ERROR_POLICY,config.cell_id(n,mode),mode)
            for kind,builder,tools in [('actor',actor_payload,CODE_TOOLS),('first_focus',focus_payload,[])]:
                def payload(c):
                    cfg=dict(c['model'],seed=c['seed'],num_predict=c['max_output_tokens'],
                        temperature=c['agent_temperature'] if kind=='actor' else c['draft_temperature'],
                        cache_prompt=kind!='actor')
                    return builder(cfg,messages,tools)
                a,b=payload(before),payload(after)
                self.assertEqual((a['seed'],b['seed']),(257,357))
                a['seed']=357
                with self.subTest(task=n,mode=mode,role=kind):
                    self.assertEqual(a,b)
                    self.assertEqual(b['max_tokens'],4096)
                    self.assertEqual(b['reasoning_budget_tokens'],-1)

    def test_seed_method_budget_deadline_and_schedule_are_fixed(self):
        for key,value in [('model_seed',257),('update_focus_reasoning_budget_tokens',-1),
                ('max_calls',81),('max_total_tokens',450001),('trigger_input_tokens',9000),
                ('operational_model_deadline_jst','2026-10-29T12:00:00+09:00'),
                ('new_probe_generations',3),('automatic_retries',1)]:
            p=plan();p[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):config.validate_plan(p)
        p=plan();p['schedule']=p['schedule'][:-1]
        with self.assertRaises(ValueError):config.validate_plan(p)
        p=plan();p['schedule'][1]=deepcopy(p['schedule'][0])
        with self.assertRaises(ValueError):config.validate_plan(p)

    def test_old_run_namespace_cannot_be_reused(self):
        original=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
        with self.assertRaises(ValueError):
            config.worker_config(original,plan(),config.TASKS[0],config.ERROR_POLICY,
                'BOC_P147_01_TR',config.MODES[0])

    def test_worker_derivation_changes_only_config_import_stop_and_phase(self):
        old=(ROOT/'scripts/run_indexed_update_cell_p147.py').read_text()
        old=old.replace('P147','P148').replace('from indexed_update_config_p147 import worker_config',
            'from indexed_update_config_p148 import worker_config')
        new=(ROOT/'scripts/run_indexed_update_cell_p148.py').read_text()
        a,b=ast.parse(old),ast.parse(new)
        a.body=a.body[1:];b.body=b.body[1:]
        self.assertEqual(ast.dump(a),ast.dump(b))


class AbsoluteDeadlineTests(unittest.TestCase):
    def test_lease_shrinks_only_with_clock_and_keeps_stop_reserve(self):
        end=datetime.fromisoformat(server.MODEL_DEADLINE_JST).timestamp()
        self.assertEqual(driver.server_seconds_at(end-30000),21600)
        self.assertEqual(driver.server_seconds_at(end-10000),9880)
        with self.assertRaises(TimeoutError):driver.server_seconds_at(end-2000)
        with self.assertRaises(TimeoutError):driver.server_seconds_at(end+1)

    def test_owned_server_must_fit_actual_absolute_deadline(self):
        now=datetime(2026,10,28,22,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp).resolve();original={'model_selection':'synthetic','model':{'num_ctx':65536}}
            runtime=dict(supervisor_pid=71,pid=72,record_directory='records/p2_servers/synthetic',
                started_at=(now-timedelta(seconds=2)).isoformat())
            owner=dict(phase='P148_pipeline',status='batch',server_owned=True,server_supervisor_pid=71,
                server_record_directory=runtime['record_directory'],server_max_seconds=3600,
                operational_model_deadline_jst=server.MODEL_DEADLINE_JST)
            command=shlex.join(['/usr/bin/python',str(ROOT/server.SUPERVISOR),'--storage-root',str(storage),
                '--selection','synthetic','--ctx-size','65536','--cache-type-k','q8_0',
                '--cache-type-v','q8_0','--max-seconds','3600'])
            remaining,_=server.owned_lease(runtime,command,now,storage=storage,source_plan=original,owner=owner)
            self.assertEqual(remaining,3598)
            for badowner,badcommand,badruntime in [
                    ({**owner,'phase':'P147_pipeline'},command,runtime),
                    ({**owner,'server_max_seconds':3601},command,runtime),
                    (owner,command.replace('--max-seconds 3600','--max-seconds 7200'),runtime),
                    (owner,command,{**runtime,'started_at':datetime.fromisoformat(server.MODEL_DEADLINE_JST).isoformat()})]:
                with self.assertRaises(ValueError):
                    server.owned_lease(badruntime,badcommand,now,storage=storage,source_plan=original,owner=badowner)
            with self.assertRaisesRegex(ValueError,'exceeds_absolute_model_deadline'):
                server.owned_lease(runtime,command.replace('--max-seconds 3600','--max-seconds 21600'),
                    now,storage=storage,source_plan=original,owner={**owner,'server_max_seconds':21600})


class BatchTests(unittest.TestCase):
    def run_batch(self,kind):
        dispatched=[]
        deadline=datetime.fromisoformat(server.MODEL_DEADLINE_JST)
        now=(deadline-timedelta(hours=4)).timestamp()
        end=(deadline-timedelta(minutes=2)).isoformat()
        if kind=='deadline':now=(deadline-timedelta(seconds=1000)).timestamp()
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp);(storage/'records/context_pilot').mkdir(parents=True)
            if kind=='explicit_stop':
                (storage/'.runtime').mkdir();(storage/'.runtime/P148.stop').touch()
            def bounded(command,log,record,save,timeout,**kwargs):
                dispatched.append(command);rid=record['run_id'];trial=storage/'records/context_pilot'/rid
                record.update(status='exited',returncode=0);save()
                if '--cell' in command:
                    n=int(command[command.index('--cell')+1]);mode=command[command.index('--arm')+1]
                    data=dict(run_id=rid,task_id=driver.TASKS[n-1],stop_reason='agent_declared_complete',
                        model_calls=2,known_total_tokens=100 if mode==driver.MODES[0] else 90,
                        unknown_usage_calls=0,api_requests=2,cleanup_confirmed=True,
                        setup={'status':'initial_public_state_matched'},unknown_effect_requests=0,
                        state_update_control={'actual_changed_old_known_actor_calls':int(mode==driver.MODES[1])})
                    if kind=='known_task_failure' and n==4:data['stop_reason']='api_request_limit'
                    if kind=='unknown_first' and len(dispatched)==1:
                        data.update(unknown_usage_calls=1,stop_reason='model_usage_unknown')
                    if kind=='unknown_last' and rid==driver.cell_id(*driver.run_order()[-1]):
                        data.update(unknown_usage_calls=1,stop_reason='model_usage_unknown')
                    if kind=='cleanup_failed':data.update(cleanup_confirmed=False,stop_reason='cleanup_error')
                    write(trial/'summary.json',data)
                else:
                    if kind=='evaluation_failed':raise RuntimeError('synthetic evaluator failure')
                    write(trial/'evaluation.json',{'official_success':not(kind=='known_task_failure' and '_04_' in rid)})
            with patch.object(driver,'bounded_process',side_effect=bounded),\
                    patch.object(driver,'live_identity',return_value=({'owned':True},end)),\
                    patch.object(driver,'wait_idle',return_value={'one_slot_idle':True}),\
                    patch.object(driver.time,'time',return_value=now),redirect_stdout(io.StringIO()):
                result=driver.batch(storage,ROOT,{}, {},{'owned':True},end)
            self.assertEqual(json.loads((storage/driver.BATCH/'status.json').read_text()),result)
            return result,dispatched

    def test_fixed_eight_all_execute_once_and_no_probe_exists(self):
        result,calls=self.run_batch('good')
        self.assertEqual(result['status'],'complete');self.assertEqual(len(calls),16)
        self.assertEqual(result['completed'],[driver.cell_id(n,m) for n,m in driver.run_order()])
        self.assertEqual(result['not_started'],[])
        self.assertFalse(hasattr(driver,'probe'))

    def test_known_failure_does_not_stop_later_conditions(self):
        result,calls=self.run_batch('known_task_failure')
        self.assertEqual(len(calls),16);self.assertEqual(result['status'],'complete')
        self.assertEqual(sum(x['success'] for x in result['rows']),6)
        self.assertTrue(result['all_eight_evaluated_known_usage'])

    def test_unknown_first_preserves_paid_tokens_and_seven_not_started(self):
        result,calls=self.run_batch('unknown_first')
        self.assertEqual(len(calls),1);self.assertEqual(result['status'],'stopped')
        self.assertEqual(result['rows'][0]['known_total_tokens'],100)
        self.assertEqual(result['rows'][0]['unknown_usage_calls'],1)
        self.assertEqual(len(result['not_started']),7)
        self.assertTrue(all(x['model_dispatched'] is False for x in result['not_started']))
        self.assertTrue(all(x is None for x in result['total_tokens_by_mode'].values()))

    def test_unknown_final_cell_never_looks_like_complete_known_gain(self):
        result,calls=self.run_batch('unknown_last')
        self.assertEqual(len(calls),15);self.assertEqual(len(result['rows']),8)
        self.assertEqual(len(result['completed']),7)
        self.assertFalse(result['all_eight_evaluated_known_usage'])
        self.assertFalse(result['development_gate_met'])
        self.assertTrue(all(x is None for x in result['total_tokens_by_mode'].values()))

    def test_deadline_and_explicit_stop_record_all_unstarted_without_dispatch(self):
        for kind in ('deadline','explicit_stop'):
            with self.subTest(kind=kind):
                result,calls=self.run_batch(kind)
                self.assertEqual(calls,[]);self.assertEqual(len(result['not_started']),8)
                self.assertFalse(result['development_gate_met'])

    def test_cleanup_and_evaluation_failures_do_not_dispatch_next_condition(self):
        for kind,expected in [('cleanup_failed',1),('evaluation_failed',2)]:
            with self.subTest(kind=kind):
                result,calls=self.run_batch(kind)
                self.assertEqual(len(calls),expected);self.assertEqual(len(result['not_started']),7)
                self.assertEqual(result['rows'][0]['known_total_tokens'],100)
                self.assertFalse(result['development_gate_met'])

    def test_common_success_gain_cannot_hide_failed_task_cost_growth(self):
        result,_=self.run_batch('known_task_failure')
        result['rows'][-2]['known_total_tokens']=300
        final=driver.summarize(result['rows'],'complete')
        self.assertLess(final['paired_successful_token_difference'],0)
        self.assertFalse(final['development_gate_met'])


class ClosedPredecessorTests(unittest.TestCase):
    def fixture(self,root,kind='closed'):
        ids=[x['run_id'].replace('P148','P147') for x in plan()['schedule']]
        state=dict(status='complete',server_stopped=True,server_supervisor_pid=71,git_commit='fixed')
        final=dict(status='stopped',exit_code=0,supervisor_pid=71,pid=72)
        rows=[dict(run_id=i,success='_04_' not in i,unknown_usage_calls=0,cleanup_confirmed=True) for i in ids]
        batch=dict(status='complete',completed=ids,rows=rows,development_gate_met=False)
        probe=dict(status='complete',rows=[dict(task_slot=n,status='ok',usage_verified=True,
            input_tokens=100,output_tokens=10,finished_at='fixed',patch_valid=True,
            shorter_full_actor_input=True,changed_old_items=1,old_state_changed=True) for n in (1,2,4)])
        if kind=='unknown':rows[-1]['unknown_usage_calls']=1
        if kind=='missing':batch['completed']=ids[:-1]
        if kind=='probe_failed':probe['rows'][-1]['patch_valid']=False
        if kind=='live':state['server_stopped']=False
        if kind=='rewritten_gate':batch['development_gate_met']=True
        write(root/'records/context_pilot/P147_pipeline_v01/status.json',state)
        write(root/'records/context_pilot/P147_pipeline_v01/server_final.json',final)
        write(root/'records/context_pilot/P147_batch_v01/status.json',batch)
        write(root/'records/context_pilot/P147_probe_v01/status.json',probe)
        write(root/'.runtime/P147_closed_independent_20261029.json',
            {'audit_status':'pass_closed_records_consistent','source_head':'fixed'})

    def test_failed_global_cost_gate_is_retained_while_probe_evidence_is_inherited(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            with patch.object(driver.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')):
                result=driver.predecessor(root,plan())
            self.assertTrue(result['inherited_probe_gate_passed'])
            self.assertFalse(result['inherited_full_task_development_gate_met'])
            self.assertEqual(result['new_probe_generations'],0)

    def test_incomplete_unknown_live_or_rewritten_predecessor_rejects(self):
        for kind in ('unknown','missing','probe_failed','live','rewritten_gate'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.fixture(root,kind)
                with patch.object(driver.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')):
                    with self.assertRaises(ValueError):driver.predecessor(root,plan())

    def test_late_pipeline_records_eight_unstarted_cells_without_launching_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'records/context_pilot').mkdir(parents=True);(root/'reports').mkdir()
            write(root/driver.PLAN,plan())
            def git(command,**_):return 'fixed\n' if 'rev-parse' in command else ''
            end=datetime.fromisoformat(server.MODEL_DEADLINE_JST).timestamp()
            with patch.object(driver.subprocess,'check_output',side_effect=git),\
                    patch.object(driver.subprocess,'Popen') as launch,\
                    patch.object(driver,'sources',return_value=(plan(),{},None,[])),\
                    patch.object(driver,'predecessor',return_value={'new_probe_generations':0}),\
                    patch.object(driver,'checked_ci',return_value=[]),\
                    patch.object(driver.time,'time',return_value=end-1000):
                self.assertEqual(driver.run(root,root,'fixed'),1)
            launch.assert_not_called()
            result=json.loads((root/'reports/P148_comparison.json').read_text())
            self.assertEqual(len(result['not_started']),8)
            self.assertEqual(result['overall_known_total_tokens'],0)
            self.assertFalse(result['development_gate_met'])


if __name__=='__main__':unittest.main()
