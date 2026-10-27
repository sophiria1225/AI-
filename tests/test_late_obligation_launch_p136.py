"""Handwritten P136 launch boundaries; no process, model or API is started."""
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
import whole_task_late_obligations_p136 as helper
import run_whole_task_late_obligations_p136 as driver
import run_whole_task_late_obligations_pipeline_p136 as pipeline
import late_obligation_server_identity_p136 as identity
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
            self.assertEqual(actual['ids_only'],actual['entity_fields'])
            self.assertEqual(actual['raw_anchor'],actual['ids_only'])

    def test_unclosed_predecessor_blocks_before_live_contact_count_or_creation(self):
        with tempfile.TemporaryDirectory()as td:
            root=Path(td)/'root';storage=Path(td).resolve()/'storage';root.mkdir();storage.mkdir()
            with patch.object(driver,'sources',return_value=({}, {}, [], [])), \
                 patch.object(driver,'launch_predecessor_closed',side_effect=ValueError('P133_active')), \
                 patch.object(driver,'live_identity')as live,patch.object(driver,'frozen_hashes')as frozen, \
                 patch.object(driver,'count_input')as count:
                with self.assertRaisesRegex(ValueError,'P133_active'):driver.preflight(storage,root)
                live.assert_not_called();frozen.assert_not_called();count.assert_not_called()
                self.assertFalse((storage/'records/context_pilot/P136_preflight_v01').exists())

    def test_pipeline_explicit_stop_and_deadline_precede_spawn(self):
        with tempfile.TemporaryDirectory()as td:
            storage=Path(td).resolve();(storage/'.runtime').mkdir();stop=storage/'.runtime/P136.stop';stop.touch()
            with patch.object(pipeline.subprocess,'Popen')as spawn,patch.object(pipeline.subprocess,'check_output')as git:
                with self.assertRaises(InterruptedError):pipeline.run(storage,'a'*40)
                git.assert_not_called();spawn.assert_not_called()
            stop.unlink();plan=helper.fixed_fields();deadline=dt.datetime.fromisoformat(plan['deadline_jst']).timestamp()
            with patch.object(pipeline.subprocess,'check_output',side_effect=['a'*40,'']), \
                 patch.object(pipeline,'check_resume',return_value={}),patch.object(pipeline,'checked_ci',return_value=[]), \
                 patch.object(pipeline,'read',return_value=plan),patch.object(pipeline.time,'time',return_value=deadline-21600+1), \
                 patch.object(pipeline.subprocess,'Popen')as spawn:
                with self.assertRaisesRegex(ValueError,'deadline'):pipeline.run(storage,'a'*40)
                spawn.assert_not_called();self.assertFalse((storage/'records/context_pilot/P136_pipeline_v01').exists())

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


class OwnedLeaseTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()/'root';self.storage=Path(temp.name).resolve()/'storage'
        self.source=self.root/identity.SUPERVISOR;self.source.parent.mkdir(parents=True);self.source.write_text('synthetic supervisor\n')
        self.plan={'model_selection':'synthetic.json','model':{'num_ctx':65536,'base_url':'http://127.0.0.1:8011'}}
        self.now=dt.datetime.now(dt.timezone.utc)
        self.runtime=dict(supervisor_pid=123,pid=124,started_at=(self.now-dt.timedelta(seconds=10)).isoformat(),record_directory='records/p2_servers/synthetic')
        self.owner=dict(phase='P136_pipeline',status='preflight',server_owned=True,server_supervisor_pid=123,server_record_directory=self.runtime['record_directory'])
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
