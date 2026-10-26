"""Handwritten process/transport records only; no server/model/API is started."""
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
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import recovery_server_identity as m


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / 'repo'; self.storage = Path(self.tmp.name).resolve() / 'storage'
        path = self.root / m.SUPERVISOR; path.parent.mkdir(parents=True); path.write_text('synthetic supervisor\n')
        self.source = path
        self.plan = {'model_selection': 'configs/models/synthetic.json', 'model': {'num_ctx': 65536, 'base_url': 'http://127.0.0.1:8011'}}
        self.now = dt.datetime.now(dt.timezone.utc)
        self.runtime = dict(supervisor_pid=123, pid=124, started_at=(self.now-dt.timedelta(seconds=10)).isoformat(),
            record_directory='records/p2_servers/synthetic', model_revision='a'*40, runtime={'binary_tag': 'synthetic'}, ctx_size=65536, status='ready')
        self.owner = dict(phase='P132_pipeline', status='preflight', server_owned=True, server_supervisor_pid=123,
                          server_record_directory=self.runtime['record_directory'])
        self.args = ['python', str(path), '--storage-root', str(self.storage), '--selection', self.plan['model_selection'],
            '--ctx-size', '65536', '--cache-type-k', 'q8_0', '--cache-type-v', 'q8_0', '--max-seconds', '5400']
        self.patches = [patch.object(m, 'ROOT', self.root), patch.object(m, 'SUPERVISOR_SHA256', hashlib.sha256(path.read_bytes()).hexdigest())]
        for p in self.patches:p.start();self.addCleanup(p.stop)

    def lease(self, args=None, runtime=None, owner=None):
        return m.owned_lease(runtime or self.runtime, shlex.join(args or self.args), self.now,
            storage=self.storage, source_plan=self.plan, owner=owner or self.owner)

    def test_exact_new_supervisor_accepts_and_accounts_elapsed_time(self):
        remaining, end = self.lease(); self.assertEqual(remaining, 5390)
        self.assertEqual(dt.datetime.fromisoformat(end), self.now + dt.timedelta(seconds=5390))

    def test_old_other_duplicate_and_longer_lease_are_rejected(self):
        variants=[]
        a=self.args[:];a[1]=str(self.root/'scripts/serve_research_model.py');variants.append(a)
        a=self.args[:];a[1]=str(Path('/unowned')/m.SUPERVISOR);variants.append(a)
        a=self.args[:];a[-1]='6000';variants.append(a)
        a=self.args[:];a[2]='--max-seconds';variants.append(a)
        a=self.args[:];a[5]='configs/models/different.json';variants.append(a)
        a=self.args[:];a.extend(['--max-seconds','5400']);variants.append(a)
        for args in variants:
            with self.subTest(args=args), self.assertRaises(ValueError):self.lease(args=args)

    def test_source_mutation_is_rejected(self):
        self.source.write_text('changed\n')
        with self.assertRaisesRegex(ValueError,'source differs'):self.lease()

    def test_owner_pid_phase_record_and_terminal_state_are_rejected(self):
        for change in [dict(server_supervisor_pid=999),dict(server_supervisor_pid=True),dict(phase='P131_pipeline'),
                       dict(server_record_directory='records/p2_servers/other'),dict(status='stopped'),dict(server_owned=False)]:
            with self.subTest(change=change), self.assertRaises(ValueError):self.lease(owner={**self.owner,**change})
        for change in [dict(pid=True),dict(pid=123),dict(started_at=(self.now+dt.timedelta(seconds=1)).isoformat()),
                       dict(started_at='2026-01-01T00:00:00')]:
            with self.subTest(change=change), self.assertRaises(ValueError):self.lease(runtime={**self.runtime,**change})

    def live(self, *, child='123', slots=None, required=480):
        if slots is None:slots=[{'id':0,'is_processing':False}]
        def read(path):return deepcopy(self.runtime if path.name=='model_server.json' else self.owner)
        with patch.object(m,'read',side_effect=read), patch.object(m.subprocess,'check_output',side_effect=[shlex.join(self.args),child]), \
             patch.object(m,'get',side_effect=[{'synthetic':'props'},slots]) as get, patch.object(m,'check_live_model') as check:
            result=m.live_identity(self.storage,self.plan,required)
            self.assertEqual(get.call_args_list[0].args,('/props',))
            check.assert_called_once_with(self.plan['model_selection'],self.runtime,{'synthetic':'props'},root=self.storage,
                expected_ctx=65536,expected_cache=('q8_0','q8_0'))
            return result

    def test_live_keeps_model_provenance_idle_and_identity_fields(self):
        identity,_=self.live();self.assertEqual(identity,{k:self.runtime[k] for k in ('model_revision','runtime','started_at','pid','supervisor_pid','ctx_size')})

    def test_wrong_child_busy_and_short_lease_rejected(self):
        for opts in [dict(child='999'),dict(slots=[{'id':0,'is_processing':True}]),dict(required=5400)]:
            with self.subTest(opts=opts),self.assertRaises(ValueError):self.live(**opts)
        for required in (True,0,-1,float('nan')):
            with self.subTest(required=required), self.assertRaises(ValueError):m.live_identity(self.storage,self.plan,required)

    def test_wait_idle_uses_new_live_identity_including_after_first_cell(self):
        identity={'synthetic':'identity'}
        response=io.StringIO(json.dumps([{'is_processing':False}]))
        with patch.object(m.urllib.request,'urlopen',return_value=response),patch.object(m,'live_identity',return_value=(identity,'end')) as live:
            got=m.wait_idle(self.storage,self.plan,identity,1)
        live.assert_called_once_with(self.storage,self.plan,1);self.assertTrue(got['one_slot_idle']);self.assertEqual(got['observations'],1)

    def test_wait_idle_rejects_changed_instance_and_expiry(self):
        with patch.object(m.urllib.request,'urlopen',return_value=io.StringIO('[{"is_processing":false}]')),patch.object(m,'live_identity',return_value=({'changed':True},'end')):
            with self.assertRaisesRegex(ValueError,'identity changed'):m.wait_idle(self.storage,self.plan,{},1)
        with patch.object(m.time,'monotonic',side_effect=[0,2]),patch.object(m,'live_identity') as live:
            with self.assertRaises(TimeoutError):m.wait_idle(self.storage,self.plan,{},1)
            live.assert_not_called()


if __name__=='__main__':unittest.main()
