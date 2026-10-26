"""Handwritten P135 launch boundaries; no process, model or API is started."""
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
import whole_task_observed_obligations_p135 as helper
import run_whole_task_observed_obligations_p135 as driver
import run_whole_task_observed_obligations_pipeline_p135 as pipeline
import obligation_server_identity_p135 as identity
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
            for mode in helper.MODES:
                cfg=helper.config_for(original,plan,task['task_id'],mode,rep)
                self.assertEqual({k:cfg[k] for k in baseline},baseline)
                self.assertEqual(cfg['max_api_requests'],80)
                messages,_=helper.initial_conversation(original,public,mode).for_model()
                actual[mode]=request(cfg,messages,helper.tools_for(mode),mode)
            self.assertEqual(actual['raw_anchor'],request(baseline,old_messages,CODE_TOOLS,'raw_anchor'))
            self.assertEqual(actual['counts_only'],actual['entity_fields'])
            self.assertNotEqual(actual['raw_anchor']['tools'],actual['counts_only']['tools'])

    def test_unclosed_predecessor_blocks_before_live_contact_count_or_creation(self):
        with tempfile.TemporaryDirectory()as td:
            root=Path(td)/'root';storage=Path(td).resolve()/'storage';root.mkdir();storage.mkdir()
            with patch.object(driver,'sources',return_value=({}, {}, [], [])), \
                 patch.object(driver,'launch_predecessor_closed',side_effect=ValueError('P133_active')), \
                 patch.object(driver,'live_identity')as live,patch.object(driver,'frozen_hashes')as frozen, \
                 patch.object(driver,'count_input')as count:
                with self.assertRaisesRegex(ValueError,'P133_active'):driver.preflight(storage,root)
                live.assert_not_called();frozen.assert_not_called();count.assert_not_called()
                self.assertFalse((storage/'records/context_pilot/P135_preflight_v01').exists())

    def test_pipeline_explicit_stop_and_deadline_precede_spawn(self):
        with tempfile.TemporaryDirectory()as td:
            storage=Path(td).resolve();(storage/'.runtime').mkdir();stop=storage/'.runtime/P135.stop';stop.touch()
            with patch.object(pipeline.subprocess,'Popen')as spawn,patch.object(pipeline.subprocess,'check_output')as git:
                with self.assertRaises(InterruptedError):pipeline.run(storage,'a'*40)
                git.assert_not_called();spawn.assert_not_called()
            stop.unlink();plan=helper.fixed_fields();deadline=dt.datetime.fromisoformat(plan['deadline_jst']).timestamp()
            with patch.object(pipeline.subprocess,'check_output',side_effect=['a'*40,'']), \
                 patch.object(pipeline,'check_resume',return_value={}),patch.object(pipeline,'checked_ci',return_value=[]), \
                 patch.object(pipeline,'read',return_value=plan),patch.object(pipeline.time,'time',return_value=deadline-21600+1), \
                 patch.object(pipeline.subprocess,'Popen')as spawn:
                with self.assertRaisesRegex(ValueError,'deadline'):pipeline.run(storage,'a'*40)
                spawn.assert_not_called();self.assertFalse((storage/'records/context_pilot/P135_pipeline_v01').exists())

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
    def test_recovery_gate_precedes_other_record_reads(self):
        with tempfile.TemporaryDirectory() as td:
            storage=Path(td).resolve()
            with patch.object(driver,'read',return_value={'status':'waiting'}) as reads, patch.object(driver.subprocess,'run') as ps:
                with self.assertRaises(ValueError):driver.launch_predecessor_closed(storage)
                reads.assert_called_once_with(storage/'.runtime/P133_reporting_recovery_v01_complete.json')
                ps.assert_not_called()

    def fixture(self,storage,*,rows_missing=False,audit_error=False,typed_rep=True):
        from whole_task_checkpoint_payback import cell_id,run_order
        def write(rel,value,*,text=False):
            path=storage/rel;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(value if text else json.dumps(value));return driver.sha(path)
        original_head='66d9eb71a1e6b8ee10b377be3bf52dca82d06cca'
        original_plan='357c59a73ed9637e9171d6729f8f4210533fef90d598ec667fa1d7154d09d986'
        qsha='888377b8c7392cfcd8664bd3ccc4c81c59b0a52d7952fc990bf68412bb216c4b'
        run='.runtime/worktrees/p133-run';recovery='.runtime/worktrees/p133-results-recovery'
        folder='records/context_pilot/P133_pipeline_v01'
        state=dict(phase='P133_pipeline',status='complete',server_stopped=True,server_supervisor_pid=123,git_commit=original_head)
        final=dict(status='stopped',supervisor_pid=123,pid=124)
        state_sha=write(folder+'/status.json',state);final_sha=write(folder+'/server_final.json',final)
        write('records/context_pilot/P133_batch_v01/status.json',dict(phase='P133',status='complete',planned=[cell_id(*x)for x in run_order()]))
        rows=[dict(run_id=cell_id(rep,n,m),replication=rep,model_seed=57 if rep==1 else 157,payback_mode=m,
                   success=False,unknown_usage_calls=1)for rep,n,m in run_order()]
        if rows_missing:rows.pop()
        if not typed_rep:rows[0]['replication']=True
        audit=dict(phase='P133',rows=rows,audit_errors=['synthetic']if audit_error else[],owned_processes_absent=True,
            pipeline_status_sha256=state_sha,server_final_sha256=final_sha)
        audit_sha=write(run+'/reports/P133_comparison.json',audit);write(recovery+'/reports/P133_comparison.json',audit)
        session=dict(phase='P133',status='stopped',owned_processes_absent=True,audit_source_sha256=audit_sha)
        session_sha=write(run+'/reports/P133_server_session.json',session);write(recovery+'/reports/P133_server_session.json',session)
        for stage,code in (('audit',0),('session',0),('report',1)):
            write('.runtime/P133_'+stage+'_once_end.json',{'exit_code':code})
        log_sha=write('.runtime/P133_report_once.log','synthetic preserved report error\n',text=True)
        write(run+'/configs/P133_whole_task_checkpoint_payback_v01.json',{'handwritten':'plan'})
        write('.runtime/P133_pipeline_once_start.json',dict(source_head=original_head,plan_sha256=original_plan))
        source_sha=write(recovery+'/scripts/synthetic_recovery.py','# handwritten source\n',text=True)
        target='materials/20261027_p133_results_recovery_v01'
        data_sha=write(recovery+'/'+target+'/summary.json',{'handwritten':'four closed slots'})
        manifest_sha=write(recovery+'/'+target+'/build_manifest.json',dict(
            source_sha256={'scripts/synthetic_recovery.py':source_sha},artifact_sha256={'summary.json':data_sha}))
        marker=dict(status='complete',source_head='e'*40,original_head=original_head,original_plan_sha256=original_plan,
            original_failure_path='.runtime/P133_report_once_end.json',
            original_failure_sha256=driver.sha(storage/'.runtime/P133_report_once_end.json'),original_report_log_sha256=log_sha,
            audit_sha256=audit_sha,session_sha256=session_sha,recovery_manifest_sha256=manifest_sha,completed_conditions=4,
            owned_processes_absent=True,additional_model_calls=0,additional_API_requests=0,additional_evaluations=0,
            additional_tokenizer_calls=0,original_audit_exit_code=0,original_session_exit_code=0,
            recovery_root=str(storage/recovery),audit_path='reports/P133_comparison.json',session_path='reports/P133_server_session.json',
            recovery_manifest_path=target+'/build_manifest.json',recovery_source_sha256={'scripts/synthetic_recovery.py':source_sha})
        write('.runtime/P133_reporting_recovery_v01_complete.json',marker)
        write('.runtime/queue_p134_after_p133_once_20261027.py','# handwritten queue\n',text=True)
        q=dict(source_head='dda97636b88ad3126647e101af9e720f745e5ec7',queue_source_sha256=qsha)
        write('.runtime/P134_queue_after_P133_once_start.json',dict(**q,queue_pid=125))
        write('.runtime/P134_queue_after_P133_once_end.json',dict(**q,status='failed_no_retry',child_started=False))
        real_sha=driver.sha
        def fake_sha(path):
            if str(path).endswith('configs/P133_whole_task_checkpoint_payback_v01.json'):return original_plan
            if Path(path).name=='queue_p134_after_p133_once_20261027.py':return qsha
            return real_sha(path)
        patcher=patch.object(driver,'sha',side_effect=fake_sha);patcher.start();self.addCleanup(patcher.stop)
        head=patch.object(driver.subprocess,'check_output',return_value='e'*40);head.start();self.addCleanup(head.stop)
        return marker

    def test_closed_failure_unknown_allowed_missing_audit_and_typed_id_rejected(self):
        for kwargs in ({},{'rows_missing':True},{'audit_error':True},{'typed_rep':False}):
            with tempfile.TemporaryDirectory() as td:
                storage=Path(td).resolve();self.fixture(storage,**kwargs)
                with patch.object(driver.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')):
                    if kwargs:
                        with self.assertRaises(ValueError):driver.launch_predecessor_closed(storage)
                    else:self.assertTrue(driver.launch_predecessor_closed(storage))

    def test_closed_metadata_cannot_override_live_PID_or_any_stop(self):
        with tempfile.TemporaryDirectory() as td:
            storage=Path(td).resolve();self.fixture(storage)
            with patch.object(driver.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='owned process')):
                with self.assertRaisesRegex(ValueError,'process_present'):driver.launch_predecessor_closed(storage)
            for phase in ('P133','P134','P135'):
                stop=storage/f'.runtime/{phase}.stop';stop.touch()
                with patch.object(driver,'read') as read:
                    with self.assertRaises(InterruptedError):driver.launch_predecessor_closed(storage)
                    read.assert_not_called()
                stop.unlink()

    def test_preserved_failure_and_no_paid_recovery_are_required(self):
        for key,value in [('additional_model_calls',1),('additional_API_requests',True),
                          ('additional_evaluations',1),('additional_tokenizer_calls',1),
                          ('original_head','0'*40),('completed_conditions',True),('original_report_log_sha256','0'*64)]:
            with tempfile.TemporaryDirectory() as td:
                storage=Path(td).resolve();marker=self.fixture(storage);marker[key]=value
                (storage/'.runtime/P133_reporting_recovery_v01_complete.json').write_text(json.dumps(marker))
                with self.subTest(key=key),self.assertRaises(ValueError):driver.launch_predecessor_closed(storage)

    def test_P134_any_start_or_live_queue_prevents_recovery_launch(self):
        for rel in ('.runtime/P134_pipeline_once_start.json','.runtime/P134_pipeline_child_once.json',
                    '.runtime/P134_pipeline_once_end.json','.runtime/P134_pipeline_once.log',
                    '.runtime/P134_report_collector_once_start.json','.runtime/P134_report_collector_once_end.json',
                    '.runtime/P134_queue_after_P133_once_child.json',
                    'records/context_pilot/P134_preflight_v01','records/context_pilot/BOC_P134_R01_01_RAW_ANCHOR'):
            with tempfile.TemporaryDirectory() as td:
                storage=Path(td).resolve();self.fixture(storage);p=storage/rel;p.parent.mkdir(parents=True,exist_ok=True);p.touch()
                with patch.object(driver.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')):
                    with self.assertRaisesRegex(ValueError,'model0'):driver.launch_predecessor_closed(storage)
        with tempfile.TemporaryDirectory() as td:
            storage=Path(td).resolve();self.fixture(storage)
            with patch.object(driver.subprocess,'run',side_effect=[SimpleNamespace(returncode=1,stdout=''),SimpleNamespace(returncode=1,stdout=''),SimpleNamespace(returncode=0,stdout='queue')]):
                with self.assertRaisesRegex(ValueError,'queue_still_present'):driver.launch_predecessor_closed(storage)

    def test_recovery_manifest_source_artifact_and_path_escape_rejected(self):
        for mutation in ('source','artifact','traversal','absolute'):
            with tempfile.TemporaryDirectory() as td:
                storage=Path(td).resolve();marker=self.fixture(storage);root=Path(marker['recovery_root'])
                if mutation=='source':(root/'scripts/synthetic_recovery.py').write_text('# changed')
                elif mutation=='artifact':(root/'materials/20261027_p133_results_recovery_v01/summary.json').write_text('{}')
                else:
                    marker['recovery_source_sha256']={('../outside'if mutation=='traversal'else'/absolute'):'a'*64}
                    (storage/'.runtime/P133_reporting_recovery_v01_complete.json').write_text(json.dumps(marker))
                with self.subTest(mutation=mutation),self.assertRaises(ValueError):driver.launch_predecessor_closed(storage)


class OwnedLeaseTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()/'root';self.storage=Path(temp.name).resolve()/'storage'
        self.source=self.root/identity.SUPERVISOR;self.source.parent.mkdir(parents=True);self.source.write_text('synthetic supervisor\n')
        self.plan={'model_selection':'synthetic.json','model':{'num_ctx':65536,'base_url':'http://127.0.0.1:8011'}}
        self.now=dt.datetime.now(dt.timezone.utc)
        self.runtime=dict(supervisor_pid=123,pid=124,started_at=(self.now-dt.timedelta(seconds=10)).isoformat(),record_directory='records/p2_servers/synthetic')
        self.owner=dict(phase='P135_pipeline',status='preflight',server_owned=True,server_supervisor_pid=123,server_record_directory=self.runtime['record_directory'])
        self.args=['python',str(self.source),'--storage-root',str(self.storage),'--selection','synthetic.json','--ctx-size','65536',
            '--cache-type-k','q8_0','--cache-type-v','q8_0','--max-seconds','21600']
        for p in (patch.object(identity,'ROOT',self.root),patch.object(identity,'SUPERVISOR_SHA256',hashlib.sha256(self.source.read_bytes()).hexdigest())):
            p.start();self.addCleanup(p.stop)
    def lease(self,*,args=None,owner=None):
        return identity.owned_lease(self.runtime,shlex.join(args or self.args),self.now,storage=self.storage,source_plan=self.plan,owner=owner or self.owner)
    def test_exact_lease_owner_and_source_are_required(self):
        self.assertEqual(self.lease()[0],21590)
        for change in ({'phase':'P133_pipeline'},{'server_supervisor_pid':True},{'server_owned':False},{'status':'stopped'}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.lease(owner={**self.owner,**change})
        for seconds in ('14400','21601'):
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

if __name__=='__main__':unittest.main()
