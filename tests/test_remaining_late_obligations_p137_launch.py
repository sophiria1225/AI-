"""Handwritten P137 launch boundaries; no process, model or API is started."""
from copy import deepcopy
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import whole_task_remaining_late_obligations_p137 as helper
import run_whole_task_remaining_late_obligations_p137 as driver
import run_whole_task_remaining_late_obligations_pipeline_p137 as pipeline
import remaining_late_obligation_server_identity_p137 as identity
from whole_task_rolling_checkpoint import config_for as original_config
from late_clock_comparison import initial_conversation as original_conversation
from api_error_comparison import task_snapshot
from tool_choice_local_llama import payload_for
from public_display import CODE_TOOLS


class InputAndLaunchTests(unittest.TestCase):
    def test_raw_anchor_preserves_P123_and_primary_pair_has_identical_capabilities(self):
        old=json.loads((ROOT/'configs/P123_whole_task_rolling_checkpoint_v01.json').read_text())
        original=json.loads((ROOT/old['source_plan']).read_text());task=next(t for t in old['known_tasks']if t['source_run']=='P29_04_CODE')
        public={'instruction':'Handwritten public fixture only.'};plan={**helper.fixed_fields(),'known_tasks':[task]}
        old_messages,_=original_conversation(original,public).for_model()
        def request(config,messages,tools,mode):
            supplied,_=helper.make_notification(messages,task_snapshot(config,[],0,0),mode,wall_limit=1800)
            cfg={**config['model'],'temperature':original['agent_temperature'],'seed':config['seed'],
                'num_predict':original['max_output_tokens'],'cache_prompt':False}
            return payload_for(cfg,supplied,tools)
        for rep,seed in ((1,57),(2,157)):
            baseline=original_config(original,{**old,'model_seed':seed},task['task_id'],'rolling_separate')
            actual={}
            for mode in helper.modes_for_replication(rep):
                cfg=helper.config_for(original,plan,task['task_id'],mode,rep)
                self.assertEqual({k:cfg[k] for k in baseline},baseline)
                self.assertEqual(cfg['max_api_requests'],80)
                messages,_=helper.initial_conversation(original,public,mode).for_model()
                actual[mode]=request(cfg,messages,helper.tools_for(mode),mode)
            expected=request(baseline,old_messages,CODE_TOOLS,'raw_anchor')
            for value in actual.values():self.assertEqual(value,expected)

    def test_unclosed_predecessor_blocks_before_live_contact_count_or_creation(self):
        with tempfile.TemporaryDirectory()as td:
            root=Path(td)/'root';storage=Path(td).resolve()/'storage';root.mkdir();storage.mkdir()
            with patch.object(driver,'sources',return_value=({}, {}, [], [])), \
                 patch.object(driver,'launch_predecessor_closed',side_effect=ValueError('P133_active')), \
                 patch.object(driver,'live_identity')as live,patch.object(driver,'frozen_hashes')as frozen, \
                 patch.object(driver,'count_input')as count:
                with self.assertRaisesRegex(ValueError,'P133_active'):driver.preflight(storage,root)
                live.assert_not_called();frozen.assert_not_called();count.assert_not_called()
                self.assertFalse((storage/'records/context_pilot/P137_preflight_v01').exists())

    def test_pipeline_explicit_stop_and_deadline_precede_spawn(self):
        with tempfile.TemporaryDirectory()as td:
            storage=Path(td).resolve();(storage/'.runtime').mkdir();stop=storage/'.runtime/P137.stop';stop.touch()
            with patch.object(pipeline.subprocess,'Popen')as spawn,patch.object(pipeline.subprocess,'check_output')as git:
                with self.assertRaises(InterruptedError):pipeline.run(storage,'a'*40)
                git.assert_not_called();spawn.assert_not_called()
            stop.unlink();plan=helper.fixed_fields();deadline=dt.datetime.fromisoformat(plan['deadline_jst']).timestamp()
            with patch.object(pipeline.subprocess,'check_output',side_effect=['a'*40,'']), \
                 patch.object(pipeline,'check_resume',return_value={}),patch.object(pipeline,'checked_ci',return_value=[]), \
                 patch.object(pipeline,'read',return_value=plan),patch.object(pipeline.time,'time',return_value=deadline-15600+1), \
                 patch.object(pipeline.subprocess,'Popen')as spawn:
                with self.assertRaisesRegex(ValueError,'deadline'):pipeline.run(storage,'a'*40)
                spawn.assert_not_called();self.assertFalse((storage/'records/context_pilot/P137_pipeline_v01').exists())

    def test_pipeline_requires_both_exact_head_CI_events(self):
        head='a'*40;origin='https://github.com/sophiria1225/AI-.git'
        valid=[dict(id=i,head_sha=head,path='.github/workflows/checks.yml',event=e,status='completed',conclusion='success')for i,e in enumerate(('push','pull_request'),1)]
        with patch.object(pipeline.subprocess,'check_output',side_effect=[origin,json.dumps({'workflow_runs':valid})]), \
             patch('probe_notice_calibration.confirmed_ci',return_value=['synthetic confirmed'])as confirm:
            self.assertEqual(pipeline.checked_ci(ROOT,head),['synthetic confirmed']);confirm.assert_called_once()
        variants=[valid[:1],[{**x,'head_sha':'b'*40}for x in valid],[valid[0],{**valid[1],'conclusion':'failure'}]]
        for records in variants:
            with patch.object(pipeline.subprocess,'check_output',side_effect=[origin,json.dumps({'workflow_runs':records})]), \
                 patch('probe_notice_calibration.confirmed_ci')as confirm,self.assertRaises(ValueError):
                pipeline.checked_ci(ROOT,head)
            confirm.assert_not_called()


class ClosedPredecessorTests(unittest.TestCase):
    def test_explicit_predecessor_or_current_stop_precedes_any_evidence_read(self):
        for phase in ('P136', 'P137'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as td:
                storage=Path(td);(storage/'.runtime').mkdir();(storage/f'.runtime/{phase}.stop').touch()
                with patch.object(driver,'read') as read, patch.object(driver.subprocess,'run') as process:
                    with self.assertRaises(InterruptedError):driver.launch_predecessor_closed(storage)
                    read.assert_not_called();process.assert_not_called()

    def test_collector_incomplete_and_bool_count_fail_before_other_evidence(self):
        valid=dict(status='complete',planned_conditions=6,evaluated_conditions=1,audit_passed=True,
            audit_errors=0,exact_total_tokens=None,development_gate_met=False,known_token_subtotal=332588,
            unknown_usage_count_missing_conditions=5)
        variants=({'status':'running'},{'planned_conditions':True},{'evaluated_conditions':True},
            {'exact_total_tokens':332588},{'development_gate_met':True},{'unknown_usage_count_missing_conditions':0})
        for changes in variants:
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as td:
                storage=Path(td);rel='.runtime/P136_report_collector_once_end.json';p=storage/rel;p.parent.mkdir()
                p.write_text(json.dumps({**valid,**changes}));h=hashlib.sha256(p.read_bytes()).hexdigest()
                with patch.object(driver,'P136_MARKER_SHA256',{rel:h}),patch.object(driver.subprocess,'run') as process:
                    with self.assertRaisesRegex(ValueError,'original_missing_slots'):driver.launch_predecessor_closed(storage)
                    process.assert_not_called()

    def test_collector_changed_bytes_are_rejected_before_json_read(self):
        with tempfile.TemporaryDirectory() as td:
            storage=Path(td);rel='.runtime/P136_report_collector_once_end.json';p=storage/rel;p.parent.mkdir();p.write_text('{}')
            with patch.object(driver,'P136_MARKER_SHA256',{rel:'0'*64}),patch.object(driver,'read') as read:
                with self.assertRaisesRegex(ValueError,'closed_evidence_changed'):driver.launch_predecessor_closed(storage)
                read.assert_not_called()

    def test_changed_prepared_proof_precedes_server_and_count(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'root';storage=Path(td)/'storage';root.mkdir();storage.mkdir()
            plan={'launch_predecessor_closure_at_preparation':{'bound':'earlier'}}
            with patch.object(driver,'sources',return_value=(plan,{},[],[])), \
                 patch.object(driver,'launch_predecessor_closed',return_value={'bound':'changed'}), \
                 patch.object(driver,'live_identity') as live,patch.object(driver,'count_input') as count:
                with self.assertRaisesRegex(ValueError,'changed_since_plan'):driver.preflight(storage,root)
                live.assert_not_called();count.assert_not_called()
                self.assertFalse((storage/'records/context_pilot/P137_preflight_v01').exists())

class OwnedLeaseTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()/'root';self.storage=Path(temp.name).resolve()/'storage'
        self.source=self.root/identity.SUPERVISOR;self.source.parent.mkdir(parents=True);self.source.write_text('synthetic supervisor\n')
        self.plan={'model_selection':'synthetic.json','model':{'num_ctx':65536,'base_url':'http://127.0.0.1:8011'}}
        self.now=dt.datetime.now(dt.timezone.utc)
        self.runtime=dict(supervisor_pid=123,pid=124,started_at=(self.now-dt.timedelta(seconds=10)).isoformat(),record_directory='records/p2_servers/synthetic')
        self.owner=dict(phase='P137_pipeline',status='preflight',server_owned=True,server_supervisor_pid=123,server_record_directory=self.runtime['record_directory'])
        self.args=['python',str(self.source),'--storage-root',str(self.storage),'--selection','synthetic.json','--ctx-size','65536',
            '--cache-type-k','q8_0','--cache-type-v','q8_0','--max-seconds','14400']
        for p in (patch.object(identity,'ROOT',self.root),patch.object(identity,'SUPERVISOR_SHA256',hashlib.sha256(self.source.read_bytes()).hexdigest())):
            p.start();self.addCleanup(p.stop)
    def lease(self,*,args=None,owner=None):
        return identity.owned_lease(self.runtime,shlex.join(args or self.args),self.now,storage=self.storage,source_plan=self.plan,owner=owner or self.owner)
    def test_exact_lease_owner_and_source_are_required(self):
        self.assertEqual(self.lease()[0],14390)
        for change in ({'phase':'P133_pipeline'},{'server_supervisor_pid':True},{'server_owned':False},{'status':'stopped'}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.lease(owner={**self.owner,**change})
        for seconds in ('21600','14401'):
            args=self.args[:];args[-1]=seconds
            with self.subTest(seconds=seconds),self.assertRaises(ValueError):self.lease(args=args)
        self.source.write_text('changed synthetic supervisor\n')
        with self.assertRaisesRegex(ValueError,'source'):self.lease()
    def test_driver_and_idle_recovery_use_same_new_identity(self):
        self.assertIs(driver.live_identity,identity.live_identity);self.assertIs(driver.wait_idle,identity.wait_idle)
        current={'synthetic':'identity'}
        with patch.object(identity.urllib.request,'urlopen',return_value=io.StringIO('[{"is_processing":false}]')), \
             patch.object(identity,'live_identity',return_value=(current,'synthetic end'))as live:
            result=identity.wait_idle(self.storage,self.plan,current,1)
        live.assert_called_once_with(self.storage,self.plan,1);self.assertTrue(result['one_slot_idle'])
        with patch.object(identity.urllib.request,'urlopen',return_value=io.StringIO('[{"is_processing":false}]')), \
             patch.object(identity,'live_identity',return_value=({'other':True},'synthetic end')):
            with self.assertRaisesRegex(ValueError,'identity changed'):identity.wait_idle(self.storage,self.plan,current,1)

class BatchProgressionTests(unittest.TestCase):
    def exercise(self, *, cleanup_ok=True, idle_error=False):
        from contextlib import ExitStack, redirect_stdout
        with tempfile.TemporaryDirectory() as td:
            storage=Path(td)/'storage';root=Path(td)/'root'
            (storage/'records/context_pilot').mkdir(parents=True);(root/'reports').mkdir(parents=True)
            plan=helper.fixed_fields();identity={'synthetic':'same-owned-server'}
            (root/driver.ACTIVATION).write_text('{}')
            (root/driver.PREFLIGHT).write_text(json.dumps({'model_identity':identity}))
            sequence=[]
            def cell(_storage,_root,_plan,rep,num,mode,rid,folder):
                sequence.append(('worker',rid));trial=storage/'records/context_pilot'/rid;trial.mkdir()
                first=len([x for x in sequence if x[0]=='worker'])==1
                value=dict(run_id=rid,task_id='synthetic',arm='error_exception',replication=rep,
                    model_seed=helper.SEEDS[rep-1],obligation_mode=mode,time_visibility='not_exposed',
                    checkpoint_policy='rolling_separate',reasoning_budget_tokens=-1,
                    stop_reason='wall_limit_during_model_call' if first else 'agent_declared_complete',
                    model_calls=1,known_total_tokens=0 if first else 100,unknown_usage_calls=int(first),
                    api_requests=0,wall_seconds=1,full_wall_seconds=2,cleanup_confirmed=cleanup_ok,
                    setup={'status':'initial_public_state_matched'},unknown_effect_requests=0)
                (folder/(rid+'_worker_exit.json')).write_text(json.dumps({'run_id':rid,'returncode':0,'status':'exited'}))
                return value
            def idle(*args):
                sequence.append(('idle',None))
                if idle_error:raise TimeoutError('synthetic idle deadline')
                return {'one_slot_idle':True}
            def evaluate(command,**kwargs):
                trial=Path(command[command.index('--trial')+1]);sequence.append(('evaluate',trial.name))
                (trial/'evaluation.json').write_text(json.dumps({'official_success':False}))
                return SimpleNamespace(returncode=0,stdout='',stderr='')
            with ExitStack() as stack:
                for obj,name,value in [(driver,'sources',(plan,{},[],[])),(driver,'validate_preflight',None),
                    (driver,'validate_activation',None),(driver,'live_identity',(identity,'synthetic-end'))]:
                    stack.enter_context(patch.object(obj,name,return_value=value))
                stack.enter_context(patch.object(driver,'bounded_cell',side_effect=cell))
                stack.enter_context(patch.object(driver,'wait_idle',side_effect=idle))
                stack.enter_context(patch.object(driver.subprocess,'check_output',return_value='a'*40))
                stack.enter_context(patch.object(driver.subprocess,'run',side_effect=evaluate))
                stack.enter_context(redirect_stdout(io.StringIO()))
                code=driver.run(storage,root)
            state=json.loads((storage/'records/context_pilot/P137_batch_v01/status.json').read_text())
            return code,state,sequence

    def test_unknown_first_cell_is_evaluated_then_next_fixed_cell_runs(self):
        code,state,sequence=self.exercise()
        ids=[helper.cell_id(rep,n,m)for rep,n,m in helper.run_order()]
        self.assertEqual(code,0);self.assertEqual(state['completed'],ids)
        self.assertEqual(sequence[:4],[('worker',ids[0]),('idle',None),('evaluate',ids[0]),('worker',ids[1])])
        self.assertEqual(state['rows'][0]['disposition'],'evaluate_unknown_usage')
        self.assertEqual(state['rows'][0]['unknown_usage_calls'],1)
        self.assertFalse(state['known_usage_complete']);self.assertEqual(state['not_run'],[])
        self.assertEqual(set(state['worker_exit_records']),set(ids))

    def test_cleanup_or_idle_failure_stops_without_dropping_planned_slots(self):
        for options in ({'cleanup_ok':False},{'idle_error':True}):
            with self.subTest(options=options):
                code,state,sequence=self.exercise(**options)
                self.assertEqual(code,1);self.assertEqual(len(state['planned']),4)
                self.assertEqual(len(state['not_run']),3);self.assertEqual(state['completed'],[])
                self.assertEqual(len([x for x in sequence if x[0]=='worker']),1)
                self.assertFalse(any(x[0]=='evaluate' for x in sequence))

    def test_nonzero_worker_signal_exit_code_is_preserved_before_raising(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);plan=helper.fixed_fields();rid=helper.cell_id(1,1,'entity_fields')
            child=SimpleNamespace(pid=123,wait=lambda **kw:-14,poll=lambda:-14)
            with patch.object(driver.subprocess,'Popen',return_value=child):
                with self.assertRaisesRegex(RuntimeError,'worker_failed_no_retry'):
                    driver.bounded_cell(folder,folder,plan,1,1,'entity_fields',rid,folder)
            receipt=json.loads((folder/(rid+'_worker_exit.json')).read_text())
            self.assertEqual(receipt['returncode'],-14);self.assertEqual(receipt['status'],'exited')
            self.assertFalse(receipt['timed_out']);self.assertEqual(receipt['error_type'],'RuntimeError')

if __name__=='__main__':unittest.main()
